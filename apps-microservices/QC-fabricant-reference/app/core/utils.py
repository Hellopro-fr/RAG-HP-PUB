"""
Utilitaires du service : extraction JSON tolerante aux sorties LLM, tracking, stopper.

Repris de QC-caracterisation sans modification de logique : la robustesse du parsing
JSON y est deja eprouvee sur des millions d'appels.
"""
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _fix_unescaped_quotes(text: str) -> str:
    """
    Repare les guillemets non-echappes a l'interieur des valeurs JSON produites par un LLM.
    Tracke l'etat cle/valeur pour distinguer une vraie fin de string d'un faux positif
    type "il a dit "bonjour", puis...". Normalise les guillemets typographiques en amont.
    """
    text = text.replace("“", '"').replace("”", '"')

    result = []
    n = len(text)
    i = 0
    in_string = False
    expecting_value = False  # True apres `:` ou `[` -> on attend une valeur

    while i < n:
        ch = text[i]

        if not in_string:
            result.append(ch)
            if ch == ':':
                expecting_value = True
            elif ch == '[':
                expecting_value = True
            elif ch in ('{', ','):
                expecting_value = False
            elif ch == '"':
                in_string = True
            i += 1
            continue

        if ch == '\\':
            result.append(ch)
            i += 1
            if i < n:
                result.append(text[i])
                i += 1
            continue

        if ch == '"':
            j = i + 1
            while j < n and text[j].isspace():
                j += 1
            nxt = text[j] if j < n else ''

            if expecting_value:
                is_end = nxt in (',', '}', ']') or j >= n
            else:
                is_end = (nxt == ':')

            if is_end:
                result.append(ch)
                in_string = False
                if expecting_value:
                    expecting_value = False
            else:
                result.append('\\"')
            i += 1
            continue

        result.append(ch)
        i += 1

    return ''.join(result)


def _strip_non_ascii_outside_strings(text: str) -> str:
    """
    Supprime les caracteres NON-ASCII situes HORS des chaines JSON : mojibake injecte
    par le LLM entre deux tokens. Le contenu DES chaines — qui peut legitimement etre
    de l'UTF-8 (accents, caracteres de substitution des titres corrompus) — est
    integralement preserve via le suivi in_string.
    """
    text = text.replace("“", '"').replace("”", '"')

    result = []
    n = len(text)
    i = 0
    in_string = False

    while i < n:
        ch = text[i]

        if in_string:
            result.append(ch)
            if ch == '\\' and i + 1 < n:  # garder la paire echappee intacte
                result.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue

        # hors chaine : conserver tout l'ASCII (structure/cles/litteraux), retirer le non-ASCII
        if ch == '"':
            in_string = True
            result.append(ch)
        elif ord(ch) < 128:
            result.append(ch)
        i += 1

    return ''.join(result)


def extract_json_from_text(text: str) -> Optional[Any]:
    """
    Extrait et parse le premier JSON valide d'une reponse LLM.

    Tolere : fences markdown, texte avant/apres, caracteres de controle litteraux,
    guillemets typographiques, mojibake hors-chaine, guillemets non echappes,
    JSON vide `[]`.

    Retourne None uniquement si aucun JSON exploitable n'est trouve.
    """
    if not text:
        return None

    # 1. Strip des fences markdown courantes (```json ... ``` ou ``` ... ```)
    text = re.sub(r'```(?:json|JSON)?\s*', '', text)
    text = text.replace('```', '')
    text = text.strip()

    if not text:
        return None

    # 2. Tentative directe. strict=False tolere les caracteres de controle
    #    (tab/newline litteraux) a l'interieur des valeurs, frequents en sortie LLM.
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        pass

    # 3. Balayage : 1er { ou [, raw_decode sur plusieurs variantes reparees.
    #    (b) est tente AVANT (c) : _strip_non_ascii_outside_strings desynchronise son
    #    suivi in_string sur un guillemet non echappe et corromprait la valeur.
    decoder = json.JSONDecoder(strict=False)
    n = len(text)
    for start in range(n):
        if text[start] not in '{[':
            continue
        sub = text[start:]
        stripped = _strip_non_ascii_outside_strings(sub)
        for candidate in (sub, _fix_unescaped_quotes(sub), stripped, _fix_unescaped_quotes(stripped)):
            try:
                obj, _ = decoder.raw_decode(candidate)
                return obj
            except json.JSONDecodeError:
                continue

    logger.error(f"Impossible d'extraire JSON de: {text[:200]}")
    return None


def to_json_string(data: Any) -> str:
    """Convertit des donnees en chaine JSON lisible (accents conserves)."""
    try:
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Erreur lors de la conversion en JSON: {e}")
        return "{}"


def ensure_directory(path: str) -> bool:
    """Cree un repertoire s'il n'existe pas.

    Un echec n'est jamais bloquant (tracking best effort) : warning, pas error.
    """
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.warning(f"Repertoire {path} non creable ({e}) — ecriture fichier ignoree")
        return False


def save_json_file(filepath: str, data: Any) -> bool:
    """Sauvegarde des donnees en JSON."""
    try:
        ensure_directory(os.path.dirname(filepath))
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde de {filepath}: {e}")
        return False


def load_json_file(filepath: str) -> Optional[Any]:
    """Charge un fichier JSON."""
    try:
        if not os.path.exists(filepath):
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Erreur lors du chargement de {filepath}: {e}")
        return None


def check_stopper(id_categorie: str, stopper_file: str = "fichiers/stopper.json") -> bool:
    """
    Verifie si la categorie doit etre stoppee manuellement.
    Retourne True si le processus doit s'arreter (et retire l'ID de la liste).
    """
    try:
        if not os.path.exists(stopper_file):
            save_json_file(stopper_file, [])
            return False

        stopper_list = load_json_file(stopper_file) or []

        if id_categorie in stopper_list:
            stopper_list.remove(id_categorie)
            save_json_file(stopper_file, stopper_list)
            logger.warning(f"Categorie {id_categorie} stoppee manuellement")
            return True

        return False
    except Exception as e:
        logger.error(f"Erreur lors de la verification du stopper: {e}")
        return False


def get_tracking_filepath(
    id_categorie: str,
    prefix: str = "fabricant-reference",
    base_dir: str = "tracking",
) -> str:
    """Genere le chemin du fichier de tracking d'un run."""
    year = datetime.now().strftime("%Y")
    month = datetime.now().strftime("%m")
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")

    directory = f"{base_dir}/{year}/{month}/"
    ensure_directory(directory)

    return os.path.join(directory, f"{timestamp}-tracking-{prefix}-{id_categorie}.txt")


# Volume de tracking non inscriptible (droits du montage) : on ne reessaie pas a chaque
# ligne de log. Un seul avertissement, puis tout reste dans la sortie standard du conteneur.
_tracking_fichier_ko = False


def write_log(filepath: str, message: str):
    """Ecrit un message dans un fichier de log (best effort).

    Si le volume n'est pas inscriptible, l'ecriture fichier est desactivee pour la duree
    du process apres UN avertissement : le run continue, les logs restent visibles dans
    la sortie standard (docker logs). Corriger les droits du volume tracking/ pour les
    retrouver sur disque.
    """
    global _tracking_fichier_ko

    if _tracking_fichier_ko:
        return

    try:
        directory = os.path.dirname(filepath)
        if directory:
            Path(directory).mkdir(parents=True, exist_ok=True)
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(f"{message}\n")
    except Exception as e:
        _tracking_fichier_ko = True
        logger.warning(
            f"Tracking fichier desactive pour ce process ({e}). "
            f"Les logs restent dans la sortie standard — corriger les droits du volume tracking/."
        )
