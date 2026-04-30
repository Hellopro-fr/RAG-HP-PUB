"""
Service métier pour l'extraction des caractéristiques influençant le prix.
Conversion de la logique PHP (api.php → run_identification) en Python.
"""
import time
import json
import logging
import asyncio
import re
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from app.core.api_client import GeminiProvider, ClaudeProvider, ChatGPTProvider, HelloProAPIClient
from app.core.utils import extract_json_from_text, get_prompt_cached, get_tracking_filepath, write_log
from app.core.search import call_search_api_async
from app.core.credentials import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers : nettoyage des prix aberrants (IQR + borne médiane, sans numpy)
# ---------------------------------------------------------------------------

def _parser_prix(valeur_str: Any) -> Optional[float]:
    """
    Convertit une chaîne de prix en float.
    Gère : symboles (≥ ≤ € $), espaces, séparateurs de milliers (. ou espace),
    virgule décimale française.
    """
    if not isinstance(valeur_str, str):
        return None
    s = re.sub(r'[≥≤<>~\s€$]', '', valeur_str)

    # "6.514.245" → séparateur de milliers → "6514245"
    if s.count('.') > 1:
        s = s.replace('.', '')
    elif s.count('.') == 1:
        avant, apres = s.split('.')
        if len(apres) == 3 and avant.isdigit() and len(avant) <= 3:
            s = s.replace('.', '')

    s = s.replace(',', '.')

    try:
        return float(s)
    except ValueError:
        return None


def _percentile_iqr(sorted_values: List[float], pct: float) -> float:
    """Percentile par interpolation linéaire (équivalent np.percentile, sans numpy)."""
    n = len(sorted_values)
    if n == 1:
        return float(sorted_values[0])
    idx = (pct / 100) * (n - 1)
    lower = int(idx)
    upper = lower + 1
    if upper >= n:
        return float(sorted_values[-1])
    frac = idx - lower
    return sorted_values[lower] + frac * (sorted_values[upper] - sorted_values[lower])


def _nettoyer_resultats_prix(
    results: List[Dict[str, Any]],
    multiplicateur: float = 1.5,
    ratio_mediane: float = 10.0,
) -> Dict[str, Any]:
    """
    Filtre les prix aberrants des résultats du matching v2 (méthode IQR + médiane).

    borne_min / borne_max ne sont définis QUE si une coupe réelle a eu lieu de ce côté :
    - borne_min est défini uniquement si des prix aberrants ont été rejetés en bas
    - borne_max est défini uniquement si des prix aberrants ont été rejetés en haut
    - None = aucune coupe de ce côté, la distribution est homogène

    Étapes :
    1. Pré-filtre médiane : élimine les prix hors [médiane/ratio ; médiane×ratio]
    2. IQR sur les prix pré-filtrés : exclut les outliers au-delà de Q1/Q3 ± mult×IQR
    3. Items sans prix parsable toujours conservés (non rejetés)

    Args:
        results: liste de dicts issus de matching_prix/matching/get
        multiplicateur: coefficient IQR (1.5 standard)
        ratio_mediane: tolérance autour de la médiane (10× par défaut)

    Returns:
        dict avec 'borne_min', 'borne_max', 'results_nettoyes', 'results_rejetes'
    """
    items_avec_prix: List[tuple] = []
    items_sans_prix: List[Dict[str, Any]] = []

    for item in results:
        bloc = item.get("prix", {})
        raw = (bloc.get("valeur_prix") or bloc.get("prix")) if isinstance(bloc, dict) else None
        p = _parser_prix(raw)
        if p is not None and p > 0:
            items_avec_prix.append((p, item))
        else:
            items_sans_prix.append(item)

    # Moins de 3 prix parsables : pas assez de données pour calculer des bornes
    if len(items_avec_prix) < 3:
        return {
            "borne_min": None,
            "borne_max": None,
            "results_nettoyes": [item for _, item in items_avec_prix] + items_sans_prix,
            "results_rejetes": [],
        }

    prix_tries = sorted(p for p, _ in items_avec_prix)
    mediane = _percentile_iqr(prix_tries, 50)

    # Bornes du pré-filtre (filtre les valeurs manifestement erronées)
    borne_inf_mediane = mediane / ratio_mediane
    borne_sup_mediane = mediane * ratio_mediane
    prix_pre = [p for p in prix_tries if borne_inf_mediane <= p <= borne_sup_mediane]

    # Bornes IQR (affinées sur les prix pré-filtrés)
    borne_inf_iqr: Optional[float] = None
    borne_sup_iqr: Optional[float] = None

    if len(prix_pre) >= 3:
        q1 = _percentile_iqr(prix_pre, 10)
        q3 = _percentile_iqr(prix_pre, 95)
        iqr = q3 - q1
        borne_inf_iqr = max(q1 - multiplicateur * iqr, borne_inf_mediane)
        borne_sup_iqr = q3 + multiplicateur * iqr

    # Borne effective : IQR si disponible, sinon pré-filtre seul
    borne_inf_effective = borne_inf_iqr if borne_inf_iqr is not None else borne_inf_mediane
    borne_sup_effective = borne_sup_iqr if borne_sup_iqr is not None else borne_sup_mediane

    # Filtrage : on suit si une coupe a réellement eu lieu de chaque côté
    results_nettoyes = list(items_sans_prix)
    results_rejetes: List[Dict[str, Any]] = []
    low_cut = False
    high_cut = False

    for prix, item in items_avec_prix:
        if prix < borne_inf_effective:
            results_rejetes.append(item)
            low_cut = True
        elif prix > borne_sup_effective:
            results_rejetes.append(item)
            high_cut = True
        else:
            results_nettoyes.append(item)

    return {
        "borne_min": round(borne_inf_effective, 2) if low_cut else None,
        "borne_max": round(borne_sup_effective, 2) if high_cut else None,
        "results_nettoyes": results_nettoyes,
        "results_rejetes": results_rejetes,
    }


def format_numeric_constraint(constraint: Any, unite: str = "") -> str:
    """
    Formate une contrainte numérique (min/max/exact) en string lisible.
    Conversion de la fonction PHP format_numeric_constraint.
    
    Args:
        constraint: dict avec clés min/max/exact ou valeur simple
        unite: unité à afficher
        
    Returns:
        String formatée de la contrainte
    """
    if not constraint:
        return ""

    u = f" {unite}" if unite else ""

    if isinstance(constraint, dict):
        parts = []
        if "min" in constraint:
            parts.append(f"≥ {constraint['min']}{u}")
        if "max" in constraint:
            parts.append(f"≤ {constraint['max']}{u}")
        if "exact" in constraint:
            parts.append(f" {constraint['exact']}{u}")
        return " & ".join(parts)

    return f"{constraint}{u}"


async def run_identification(id_categorie: str, id_prompt: Optional[str] = None) -> Dict[str, Any]:
    """
    Logique principale d'identification des caractéristiques influençant le prix.
    Conversion de la logique PHP run_identification en Python.
    
    Étapes :
    1. Récupère les données de la catégorie via l'API HelloPro
    2. Récupère le prompt configuré
    3. Construit le prompt final et appelle Gemini
    4. Parse la réponse JSON
    5. Retourne le résultat structuré
    
    Args:
        id_categorie: ID de la catégorie à analyser
        id_prompt: ID du prompt (utilise la config par défaut si None)
        
    Returns:
        Dict avec 'success', 'data', 'llm_response', 'message'
    """
    start_time = time.time()
    prompt_id = id_prompt or settings.PROMPT_ID_CARAC_PRIX
    
    api_client = HelloProAPIClient()

    ID_PROCESS = "37"
    
    try:
        # =====================================================================
        # ÉTAPE 0 : Récupérer les données de la catégorie : nom catégorie
        # =====================================================================
        logger.info(f"[{id_categorie}] Récupération des données de la catégorie...")
        
        category_info = await api_client.post(
            "category",
            "info",
            "get",
            {"id_categorie": id_categorie}
        )
        nom_categorie = category_info.get("nom_rubrique", "")
        
        if not category_info or not nom_categorie:
            elapsed = time.time() - start_time
            logger.error(f"[{id_categorie}] Impossible de récupérer les données de la catégorie")
            return {
                "success": False,
                "data": None,
                "llm_response": None,
                "time_elapsed": elapsed,
                "message": f"Impossible de récupérer les données de la catégorie {id_categorie}"
            }
        
        logger.info(f"[{id_categorie}] Données catégorie récupérées avec succès")
        
        # =====================================================================
        # ÉTAPE 1 : Récupérer les données de la catégorie : Q1 + jeu caractéristiques + caractéristiques prix existant 
        # =====================================================================
        logger.info(f"[{id_categorie}] Récupération des données de la catégorie...")

        # Charger les réponses de Question 1 + caractéristiques prix existant 
        reponses_q1_carac_prix = await api_client.post(
            "prix",
            "caracteristique",
            "get",
            {"id_categorie": id_categorie}
        )

        # Charger les caractéristiques finales 
        jeu_caracteristiques = await api_client.post(
            "caracteristique",
            "final",
            "get",
            {"id_categorie": id_categorie}
        )
        # Sérialiser les données de la catégorie en JSON pour le prompt
        jeu_caracteristiques_json = json.dumps(jeu_caracteristiques, ensure_ascii=False, indent=2)
        
        if not reponses_q1_carac_prix or not jeu_caracteristiques:
            elapsed = time.time() - start_time
            logger.error(f"[{id_categorie}] Impossible de récupérer les données de la catégorie")
            return {
                "success": False,
                "data": None,
                "llm_response": None,
                "time_elapsed": elapsed,
                "message": f"Impossible de récupérer les données de la catégorie {id_categorie} Q1 : {len(reponses_q1_carac_prix)} Caracteristiques : {len(jeu_caracteristiques)}"
            }
        
        logger.info(f"[{id_categorie}] Données catégorie récupérées avec succès")

        logger.info(f"[{id_categorie}] jeu_caracteristiques : {jeu_caracteristiques_json[:100]}")        


        # =====================================================================
        # ÉTAPE 2 : Récupérer le prompt
        # =====================================================================
        logger.info(f"[{id_categorie}] Récupération du prompt (id={prompt_id})...")
        
        prompt_config = await get_prompt_cached(prompt_id)
        
        if not prompt_config:
            elapsed = time.time() - start_time
            logger.error(f"[{id_categorie}] Impossible de récupérer le prompt id={prompt_id}")
            return {
                "success": False,
                "data": None,
                "llm_response": None,
                "time_elapsed": elapsed,
                "message": f"Impossible de récupérer le prompt id={prompt_id}"
            }
        
        # Extraire le contenu du prompt
        prompt_text = prompt_config.get("contenu_prompt", "")
        logger.info(f"[{id_categorie}] Prompt récupéré : {prompt_text[:100]}...")
        
        # =====================================================================
        # ÉTAPE 3 : Initialiser Gemini
        # =====================================================================
        gemini = GeminiProvider(
            model=settings.GEMINI_MODEL_NAME
        )
        
        # =====================================================================
        # ÉTAPE 4 : Pour chaque réponse Q1, appel LLM + sauvegarde
        # =====================================================================
        results_by_reponse = []
        skipped = []
        errors = []
        
        for rep in reponses_q1_carac_prix:
            id_reponse = rep.get("id_reponse", "")
            reponse = rep.get("reponse", rep.get("texte_reponse", ""))
            if not reponse:
                logger.warning(f"[{id_categorie}] - Réponse {id_reponse} - Aucune réponse trouvée")
                continue
            has_data = rep.get("has_data", False)
            caracteristiques_prix_existant = rep.get("caracteristiques_prix", [])

            logger.info(f"[{id_categorie}] - Réponse {id_reponse} - {reponse}")

            if has_data and caracteristiques_prix_existant:
                logger.warning(f"[{id_categorie}] - Caracteristiques prix existantes pour la reponse {id_reponse} - {reponse}")
                skipped.append({
                    "id_reponse": id_reponse,
                    "reponse": reponse,
                })
                continue
            
            # Récupérer les caractéristiques d'équivalence pour cette réponse
            list_carac_equiv = []
            equivalences = rep.get("equivalence", [])
            if equivalences and isinstance(equivalences, list):
                for equiv in equivalences:
                    if isinstance(equiv, dict):
                        id_c = equiv.get("id_caracteristique")
                        poids = equiv.get("poids")
                        if id_c and poids == "critique":
                            list_carac_equiv.append(str(id_c))
                    else:
                        logger.warning(f"[{id_categorie}] Équivalence non valide pour la réponse '{reponse}' (id={id_reponse}): {equivalences}")
            
            logger.info(f"[{id_categorie}] Traitement réponse Q1: '{reponse}' (id={id_reponse})")
            
            # --- Construction du prompt avec remplacement des variables dynamiques ---
            final_prompt = prompt_text
            final_prompt = final_prompt.replace("{nom_categorie}", nom_categorie)
            final_prompt = final_prompt.replace("{reponse_question_1}", reponse)
            final_prompt = final_prompt.replace("{jeu_caracteristique}", jeu_caracteristiques_json)
            
            logger.info(f"[{id_categorie}] Appel Gemini pour réponse '{reponse}' ({len(final_prompt)} chars)...")
            
            # --- Appel Gemini ---
            llm_result = await gemini.chat(final_prompt)

            # Log LLM usage pour Gemini
            usage_metadata = llm_result.get("api_response", {}).get("usage_metadata", {})
            await api_client.log_llm_usage(
                type_ia=3,  # Gemini
                model=settings.GEMINI_MODEL_NAME,
                input_token=usage_metadata.get("prompt_token_count") or 0,
                output_token=(usage_metadata.get("candidates_token_count") or 0) + (usage_metadata.get("thoughtsTokenCount") or 0),
                id_process=ID_PROCESS,
                origine="prix-extraction-devis",
                etat=1 if "error" not in llm_result else 2,
                retour_erreur=str(llm_result.get("error", "")) if "error" in llm_result else ""
            )
            
            # Vérifier si erreur LLM
            if "error" in llm_result:
                error_msg = f"Erreur Gemini pour la réponse '{reponse}' (code {llm_result.get('error', '')})"
                logger.error(f"[{id_categorie}] {error_msg}")
                errors.append(error_msg)
                continue
            
            llm_text = llm_result.get("message", "")
            logger.info(f"[{id_categorie}] Réponse Gemini : {llm_text}")
            
            # --- Parser la réponse JSON du LLM ---
            parsed = extract_json_from_text(llm_text)
            
            caracteristiques_prix = []
            
            if not parsed or not isinstance(parsed, dict) or not parsed.get("caracteristiques_prix"):
                error_msg = f"Réponse JSON vide ou malformée pour réponse='{reponse}' (id={id_reponse})"
                logger.error(f"[{id_categorie}] {error_msg}")
                errors.append(error_msg)
                continue
            
            # --- Ajouter les caractéristiques d'équivalence ---
            if list_carac_equiv:
                for carac_equiv in list_carac_equiv:
                    caracteristiques_prix.append(str(carac_equiv))

            # Extraire les IDs des caractéristiques prix identifiées par le LLM
            for carac_prix in parsed["caracteristiques_prix"]:                
                id_carac = carac_prix.get("id", "")
                if id_carac:
                    caracteristiques_prix.append(str(id_carac))  
            
            # --- Dédupliquer ---
            caracteristiques_prix = list(dict.fromkeys(caracteristiques_prix))
            
            # --- Sauvegarde via API ---                
            save_result = await api_client.post(
                "prix",
                "caracteristique",
                "save",
                {
                    "id_categorie": id_categorie,
                    "id_reponse": id_reponse,
                    "caracteristiques_prix": caracteristiques_prix
                }
            )
            saved_ids = save_result.get("saved_ids", [])
            if save_result is not None and len(saved_ids) > 0:
                logger.info(f"[{id_categorie}] Sauvegardé: {len(saved_ids)} caractéristiques pour réponse='{reponse}' (id={id_reponse})")
            else:
                error_msg = f"Échec sauvegarde: {len(saved_ids)} caractéristiques pour réponse='{reponse}' (id={id_reponse})"
                logger.warning(f"[{id_categorie}] Échec sauvegarde: {len(saved_ids)} caractéristiques pour réponse='{reponse}' (id={id_reponse})")
                errors.append(error_msg)
                continue
            
            results_by_reponse.append({
                "id_reponse": id_reponse,
                "reponse": reponse,
                "sous_type": parsed.get("sous_type", ""),
                "caracteristiques_prix": caracteristiques_prix,
                "ids_saved": saved_ids,
            })
            
            logger.info(f"[{id_categorie}] Réponse '{reponse}': {len(saved_ids)} caractéristiques sauvegardées")
        
        # =====================================================================
        # ÉTAPE 5 : Construction du résultat final
        # =====================================================================
        elapsed = time.time() - start_time
        
        # Cas : aucune réponse traitée et des erreurs
        if not results_by_reponse and errors:
            return {
                "success": False,
                "data": [],
                "raw": results_by_reponse,
                "errors": errors,
                "skipped": skipped,
                "time_elapsed": elapsed,
                "message": "; ".join(errors)
            }
        
        # Cas : aucune réponse traitée et pas d'erreurs (tout déjà traité)
        if not results_by_reponse and not errors:
            return {
                "success": False,
                "data": [],
                "raw": results_by_reponse,
                "errors": errors,
                "skipped": skipped,
                "time_elapsed": elapsed,
                "message": "Toutes les réponses Q1 ont déjà été traitées. Supprimez celles que vous souhaitez relancer."
            }
        
        # Construction du message récapitulatif
        msg = f"{len(results_by_reponse)} réponse(s) traitée(s)"
        if skipped:
            msg += f", {len(skipped)} ignorée(s) (déjà traitées)"
        if errors:
            msg += f", {len(errors)} erreur(s)"
        
        logger.info(f"[{id_categorie}] Identification terminée en {elapsed}s: {msg}")
        
        return {
            "success": True,
            "data": results_by_reponse,
            "raw": results_by_reponse,
            "errors": errors,
            "skipped": skipped,
            "time_elapsed": elapsed,
            "message": msg
        }
    
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[{id_categorie}] Erreur inattendue dans run_identification: {e}", exc_info=True)
        return {
            "success": False,
            "data": None,
            "llm_response": None,
            "time_elapsed": elapsed,
            "message": f"Erreur inattendue: {str(e)}"
        }
    
    finally:
        await api_client.close()


async def run_questionnaire(texte_recherche: str, id_categorie: str , nom_categorie: str, texte_prompt: Optional[str] = None, model: Optional[str] = None, type_source: Optional[str] = None) -> Dict[str, Any]:
    """
    Recherche RAG sur la source "prix" filtrée par id_categorie, 
    formate les chunks et les envoie au LLM (Gemini) avec le prompt 114.
    
    Étapes :
    1. Recherche RAG dans Milvus (source=prix, top_k=30, filtre=id_categorie)
    2. Formate chaque chunk en texte structuré (titre, fournisseur, catégorie, texte, prix, caractéristiques)
    3. Récupère le prompt configuré (id=114)
    4. Injecte les chunks formatés dans le prompt et appelle Gemini
    5. Retourne la réponse LLM
    
    Args:
        texte_recherche: Texte libre pour la recherche RAG
        id_categorie: ID de la catégorie pour filtrer les résultats
        
    Returns:
        Dict avec 'success', 'reponse', 'chunks_count', 'time_elapsed', 'message'
    """
    start_time = time.time()
    prompt_id = settings.PROMPT_ID_QUESTIONNAIRE
    
    api_client = HelloProAPIClient()
    ID_PROCESS = "37"
    
    try:
        # =====================================================================
        # ÉTAPE 1+3 : Recherche RAG + Récupération du prompt EN PARALLÈLE
        # =====================================================================
        logger.info(f"[{id_categorie}] Nom catégorie : {nom_categorie} ,  Recherche RAG + prompt en parallèle: texte='{texte_recherche}...', source=prix, top_k=50")

        # Filtre page_type pour la recherche RAG
        filtre_page_type: Dict[str, Any] = {            
            "id_categorie": id_categorie
        }

        if type_source == "other":
            logger.info(f"[{id_categorie}] Type source: messages, devis, site_web")
            filtre_page_type["source"] = [
                "devis",
                "message",
                "siteweb"
            ]
        elif type_source == "produit":
            logger.info(f"[{id_categorie}] Type source: produit")
            filtre_page_type["source"] = "produit"
        elif type_source == "message":
            logger.info(f"[{id_categorie}] Type source: message")
            filtre_page_type["source"] = "message"
        elif type_source == "devis":
            logger.info(f"[{id_categorie}] Type source: devis")
            filtre_page_type["source"] = "devis"
        elif type_source == "siteweb":
            logger.info(f"[{id_categorie}] Type source: siteweb")
            filtre_page_type["source"] = "siteweb"

        chunks, prompt_config = await asyncio.gather(
            call_search_api_async(
                prompt=texte_recherche,
                num_results=100,
                source="prix",
                filtre=filtre_page_type
            ),
            get_prompt_cached(prompt_id)
        )

        if not chunks:
            elapsed = time.time() - start_time
            logger.warning(f"[{id_categorie}] Aucun résultat RAG trouvé")
            return {
                "success": False,
                "reponse": None,
                "api_response": {},
                "time_elapsed": elapsed,
                "message": f"Aucun résultat RAG trouvé pour la catégorie {id_categorie}"
            }

        if not prompt_config:
            elapsed = time.time() - start_time
            logger.error(f"[{id_categorie}] Impossible de récupérer le prompt id={prompt_id}")
            return {
                "success": False,
                "reponse": None,
                "api_response": {},
                "time_elapsed": elapsed,
                "message": f"Impossible de récupérer le prompt id={prompt_id}"
            }

        logger.info(f"[{id_categorie}] {len(chunks)} chunks RAG trouvés")

        # =====================================================================
        # ÉTAPE 2 : Formater les chunks pour le prompt
        # =====================================================================
        formatted_chunks = []

        for i, chunk in enumerate(chunks):
            meta = chunk.get("metadata", {}).get("entity", {})

            nom_produit = meta.get("nom_produit", "N/A")
            fournisseur = meta.get("fournisseur", "N/A")
            nom_categorie = meta.get("nom_categorie", meta.get("categorie", "N/A"))
            description_produit = meta.get("description_produit", "")
            valeur_reponse_q1 = meta.get("valeur_reponse_q1", "")
            type_transaction = meta.get("type_transaction", "")
            structure_prix = meta.get("structure_prix", "")

            # Construction de la ligne de prix
            prix_line = ""
            valeur_prix = meta.get("valeur_prix", "")
            if valeur_prix:
                prix_parts = [str(valeur_prix)]
                devise = meta.get("devise", "")
                taxe = meta.get("taxe", "")
                unite = meta.get("unite", "")
                extras = [e for e in [devise, taxe, unite] if e]
                if extras:
                    prix_parts.append(f"{' '.join(extras)}")
                prix_line = " ".join(prix_parts)

            caracteristique = meta.get("caracteristique", "")
            date_prix = meta.get("date_prix", "")

            chunk_text = f"""Titre du produit : {nom_produit}
            Description du produit : {description_produit}
            Réponse Question 1 : {valeur_reponse_q1}
            Caractéristiques : {caracteristique}
            Fournisseur : {fournisseur}
            Nom de la catégorie : {nom_categorie}
            Type de transaction : {type_transaction}
            Prix : {prix_line}
            Date du prix : {date_prix}
            Structure du prix : {structure_prix}"""

            formatted_chunks.append(chunk_text)

        # Joindre tous les chunks avec un séparateur
        all_chunks_text = "\n\n---\n\n".join(formatted_chunks)

        logger.info(f"[{id_categorie}] chunks formatés ({len(all_chunks_text)} chars)")
        # logger.info(f"[{id_categorie}] all chunk : {all_chunks_text}")

        prompt_text = prompt_config.get("contenu_prompt", "")        
        
        # =====================================================================
        # ÉTAPE 4 : Construire le prompt final et appeler Gemini
        # =====================================================================
        # Remplacer les placeholders dans le prompt
        final_prompt = prompt_text
        final_prompt = final_prompt.replace("{chunks}", all_chunks_text)
        requete_rag_value = texte_recherche
        if isinstance(texte_prompt, str) and len(texte_prompt.strip()) > 0:
            requete_rag_value = texte_prompt.strip()
            logger.info(f"[{id_categorie}] Requête dans le prompt changé en : {requete_rag_value}")
        final_prompt = final_prompt.replace("{requete_rag}", requete_rag_value)
        final_prompt = final_prompt.replace("{nom_categorie}", nom_categorie)
        
        llm_model = model if isinstance(model, str) and len(model.strip()) > 0 else settings.CHATGPT_MODEL_NAME
        use_gemini = llm_model.startswith("gemini")
        use_chatgpt = llm_model.startswith("chatgpt") or llm_model.startswith("gpt")
        use_claude = llm_model.startswith("claude")

        logger.info(f"[{id_categorie}] Prompt : {final_prompt[:100]}...")

        if use_gemini:
            # ---- Gemini ----
            actual_model = llm_model if llm_model != "gemini" else settings.GEMINI_MODEL_NAME
            type_ia = 3
            logger.info(f"[{id_categorie}] Appel Gemini (model={actual_model}, {len(final_prompt)} chars)...")

            gemini = GeminiProvider(
                model=actual_model,
                thinking_level="low"
            )

            llm_result = await gemini.chat(final_prompt)

        elif use_claude:
            # ---- Claude (défaut) ----
            actual_model = llm_model if llm_model != "claude" else settings.CLAUDE_MODEL_NAME
            type_ia = 4

            # Parser les suffixes raccourcis : -e-{effort} ou -b-{budget_tokens}
            # Ex: claude-haiku-4-5-e-high → model=claude-haiku-4-5, effort=high
            # Ex: claude-haiku-4-5-b-2048 → model=claude-haiku-4-5, budget_tokens=2048
            effort = None
            budget_tokens = None
            match_effort = re.search(r"-e-(low|medium|high)$", actual_model)
            match_budget = re.search(r"-b-(\d+)$", actual_model)
            if match_effort:
                effort = match_effort.group(1)
                actual_model = actual_model[:match_effort.start()]
            elif match_budget:
                budget_tokens = int(match_budget.group(1))
                actual_model = actual_model[:match_budget.start()]

            logger.info(f"[{id_categorie}] Appel Claude (model={actual_model}, effort={effort}, budget_tokens={budget_tokens}, {len(final_prompt)} chars)...")

            claude = ClaudeProvider(
                model=actual_model,
                effort=effort,
                budget_tokens=budget_tokens,
            )

            llm_result = await claude.chat(final_prompt)

        else:

            # ---- ChatGPT ----
            actual_model = llm_model if llm_model != "chatgpt" else settings.CHATGPT_MODEL_NAME
            type_ia = 1
            logger.info(f"[{id_categorie}] Appel ChatGPT (model={actual_model}, {len(final_prompt)} chars)...")

            gpt = ChatGPTProvider(
                model=actual_model
            )

            llm_result = await gpt.chat(final_prompt)

        # Extraction usage commun (format normalisé pour les 3 providers)
        usage = llm_result.get("api_response", {}).get("usage", {})
        input_tokens = usage.get("input_tokens") or 0
        output_tokens = usage.get("output_tokens") or 0

        # Log LLM usage commun (fire-and-forget)
        logger.info(f"[{id_categorie}] Response LLM: {llm_result.get('api_response', {})}")
        asyncio.create_task(api_client.log_llm_usage(
            type_ia=type_ia,
            model=actual_model,
            input_token=input_tokens,
            output_token=output_tokens,
            id_process=ID_PROCESS,
            origine="prix-traitement-questionnaire",
            etat=1 if "error" not in llm_result else 2,
            retour_erreur=str(llm_result.get("error", "")) if "error" in llm_result else "",
            temperature=0.0
        ))

        elapsed = time.time() - start_time
        # Vérifier si erreur LLM
        if "error" in llm_result:
            error_msg = f"Erreur LLM: {llm_result.get('error', '')}"
            logger.error(f"[{id_categorie}] {error_msg}")
            return {
                "success": False,
                "reponse": None,
                "api_response": llm_result.get("api_response", {}),
                "time_elapsed": elapsed,
                "message": error_msg
            }
        
        llm_text = llm_result.get("message", "")
        
        
        logger.info(f"[{id_categorie}] Réponse Claude reçue : {llm_text} en {elapsed:.1f}s")

        parsed = extract_json_from_text(llm_text)
        if not parsed or not isinstance(parsed, dict):
            error_msg = f"Réponse JSON vide ou malformée pour réponse='{llm_text}'"
            logger.error(f"[{id_categorie}] {error_msg}")
            return {
                "success": False,
                "reponse": None,
                "api_response": llm_result.get("api_response", {}),
                "time_elapsed": elapsed,
                "message": error_msg
            }

        # Compatibilité prix_median <-> prix_moyen dans fourchette
        fourchette = parsed.get("fourchette")
        if isinstance(fourchette, dict):
            if "prix_moyen" in fourchette and "prix_median" not in fourchette:
                fourchette["prix_median"] = fourchette["prix_moyen"]
            elif "prix_median" in fourchette and "prix_moyen" not in fourchette:
                fourchette["prix_moyen"] = fourchette["prix_median"]

        return {
            "success": True,
            "reponse": parsed,
            "api_response": llm_result.get("api_response", {}),
            "time_elapsed": elapsed,
            "message": f"{len(chunks)} chunks traités en {elapsed:.1f}s"
        }
    
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[{id_categorie}] Erreur inattendue dans run_questionnaire: {e}", exc_info=True)
        return {
            "success": False,
            "reponse": None,
            "api_response": {},
            "time_elapsed": elapsed,
            "message": f"Erreur inattendue: {str(e)}"
        }


def _dedupe_matching_results(
    results: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Dédoublonne les résultats du matching (Option A : garde le 1er représentant).
    Doublon si TOUS les critères sont vrais :
      - fournisseur == (normalisé : lowercase + strip + collapse + sans accents)
      - valeur_prix == (arrondi à 2 décimales après conversion float)
      - taxe == (normalisée ; HT vs TTC vs "" → non doublons entre eux)
      - nom_produit similaire à ≥ 90 % (SequenceMatcher, uniquement ce champ)
    Items sans prix ou sans fournisseur → pas dédoublonnés (laissés tels quels).
    Retourne : (results_uniques, doublons_info) — doublons_info pour tracking.
    """
    import unicodedata as _unicodedata
    from difflib import SequenceMatcher

    def _norm_txt(s: Any) -> str:
        if not s:
            return ""
        s = str(s).strip().lower()
        nfkd = _unicodedata.normalize("NFKD", s)
        s = "".join(c for c in nfkd if not _unicodedata.combining(c))
        return re.sub(r"\s+", " ", s)

    def _norm_prix(p: Any) -> Optional[float]:
        try:
            return round(float(p), 2)
        except (TypeError, ValueError):
            return None

    # Pré-calcul des champs normalisés par index
    # Clé bucket = (fournisseur, prix, taxe) en match EXACT ==
    fields: List[tuple] = []  # (f_norm, p_norm, tx_norm, t_norm, t_orig)
    buckets: Dict[tuple, List[int]] = {}
    for i, item in enumerate(results):
        prix_info = item.get("prix", {}) or {}
        f_norm = _norm_txt(prix_info.get("fournisseur", ""))
        p_norm = _norm_prix(prix_info.get("valeur_prix"))
        tx_norm = _norm_txt(prix_info.get("taxe", ""))
        t_orig = prix_info.get("nom_produit", "") or ""
        t_norm = _norm_txt(t_orig)
        fields.append((f_norm, p_norm, tx_norm, t_norm, t_orig))
        if f_norm and p_norm is not None:
            buckets.setdefault((f_norm, p_norm, tx_norm), []).append(i)

    kept_flags = [True] * len(results)
    duplicates_info: List[Dict[str, Any]] = []

    # Dans chaque bucket (fournisseur/prix/taxe identiques), compare les titres à ≥90 %
    for (f_norm, p_norm, tx_norm), indices in buckets.items():
        if len(indices) < 2:
            continue

        clusters: List[List[int]] = []
        for i in indices:
            t_i = fields[i][3]
            placed = False
            for cluster in clusters:
                t_ref = fields[cluster[0]][3]
                if SequenceMatcher(None, t_i, t_ref).ratio() >= 0.9:
                    cluster.append(i)
                    placed = True
                    break
            if not placed:
                clusters.append([i])

        for cluster in clusters:
            if len(cluster) < 2:
                continue
            # Option A : garde le premier
            kept_idx = cluster[0]
            removed = cluster[1:]
            for r in removed:
                kept_flags[r] = False
            duplicates_info.append({
                "fournisseur": f_norm,
                "prix": p_norm,
                "taxe": tx_norm,
                "garde": fields[kept_idx][4],
                "retires": [fields[r][4] for r in removed],
            })

    deduped = [results[i] for i in range(len(results)) if kept_flags[i]]
    return deduped, duplicates_info


def _format_fr_number(n: float) -> str:
    """Formate un nombre en français avec espace insécable comme séparateur de milliers."""
    return f"{int(round(n)):,}".replace(",", "\u00a0")


def _replace_price_in_phrase(phrase: str, old_val: float, new_val: float) -> str:
    """
    Remplace une occurrence de prix (old_val) par new_val dans la phrase.
    Tolère les séparateurs de milliers : espace, espace insécable, point, virgule, apostrophe.
    Ex: 1800 → matche "1800", "1 800", "1\u00a0800", "1.800", "1'800".
    """
    old_int = int(round(old_val))
    new_str = _format_fr_number(new_val)
    s = str(old_int)

    if len(s) <= 3:
        pattern = r"(?<!\d)" + re.escape(s) + r"(?!\d)"
    else:
        # Découpe en groupes de 3 depuis la droite : 1800 → ["1", "800"]
        groups = []
        for i in range(len(s), 0, -3):
            start = max(0, i - 3)
            groups.append(s[start:i])
        groups.reverse()
        sep = r"[\s\u00a0.,'\u202f]?"
        pattern = r"(?<!\d)" + sep.join(re.escape(g) for g in groups) + r"(?!\d)"

    return re.sub(pattern, new_str, phrase)


def _adjust_fourchette_from_exemples(parsed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Vérifie que les prix des exemples_produits sont dans [borne_basse, borne_haute].
    Si un prix est hors bornes, étend la fourchette :
      - borne_haute = max(borne_haute, plus_haut_prix) arrondi à la dizaine supérieure
      - borne_basse = min(borne_basse, plus_bas_prix)  arrondi à la dizaine inférieure
    Puis recalcule prix_moyen = prix_median = (borne_basse + borne_haute) / 2.
    Retourne un dict de détails pour tracking (adjusted=True/False), ou None si non applicable.
    """
    import math as _math

    fourchette = parsed.get("fourchette")
    exemples = parsed.get("exemples_produits") or []
    if not isinstance(fourchette, dict) or not isinstance(exemples, list) or not exemples:
        return None

    try:
        borne_basse = float(fourchette.get("borne_basse"))
        borne_haute = float(fourchette.get("borne_haute"))
    except (TypeError, ValueError):
        return None

    prix_exemples: List[float] = []
    for ex in exemples:
        try:
            prix_exemples.append(float(ex.get("prix")))
        except (TypeError, ValueError):
            continue

    if not prix_exemples:
        return None

    max_ex = max(prix_exemples)
    min_ex = min(prix_exemples)

    new_haute = borne_haute
    new_basse = borne_basse
    adjusted = False

    if max_ex > borne_haute:
        # ≥ 1000 : arrondi à la dizaine supérieure ; < 1000 : arrondi simple supérieur (ceil)
        new_haute = _math.ceil(max_ex / 10) * 10 if max_ex >= 1000 else _math.ceil(max_ex)
        adjusted = True
    if min_ex < borne_basse:
        # ≥ 1000 : arrondi à la dizaine inférieure ; < 1000 : arrondi simple inférieur (floor)
        new_basse = _math.floor(min_ex / 10) * 10 if min_ex >= 1000 else _math.floor(min_ex)
        adjusted = True

    if not adjusted:
        return {"adjusted": False}

    new_moyen = (new_basse + new_haute) / 2

    # Capture des valeurs avant écrasement (pour mise à jour de phrase_prix)
    old_moyen = None
    try:
        old_moyen = float(fourchette.get("prix_moyen"))
    except (TypeError, ValueError):
        old_moyen = None

    details = {
        "adjusted": True,
        "borne_basse_avant": borne_basse,
        "borne_haute_avant": borne_haute,
        "borne_basse_apres": new_basse,
        "borne_haute_apres": new_haute,
        "min_exemple": min_ex,
        "max_exemple": max_ex,
        "prix_moyen_avant": old_moyen,
        "prix_moyen_apres": new_moyen,
    }

    # Mise à jour in-place de parsed["fourchette"]
    fourchette["borne_basse"] = new_basse
    fourchette["borne_haute"] = new_haute
    fourchette["prix_moyen"] = new_moyen
    fourchette["prix_median"] = new_moyen
    fourchette["ajustement"] = details

    # Mise à jour de phrase_prix : remplace les anciens prix par les nouveaux
    phrase = parsed.get("phrase_prix")
    if isinstance(phrase, str) and phrase:
        new_phrase = phrase
        replacements = []
        if new_basse != borne_basse:
            replacements.append((borne_basse, new_basse))
        if new_haute != borne_haute:
            replacements.append((borne_haute, new_haute))
        if old_moyen is not None and old_moyen != new_moyen \
                and old_moyen != borne_basse and old_moyen != borne_haute:
            replacements.append((old_moyen, new_moyen))

        for old_val, new_val in replacements:
            new_phrase = _replace_price_in_phrase(new_phrase, old_val, new_val)

        if new_phrase != phrase:
            details["phrase_prix_avant"] = phrase
            details["phrase_prix_apres"] = new_phrase
            parsed["phrase_prix"] = new_phrase

    return details


# ---------------------------------------------------------------------------
# Helpers : estimation de tokens et trim des chunks au budget LLM
# ---------------------------------------------------------------------------

# Limites tokens par provider : `max_input` = fenêtre totale du context window
# (input + output partagent la même fenêtre), `reserve_output` = budget gardé
# pour la réponse du LLM. Valeurs vérifiées via la doc officielle des providers.
TOKEN_LIMITS_BY_PROVIDER: Dict[str, Dict[str, int]] = {
    # Claude 4.x (haiku-4-5, sonnet-4-6, opus-4-7) : 200k context window
    "claude": {"max_input": 200_000, "reserve_output": 16_000},
    # Gemini 3.x Pro/Flash : 1 048 576 context window, 65 536 max output
    "gemini": {"max_input": 1_048_576, "reserve_output": 65_536},
    # GPT-5.x (mini/standard) : 400k context window, 128k max output
    "gpt":    {"max_input": 400_000, "reserve_output": 32_000},
}

# Ratios chars/token par provider :
#   - Claude : heuristique safe utilisée DANS la boucle de trim uniquement (rapide,
#     pas d'appel réseau). Le check du final_prompt passe par l'API Anthropic exacte
#     via `_count_tokens_claude_api` ci-dessous.
#   - GPT / Gemini : heuristiques calibrées FR + données structurées.
CHARS_PER_TOKEN_BY_PROVIDER: Dict[str, float] = {
    "claude": 2.5,   # heuristique conservatrice (réel mesuré ~2.58)
    "gpt":    3.01,
    "gemini": 3.16,
}

# Modèle Claude par défaut pour le comptage exact (la famille Claude 4.x partage
# le même tokenizer, donc le choix précis du modèle a peu d'impact).
_CLAUDE_DEFAULT_MODEL_FOR_COUNT = "claude-haiku-4-5"

# Client Anthropic en cache (singleton) pour éviter de recréer un client par appel.
_anthropic_count_client = None


async def _count_tokens_claude_api(
    text: str,
    model: str = _CLAUDE_DEFAULT_MODEL_FOR_COUNT,
) -> int:
    """
    Comptage tokens exact via l'endpoint officiel Anthropic `messages.count_tokens`.
    Précis 100 %, ~100-300 ms par appel — réservé aux vérifications ponctuelles
    (avant / après trim), pas à la boucle de trim qui passe par l'heuristique.
    """
    global _anthropic_count_client
    if _anthropic_count_client is None:
        from anthropic import AsyncAnthropic
        _anthropic_count_client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await _anthropic_count_client.messages.count_tokens(
        model=model,
        messages=[{"role": "user", "content": text}],
    )
    return response.input_tokens


def _estimate_tokens(text: str, provider: str = "claude") -> int:
    """
    Estimation token-count par heuristique chars/token (sync, sans réseau).

    Pour Claude, préférer `_count_tokens_claude_api` quand la précision compte
    (vérification du final_prompt). L'heuristique reste utile dans la boucle de
    trim où on ne peut pas se permettre N appels API.
    """
    if not text:
        return 0

    ratio = CHARS_PER_TOKEN_BY_PROVIDER.get(provider, 3.0)
    n = len(text)
    return int(n / ratio) + (1 if n % ratio else 0)


def _trim_chunks_to_token_budget(
    chunks: List[str],
    budget_tokens: int,
    provider: str = "claude",
    sep: str = "\n\n---\n\n",
) -> Tuple[List[str], int]:
    """
    Garde les premiers chunks tant que leur jointure tient dans `budget_tokens`.
    Les chunks en entrée sont supposés ordonnés par pertinence (les premiers gagnent).
    Retourne (chunks_gardes, nb_retires).
    """
    if budget_tokens <= 0 or not chunks:
        return [], len(chunks)

    sep_tokens = _estimate_tokens(sep, provider=provider)
    cumulative = 0
    kept = 0
    for i, c in enumerate(chunks):
        added = _estimate_tokens(c, provider=provider) + (sep_tokens if i > 0 else 0)
        if cumulative + added > budget_tokens:
            break
        cumulative += added
        kept += 1
    return chunks[:kept], len(chunks) - kept


async def run_questionnaire_v2(equivalences: List[Dict[str, Any]], id_categorie: str, nom_categorie: str, texte_prompt: Optional[str] = None, model: Optional[str] = None , id_reponse_q1: Optional[str] = None, nom_reponse_q1: Optional[str] = None) -> Dict[str, Any]:
    """
    Version 2 du questionnaire prix : remplace la recherche RAG par le matching
    via l'endpoint BO matching_prix.php (correspondance équivalences × _cppi).

    Étapes :
    1. Appel BO matching_prix/matching/get avec les équivalences filtrées
    2. Formate les résultats matchés en texte structuré (même format que v1)
    3. Récupère le prompt 114
    4. Injecte les résultats formatés + requête dans le prompt, appelle LLM
    5. Retourne la réponse LLM structurée

    Args:
        equivalences: Équivalences prix filtrées (textuelles uniquement)
        id_categorie: ID de la catégorie
        nom_categorie: Nom de la catégorie
        texte_prompt: Texte optionnel à injecter comme {requete_rag} dans le prompt
        model: Modèle LLM à utiliser

    Returns:
        Dict avec 'success', 'reponse', 'matching', 'api_response', 'time_elapsed', 'message'
    """
    start_time = time.time()
    prompt_id = settings.PROMPT_ID_QUESTIONNAIRE

    api_client = HelloProAPIClient()
    ID_PROCESS = "37"

    # =========================================================================
    # Choix du modèle LLM par défaut : "claude" | "chatgpt" | "gemini"
    # Si `model` n'est pas fourni, on utilise le provider défini ici.
    # =========================================================================
    model_pardefaut = "claude"  # ← changer ici : "claude" | "chatgpt" | "gemini"

    default_model_by_provider = {
        "claude": settings.CLAUDE_MODEL_NAME,
        "chatgpt": settings.CHATGPT_MODEL_NAME,
        "gemini": settings.GEMINI_MODEL_NAME,
    }
    default_model_name = default_model_by_provider.get(model_pardefaut, settings.CLAUDE_MODEL_NAME)

    # Tracking file (visualisé dans QC-tracking-service)
    tracking_file = get_tracking_filepath(id_categorie, prefix="prix-traitement-v2")
    write_log(tracking_file, "=" * 80)
    write_log(tracking_file, f"RUN_QUESTIONNAIRE_V2 — {datetime.now().isoformat()}")
    write_log(tracking_file, "=" * 80)
    write_log(tracking_file, f"id_categorie: {id_categorie}")
    write_log(tracking_file, f"nom_categorie: {nom_categorie}")
    write_log(tracking_file, f"model: {model or default_model_name} (model_pardefaut={model_pardefaut})")
    write_log(tracking_file, "")
    write_log(tracking_file, f"--- EQUIVALENCES ({len(equivalences)}) ---")
    write_log(tracking_file, f"id_reponse_q1: {id_reponse_q1}")
    write_log(tracking_file, f"nom_reponse_q1: {nom_reponse_q1}")
    write_log(tracking_file, json.dumps(equivalences, ensure_ascii=False, indent=2))
    write_log(tracking_file, "")

    try:
        # =====================================================================
        # ÉTAPE 1 : Matching prix via BO + récupération prompt EN PARALLÈLE
        # =====================================================================
        logger.info(f"[{id_categorie}] V2 — Matching prix + prompt en parallèle ({len(equivalences)} équivalences)")

        matching_response, prompt_config = await asyncio.gather(
            api_client.post(
                "matching_prix", "matching", "get",
                {"id_categorie": id_categorie, "equivalences": equivalences, "id_reponse_q1": id_reponse_q1}
            ),
            get_prompt_cached(prompt_id)
        )

        if not matching_response or matching_response.get("erreur"):
            elapsed = time.time() - start_time
            err_msg = (matching_response or {}).get("message", "Erreur appel matching_prix")
            logger.warning(f"[{id_categorie}] V2 — Matching échoué: {err_msg}")
            return {
                "success": False,
                "reponse": None,
                # "matching": matching_response,  # désactivé temporairement
                "api_response": {},
                "time_elapsed": elapsed,
                "message": err_msg
            }

        results = matching_response.get("results", [])
        if not results:
            elapsed = time.time() - start_time
            logger.warning(f"[{id_categorie}] V2 — Aucun prix matché")
            return {
                "success": False,
                "reponse": None,
                # "matching": matching_response,  # désactivé temporairement
                "api_response": {},
                "time_elapsed": elapsed,
                "message": f"Aucun prix correspondant trouvé pour la catégorie {id_categorie}"
            }

        if not prompt_config:
            elapsed = time.time() - start_time
            logger.error(f"[{id_categorie}] V2 — Impossible de récupérer le prompt id={prompt_id}")
            return {
                "success": False,
                "reponse": None,
                # "matching": matching_response,  # désactivé temporairement
                "api_response": {},
                "time_elapsed": elapsed,
                "message": f"Impossible de récupérer le prompt id={prompt_id}"
            }

        logger.info(f"[{id_categorie}] V2 — {len(results)} prix matchés")

        if model == "gemini":  # Pas de nettoyage pour Claude (effort déjà intégré)
            # =====================================================================
            # ÉTAPE 1b : Filtrage des prix aberrants (IQR + borne médiane)
            # =====================================================================
            nettoyage = _nettoyer_resultats_prix(results)
            results = nettoyage["results_nettoyes"]
            nb_rejetes = len(nettoyage["results_rejetes"])

            borne_min = nettoyage["borne_min"]
            borne_max = nettoyage["borne_max"]
            if borne_min is not None and borne_max is not None:
                bornes_str = f" (bornes [{borne_min:.2f} – {borne_max:.2f}])"
            elif borne_min is not None:
                bornes_str = f" (borne min {borne_min:.2f})"
            elif borne_max is not None:
                bornes_str = f" (borne max {borne_max:.2f})"
            else:
                bornes_str = ""
            write_log(tracking_file, "--- NETTOYAGE PRIX ---")
            write_log(tracking_file, f"Gardés : {len(results)} | Rejetés : {nb_rejetes}{bornes_str}")
            write_log(tracking_file, json.dumps(
                {
                    "borne_min": nettoyage["borne_min"],
                    "borne_max": nettoyage["borne_max"],
                    "nb_gardes": len(results),
                    "nb_rejetes": nb_rejetes,
                    "prix_gardes": [
                        (item.get("prix") or {}).get("valeur_prix") or (item.get("prix") or {}).get("prix")
                        for item in results
                    ],
                    "prix_rejetes": [
                        (item.get("prix") or {}).get("valeur_prix") or (item.get("prix") or {}).get("prix")
                        for item in nettoyage["results_rejetes"]
                    ],
                },
                ensure_ascii=False, indent=2
            ))
            write_log(tracking_file, "")

            if not results:
                elapsed = time.time() - start_time
                write_log(tracking_file, "ERREUR : Tous les prix ont été rejetés après nettoyage")
                return {
                    "success": False,
                    "reponse": None,
                    # "matching": matching_response,  # désactivé temporairement
                    "api_response": {},
                    "time_elapsed": elapsed,
                    "message": "Tous les prix matchés ont été éliminés comme aberrants"
                }
        else:
            write_log(tracking_file, "--- NO NETTOYAGE PRIX ---")
            

        # =====================================================================
        # ÉTAPE 2 : Formater les résultats matchés (même format que v1 chunks)
        # =====================================================================

        # Dédoublonnage : fournisseur + prix + taxe identiques + nom_produit ≥ 90 %
        raw_count = len(results)
        results, duplicates_info = _dedupe_matching_results(results)
        if raw_count > len(results):
            logger.info(
                f"[{id_categorie}] V2 — Dédoublonnage : {raw_count} → {len(results)} "
                f"(retirés : {raw_count - len(results)})"
            )
            write_log(tracking_file, "--- DEDOUBLONNAGE MATCHING ---")
            write_log(tracking_file, f"Avant: {raw_count} | Après: {len(results)} | Retirés: {raw_count - len(results)}")
            write_log(tracking_file, json.dumps(duplicates_info, ensure_ascii=False, indent=2))
            write_log(tracking_file, "")
        else:
            write_log(tracking_file, "--- DEDOUBLONNAGE MATCHING : 0 doublon ---")
            write_log(tracking_file, "")

        formatted_chunks = []

        for item in results:
            prix = item.get("prix", {})

            prix_line = prix.get("prix", "")
            caracteristiques = item.get("caracteristiques", prix.get("caracteristique", ""))

            chunk_text = f"""Titre du produit : {prix.get("nom_produit", "N/A")}
            Description du produit : {prix.get("description_produit", "")}
            Réponse Question 1 : {prix.get("valeur_reponse_q1", "")}
            Caractéristiques : {caracteristiques}
            Fournisseur : {prix.get("fournisseur", "N/A")}
            Nom de la catégorie : {prix.get("nom_categorie", "N/A")}
            Type de transaction : {prix.get("type_transaction", "")}
            Prix : {prix_line}
            Date du prix : {prix.get("date_prix", "")}
            Structure du prix : {prix.get("structure_prix", "")}"""

            formatted_chunks.append(chunk_text)

        all_chunks_text = "\n\n---\n\n".join(formatted_chunks)

        logger.info(f"[{id_categorie}] V2 — {len(formatted_chunks)} chunks formatés ({len(all_chunks_text)} chars)")

        write_log(tracking_file, f"--- ALL_CHUNKS_TEXT ({len(formatted_chunks)} chunks, {len(all_chunks_text)} chars) ---")
        write_log(tracking_file, all_chunks_text)
        write_log(tracking_file, "")

        prompt_text = prompt_config.get("contenu_prompt", "")

        # =====================================================================
        # ÉTAPE 3 : Construire le prompt final et appeler LLM
        # =====================================================================
        final_prompt = prompt_text
        final_prompt = final_prompt.replace("{chunks}", all_chunks_text)

        # {requete_rag} = texte_prompt si fourni
        requete_rag_value = texte_prompt.strip()
        logger.info(f"[{id_categorie}] V2 — Requête prompt surchargée: {requete_rag_value}")

        write_log(tracking_file, "--- REQUETE_RAG_VALUE ---")
        write_log(tracking_file, requete_rag_value)
        write_log(tracking_file, "")

        final_prompt = final_prompt.replace("{requete_rag}", requete_rag_value)
        final_prompt = final_prompt.replace("{nom_categorie}", nom_categorie)
        final_prompt = final_prompt.replace("{nom_reponse_q1}", nom_reponse_q1)

        # `model_pardefaut` / `default_model_name` définis en tête de fonction.
        # Routage : si `model` fourni → détection par préfixe ; sinon → `model_pardefaut`.
        if isinstance(model, str) and len(model.strip()) > 0:
            llm_model = model
            use_gemini = llm_model.startswith("gemini")
            use_chatgpt = llm_model.startswith("chatgpt") or llm_model.startswith("gpt")
            use_claude = llm_model.startswith("claude")
        else:
            llm_model = default_model_name
            use_gemini = model_pardefaut == "gemini"
            use_chatgpt = model_pardefaut == "chatgpt"
            use_claude = model_pardefaut == "claude"

        # =====================================================================
        # Vérification budget tokens du final_prompt — trim si dépassement
        # Pour Claude : comptage exact via API ; sinon : heuristique chars/token.
        # =====================================================================
        provider_key = "gemini" if use_gemini else ("claude" if use_claude else "gpt")
        limits = TOKEN_LIMITS_BY_PROVIDER[provider_key]
        budget_max = limits["max_input"] - limits["reserve_output"]

        async def _count_tokens(t: str) -> int:
            if provider_key == "claude":
                try:
                    return await _count_tokens_claude_api(t)
                except Exception as exc:
                    logger.warning(
                        f"[{id_categorie}] V2 — count_tokens API échoué, fallback heuristique: {exc}"
                    )
            return _estimate_tokens(t, provider=provider_key)

        final_prompt_tokens = await _count_tokens(final_prompt)

        if final_prompt_tokens > budget_max:
            # Tokens fixes du template (final_prompt sans la partie chunks)
            chunks_tokens = await _count_tokens(all_chunks_text)
            template_tokens = final_prompt_tokens - chunks_tokens
            budget_chunks_tokens = budget_max - template_tokens

            nb_chunks_avant = len(formatted_chunks)
            formatted_chunks, nb_retires = _trim_chunks_to_token_budget(
                formatted_chunks, budget_chunks_tokens, provider=provider_key
            )
            all_chunks_text = "\n\n---\n\n".join(formatted_chunks)

            # Reconstruire final_prompt avec les chunks réduits
            final_prompt = prompt_text
            final_prompt = final_prompt.replace("{chunks}", all_chunks_text)
            final_prompt = final_prompt.replace("{requete_rag}", requete_rag_value)
            final_prompt = final_prompt.replace("{nom_categorie}", nom_categorie)
            final_prompt = final_prompt.replace("{nom_reponse_q1}", nom_reponse_q1)


            logger.warning(
                f"[{id_categorie}] V2 — Budget tokens {provider_key} dépassé : "
                f"{nb_retires}/{nb_chunks_avant} chunks retirés "
                f"(prompt avant={final_prompt_tokens} tk > budget={budget_max} tk, "
            )
            write_log(tracking_file, "--- BUDGET TOKENS DÉPASSÉ → TRIM ---")
            write_log(tracking_file, json.dumps({
                "provider": provider_key,
                "max_input": limits["max_input"],
                "reserve_output": limits["reserve_output"],
                "budget_max": budget_max,
                "final_prompt_tokens_avant": final_prompt_tokens,
                "chunks_avant": nb_chunks_avant,
                "chunks_apres": len(formatted_chunks),
                "chunks_retires": nb_retires,
            }, ensure_ascii=False, indent=2))
            write_log(tracking_file, "")

        logger.info(f"[{id_categorie}] V2 — Prompt: {final_prompt[:100]}...")

        if use_gemini:
            actual_model = llm_model if llm_model != "gemini" else settings.GEMINI_MODEL_NAME
            type_ia = 3
            logger.info(f"[{id_categorie}] V2 — Appel Gemini (model={actual_model}, {len(final_prompt)} chars)...")
            write_log(tracking_file, f"--- Appel Gemini (model={actual_model}, {len(final_prompt)} chars)...")            
            gemini = GeminiProvider(model=actual_model, thinking_level="low")
            llm_result = await gemini.chat(final_prompt)

        elif use_claude:
            actual_model = llm_model if llm_model != "claude" else settings.CLAUDE_MODEL_NAME
            type_ia = 4
            effort = None
            budget_tokens = None
            match_effort = re.search(r"-e-(low|medium|high)$", actual_model)
            match_budget = re.search(r"-b-(\d+)$", actual_model)
            if match_effort:
                effort = match_effort.group(1)
                actual_model = actual_model[:match_effort.start()]
            elif match_budget:
                budget_tokens = int(match_budget.group(1))
                actual_model = actual_model[:match_budget.start()]
            logger.info(f"[{id_categorie}] V2 — Appel Claude (model={actual_model}, effort={effort}, budget_tokens={budget_tokens}, {len(final_prompt)} chars)...")
            write_log(tracking_file, f"--- Appel Claude (model={actual_model}, effort={effort}, budget_tokens={budget_tokens}, {len(final_prompt)} chars)...") 
            claude = ClaudeProvider(model=actual_model, effort=effort, budget_tokens=budget_tokens)
            llm_result = await claude.chat(final_prompt)

        elif use_chatgpt:
            actual_model = llm_model if llm_model != "chatgpt" else settings.CHATGPT_MODEL_NAME
            type_ia = 1
            effort = None
            match_effort = re.search(r"-e-(low|medium|high)$", actual_model)
            if match_effort:
                effort = match_effort.group(1)
                actual_model = actual_model[:match_effort.start()]
            logger.info(f"[{id_categorie}] V2 — Appel ChatGPT (model={actual_model}, effort={effort}, {len(final_prompt)} chars)...")
            write_log(tracking_file, f"--- Appel ChatGPT (model={actual_model}, effort={effort}, {len(final_prompt)} chars)...") 
            gpt = ChatGPTProvider(model=actual_model, reasoning_effort=effort)
            llm_result = await gpt.chat(final_prompt)

        # Extraction usage commun
        usage = llm_result.get("api_response", {}).get("usage", {})
        input_tokens = usage.get("input_tokens") or 0
        output_tokens = usage.get("output_tokens") or 0

        # Log LLM usage (fire-and-forget)
        asyncio.create_task(api_client.log_llm_usage(
            type_ia=type_ia,
            model=actual_model,
            input_token=input_tokens,
            output_token=output_tokens,
            id_process=ID_PROCESS,
            origine="prix-traitement-questionnaire-v2",
            etat=1 if "error" not in llm_result else 2,
            retour_erreur=str(llm_result.get("error", "")) if "error" in llm_result else "",
            temperature=0.0
        ))

        elapsed = time.time() - start_time

        if "error" in llm_result:
            error_msg = f"Erreur LLM: {llm_result.get('error', '')}"
            logger.error(f"[{id_categorie}] V2 — {error_msg}")
            return {
                "success": False,
                "reponse": None,
                # "matching": matching_response,  # désactivé temporairement
                "api_response": llm_result.get("api_response", {}),
                "time_elapsed": elapsed,
                "message": error_msg
            }

        llm_text = llm_result.get("message", "")
        logger.info(f"[{id_categorie}] V2 — Réponse LLM reçue: {llm_text[:200]}... en {elapsed:.1f}s")

        write_log(tracking_file, f"--- LLM_TEXT ({len(llm_text)} chars, {elapsed:.1f}s) ---")
        write_log(tracking_file, llm_text)
        write_log(tracking_file, "")

        parsed = extract_json_from_text(llm_text)
        if not parsed or not isinstance(parsed, dict):
            error_msg = f"Réponse JSON vide ou malformée: '{llm_text[:100]}'"
            logger.error(f"[{id_categorie}] V2 — {error_msg}")
            return {
                "success": False,
                "reponse": None,
                # "matching": matching_response,  # désactivé temporairement
                "api_response": llm_result.get("api_response", {}),
                "time_elapsed": elapsed,
                "message": error_msg
            }

        # Compatibilité prix_median <-> prix_moyen dans fourchette
        fourchette = parsed.get("fourchette")
        if isinstance(fourchette, dict):
            if "prix_moyen" in fourchette and "prix_median" not in fourchette:
                fourchette["prix_median"] = fourchette["prix_moyen"]
            elif "prix_median" in fourchette and "prix_moyen" not in fourchette:
                fourchette["prix_moyen"] = fourchette["prix_median"]

        # Ajustement des bornes si un exemple_produit est hors fourchette
        adjust_details = _adjust_fourchette_from_exemples(parsed)
        if adjust_details is not None:
            write_log(tracking_file, "--- AJUSTEMENT BORNES FOURCHETTE ---")
            write_log(tracking_file, json.dumps(adjust_details, ensure_ascii=False, indent=2))
            write_log(tracking_file, "")
            if adjust_details.get("adjusted"):
                logger.info(
                    f"[{id_categorie}] V2 — Fourchette ajustée : "
                    f"[{adjust_details['borne_basse_avant']}, {adjust_details['borne_haute_avant']}] → "
                    f"[{adjust_details['borne_basse_apres']}, {adjust_details['borne_haute_apres']}] "
                    f"(min_ex={adjust_details['min_exemple']}, max_ex={adjust_details['max_exemple']})"
                )

        return {
            "success": True,
            "reponse": parsed,
            # "matching": matching_response,  # désactivé temporairement
            "api_response": llm_result.get("api_response", {}),
            "time_elapsed": elapsed,
            "message": f"{len(results)} prix matchés traités en {elapsed:.1f}s"
        }

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[{id_categorie}] Erreur inattendue dans run_questionnaire_v2: {e}", exc_info=True)
        return {
            "success": False,
            "reponse": None,
            # "matching": None,  # désactivé temporairement
            "api_response": {},
            "time_elapsed": elapsed,
            "message": f"Erreur inattendue: {str(e)}"
        }


# =========================================================================
# BATCH : traitement parallèle de plusieurs catégories (semaphore = 5)
# =========================================================================

# Nombre max de traitements parallèles pour le lot
MAX_PARALLEL_CATEGORIES = 5

async def _process_single_category(
    semaphore: asyncio.Semaphore,
    id_categorie: str,
    id_prompt: Optional[str],
    index: int,
    total: int
) -> Dict[str, Any]:
    """
    Traite une seule catégorie sous le contrôle du sémaphore.
    
    Args:
        semaphore: Sémaphore asyncio pour limiter le parallélisme
        id_categorie: ID de la catégorie à traiter
        id_prompt: ID du prompt (optionnel)
        index: Index dans le lot (pour les logs)
        total: Nombre total dans le lot (pour les logs)
        
    Returns:
        Dict avec le résultat de run_identification + id_categorie
    """
    async with semaphore:
        logger.info(f"[LOT {index + 1}/{total}] Début traitement catégorie {id_categorie}")
        try:
            result = await run_identification(
                id_categorie=id_categorie,
                id_prompt=id_prompt
            )
            result["id_categorie"] = id_categorie
            logger.info(f"[LOT {index + 1}/{total}] Fin catégorie {id_categorie}: success={result.get('success')}")
            return result
        except Exception as e:
            logger.error(f"[LOT {index + 1}/{total}] Erreur catégorie {id_categorie}: {e}", exc_info=True)
            return {
                "id_categorie": id_categorie,
                "success": False,
                "data": None,
                "raw": None,
                "errors": [str(e)],
                "skipped": [],
                "time_elapsed": None,
                "message": f"Erreur: {str(e)}"
            }


async def run_identification_lot(
    categories: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Traitement batch de plusieurs catégories en parallèle (max 5 simultanées).
    Basé sur le pattern asyncio.Semaphore de prix-extraction-message/prix_extractor.py.
    
    Args:
        categories: Liste de dicts avec 'id_categorie' et optionnellement 'id_prompt'
        
    Returns:
        Dict avec 'success', 'total', 'success_count', 'error_count', 'results', 'time_elapsed', 'message'
    """
    start_time = time.time()
    total = len(categories)
    
    if total == 0:
        return {
            "success": True,
            "total": 0,
            "success_count": 0,
            "error_count": 0,
            "results": [],
            "time_elapsed": 0.0,
            "message": "Aucune catégorie à traiter"
        }
    
    logger.info(f"[LOT] Démarrage batch: {total} catégories, {MAX_PARALLEL_CATEGORIES} en parallèle")
    
    # Créer le sémaphore pour limiter à MAX_PARALLEL_CATEGORIES traitements simultanés
    semaphore = asyncio.Semaphore(MAX_PARALLEL_CATEGORIES)
    
    # Créer les tâches pour chaque catégorie
    tasks = [
        _process_single_category(
            semaphore=semaphore,
            id_categorie=str(cat.get("id_categorie", "")),
            id_prompt=cat.get("id_prompt"),
            index=i,
            total=total
        )
        for i, cat in enumerate(categories)
    ]
    
    # Lancer toutes les tâches en parallèle (le sémaphore contrôle la concurrence)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    elapsed = time.time() - start_time
    
    # Agréger les résultats
    success_count = 0
    error_count = 0
    item_results = []
    
    for r in results:
        if isinstance(r, Exception):
            # Exception non capturée (ne devrait pas arriver car _process_single_category gère les exceptions)
            error_count += 1
            item_results.append({
                "id_categorie": "inconnu",
                "success": False,
                "data": None,
                "raw": None,
                "errors": [str(r)],
                "skipped": [],
                "time_elapsed": None,
                "message": f"Exception: {str(r)}"
            })
        elif isinstance(r, dict):
            item_results.append(r)
            if r.get("success"):
                success_count += 1
            else:
                error_count += 1
        else:
            error_count += 1
            item_results.append({
                "id_categorie": "inconnu",
                "success": False,
                "data": None,
                "raw": None,
                "errors": [f"Résultat inattendu: {type(r)}"],
                "skipped": [],
                "time_elapsed": None,
                "message": f"Résultat inattendu: {type(r)}"
            })
    
    logger.info(f"[LOT] Batch terminé: {success_count} succès, {error_count} erreurs en {elapsed:.1f}s")
    
    return {
        "success": error_count == 0,
        "total": total,
        "success_count": success_count,
        "error_count": error_count,
        "results": item_results,
        "time_elapsed": elapsed,
        "message": f"{total} catégories traitées ({success_count} succès, {error_count} erreurs) en {elapsed:.1f}s"
    }
