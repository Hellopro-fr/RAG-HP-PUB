"""
Module principal de traitement: extraction de prix depuis les chunks Milvus via LLM.
Traitement parallèle asynchrone avec asyncio.
"""
import re
import time
import logging
import asyncio
import contextvars
from typing import Dict, List, Any, Optional

from app.core.api_client import HelloProAPIClient, GeminiProvider, DeepSeek
from app.core.search import call_search_api_async
from app.core import utils
from app.schemas.prix_extraction import (
    RequestProcessus,
    ItemResult,
    PrixExtractionResult
)
from app.schemas.produit_prix_payload import ProduitPrixPayload
from app.core.credentials import settings


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class PrixExtractor:
    """Extracteur de prix via RAG (Milvus) + LLM (Gemini/DeepSeek)"""

    _current_chunk_id = contextvars.ContextVar('current_chunk_id', default=None)

    # ID du prompt statique
    PROMPT_ID = settings.PROMPT_ID  # "140"

    # ID process
    ID_PROCESS = "37"

    # Type extraction (4 = siteweb)
    TYPE_EXTRACTION = "4"

    # Provider LLM forcé (ne dépend pas de la variable d'env globale LLM_PROVIDER)
    LLM_PROVIDER = "gemini"

    # Modèle Gemini par défaut
    GEMINI_MODEL = settings.GEMINI_MODEL_NAME

    # Nombre max de traitements parallèles pour les chunks
    MAX_PARALLEL_CHUNKS = 5

    ETAPE = "11"

    def __init__(self, api_client: Optional[HelloProAPIClient] = None):
        self.api_client = api_client or HelloProAPIClient()
        self.tracking_file = None
        self.prompt_config = None  # Sera chargé lors du premier traitement
        self.info_q1 = ""  # Sera chargé lors du traitement (Question 1)
        self._semaphore = asyncio.Semaphore(self.MAX_PARALLEL_CHUNKS)
        # Buffer de logs par chunk pour éviter l'entrelacement en mode parallèle
        self._chunk_log_buffers: Dict[str, List[str]] = {}


    def _log(self, message: str):
        """
        Écrit dans le fichier de tracking et les logs.
        En mode parallèle, bufferise les logs par chunk pour éviter l'entrelacement.
        """
        chunk_id = self._current_chunk_id.get(None)

        if chunk_id is not None:
            prefixed = f"[C-{chunk_id}] {message}"
            if chunk_id not in self._chunk_log_buffers:
                self._chunk_log_buffers[chunk_id] = []
            self._chunk_log_buffers[chunk_id].append(prefixed)
            logger.info(prefixed)
        else:
            if self.tracking_file:
                utils.write_log(self.tracking_file, message)
            logger.info(message)

    def _flush_chunk_logs(self, chunk_id: str):
        """
        Écrit tous les logs bufferisés d'un chunk d'un seul bloc dans le fichier de tracking.
        Garantit que les logs d'un même chunk restent groupés et lisibles.
        """
        if chunk_id in self._chunk_log_buffers:
            logs = self._chunk_log_buffers.pop(chunk_id)
            if self.tracking_file and logs:
                block = "\n".join(logs)
                utils.write_log(self.tracking_file, block)

    def _clean_q1_data(self, q1_response: dict) -> dict:
        """
        Nettoie les données Question 1 en retirant les champs inutiles
        (equivalence, id_reponse_parent, id_question_parent, choix, et tous les id_*).
        """
        data = q1_response.get("response", q1_response)

        cleaned = {
            "intitule": data.get("intitule", ""),
            "justification": data.get("justification", ""),
            "reponses": []
        }

        for rep in data.get("reponses", []):
            cleaned["reponses"].append({
                "reponse": rep.get("reponse", "")
            })

        return cleaned

    async def _load_prompt(self, id_categorie: str):
        """Charge le prompt une seule fois au début du traitement"""
        if self.prompt_config is None:
            self.prompt_config = await utils.get_prompt(self.PROMPT_ID)
            if not self.prompt_config:
                self._log("ERREUR: Impossible de charger le prompt d'extraction de prix")
                raise Exception(f"Impossible de charger le prompt ID={self.PROMPT_ID}")
            self._log(f"Prompt chargé (ID: {self.PROMPT_ID})")

    def _build_prompt(self, chunk_metadata: dict, category_name: str = "") -> str:
        """
        Construit le prompt final en injectant le contenu du chunk dans le template.
        
        Args:
            chunk_metadata: Le contenu du chunk Milvus
            category_name: Le nom de la catégorie (optionnel)
            
        Returns:
            Le prompt final à envoyer au LLM
        """
        prompt_text = self.prompt_config.get("contenu_prompt", "")        

        chunk_siteweb = f"""url : {chunk_metadata.get("url", "")}
                    Contenu : {chunk_metadata.get("text", "")}
                    Fournisseur : {chunk_metadata.get("fournisseur", "")}
                    Page_type : {chunk_metadata.get("page_type", "")}
                    Date_ajout : {chunk_metadata.get("date_ajout", "")}
                """
        
        # Remplacer les placeholders si présents
        prompt_text = prompt_text.replace("{chunk_siteweb}", chunk_siteweb)
        prompt_text = prompt_text.replace("{info_q1}", self.info_q1)
        prompt_text = prompt_text.replace("{nom_categorie}", category_name)
        
        return prompt_text

    async def _call_llm(self, prompt_text: str, id_categorie: str) -> Dict[str, Any]:
        """
        Appelle le LLM configuré (Gemini ou DeepSeek) avec le prompt.
        
        Args:
            prompt_text: Le prompt à envoyer
            id_categorie: ID de la catégorie pour le tracking
            
        Returns:
            Dict avec le résultat du LLM
        """
        provider = self.LLM_PROVIDER.lower()
        
        if provider == "gemini":
            gemini = GeminiProvider(
                model=self.GEMINI_MODEL,
                thinking_level="high",
                max_retries=10
            )
            result = await asyncio.to_thread(gemini.chat, prompt_text)
            
            # Log LLM usage pour Gemini
            usage_metadata = result.get("api_response", {}).get("usage_metadata", {})
            await self.api_client.log_llm_usage(
                type_ia=3,  # Gemini
                model=self.GEMINI_MODEL,
                input_token=usage_metadata.get("prompt_token_count") or 0,
                output_token=(usage_metadata.get("candidates_token_count") or 0) + (usage_metadata.get("thoughtsTokenCount") or 0),
                id_process=self.ID_PROCESS,
                origine="prix-extraction-siteweb",
                etat=1 if "code" not in result else 2,
                retour_erreur=str(result.get("error", "")) if "code" in result else ""
            )
            
            return result
            
        elif provider == "deepseek":
            # Récupérer la température depuis le prompt config
            temperature = float(self.prompt_config.get("temperature_apc", 0.1))
            deepseek = DeepSeek(temperature=temperature)
            result = await asyncio.to_thread(deepseek.chat, prompt_text)
            
            # Log LLM usage pour DeepSeek
            response_obj = result.get("response")
            input_tokens = 0
            output_tokens = 0
            if response_obj and hasattr(response_obj, 'usage'):
                input_tokens = response_obj.usage.prompt_tokens or 0
                output_tokens = response_obj.usage.completion_tokens or 0
            
            await self.api_client.log_llm_usage(
                type_ia=2,  # DeepSeek
                model="deepseek-v4-flash",
                input_token=input_tokens,
                output_token=output_tokens,
                id_process=self.ID_PROCESS,
                origine="prix-extraction-siteweb",
                etat=1,
                temperature=temperature
            )
            
            # Normaliser le format de retour pour être compatible avec le format Gemini
            return {
                "message": result.get("content", ""),
                "api_response": {}
            }
        else:
            raise ValueError(f"Provider LLM inconnu: {provider}. Utilisez 'gemini' ou 'deepseek'.")

    def _validate_and_build_payload(
        self,
        prix_data: dict,
        chunk_id: str,
        id_categorie: str,
        category_name: str,
        chunk_metadata: dict
    ):
        """
        Valide les données extraites par le LLM et construit un ProduitPrixPayload.

        Args:
            prix_data     : Données JSON extraites par le LLM depuis le chunk siteweb
            chunk_id      : ID du chunk Milvus source (stocké en tant que source_chunk_id)
            id_categorie  : ID de la catégorie
            category_name : Nom de la catégorie
            chunk_metadata: Métadonnées du chunk (peut contenir domaine, fournisseur, etc.)

        Returns:
            ProduitPrixPayload validé, ou None si les données sont insuffisantes.
        """
        if not prix_data or not isinstance(prix_data, dict):
            self._log(f"⚠️ Pas de données prix pour chunk {chunk_id}")
            return None
        try:
            payload = ProduitPrixPayload(
                source="siteweb",
                source_chunk_id=chunk_id,
                id_categorie=id_categorie,
                nom_categorie=category_name,
                # Champs obligatoires attendus dans la réponse LLM
                nom_produit=str(prix_data.get("nom_produit", "")).strip(),
                description_produit=str(prix_data.get("description_produit", "")).strip(),
                valeur_prix=str(prix_data.get("valeur_prix", "")).strip(),
                # Champs optionnels extraits par le LLM                
                caracteristique=prix_data.get("caracteristique") or None,
                date_prix=prix_data.get("date_prix") or None,
                id_lead=prix_data.get("id_lead") or None,
                id_produit=str(prix_data.get("id_produit", "")) or None,
                domaine=chunk_metadata.get("domaine") or None,
                id_societe_ia=str(prix_data.get("id_societe_ia", "")) or None,
                valeur_reponse_q1=prix_data.get("valeur_reponse_q1") or None,
                prix_original=str(prix_data.get("prix_original", "")).strip() or None,
                structure_prix=prix_data.get("structure_prix") or None,
                unite=prix_data.get("unite") or None,
                devise=prix_data.get("devise") or None,
                taxe=prix_data.get("taxe") or None,
                type_transaction=prix_data.get("type_transaction") or None,
                perimetre=prix_data.get("perimetre") or None,
                id_fournisseur=str(chunk_metadata.get("id_fournisseur", "")) or None,
                fournisseur=chunk_metadata.get("fournisseur") or None,
            )
            return payload
        except Exception as e:
            self._log(f"⚠️ Validation échouée pour chunk {chunk_id}: {e}")
            return None

    async def _process_single_chunk(
        self,
        chunk: Dict[str, Any],
        chunk_index: int,
        total_chunks: int,
        id_categorie: str,
        category_name: str = ""
    ) -> ItemResult:
        """
        Traite un seul chunk Milvus siteweb: LLM call + validation payload.

        En cas d'erreur (LLM, JSON, validation), une exception est levée
        afin d'interrompre immédiatement le traitement de la catégorie.

        Args:
            chunk        : Les données du chunk Milvus
            chunk_index  : Index du chunk (pour les logs)
            total_chunks : Nombre total de chunks
            id_categorie : ID de la catégorie
            category_name: Nom de la catégorie

        Returns:
            ItemResult avec status="success" et prix_data validé.

        Raises:
            Exception si le LLM échoue, si le JSON est illisible ou si la
            validation du payload échoue.
        """
        async with self._semaphore:
            chunk_id = str(chunk.get("id", chunk.get("chunk_id", f"unknown_{chunk_index}")))
            # Les données Milvus sont dans metadata.entity
            metadata = chunk.get("metadata", {})
            context_pre = metadata.get("context_pre") or ""
            context_post = metadata.get("context_post") or ""

            chunk_metadata = metadata.get("entity", metadata)
            chunk_content = chunk_metadata.get("text", "")

            # verification s'il y a context_pre et context_post dans metadata ajouter dans avant / apres chunk_content
            # possible null
            # maj metadata.entity.text avec chunk_content
            if context_pre or context_post:
                self._log(f"[{chunk_index + 1}/{total_chunks}] context_pre: {context_pre}")
                self._log(f"[{chunk_index + 1}/{total_chunks}] context_post: {context_post}")
                chunk_metadata["text"] = context_pre + "  " + chunk_content + "  " + context_post
                chunk_metadata["context_pre"] = context_pre
                chunk_metadata["context_post"] = context_post
                chunk_content = chunk_metadata["text"]

            # Activer le contexte chunk pour bufferiser les logs
            token = self._current_chunk_id.set(chunk_id)

            self._log(f"[{chunk_index + 1}/{total_chunks}] Traitement chunk {chunk_id}")
            self._log(f"[{chunk_index + 1}/{total_chunks}] chunk_metadata: ({chunk_metadata})")

            # Pré-filtre : si le texte ne contient aucune mention de prix, skip sans appeler le LLM
            if not re.search(r'€|\d+\s*(euros?|€|EUR)|\d[\d\s.,]*\s*H\.?T\.?|\d[\d\s.,]*\s*TTC|prix\s+de\s+\d+', chunk_content, re.IGNORECASE):
                self._log(f"[{chunk_index + 1}/{total_chunks}] ⏭️ Chunk {chunk_id} — aucune mention de prix (€/euro/EUR) → skip")
                self._flush_chunk_logs(chunk_id)
                self._current_chunk_id.reset(token)
                return ItemResult(
                    item_id=chunk_id,
                    source=settings.MILVUS_SOURCE,
                    content=chunk_content,
                    prix_data=None,
                    status="skipped"
                )

            # 1. Construire le prompt avec le contenu du chunk
            prompt_text = self._build_prompt(chunk_metadata, category_name)

            # 2. Appeler le LLM
            result = await self._call_llm(prompt_text, id_categorie)

            # Vérifier si c'est une erreur (format Gemini avec "code")
            if "code" in result:
                error_msg = str(result.get("error", "Erreur LLM inconnue"))
                self._log(f"[{chunk_index + 1}/{total_chunks}] ❌ Erreur LLM chunk {chunk_id}: {error_msg}")
                self._flush_chunk_logs(chunk_id)
                self._current_chunk_id.reset(token)
                raise Exception(f"Erreur LLM pour chunk {chunk_id}: {error_msg}")

            # 3. Extraire la réponse
            response_text = result.get("message", "")
            self._log(f"[{chunk_index + 1}/{total_chunks}] Réponse LLM reçue ({response_text})")

            # Tenter d'extraire le JSON de la réponse
            prix_data_raw = utils.extract_json_from_text(response_text)
            if prix_data_raw is None:
                self._log("ERREUR: Impossible d'extraire le JSON")
                await self.api_client.post(
                    "prix",
                    "mail",
                    "error",
                    {
                        "id_categorie" : id_categorie,
                        "error_message": "Erreur extraction JSON",
                        "etape"        : self.ETAPE,
                        "error_detail" : {"response_text": response_text},
                        "tracking_file": self.tracking_file
                    }
                )
                self._flush_chunk_logs(chunk_id)
                self._current_chunk_id.reset(token)
                raise Exception(f"Impossible d'extraire le JSON de la réponse LLM pour chunk {chunk_id}")

            # Liste vide = le LLM n'a trouvé aucun prix dans ce chunk → skip
            if isinstance(prix_data_raw, list) and len(prix_data_raw) == 0:
                self._log(f"[{chunk_index + 1}/{total_chunks}] ⏭️ Chunk {chunk_id} — aucun prix trouvé par le LLM")
                self._flush_chunk_logs(chunk_id)
                self._current_chunk_id.reset(token)
                return ItemResult(
                    item_id=chunk_id,
                    source=settings.MILVUS_SOURCE,
                    content=chunk_content,
                    prix_data=None,
                    status="skipped"
                )

            # Normaliser en liste (le LLM peut retourner un dict ou une liste)
            if isinstance(prix_data_raw, dict):
                prix_data_raw = [prix_data_raw]

            # 3b. Valider et construire les payloads pour chaque produit
            payloads = []
            for single_prix in prix_data_raw:
                payload = self._validate_and_build_payload(
                    prix_data=single_prix,
                    chunk_id=chunk_id,
                    id_categorie=id_categorie,
                    category_name=category_name,
                    chunk_metadata=chunk_metadata
                )
                if payload is None:
                    self._flush_chunk_logs(chunk_id)
                    self._current_chunk_id.reset(token)
                    raise ValueError(
                        f"Validation du payload échouée (champs obligatoires manquants) : "
                        f"Catégorie {id_categorie} - Chunk {chunk_id} - Data : {single_prix}"
                    )
                payloads.append(payload)

            prix_data = [p.dict() for p in payloads]

            self._log(f"[{chunk_index + 1}/{total_chunks}] ✅ Chunk {chunk_id} validé")
            self._flush_chunk_logs(chunk_id)
            self._current_chunk_id.reset(token)
            return ItemResult(
                item_id=chunk_id,
                source=settings.MILVUS_SOURCE,
                content=chunk_content,
                prix_data=prix_data,
                status="success"
            )

    async def extract_prix_for_category(
        self,
        request: RequestProcessus
    ) -> PrixExtractionResult:
        """
        Processus principal: extraction de prix pour une catégorie.
        
        1. Charge le prompt (ID=140)
        2. Recherche dans Milvus (top_k=30, source=siteweb)
        3. Traite chaque chunk en parallèle via asyncio
        4. Pour chaque chunk: LLM call → stockage API
        5. Retourne les résultats individuels pour que le consumer publie vers prix-normalisation
        
        Args:
            request: RequestProcessus avec id_categorie et is_reset
            
        Returns:
            PrixExtractionResult avec le bilan du traitement
        """
        id_categorie = request.id_categorie
        
        # Initialiser le fichier de tracking
        self.tracking_file = utils.get_tracking_filepath(id_categorie)
        
        self._log("=" * 60)
        self._log("EXTRACTION PRIX SITE WEB")
        self._log(f"Catégorie: {id_categorie}")
        self._log(f"Reset: {request.is_reset}")
        self._log(f"Provider LLM: {self.LLM_PROVIDER}")
        self._log(f"Model LLM: {self.GEMINI_MODEL}")
        self._log(f"Source Milvus: {settings.MILVUS_SOURCE}")
        self._log(f"Top K: {settings.MILVUS_TOP_K}")
        self._log("=" * 60)
        
        # Vérifier le stopper manuel
        if utils.check_stopper(id_categorie):
            self._log("ARRÊT MANUEL DÉTECTÉ")
            raise Exception("Processus arrêté manuellement")
        
        # Récupérer les infos de la catégorie
        category_info = await self.api_client.post(
            "category",
            "info",
            "get",
            {"id_categorie": id_categorie}
        )
        
        if not category_info:
            self._log(f"ERREUR: Catégorie {id_categorie} non trouvée")
            raise ValueError(f"Catégorie {id_categorie} non trouvée")
        
        category_name = category_info.get("nom_rubrique", "")
        self._log(f"Catégorie: {category_name}")
        
        # Reset si demandé
        if request.is_reset:
            self._log("RESET DU PROCESSUS")
            await self.api_client.post(
                "prix",
                "process",
                "reset",
                {"id_categorie": id_categorie, "type_extraction": self.TYPE_EXTRACTION}
            )
        
        # Charger le prompt
        await self._load_prompt(id_categorie)

        # Récupérer Question 1 pour le contexte du prompt
        self._log("Récupération Question 1...")
        q1_raw = await self.api_client.post(
            "question",
            "question1",
            "get",
            {"id_categorie": id_categorie}
        )
        if not q1_raw:
            self._log(f"ERREUR: Aucune donnée Question 1 pour la catégorie {id_categorie}")
            raise Exception(f"Impossible de récupérer Question 1 pour la catégorie {id_categorie}")
        self.info_q1 = utils.to_json_string(self._clean_q1_data(q1_raw))
        self._log(f"Question 1 chargée: {self.info_q1}")

        # Extraire les réponses Q1 pour la boucle de recherche
        q1_data = q1_raw.get("response", q1_raw)
        reponses_q1 = q1_data.get("reponses", [])
        if not reponses_q1:
            self._log("ERREUR: Aucune réponse dans Question 1")
            raise Exception(f"Aucune réponse Q1 pour la catégorie {id_categorie}")

        # Filtre page_type pour la recherche RAG
        filtre_page_type = {
            "page_type": [
                "article", "blog", "ecommerce", "faq", "home",
                "landing", "listing_produit", "Page_local", "fiche_produit"
            ],
            "autre_chunks": "adjacent"
        }

        # Compteurs globaux sur toutes les boucles Q1
        total_success = 0
        total_skipped = 0
        total_error = 0
        total_chunks_global = 0
        all_item_results: List[ItemResult] = []
        start_time_global = time.time()

        # Récupérer les ids chunks déjà traités (partagé entre toutes les boucles Q1)
        self._log("Récupération des ids chunks déjà traités...")
        ids_chunks_traites = await self.api_client.post(
            "prix",
            "process",
            "get",
            {"id_categorie": id_categorie, "type_extraction": self.TYPE_EXTRACTION}
        )
        ids_chunks_traites = set(ids_chunks_traites) if ids_chunks_traites else set()

        # Boucle sur chaque réponse Q1
        for idx_q1, rep_q1 in enumerate(reponses_q1, 1):
            reponse_text = rep_q1.get("reponse", "")
            self._log(f"\n{'='*60}")
            self._log(f"BOUCLE Q1 [{idx_q1}/{len(reponses_q1)}] : {reponse_text}")
            self._log(f"{'='*60}")

            # Recherche RAG avec prompt enrichi par la réponse Q1
            reponse_clean = re.sub(r'\s*\(.*?\)', '', reponse_text).strip()
            search_prompt = f"prix {category_name} {reponse_clean} €"
            self._log(f"\n--- Recherche Milvus: '{search_prompt}' (top_k=30) ---")
            chunks = await call_search_api_async(
                prompt=search_prompt,
                num_results=settings.MILVUS_TOP_K,
                source=settings.MILVUS_SOURCE,
                filtre=filtre_page_type
            )

            if not chunks:
                self._log(f"⚠️ Aucun résultat Milvus pour Q1[{idx_q1}]")
                continue

            self._log(f"📊 {len(chunks)} chunks trouvés dans Milvus")

            # Filtrer les chunks déjà traités + dédoublonnage intra-résultat RAG
            chunks_filtres = []
            ids_vus_dans_batch = {}  # chunk_id -> fingerprint (text + context)
            for chunk in chunks:
                chunk_id = str(chunk.get("id", ""))
                metadata = chunk.get("metadata", {})
                entity = metadata.get("entity", metadata)
                fingerprint = (
                    entity.get("text", ""),
                    metadata.get("context_pre") or entity.get("context_pre") or "",
                    metadata.get("context_post") or entity.get("context_post") or ""
                )
                if chunk_id in ids_chunks_traites:
                    self._log(f"Chunk {chunk_id} déjà traité")
                elif chunk_id in ids_vus_dans_batch:
                    if ids_vus_dans_batch[chunk_id] == fingerprint:
                        self._log(f"Chunk {chunk_id} doublon identique dans résultat RAG — ignoré")
                    else:
                        self._log(f"Chunk {chunk_id} même ID mais contenu différent — conservé")
                        chunks_filtres.append(chunk)
                else:
                    ids_vus_dans_batch[chunk_id] = fingerprint
                    chunks_filtres.append(chunk)
            chunks = chunks_filtres

            if not chunks:
                self._log(f"⚠️ Tous les chunks déjà traités pour Q1[{idx_q1}]")
                continue

            total_chunks = len(chunks)
            total_chunks_global += total_chunks
            self._log(f"📊 {total_chunks} chunks à traiter après dédoublonnage")

            # Traitement parallèle des chunks
            self._log(f"\n--- Traitement parallèle ({self.MAX_PARALLEL_CHUNKS} max simultanés) ---")

            tasks = [
                self._process_single_chunk(
                    chunk=chunk,
                    chunk_index=i,
                    total_chunks=total_chunks,
                    id_categorie=id_categorie,
                    category_name=category_name
                )
                for i, chunk in enumerate(chunks)
            ]

            results: List[ItemResult] = await asyncio.gather(*tasks, return_exceptions=True)            

            # Flush les logs bufferisés des chunks
            for chunk_id_key in list(self._chunk_log_buffers.keys()):
                self._flush_chunk_logs(chunk_id_key)

            # Collecter les résultats
            batch_item_results: List[ItemResult] = []
            for r in results:
                if isinstance(r, Exception):
                    self._log(f"❌ Exception critique: {r}")
                    raise r
                elif isinstance(r, ItemResult):
                    batch_item_results.append(r)
                    if r.status == "success":
                        total_success += 1
                    elif r.status == "skipped":
                        total_skipped += 1
                    else:
                        total_error += 1
                        self._log(f"❌ Chunk en erreur: {r.item_id} — {r.error_message}")
                        raise Exception(f"Chunk {r.item_id} en erreur: {r.error_message}")
                else:
                    raise Exception(f"Résultat inattendu: {type(r)} — {r}")

            all_item_results.extend(batch_item_results)

            # Sauvegarde batch des IDs traités (success et skipped séparément)
            success_ids = [r.item_id for r in batch_item_results if r.status == "success"]
            skipped_ids = [r.item_id for r in batch_item_results if r.status == "skipped"]

            if success_ids:
                self._log(f"\n--- Sauvegarde batch de {len(success_ids)} ID(s) success siteweb ---")
                save_result = await self.api_client.post(
                    "prix",
                    "process",
                    "save",
                    {
                        "id_categorie":    id_categorie,
                        "type_extraction": self.TYPE_EXTRACTION,
                        "id_cibles":       success_ids,
                        "flag":            1
                    }
                )
                if save_result and not save_result.get("erreur"):
                    nb = save_result.get("nb_insere", len(success_ids))
                    self._log(f"✅ Batch save OK: {nb} ID(s) success enregistré(s)")
                else:
                    self._log(f"⚠️ Batch save: réponse inattendue: {save_result}")
                    raise Exception(f"Batch save: réponse inattendue: {save_result}")

            if skipped_ids:
                self._log(f"--- Sauvegarde batch de {len(skipped_ids)} ID(s) skipped siteweb ---")
                save_result = await self.api_client.post(
                    "prix",
                    "process",
                    "save",
                    {
                        "id_categorie":    id_categorie,
                        "type_extraction": self.TYPE_EXTRACTION,
                        "id_cibles":       skipped_ids,
                        "flag":            0
                    }
                )
                if save_result and not save_result.get("erreur"):
                    nb = save_result.get("nb_insere", len(skipped_ids))
                    self._log(f"✅ Batch save OK: {nb} ID(s) skipped enregistré(s)")
                else:
                    self._log(f"⚠️ Batch save: réponse inattendue: {save_result}")
                    raise Exception(f"Batch save: réponse inattendue: {save_result}")

            if success_ids or skipped_ids:
                # Ajouter les IDs traités au set global pour dédoublonnage des prochaines boucles
                ids_chunks_traites.update(success_ids + skipped_ids)
            else:
                self._log(f"ℹ️ Aucun ID à sauvegarder pour Q1[{idx_q1}]")

        # Fin de toutes les boucles Q1
        elapsed_global = time.time() - start_time_global

        self._log("\n" + "=" * 60)
        self._log("EXTRACTION TERMINÉE")
        self._log(f"Réponses Q1 traitées: {len(reponses_q1)}")
        self._log(f"Total chunks: {total_chunks_global}")
        self._log(f"Succès: {total_success}")
        self._log(f"Skipped: {total_skipped}")
        self._log(f"Erreurs: {total_error}")
        self._log(f"Durée: {elapsed_global:.1f}s")
        self._log("=" * 60)
        
        await self.api_client.post(
            "prix",
            "mail",
            "success",
            {
                "id_categorie": id_categorie,
                "etape": self.ETAPE,
                "tracking_file": self.tracking_file
            }
        )

        return PrixExtractionResult(
            id_categorie=id_categorie,
            total_chunks=total_chunks_global,
            processed=total_success + total_error,
            success=total_success,
            errors=total_error,
            status="completed" if total_error == 0 else "completed_with_errors",
            item_results=all_item_results
        )
    
    async def close(self):
        """Ferme les connexions"""
        await self.api_client.close()
