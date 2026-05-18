"""
Logique métier de caractérisation des prix (collection Milvus `prix`).

Flux par catégorie :
  1. Récupère les points Milvus `prix` (par source) via api-rest-milvus /search.
  2. Récupère les caractérisations déjà présentes en BDD via v2/prix/caracterisation/get.
  3. Filtre les prix non encore traités.
  4. Pour chaque prix non traité :
       - source = produit : on copie directement les caracs de caracterisation_produit_ia
                            (id_produit connu ; confiance='haute').
       - autre source     : appel LLM DeepSeek (prompt caractérisation + prompt repasse,
                            même pattern que QC-caracterisation) ; confiance='moyenne'.
  5. Sauvegarde via v2/prix/caracterisation/save
       - payload distinct pour source produit (seulement id_chunk + id_produit + source
         — l'API BO réhydrate les caracs depuis caracterisation_produit_ia).
       - payload complet pour autres sources (liste des caracs extraites).
  6. Mail de fin.
"""
import re
import time
import logging
import asyncio
import contextvars
import unicodedata
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple

from app.core.api_client import HelloProAPIClient, DeepSeek
from app.core.milvus_client import MilvusPrixClient, SOURCE_STRING_TO_TINYINT, PRIX_CIBLE_FIELDS
from app.core import utils
from app.schemas.caracterisation_prix import RequestProcessus, CaracterisationPrixResult
from app.core.credentials import settings


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class CaracterisationPrixGenerator:
    """Caractérisation des prix Milvus via DeepSeek (ou copie _cpi pour source produit)."""

    # Prompts (chargés depuis action_prompt_chatgpt via l'API BO)
    PROMPT_CARACTERISATION_ID = settings.PROMPT_CARACTERISATION_ID
    PROMPT_REPASSE_ID = settings.PROMPT_REPASSE_ID
    DEEPSEEK_MODEL = "deepseek-v4-flash"

    # ID étape prix
    ETAPE = "13"
    ID_PROCESS = "37"

    # Traitement parallèle
    MAX_PARALLEL_ITEMS = 10

    # Ordre de traitement des sources (produit en premier car copie simple)
    SOURCES_ORDER = ["produit", "devis", "message", "siteweb"]

    _current_item_id = contextvars.ContextVar("current_item_id", default=None)

    def __init__(
        self,
        api_client: Optional[HelloProAPIClient] = None,
        milvus_client: Optional[MilvusPrixClient] = None,
    ):
        self.api_client = api_client or HelloProAPIClient()
        self.milvus_client = milvus_client or MilvusPrixClient()
        self.tracking_file: Optional[str] = None
        self.prompt_caracterisation: Optional[Dict[str, Any]] = None
        self.prompt_repasse: Optional[Dict[str, Any]] = None
        self._semaphore = asyncio.Semaphore(self.MAX_PARALLEL_ITEMS)
        self._item_log_buffers: Dict[str, List[str]] = {}

    # ======================================================================
    # Logs bufferisés par item (évite l'entrelacement en mode parallèle)
    # ======================================================================

    def _log(self, message: str):
        item_id = self._current_item_id.get(None)
        if item_id is not None:
            prefixed = f"[I-{item_id}] {message}"
            self._item_log_buffers.setdefault(item_id, []).append(prefixed)
            logger.info(prefixed)
        else:
            if self.tracking_file:
                utils.write_log(self.tracking_file, message)
            logger.info(message)

    def _flush_item_logs(self, item_id: str):
        if item_id in self._item_log_buffers:
            logs = self._item_log_buffers.pop(item_id)
            if self.tracking_file and logs:
                utils.write_log(self.tracking_file, "\n".join(logs))

    # ======================================================================
    # Helpers
    # ======================================================================

    def _normalize_for_comparison(self, text: str) -> str:
        if not text:
            return ""
        text = str(text).lower()
        nfkd = unicodedata.normalize("NFKD", text)
        text_clean = "".join([c for c in nfkd if not unicodedata.combining(c)])
        return re.sub(r"[^a-z]", "", text_clean)

    def _clean_caracteristiques_for_prompt(
        self,
        caracteristiques: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Nettoie et prépare les caractéristiques pour le prompt LLM (pattern QC-caracterisation).
          - Enlève micro-explication et autres-formulations des valeurs
          - Ajoute type=Textuelle si unité vide ou type non numérique
        """
        cleaned: List[Dict[str, Any]] = []
        for carac in caracteristiques:
            carac_copy = carac.copy()

            unite = carac_copy.get("unite", "")
            type_carac = carac_copy.get("type", "")

            if not unite or not re.match(r".*num.*", str(type_carac), re.IGNORECASE):
                if not re.match(r".*text.*", str(type_carac), re.IGNORECASE):
                    carac_copy["type"] = "Textuelle"

            if carac_copy.get("valeurs"):
                valeurs_clean = []
                for valeur in carac_copy["valeurs"]:
                    valeur_copy = valeur.copy()
                    valeur_copy.pop("micro-explication", None)
                    valeur_copy.pop("micro_explication", None)
                    valeur_copy.pop("autres-formulations", None)
                    valeur_copy.pop("autres_formulations", None)
                    valeurs_clean.append(valeur_copy)
                carac_copy["valeurs"] = valeurs_clean

            cleaned.append(carac_copy)

        return cleaned

    def _deduplicate_by_id_cible(self, milvus_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Dédoublonne les items Milvus par id_cible.
        Quand un même document est découpé en plusieurs chunks pour l'embedding,
        on les fusionne en un seul item :
          - id (id_prix_milvus) : concaténation des IDs Milvus séparés par ',' ordonnés par chunk_id
          - text : concaténation du texte de tous les chunks ordonnés par chunk_id
          - description_produit : identique sur tous les chunks → on garde celui du premier
        """
        groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for item in milvus_items:
            id_cible = self._get_id_cible(item)
            groups[id_cible].append(item)

        deduplicated: List[Dict[str, Any]] = []
        for id_cible, items in groups.items():
            if len(items) == 1:
                deduplicated.append(items[0])
                continue

            # Trier par chunk_id (1 à n)
            items.sort(key=lambda x: int(x.get("chunk_id", 0) or 0))

            # Base = premier chunk, on écrase les champs fusionnés
            merged = items[0].copy()

            # Concaténer les IDs Milvus ordonnés par chunk_id
            merged["id"] = ",".join(str(it.get("id") or it.get("pk") or "") for it in items)

            # Concaténer uniquement les textes (chunks du même document)
            texts = [str(it.get("text", "") or "") for it in items]
            merged["text"] = " ".join(t for t in texts if t)

            deduplicated.append(merged)

        return deduplicated

    def _build_enriched_descriptif(
        self,
        description: str,
        item: Dict[str, Any],
        nom_rubrique: str,
    ) -> str:
        """
        Enrichit la description produit avec les infos prix Milvus de l'item courant.
        Le résultat est injecté dans le placeholder {DESCRIPTIF_CATEGORIE} des prompts 100/103.
        """
        price_lines: List[str] = []

        for key, label in [
            ("valeur_reponse_q1",  nom_rubrique),
            ("caracteristique",    "Caractéristique du produit :"),
            # ("prix_original",      "Prix brut"),
            ("structure_prix",     "Structure prix :"),
            ("type_transaction",   "Type transaction :"),
            ("perimetre",          "Périmètre :"),
            # ("date_prix",          "Date prix"),
            # ("fournisseur",        "Fournisseur"),
        ]:
            val = item.get(key)
            if val:
                price_lines.append(f"{label} {val}.")

        valeur_prix = item.get("valeur_prix")
        if valeur_prix:
            prix_parts = [f"Valeur: {valeur_prix}"]
            if item.get("devise"):
                prix_parts.append(str(item["devise"]))
            if item.get("taxe"):
                prix_parts.append(str(item["taxe"]))
            if item.get("unite"):
                prix_parts.append(f"({item['unite']})")
            price_lines.append("Prix: " + " ".join(prix_parts))

        if not price_lines:
            return description or ""

        prix_block = "  ".join(price_lines)
        base = (description or "").strip()
        if base:
            return f"{base}.  {prix_block}."
        return f"{prix_block}."

    async def _load_prompts(self, id_categorie: str):
        """Charge les 2 prompts (caractérisation + repasse) une seule fois."""
        if self.prompt_caracterisation is None:
            self.prompt_caracterisation = await utils.get_prompt(self.PROMPT_CARACTERISATION_ID)
            if not self.prompt_caracterisation:
                raise Exception(f"Impossible de charger le prompt caractérisation (ID={self.PROMPT_CARACTERISATION_ID})")
            self._log(f"Prompt caractérisation chargé (ID: {self.PROMPT_CARACTERISATION_ID})")

        if self.prompt_repasse is None:
            self.prompt_repasse = await utils.get_prompt(self.PROMPT_REPASSE_ID)
            if not self.prompt_repasse:
                raise Exception(f"Impossible de charger le prompt repasse (ID={self.PROMPT_REPASSE_ID})")
            self._log(f"Prompt repasse chargé (ID: {self.PROMPT_REPASSE_ID})")

    def _get_milvus_id(self, item: Dict[str, Any]) -> str:
        """Retourne l'identifiant du point Milvus (id_prix_milvus_cppi).
        Tronqué à 255 chars si nécessaire (VARCHAR(255) côté SQL)."""
        raw = str(item.get("id") or item.get("pk") or "")
        return raw[:255]

    def _get_id_cible(self, item: Dict[str, Any]) -> str:
        """Retourne l'id métier polymorphe selon la source.
        Tronqué à 255 chars si nécessaire (VARCHAR(255) côté SQL)."""
        source = str(item.get("source", "")).lower()
        if source == "produit":
            return str(item.get("id_produit", "") or "")[:255]
        if source == "message":
            return str(item.get("id_lead", "") or "")[:255]
        # devis / siteweb
        return str(item.get("source_chunk_id", "") or "")[:255]

    def _build_prix_cible(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extrait les champs Milvus destinés à la table prix_cible_ia."""
        return {f: item.get(f) for f in PRIX_CIBLE_FIELDS}

    # ======================================================================
    # Appel LLM (DeepSeek + repasse) pour sources non-produit
    # ======================================================================

    async def _caracterise_via_llm(
        self,
        id_categorie: str,
        nom_rubrique: str,
        description_categorie: str,
        item: Dict[str, Any],
        caracteristiques_for_llm: List[Dict[str, Any]],
        jeu_carac_dict: Dict[Any, Dict],
    ) -> List[Dict[str, Any]]:
        """
        Caractérisation LLM (2 passes : extraction + repasse de validation).
        Pattern identique à QC-caracterisation.caracterise_produit + repasse_caracterisation.
        """
        titre = str(item.get("nom_produit", "") or "")
        description = str(item.get("description_produit", "") or item.get("text", "") or "")

        # Enrichir la description produit avec les infos prix Milvus
        enriched_description = self._build_enriched_descriptif(description, item, nom_rubrique)

        self._log(f"Titre: {titre}")
        self._log(f"Enriched description: {enriched_description}")

        # Pass 1 : extraction
        prompt_config = self.prompt_caracterisation.copy()
        prompt_text = prompt_config["contenu_prompt"]
        prompt_text = prompt_text.replace("{JEU_CARACTERISTIQUE}", utils.to_json_string(caracteristiques_for_llm))
        prompt_text = prompt_text.replace("{CATEGORIE}", nom_rubrique)
        prompt_text = prompt_text.replace("{DESCRIPTIF_CATEGORIE}", description_categorie or "")
        prompt_text = prompt_text.replace("{TITRE_DESCRIPTION}", f"{titre} {enriched_description}")

        temperature = float(prompt_config.get("temperature") or 0.1)
        deepseek = DeepSeek(temperature=temperature, max_retries=5)
        result = await asyncio.to_thread(deepseek.chat, prompt_text)

        # Tracking LLM
        is_error = "code" in result
        response_obj = result.get("response")
        if response_obj and hasattr(response_obj, "usage"):
            await self.api_client.log_llm_usage(
                type_ia=2,  # DeepSeek
                model=self.DEEPSEEK_MODEL,
                input_token=response_obj.usage.prompt_tokens or 0,
                output_token=response_obj.usage.completion_tokens or 0,
                id_process=self.ID_PROCESS,
                origine="prix-caracterisation",
                etat=2 if is_error else 1,
                retour_erreur=str(result.get("error", "")) if is_error else "",
                temperature=temperature,
            )
        if is_error:
            raise Exception(f"Erreur LLM caractérisation: {result.get('error')}")

        response_text = (result.get("content") or "").strip()
        self._log(f"Pass 1 réponse LLM: {response_text[:200]}...")
        json_data = utils.extract_json_from_text(response_text)

        # Réponse vide valide
        if json_data is None and re.sub(r"[^\[\]]", "", response_text) == "[]":
            return []
        if not json_data and json_data != []:
            raise Exception("Impossible d'extraire le JSON de la réponse (pass 1)")

        produit_caract = json_data if isinstance(json_data, list) else [json_data]

        if not produit_caract:
            return []

        # Pass 2 : repasse de validation
        carac_referentiel = [
            jeu_carac_dict[c.get("id_caracteristique")]
            for c in produit_caract
            if c.get("id_caracteristique") in jeu_carac_dict
        ]

        if carac_referentiel:
            prompt_config_r = self.prompt_repasse.copy()
            prompt_text_r = prompt_config_r["contenu_prompt"]
            prompt_text_r = prompt_text_r.replace("{JEU_CARACTERISTIQUE}", utils.to_json_string(carac_referentiel))
            prompt_text_r = prompt_text_r.replace("{CARACTERISTIQUE_PRODUIT}", utils.to_json_string(produit_caract))
            prompt_text_r = prompt_text_r.replace("{CATEGORIE}", nom_rubrique)
            prompt_text_r = prompt_text_r.replace("{TITRE_DESCRIPTION}", f"{titre} {description}")

            temperature_r = float(prompt_config_r.get("temperature") or 0.1)
            deepseek_r = DeepSeek(temperature=temperature_r, max_retries=5)
            result_r = await asyncio.to_thread(deepseek_r.chat, prompt_text_r)

            is_error_r = "code" in result_r
            response_obj_r = result_r.get("response")
            if response_obj_r and hasattr(response_obj_r, "usage"):
                await self.api_client.log_llm_usage(
                    type_ia=2,
                    model=self.DEEPSEEK_MODEL,
                    input_token=response_obj_r.usage.prompt_tokens or 0,
                    output_token=response_obj_r.usage.completion_tokens or 0,
                    id_process=self.ID_PROCESS,
                    origine="prix-caracterisation-repasse",
                    etat=2 if is_error_r else 1,
                    retour_erreur=str(result_r.get("error", "")) if is_error_r else "",
                    temperature=temperature_r,
                )
            if is_error_r:
                raise Exception(f"Erreur LLM repasse: {result_r.get('error')}")

            response_text_r = (result_r.get("content") or "").strip()
            self._log(f"Pass 2 (repasse) réponse LLM: {response_text_r[:200]}...")
            json_data_r = utils.extract_json_from_text(response_text_r)

            if json_data_r is None and re.sub(r"[^\[\]]", "", response_text_r) == "[]":
                return []
            if json_data_r is not None and (json_data_r or json_data_r == []):
                produit_caract = json_data_r if isinstance(json_data_r, list) else [json_data_r]

        return produit_caract

    # ======================================================================
    # Traitement d'un item Milvus
    # ======================================================================

    async def _process_single_item(
        self,
        item: Dict[str, Any],
        item_index: int,
        total_items: int,
        id_categorie: str,
        nom_rubrique: str,
        description_categorie: str,
        caracteristiques_for_llm: List[Dict[str, Any]],
        jeu_carac_dict: Dict[Any, Dict],
    ) -> Optional[Dict[str, Any]]:
        """
        Traite un item Milvus prix et retourne le payload save (ou None si skip).
        Le payload diffère selon la source :
          - produit : {id_prix_milvus, source, id_cible (= id_produit)} → BO réhydrate via _cpi
          - autres  : {id_prix_milvus, source, id_cible, caracteristiques: [...], confiance}
        """
        async with self._semaphore:
            id_milvus = self._get_milvus_id(item)
            source = str(item.get("source", "")).lower()
            id_cible = self._get_id_cible(item)

            token = self._current_item_id.set(id_milvus)
            try:
                self._log(f"[{item_index + 1}/{total_items}] source={source} id_milvus={id_milvus} id_cible={id_cible}")

                if not id_milvus:
                    self._log("⚠️ id Milvus manquant, skip")
                    return None

                source_tinyint = SOURCE_STRING_TO_TINYINT.get(source)
                if source_tinyint is None:
                    self._log(f"⚠️ source inconnue '{source}', skip")
                    return None

                # ============================================================
                # Cas 1 : source = produit → copie depuis caracterisation_produit_ia
                # ============================================================
                if source == "produit":
                    if not id_cible:
                        self._log("⚠️ id_produit manquant pour source=produit, skip")
                        return None

                    self._log(f"✅ source=produit → délégation _cpi via BO (id_produit={id_cible})")
                    # Payload minimal : l'API BO va copier les lignes de caracterisation_produit_ia
                    # dans caracterisation_prix_produit_ia pour ce couple (id_prix_milvus, id_produit).
                    return {
                        "id_prix_milvus": id_milvus,
                        "source":         source_tinyint,   # 3 = produit
                        "id_cible":       id_cible,
                        "id_categorie":   str(id_categorie),
                        "mode":           "copy_from_cpi",
                        "prix_cible":     self._build_prix_cible(item),
                    }

                # ============================================================
                # Cas 2 : autres sources → LLM DeepSeek
                # ============================================================
                caracs_llm = await self._caracterise_via_llm(
                    id_categorie=id_categorie,
                    nom_rubrique=nom_rubrique,
                    description_categorie=description_categorie,
                    item=item,
                    caracteristiques_for_llm=caracteristiques_for_llm,
                    jeu_carac_dict=jeu_carac_dict,
                )

                prix_cible = self._build_prix_cible(item)

                if not caracs_llm:
                    self._log("Aucune caractéristique extraite par le LLM")
                    return {
                        "id_prix_milvus":   id_milvus,
                        "source":           source_tinyint,
                        "id_cible":         id_cible,
                        "id_categorie":     str(id_categorie),
                        "mode":             "llm",
                        "caracteristiques": [],
                        "prix_cible":       prix_cible,
                    }

                self._log(f"✅ {len(caracs_llm)} caracs extraites via LLM")
                return {
                    "id_prix_milvus":   id_milvus,
                    "source":           source_tinyint,
                    "id_cible":         id_cible,
                    "id_categorie":     str(id_categorie),
                    "mode":             "llm",
                    "caracteristiques": caracs_llm,
                    "prix_cible":       prix_cible,
                }
            finally:
                self._flush_item_logs(id_milvus)
                self._current_item_id.reset(token)

    # ======================================================================
    # Récupération & filtrage des prix à traiter
    # ======================================================================

    async def _fetch_existing_caracterisations(
        self,
        id_categorie: str,
        source: Optional[str] = None,
    ) -> set:
        """
        Appelle v2/prix/caracterisation/get pour connaître les (id_prix_milvus) déjà traités.
        ⚠ Endpoint à créer côté PHP (BO/api/v2/prix.php).
        """
        payload = {"id_categorie": str(id_categorie)}
        if source:
            payload["source"] = source

        response = await self.api_client.post("prix", "caracterisation", "get", payload) or {}
        existing_ids = response.get("id_prix_milvus") or response.get("ids") or []
        existing_set = {str(x) for x in existing_ids}
        self._log(f"Déjà traités (source={source or '*'}): {len(existing_set)}")
        return existing_set

    # ======================================================================
    # Orchestration par catégorie
    # ======================================================================

    async def generate_all_caracterisations(self, request: RequestProcessus) -> CaracterisationPrixResult:
        id_categorie = request.id_categorie
        filter_source = (request.source or "").lower() or None

        # Tracking file
        self.tracking_file = utils.get_tracking_filepath(id_categorie, prefix="prix-caracterisation")

        self._log("=" * 60)
        self._log("CARACTÉRISATION PRIX (Milvus → _cppi)")
        self._log(f"Catégorie: {id_categorie}")
        self._log(f"Reset: {request.is_reset}")
        self._log(f"Source filtre: {filter_source or '*'}")
        self._log("=" * 60)

        if utils.check_stopper(id_categorie):
            raise Exception("Processus arrêté manuellement")

        # Catégorie
        category_info = await self.api_client.post(
            "category", "info", "get", {"id_categorie": id_categorie}
        )
        if not category_info:
            await self.api_client.post(
                "prix", "mail", "error",
                {"id_categorie": id_categorie, "etape": self.ETAPE,
                 "error_message": f"Catégorie {id_categorie} non trouvée",
                 "tracking_file": self.tracking_file},
            )
            raise ValueError(f"Catégorie {id_categorie} non trouvée")

        nom_rubrique = category_info.get("nom_rubrique", "") or ""
        description_categorie = category_info.get("description", "") or ""
        self._log(f"Rubrique: {nom_rubrique}")

        # Reset (si demandé) — délègue à BO : truncate _cppi pour cette catégorie
        if request.is_reset:
            self._log("RESET DU PROCESSUS (delete _cppi pour la catégorie)")
            await self.api_client.post(
                "prix", "caracterisation", "reset",
                {"id_categorie": id_categorie, "source": filter_source},
            )

        # Charger prompts + jeu de caractéristiques
        await self._load_prompts(id_categorie)

        jeu_caracteristique = await self.api_client.post(
            "caracteristique", "final", "get", {"id_categorie": id_categorie}
        )
        if not jeu_caracteristique:
            raise Exception("Jeu de caractéristiques final non trouvé pour cette catégorie")

        # Nettoyage du jeu pour le prompt LLM (retire micro-explication / autres-formulations,
        # force type=Textuelle si nécessaire) — pattern identique à QC-caracterisation.
        caracteristiques_cleaned = self._clean_caracteristiques_for_prompt(jeu_caracteristique)
        jeu_carac_dict = {
            c.get("id_caracteristique"): c for c in caracteristiques_cleaned
        }
        self._log(
            f"Jeu de caractéristiques: {len(jeu_caracteristique)} entrées "
            f"({len(caracteristiques_cleaned)} après nettoyage pour prompt)"
        )

        self._log(f"Jeu de caractéristiques: {caracteristiques_cleaned}")

        # Sources à traiter (filtre si demandé, sinon toutes)
        sources_to_process = [filter_source] if filter_source else self.SOURCES_ORDER

        total_prix = 0
        total_processed = 0
        total_skipped = 0
        total_errors = 0
        by_source: Dict[str, int] = {}
        start_time = time.time()

        for source in sources_to_process:
            self._log(f"\n--- Source: {source} ---")

            # 1. Récupération Milvus (pymilvus sync → wrap asyncio.to_thread)
            milvus_items = await asyncio.to_thread(
                self.milvus_client.search_prix,
                id_categorie=str(id_categorie),
                source=source,
            )
            if not milvus_items:
                self._log(f"Aucun prix Milvus pour source={source}")
                by_source[source] = 0
                continue

            # 1b. Dédoublonnage par id_cible (source produit uniquement)
            if source == "produit":
                raw_count = len(milvus_items)
                milvus_items = self._deduplicate_by_id_cible(milvus_items)
                if len(milvus_items) < raw_count:
                    self._log(f"{raw_count} chunks Milvus → {len(milvus_items)} items uniques (dédoublonnage par id_cible)")
            total_prix += len(milvus_items)

            # 2. Existants côté BDD
            existing_ids = await self._fetch_existing_caracterisations(
                id_categorie=id_categorie, source=source
            )

            # 3. Filtrer les non-traités
            items_to_process = [
                it for it in milvus_items
                if self._get_milvus_id(it) and self._get_milvus_id(it) not in existing_ids
            ]
            skipped = len(milvus_items) - len(items_to_process)
            total_skipped += skipped
            self._log(f"source={source}: {len(items_to_process)} à traiter, {skipped} déjà traités")

            if not items_to_process:
                by_source[source] = 0
                continue

            # 4. Traitement parallèle par batch de MAX_PARALLEL_ITEMS
            batch_size = self.MAX_PARALLEL_ITEMS
            source_processed = 0
            payloads_copy: List[Dict[str, Any]] = []
            payloads_llm: List[Dict[str, Any]] = []

            for batch_start in range(0, len(items_to_process), batch_size):
                batch = items_to_process[batch_start: batch_start + batch_size]
                tasks = [
                    self._process_single_item(
                        item=it,
                        item_index=batch_start + i,
                        total_items=len(items_to_process),
                        id_categorie=id_categorie,
                        nom_rubrique=nom_rubrique,
                        description_categorie=description_categorie,
                        caracteristiques_for_llm=caracteristiques_cleaned,
                        jeu_carac_dict=jeu_carac_dict,
                    )
                    for i, it in enumerate(batch)
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Flush logs bufferisés
                for key in list(self._item_log_buffers.keys()):
                    self._flush_item_logs(key)

                for r in results:
                    if isinstance(r, Exception):
                        total_errors += 1
                        self._log(f"❌ Exception item: {r}")
                        continue
                    if r is None:
                        continue
                    source_processed += 1
                    total_processed += 1
                    if r.get("mode") == "copy_from_cpi":
                        payloads_copy.append(r)
                    else:
                        payloads_llm.append(r)

            # 5. Sauvegarde batch (distincts par mode)
            if payloads_copy:
                self._log(f"Save batch {len(payloads_copy)} payload(s) produit → copy_from_cpi")
                save_res = await self.api_client.post(
                    "prix", "caracterisation", "save_produit",
                    {"id_categorie": str(id_categorie), "items": payloads_copy},
                )
                if save_res and save_res.get("erreur"):
                    raise Exception(f"Échec save_produit: {save_res}")

            if payloads_llm:
                self._log(f"Save batch {len(payloads_llm)} payload(s) LLM (source={source})")
                save_res = await self.api_client.post(
                    "prix", "caracterisation", "save",
                    {"id_categorie": str(id_categorie), "items": payloads_llm},
                )
                if save_res and save_res.get("erreur"):
                    raise Exception(f"Échec save caractérisation LLM: {save_res}")

            by_source[source] = source_processed

        elapsed = time.time() - start_time
        status = "completed" if total_errors == 0 else "completed_with_errors"

        self._log("\n" + "=" * 60)
        self._log("CARACTÉRISATION PRIX TERMINÉE")
        self._log(f"Total Milvus: {total_prix}")
        self._log(f"Traités: {total_processed}")
        self._log(f"Déjà présents (skip): {total_skipped}")
        self._log(f"Erreurs: {total_errors}")
        self._log(f"Par source: {by_source}")
        self._log(f"Durée: {elapsed:.1f}s")
        self._log("=" * 60)

        # 6. Mail fin
        await self.api_client.post(
            "prix", "mail", "success",
            {
                "id_categorie": id_categorie,
                "etape": self.ETAPE,
                "tracking_file": self.tracking_file,
                "total_processed": total_processed,
            },
        )

        return CaracterisationPrixResult(
            id_categorie=id_categorie,
            nom_rubrique=nom_rubrique,
            total_prix=total_prix,
            total_processed=total_processed,
            total_skipped=total_skipped,
            total_errors=total_errors,
            by_source=by_source,
            status=status,
        )

    async def close(self):
        await self.api_client.close()
        await self.milvus_client.close()
