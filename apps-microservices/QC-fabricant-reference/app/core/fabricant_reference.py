"""
Extraction marque / reference par produit (etape PSI 16, prompt 133).

Deux principes commandent ce module :

1. INDEPENDANCE DES SOURCES — le prompt ne recoit jamais de donnee fournisseur.
   Le statut fabricant/revendeur est calcule en aval par rapprochement entre la marque
   du produit et l'identite du fournisseur ; si le modele voyait le nom du fournisseur,
   il le recopierait en marque et fabriquerait lui-meme la concordance.
   `_assert_no_supplier_data` en fait une erreur bloquante, pas une convention.

2. COUT D'ERREUR ASYMETRIQUE — une marque absente se recupere en aval (marque inferee
   depuis le catalogue du fournisseur) ; une marque fausse s'affiche publiquement et
   rien ne la corrige. Tous les garde-fous de `_validate_extraction` tranchent donc
   vers l'abstention. Ils sont deterministes, donc gratuits et corrigeables sans
   relancer le run.
"""
import asyncio
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional

from app.core import utils
from app.core.api_client import DeepSeek, HelloProAPIClient
from app.core.credentials import settings
from app.schemas.fabricant_reference import (
    ExtractionProduit,
    FabricantReferenceResult,
    RequestFabricantReference,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


BATCH_PRODUITS = settings.BATCH_PRODUITS        # produits par appel LLM
APPELS_PARALLELES = settings.APPELS_PARALLELES  # appels LLM simultanes
MAX_ECHECS_BATCH = settings.MAX_ECHECS_BATCH    # echecs consecutifs avant abandon

# Champs interdits dans le payload envoye au modele (principe 1)
CHAMPS_FOURNISSEUR = (
    "fournisseur", "societe", "raison_sociale", "vendeur",
    "site_web", "siteweb", "url", "email", "mail", "domaine",
)

# Classes exclues du cadrage : ce qui ne peut jamais etre une marque ni une reference
MOTIFS_EXCLUS = (
    # valeur mesuree
    r"^\d+([.,]\d+)?\s*(kw|w|kva|kg|g|t|mm|cm|m|km|l|ml|m2|m3|v|a|hz|bar|rpm|tr/min|g/m2|%|°c)$",
    # classe ou calibre
    r"^(dn|taille|pointure)\s*\d+$",
    r"^\d+\s*t$",
    # norme, certification, classement
    r"^(ce|rohs|atex|ip\s*\d{2}|iso\s*\d+|en\s*\d+|nf\s*\w*|a\+{0,3})$",
    # forme juridique
    r"^(sarl|sas|sasu|sa|eurl|snc|ets|etablissements|gmbh|bv|ltd|limited|spa|srl|nv|ag|plc|inc|llc)$",
    # etat ou transaction
    r"^(neuf|neuve|occasion|d?occasion|location|leasing|reconditionne|reconditionnee|destockage)$",
    # role commercial
    r"^(vendu par|distribue par|revendeur|revendeur agree|distributeur|fabricant|constructeur|editeur|importateur)$",
    # origine geographique seule (« France Levage » n'est pas concerne : ancrage complet)
    r"^(france|francaise|allemagne|germany|deutschland|italie|italia|espagne|chine|china|europe)$",
    r"^made in .+$",
    r"^fabrication (francaise|allemande|italienne|europeenne)$",
)


class FabricantReferenceGenerator:
    """Extrait marque et reference des produits d'une categorie via le prompt 133."""

    PROMPT_EXTRACTION_ID = settings.PROMPT_EXTRACTION_ID  # 133
    ETAPE = "16"
    ID_PROCESS = "31"
    TYPE_IA_DEEPSEEK = 2
    ORIGINE = "qc-fabricant-reference"

    PROVENANCES = ("titre", "description", "libelle_explicite", "absente")

    # Alertes produites par le prompt
    ALERTES_PROMPT = (
        "marque_composant", "marque_compatibilite", "marque_courte",
        "plusieurs_candidats", "gamme_possible", "reference_incertaine",
    )
    # Alertes ajoutees par les garde-fous du service
    ALERTES_SERVICE = (
        "absent_reponse_llm", "marque_absente_du_texte", "reference_absente_du_texte",
        "marque_generique", "marque_classe_exclue",
    )

    def __init__(self, api_client: Optional[HelloProAPIClient] = None):
        self.api_client = api_client or HelloProAPIClient()
        self.tracking_file = None
        self.prompt_extraction = None
        # Serialise les sauvegardes des batchs d'un meme run. Voir _process_batch.
        self._save_lock = asyncio.Lock()

    # ── logs ────────────────────────────────────────────────────────────────

    def _log(self, message: str):
        if self.tracking_file:
            utils.write_log(self.tracking_file, message)
        logger.info(message)

    # ── prompt ──────────────────────────────────────────────────────────────

    async def _load_prompt(self, id_categorie: str) -> Dict[str, Any]:
        """Charge le prompt 133 (table action_prompt_chatgpt) une seule fois par run."""
        if self.prompt_extraction is not None:
            return self.prompt_extraction

        prompt_config = await self.api_client.post(
            "prompt", "info", "get", {"id_prompt": self.PROMPT_EXTRACTION_ID}
        )

        if not prompt_config or not prompt_config.get("contenu_prompt"):
            await self._mail_erreur(
                id_categorie,
                f"Impossible de charger le prompt {self.PROMPT_EXTRACTION_ID}",
            )
            raise Exception(f"Impossible de charger le prompt {self.PROMPT_EXTRACTION_ID}")

        self.prompt_extraction = prompt_config
        self._log(f"Prompt d'extraction charge (ID: {self.PROMPT_EXTRACTION_ID})")
        return prompt_config

    # ── normalisation interne (comparaison uniquement) ──────────────────────

    @staticmethod
    def _cle(text: Optional[str]) -> str:
        """Cle de comparaison : majuscules, sans accents, alphanumerique seul.

        N'est jamais persistee : la valeur affichable reste le verbatim du modele.
        """
        if not text:
            return ""
        nfkd = unicodedata.normalize("NFKD", str(text))
        sans_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
        return re.sub(r"[^A-Z0-9]", "", sans_accents.upper())

    @staticmethod
    def _clean_str(value: Any) -> Optional[str]:
        """Normalise les vides ('', '  ', 'null') en None, sinon rend le verbatim."""
        if value is None:
            return None
        texte = str(value).strip()
        if not texte or texte.lower() in ("null", "none", "n/a"):
            return None
        return texte

    @classmethod
    def _est_classe_exclue(cls, valeur: str) -> bool:
        nfkd = unicodedata.normalize("NFKD", valeur.strip().lower())
        candidat = "".join(c for c in nfkd if not unicodedata.combining(c))
        candidat = candidat.replace("'", "").replace("’", "")
        return any(re.match(motif, candidat) for motif in MOTIFS_EXCLUS)

    def _est_generique(self, marque: str, libelle_categorie: str) -> bool:
        """Un mot qui reprend le libelle de la categorie n'est jamais une marque."""
        cle_marque = self._cle(marque)
        if not cle_marque or not libelle_categorie:
            return False
        if cle_marque == self._cle(libelle_categorie):
            return True
        return cle_marque in {self._cle(mot) for mot in re.split(r"[\s/,-]+", libelle_categorie) if mot}

    def _clean_alertes(self, alertes: Any) -> List[str]:
        """Ne conserve que les alertes du contrat : une alerte inventee n'est pas stockee."""
        connues = set(self.ALERTES_PROMPT) | set(self.ALERTES_SERVICE)
        if isinstance(alertes, str):
            alertes = [alertes]
        if not isinstance(alertes, list):
            return []
        retenues = []
        for alerte in alertes:
            nom = str(alerte).strip()
            if nom in connues and nom not in retenues:
                retenues.append(nom)
        return retenues

    # ── construction du payload ─────────────────────────────────────────────

    def _build_batch_payload(self, produits: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Reduit chaque produit aux 4 champs du prompt. Tout le reste est ecarte."""
        payload = []
        for produit in produits:
            objet = {
                "id_produit": str(produit.get("id_produit", "")),
                "categorie": self._clean_str(produit.get("categorie")) or "",
                "titre": self._clean_str(produit.get("titre")) or "",
            }
            description = self._clean_str(produit.get("description"))
            if description:
                objet["description"] = description
            payload.append(objet)
        return payload

    def _assert_no_supplier_data(self, payload: List[Dict[str, Any]]):
        """Garde-fou d'independance : leve si une donnee fournisseur atteint le prompt."""
        autorises = {"id_produit", "categorie", "titre", "description"}
        for objet in payload:
            interdits = set(objet.keys()) - autorises
            if interdits:
                raise ValueError(
                    f"Donnee fournisseur ou champ non autorise dans le payload du prompt: "
                    f"{sorted(interdits)}"
                )
            for cle in objet:
                if any(motif in cle.lower() for motif in CHAMPS_FOURNISSEUR):
                    raise ValueError(f"Champ fournisseur interdit dans le payload: {cle}")

    # ── appel LLM ───────────────────────────────────────────────────────────

    async def _call_llm(self, prompt_text: str, id_categorie: str, nb_produits: int) -> Any:
        """Appelle DeepSeek, journalise tokens et couts, retourne le JSON extrait."""
        temperature = float(self.prompt_extraction.get("temperature") or 0)
        deepseek = DeepSeek(temperature=temperature)
        result = await asyncio.to_thread(deepseek.chat, prompt_text)

        response_obj = result.get("response")
        if response_obj is not None and getattr(response_obj, "usage", None):
            await self.api_client.log_llm_usage(
                type_ia=self.TYPE_IA_DEEPSEEK,
                model=deepseek.MODEL,
                input_token=response_obj.usage.prompt_tokens,
                output_token=response_obj.usage.completion_tokens,
                id_process=self.ID_PROCESS,
                origine=self.ORIGINE,
                etat=1 if "code" not in result else 2,
                retour_erreur=str(result.get("error", "")) if "code" in result else "",
                temperature=temperature,
            )

        if "code" in result:
            raise Exception(f"Erreur API DeepSeek ({result.get('code')}): {result.get('error')}")

        response_text = (result.get("content") or "").strip()
        json_data = utils.extract_json_from_text(response_text)

        if json_data is None and re.sub(r"[^\[\]]", "", response_text) == "[]":
            return []

        if json_data is None:
            raise Exception(f"Impossible d'extraire le JSON de la reponse ({nb_produits} produits)")

        return json_data

    # ── alignement et garde-fous ────────────────────────────────────────────

    def _reconcile_batch(
        self, produits: List[Dict[str, Any]], sorties: Any
    ) -> List[ExtractionProduit]:
        """Aligne la sortie du modele sur les produits envoyes, par id_produit.

        L'ordre de la reponse n'est jamais suppose : un id manquant devient une
        abstention alertee, un id inconnu (hallucine) est ignore.
        """
        par_id: Dict[str, Dict[str, Any]] = {}
        if isinstance(sorties, list):
            for item in sorties:
                if isinstance(item, dict) and item.get("id_produit") is not None:
                    par_id[str(item["id_produit"])] = item

        ids_attendus = {str(p.get("id_produit", "")) for p in produits}
        ignores = set(par_id) - ids_attendus
        if ignores:
            self._log(f"AVERTISSEMENT: {len(ignores)} id_produit inconnus ignores: {sorted(ignores)}")

        resultats = []
        for produit in produits:
            id_produit = str(produit.get("id_produit", ""))
            item = par_id.get(id_produit)
            if item is None:
                resultats.append(
                    ExtractionProduit(id_produit=id_produit, alertes=["absent_reponse_llm"])
                )
                continue
            resultats.append(self._validate_extraction(item, produit))
        return resultats

    def _validate_extraction(
        self, item: Dict[str, Any], produit: Dict[str, Any]
    ) -> ExtractionProduit:
        """Applique les garde-fous deterministes. En cas de doute : abstention."""
        id_produit = str(item.get("id_produit") or produit.get("id_produit") or "")
        alertes = self._clean_alertes(item.get("alertes"))
        libelle_categorie = self._clean_str(produit.get("categorie")) or ""
        texte_source = self._cle(
            f"{produit.get('titre') or ''} {produit.get('description') or ''}"
        )

        def alerter(nom: str):
            if nom not in alertes:
                alertes.append(nom)

        marque = self._clean_str(item.get("marque"))
        if marque:
            if self._est_generique(marque, libelle_categorie):
                marque = None
                alerter("marque_generique")
            elif self._est_classe_exclue(marque):
                marque = None
                alerter("marque_classe_exclue")
            elif self._cle(marque) not in texte_source:
                # « verbatim » implique present dans le texte : sinon c'est une invention
                marque = None
                alerter("marque_absente_du_texte")
            elif len(marque) <= 3:
                alerter("marque_courte")

        reference = self._clean_str(item.get("reference"))
        if reference:
            if self._est_classe_exclue(reference):
                reference = None
                alerter("marque_classe_exclue")
            elif self._cle(reference) not in texte_source:
                reference = None
                alerter("reference_absente_du_texte")

        provenance = self._clean_str(item.get("provenance")) or "absente"
        if provenance not in self.PROVENANCES or not marque:
            provenance = "absente"

        return ExtractionProduit(
            id_produit=id_produit,
            marque=marque,
            reference=reference,
            modele=self._clean_str(item.get("modele")),
            provenance=provenance,
            extrait_marque=self._clean_str(item.get("extrait_marque")) if marque else None,
            alertes=alertes,
        )

    # ── traitement d'un batch ───────────────────────────────────────────────

    async def _process_batch(
        self,
        semaphore: asyncio.Semaphore,
        produits: List[Dict[str, Any]],
        id_categorie: str,
        source: str,
        numero: int,
    ) -> int:
        """Traite un batch : payload -> LLM -> alignement -> garde-fous -> sauvegarde.

        Retourne le nombre de produits enregistres. Leve en cas d'echec du batch.
        """
        async with semaphore:
            payload = self._build_batch_payload(produits)
            self._assert_no_supplier_data(payload)

            prompt_text = self.prompt_extraction["contenu_prompt"].replace(
                "{PRODUITS}", utils.to_json_string(payload)
            )

            self._log(f"[B{numero}] Appel LLM sur {len(payload)} produits")
            sorties = await self._call_llm(prompt_text, id_categorie, len(payload))

            extractions = self._reconcile_batch(produits, sorties)
            nb_marques = sum(1 for e in extractions if e.marque)

            # Les appels LLM restent paralleles ; les sauvegardes, non.
            # Cote BO, save alimente aussi le referentiel des marques de la categorie :
            # deux batchs simultanes qui portent deux graphies d'une meme marque
            # ("Wacker-Neuson" et "Wacker Neuson") ne la trouveraient ni l'un ni l'autre
            # et creeraient deux lignes, scindant nb_occurrences_fmr. Un run = une
            # categorie = ce verrou, donc la serialisation est complete pour la donnee
            # concernee. Le cout est nul : la sauvegarde dure quelques dizaines de ms
            # contre plusieurs secondes d'appel LLM.
            async with self._save_lock:
                enregistre = await self.api_client.post(
                    "fabricant_reference", "extraction", "save",
                    {
                        "id_categorie": id_categorie,
                        "source": source,
                        "extractions": [e.model_dump() for e in extractions],
                    },
                )

            if enregistre is False or enregistre is None:
                raise Exception(f"Echec de la sauvegarde du batch {numero}")

            self._log(f"[B{numero}] OK — {len(extractions)} enregistres, {nb_marques} avec marque")
            return nb_marques

    # ── run complet ─────────────────────────────────────────────────────────

    async def run(self, request: RequestFabricantReference) -> FabricantReferenceResult:
        """Extrait marque et reference pour tous les produits restants d'une categorie."""
        id_categorie = request.id_categorie
        source = request.source

        category_info = await self.api_client.post(
            "category", "info", "get", {"id_categorie": id_categorie}
        )
        if not category_info:
            await self._mail_erreur(id_categorie, f"Categorie {id_categorie} non trouvee")
            raise ValueError(f"Categorie {id_categorie} non trouvee")

        nom_rubrique = category_info.get("nom_rubrique", "")
        self.tracking_file = utils.get_tracking_filepath(id_categorie)

        if utils.check_stopper(id_categorie):
            await self._mail_erreur(id_categorie, "Le processus a ete arrete manuellement")
            raise Exception("Processus arrete manuellement")

        self._log("=" * 60)
        self._log(f"Extraction fabricant / reference — {id_categorie} - {nom_rubrique}")
        self._log(f"Source: {source} | batch: {BATCH_PRODUITS} | parallele: {APPELS_PARALLELES}")
        self._log("=" * 60)

        await self._load_prompt(id_categorie)

        process_data = await self.api_client.post(
            "fabricant_reference", "process", "get",
            {"id_categorie": id_categorie, "etape": self.ETAPE, "source": source},
        ) or {}

        if not process_data.get("can_start", False):
            await self._mail_erreur(id_categorie, "Le processus ne peut pas commencer")
            raise Exception("Le processus ne peut pas commencer")

        if request.is_reset:
            self._log("RESET DU PROCESSUS")
            await self.api_client.post(
                "fabricant_reference", "process", "reset",
                {"id_categorie": id_categorie, "etape": self.ETAPE, "source": source},
            )

        # only_missing: un produit deja present dans produit_fabricant_reference est traite
        produits = await self.api_client.post(
            "fabricant_reference", "produits", "get",
            {"id_categorie": id_categorie, "source": source, "only_missing": True},
        ) or []

        if not produits:
            self._log("Aucun produit a traiter")
            return FabricantReferenceResult(
                id_categorie=id_categorie, nom_rubrique=nom_rubrique, status="completed"
            )

        self._log(f"Produits a traiter: {len(produits)}")

        batches = [
            produits[i:i + BATCH_PRODUITS]
            for i in range(0, len(produits), BATCH_PRODUITS)
        ]
        semaphore = asyncio.Semaphore(APPELS_PARALLELES)

        total_processed = 0
        total_marques = 0
        total_echecs = 0
        echecs_consecutifs = 0

        for debut in range(0, len(batches), APPELS_PARALLELES):
            if utils.check_stopper(id_categorie):
                await self._mail_erreur(id_categorie, "Le processus a ete arrete manuellement")
                raise Exception("Processus arrete manuellement")

            vague = batches[debut:debut + APPELS_PARALLELES]
            resultats = await asyncio.gather(
                *[
                    self._process_batch(semaphore, batch, id_categorie, source, debut + i + 1)
                    for i, batch in enumerate(vague)
                ],
                return_exceptions=True,
            )

            for batch, resultat in zip(vague, resultats):
                if isinstance(resultat, BaseException):
                    total_echecs += 1
                    echecs_consecutifs += 1
                    self._log(f"ECHEC batch de {len(batch)} produits: {resultat}")
                else:
                    total_processed += len(batch)
                    total_marques += resultat
                    echecs_consecutifs = 0

            if echecs_consecutifs >= MAX_ECHECS_BATCH:
                message = (
                    f"{echecs_consecutifs} batchs consecutifs en echec — run interrompu "
                    f"({total_processed} produits traites avant l'arret)"
                )
                self._log(f"ARRET: {message}")
                await self._mail_erreur(id_categorie, message)
                raise Exception(message)

        status = "completed_with_errors" if total_echecs else "completed"

        self._log("=" * 60)
        self._log(f"TERMINE — {total_processed} produits, {total_marques} avec marque, "
                  f"{total_echecs} batchs en echec")
        self._log("=" * 60)

        await self.api_client.post(
            "fabricant_reference", "mail", "success" if not total_echecs else "error",
            {
                "id_categorie": id_categorie,
                "etape": self.ETAPE,
                "source": source,
                "tracking_file": self.tracking_file,
                "total_processed": total_processed,
                "total_marques": total_marques,
                "total_echecs": total_echecs,
            },
        )

        return FabricantReferenceResult(
            id_categorie=id_categorie,
            nom_rubrique=nom_rubrique,
            total_processed=total_processed,
            total_marques=total_marques,
            total_echecs=total_echecs,
            status=status,
        )

    async def _mail_erreur(self, id_categorie: str, message: str):
        await self.api_client.post(
            "fabricant_reference", "mail", "error",
            {
                "id_categorie": id_categorie,
                "etape": self.ETAPE,
                "error_message": message,
                "tracking_file": self.tracking_file,
            },
        )

    async def close(self):
        await self.api_client.close()
