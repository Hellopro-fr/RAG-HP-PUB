"""
Module principal de traitement: extraction de prix depuis les données devis via LLM.
Traitement parallèle asynchrone avec asyncio.
"""
import re
import time
import logging
import asyncio
import contextvars
from typing import Dict, List, Any, Optional

from app.core.api_client import HelloProAPIClient, GeminiProvider, DeepSeek
from app.core import utils
from app.schemas.prix_extraction import (
    RequestProcessus,
    ItemResult,
    PrixExtractionResult
)
import json
import sys
# from api_recherche_lib.schemas.search import SearchRequestWs, SourcesFiltre
# from api_recherche_lib.core.recherche import search_in_milvus, search_in_milvus_classique


from common_utils.grpc_clients import (
    embedding_client,
    database_client,
    reranking_client,
)
from google.protobuf.json_format import MessageToDict


from app.schemas.produit_prix_payload import ProduitPrixPayload
from app.core.credentials import settings


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class PrixExtractor:
    """Extracteur de prix depuis les données devis via LLM (Gemini/DeepSeek)"""

    _current_item_id = contextvars.ContextVar('current_item_id', default=None)

    # ID du prompt statique - Devis
    PROMPT_ID = settings.PROMPT_ID  # "73"

    # ID process
    ID_PROCESS = "37"

    # Type extraction (1 = devis)
    TYPE_EXTRACTION = "1"

    # Provider LLM forcé (ne dépend pas de la variable d'env globale LLM_PROVIDER)
    LLM_PROVIDER = "gemini"

    # Modèle Gemini par défaut
    GEMINI_MODEL = settings.GEMINI_MODEL_NAME

    # Nombre max de traitements parallèles pour les items
    MAX_PARALLEL_ITEMS = 5

    ETAPE = "8"

    def __init__(self, api_client: Optional[HelloProAPIClient] = None):
        self.api_client = api_client or HelloProAPIClient()
        self.tracking_file = None
        self.prompt_config = None  # Sera chargé lors du premier traitement
        self.info_q1 = ""  # Sera chargé lors du traitement (Question 1)
        self._semaphore = asyncio.Semaphore(self.MAX_PARALLEL_ITEMS)
        # Buffer de logs par item pour éviter l'entrelacement en mode parallèle
        self._item_log_buffers: Dict[str, List[str]] = {}

    def _log(self, message: str):
        """
        Écrit dans le fichier de tracking et les logs.
        En mode parallèle, bufferise les logs par item pour éviter l'entrelacement.
        """
        item_id = self._current_item_id.get(None)

        if item_id is not None:
            prefixed = f"[I-{item_id}] {message}"
            if item_id not in self._item_log_buffers:
                self._item_log_buffers[item_id] = []
            self._item_log_buffers[item_id].append(prefixed)
            logger.info(prefixed)
        else:
            if self.tracking_file:
                utils.write_log(self.tracking_file, message)
            logger.info(message)

    def _flush_item_logs(self, item_id: str):
        """
        Écrit tous les logs bufferisés d'un item d'un seul bloc dans le fichier de tracking.
        Garantit que les logs d'un même item restent groupés et lisibles.
        """
        if item_id in self._item_log_buffers:
            logs = self._item_log_buffers.pop(item_id)
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
                self._log("ERREUR: Impossible de charger le prompt d'extraction de prix devis")
                raise Exception(f"Impossible de charger le prompt ID={self.PROMPT_ID}")
            self._log(f"Prompt chargé (ID: {self.PROMPT_ID})")

    def _build_prompt(self, item_content: str, category_name: str = "") -> str:
        """
        Construit le prompt final en injectant le contenu de l'item dans le template.

        Args:
            item_content: Le contenu de l'item à traiter
            category_name: Le nom de la catégorie (optionnel)

        Returns:
            Le prompt final à envoyer au LLM
        """
        prompt_text = self.prompt_config.get("contenu_prompt", "")

        # Remplacer les placeholders si présents
        # prompt_text = prompt_text.replace("{ITEM_CONTENT}", item_content)
        # prompt_text = prompt_text.replace("{CONTENU}", item_content)
        # prompt_text = prompt_text.replace("{CATEGORIE}", category_name)
        prompt_text = prompt_text.replace("{json_devis_pdf}", item_content)
        prompt_text = prompt_text.replace("{info_q1}", self.info_q1)
        prompt_text = prompt_text.replace("{nom_categorie}", category_name)
        self._log(f"prompt_text ok = {prompt_text}")

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
                origine="prix-extraction-devis",
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
                model="deepseek-chat",
                input_token=input_tokens,
                output_token=output_tokens,
                id_process=self.ID_PROCESS,
                origine="prix-extraction-devis",
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
        item_id: str,
        source_chunk_id: str,
        id_categorie: str,
        category_name: str,
        item_metadata: dict
    ):
        """
        Valide les données extraites par le LLM et construit un ProduitPrixPayload.

        Args:
            prix_data     : Données JSON extraites par le LLM depuis le devis
            item_id       : ID du devis source (stocké en tant que id_lead)
            id_categorie  : ID de la catégorie
            category_name : Nom de la catégorie
            item_metadata : Métadonnées de l'item devis

        Returns:
            ProduitPrixPayload validé, ou None si les données sont insuffisantes.
        """
        if not prix_data or not isinstance(prix_data, dict):
            self._log(f"⚠️ Pas de données prix pour item {item_id}")
            return None
        try:
            payload = ProduitPrixPayload(
                source="devis",
                id_lead=str(prix_data.get("id_lead", "")).strip(),
                id_categorie=id_categorie,
                nom_categorie=category_name,
                # Champs obligatoires attendus dans la réponse LLM
                nom_produit=str(prix_data.get("nom_produit", "")).strip(),
                description_produit=str(prix_data.get("description_produit", "")).strip(),
                valeur_prix=str(prix_data.get("valeur_prix", "")).strip(),
                # Champs optionnels extraits par le LLM
                caracteristique=prix_data.get("caracteristique") or None,
                date_prix=prix_data.get("date_prix") or None,
                id_produit=str(prix_data.get("id_produit", "")) or None,
                source_chunk_id=source_chunk_id,
                domaine=prix_data.get("domaine") or item_metadata.get("domaine") or None,
                id_societe_ia=str(prix_data.get("id_societe_ia", "")) or None,
                valeur_reponse_q1=prix_data.get("valeur_reponse_q1") or None,
                prix_original=str(prix_data.get("prix_original", "")).strip() or None,
                structure_prix=prix_data.get("structure_prix") or None,
                unite=prix_data.get("unite") or None,
                devise=prix_data.get("devise") or None,
                taxe=prix_data.get("taxe") or None,
                type_transaction=prix_data.get("type_transaction") or None,
                perimetre=prix_data.get("perimetre") or None,
                id_fournisseur=str(prix_data.get("id_fournisseur", "")) or None,
                fournisseur=prix_data.get("fournisseur") or item_metadata.get("fournisseur") or None,
            )
            return payload
        except Exception as e:
            self._log(f"⚠️ Validation échouée pour item {item_id}: {e}")
            return None

    async def _process_single_item(
        self,
        item: Dict[str, Any],
        item_index: int,
        total_items: int,
        id_categorie: str,
        category_name: str = ""
    ) -> ItemResult:
        """
        Traite un seul item devis: LLM call + validation payload.

        En cas d'erreur (LLM, JSON, validation), une exception est levée
        afin d'interrompre immédiatement le traitement de la catégorie.

        Args:
            item         : L'objet à traiter
            item_index   : Index de l'item (pour les logs)
            total_items  : Nombre total d'items
            id_categorie : ID de la catégorie
            category_name: Nom de la catégorie

        Returns:
            ItemResult avec status="success" et prix_data validé.

        Raises:
            Exception si le LLM échoue, si le JSON est illisible ou si la
            validation du payload échoue — l'appel à asyncio.gather propagera
            l'exception, stoppant le traitement de la catégorie.
        """
        async with self._semaphore:
            item_id = str(item.get("id", item.get("item_id", f"item_{item_index}")))
            item_content = json.dumps(item, ensure_ascii=False)
            source_chunk_id = str(item.get("source_chunk_id", item.get("id", f"item_{item_index}")))

            # Activer le contexte item pour bufferiser les logs
            token = self._current_item_id.set(item_id)

            self._log(f"[{item_index + 1}/{total_items}] Traitement item {item_id}")

            # Pré-filtre : si le texte ne contient aucune mention de prix, skip sans appeler le LLM
            # if not re.search(r'€|\d+\s*(euros?|€|EUR)|\d[\d\s.,]*\s*H\.?T\.?|\d[\d\s.,]*\s*TTC|prix\s+de\s+\d+', item_content, re.IGNORECASE):
            #     self._log(f"[{item_index + 1}/{total_items}] ⏭️ Item {item_id} — aucune mention de prix (€/euro/EUR) → skip")
            #     self._flush_item_logs(item_id)
            #     self._current_item_id.reset(token)
            #     return ItemResult(
            #         item_id=item_id,
            #         source="devis",
            #         content=item_content,
            #         prix_data=None,
            #         status="skipped"
            #     )

            # 1. Construire le prompt avec le contenu de l'item
            prompt_text = self._build_prompt(item_content, category_name)
            # 2. Appeler le LLM
            result = await self._call_llm(prompt_text, id_categorie)

            # Vérifier si c'est une erreur (format Gemini avec "code")
            if "code" in result:
                error_msg = str(result.get("error", "Erreur LLM inconnue"))
                self._log(f"[{item_index + 1}/{total_items}] ❌ Erreur LLM item {item_id}: {error_msg}")
                self._flush_item_logs(item_id)
                self._current_item_id.reset(token)
                raise Exception(f"Erreur LLM pour item {item_id}: {error_msg}")

            # 3. Extraire la réponse
            response_text = result.get("message", "")
            self._log(f"[{item_index + 1}/{total_items}] Réponse LLM reçue ({len(response_text)} chars)")
            self._log(f"response_text = {response_text}")

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
                self._flush_item_logs(item_id)
                self._current_item_id.reset(token)
                raise Exception(f"Impossible d'extraire le JSON de la réponse LLM pour item {item_id}")

            # Liste vide = le LLM n'a trouvé aucun prix dans cet item → skip
            if isinstance(prix_data_raw, list) and len(prix_data_raw) == 0:
                self._log(f"[{item_index + 1}/{total_items}] ⏭️ Item {item_id} — aucun prix trouvé par le LLM")
                self._flush_item_logs(item_id)
                self._current_item_id.reset(token)
                return ItemResult(
                    item_id=item_id,
                    source="devis",
                    content=item_content,
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
                    item_id=item_id,
                    source_chunk_id=source_chunk_id,
                    id_categorie=id_categorie,
                    category_name=category_name,
                    item_metadata=item.get("metadata", {})
                )
                if payload is None:
                    self._flush_item_logs(item_id)
                    self._current_item_id.reset(token)
                    raise Exception(
                        f"Validation du payload échouée (champs obligatoires manquants) : "
                        f"Catégorie {id_categorie} - Item {item_id} - Data : {single_prix}"
                    )
                payloads.append(payload)

            prix_data = [p.dict() for p in payloads]

            self._log(f"[{item_index + 1}/{total_items}] ✅ Item {item_id} validé")
            self._flush_item_logs(item_id)
            self._current_item_id.reset(token)
            return ItemResult(
                item_id=item_id,
                source="devis",
                content=item_content,
                prix_data=prix_data,
                status="success"
            )

    async def _fetch_items(self, id_categorie: str, category_name: str) -> List[Dict[str, Any]]:
        """
        Récupère les items à traiter pour cette catégorie, groupés par id_demande et metadata.id.

        Returns:
            Liste d'objets groupés par id_demande, puis par metadata.id, contenant:
            - 'id_demande': identifiant de la demande
            - 'metadata_id': identifiant du document source (metadata.id)
            - 'total_chunks': nombre total de chunks pour ce document
            - 'chunks': liste des chunks avec leur contenu et métadonnées

        Structure:
            [
                {
                    "id_demande": "3737139",
                    "metadata_id": "463593687250988350",
                    "total_chunks": 4,
                    "chunks": [...]
                },
                ...
            ]
        """
        # Valeurs par défaut depuis les settings
        # self._log(f"Prompt Recherche de prix: '{self.prompt_config}'")
        
        if not self.prompt_config:
            logger.warning(f"Prompt ID {self.PROMPT_ID} non trouvé, "
                        "utilisation d'une chaîne vide")

        source_name = settings.MILVUS_SOURCE
        
        # Construire le filtre Milvus
        final_filter_expr = f"id_categorie in ['{id_categorie}'] and page_type in ['{settings.MILVUS_PAGE_TYPE}']"
        
        # logger.info(f"Filtre Milvus: {final_filter_expr}")
        self._log(f"Filtre Milvus: {final_filter_expr}")

        source_results = await database_client.classic_search_vector(
            collection    = source_name,
            filter_expr   = final_filter_expr,
            k = settings.MILVUS_TOP_K
        )
        # self._log(f"source_results: {source_results}")
        
        # Convertir les résultats en dictionnaires
        all_results_list = [MessageToDict(res) for res in source_results]
        # self._log(f"all_results_list: {json.dumps(all_results_list)}")
        
        # Extraction de la liste pjechanges
        # pjechanges = all_results_list.get("results", {}).get("matches", {}).get("pjechanges", [])
        grouped = {}

        for item in all_results_list:
            outer_id = item.get("id")
            metadata = item.get("metadata", {})
            entity = metadata.get("entity", {})
            
            fichier_source = entity.get("fichier_source")
            chunk_number = entity.get("chunk_number")
            chunk_id = entity.get("chunk_id")
            text = entity.get("text", "")

            if not fichier_source:
                logger.warning(f"Élément ignoré: fichier_source vide pour id={outer_id}")
                continue

            if fichier_source not in grouped:
                grouped[fichier_source] = {
                    "fields": entity.copy(),
                    "items_to_sort": []
                }
            
            # On stocke les infos nécessaires dans un dictionnaire simple
            grouped[fichier_source]["items_to_sort"].append({
                "chunk_number": chunk_number,
                "chunk_id": str(chunk_id),
                "text": text,
                "outer_id": str(outer_id)
            })

        final_result = []

        for fichier_source, content in grouped.items():
            # 2. Trier par chunk_number pour respecter l'ordre (1, 2, 3...)
            sorted_items = sorted(content["items_to_sort"], key=lambda x: int(x["chunk_number"]) if x["chunk_number"] else 0)
            
            # 3. Fusion du texte avec gestion de l'overlap (chevauchement)
            full_text = ""
            for item in sorted_items:
                # CORRECTION ICI : on utilise item["text"] directement
                current = item["text"] 

                if not full_text:
                    full_text = current
                else:
                    # On cherche le plus grand overlap entre la fin de full_text et le début de current
                    # On nettoie les espaces pour la comparaison
                    s_full = full_text.rstrip()
                    s_current = current.lstrip()
                    
                    max_o = min(len(s_full), len(s_current), 150) # limite de recherche TODO: à voir comment le transformer en 100 chunks
                    overlap_len = 0
                    
                    for o in range(max_o, 0, -1):
                        if s_full.endswith(s_current[:o]):
                            overlap_len = o
                            break
                    
                    if overlap_len > 0:
                        # On ajoute la suite du texte après l'overlap
                        full_text = s_full + s_current[overlap_len:]
                    else:
                        # Pas d'overlap, on ajoute un espace si nécessaire
                        full_text = s_full + " " + s_current

            # 4. Concaténation des IDs et numéros de chunks
            merged_ids = ",".join([i["outer_id"] for i in sorted_items])
            merged_chunk_numbers = ",".join([str(int(i["chunk_number"])) if i["chunk_number"] else "0" for i in sorted_items])
            merged_chunk_ids = ",".join([i["chunk_id"] for i in sorted_items])
            
            # 5. Mise à jour de l'objet final
            item_data = content["fields"]
            item_data["text"] = full_text.strip()
            item_data["id"] = merged_ids
            item_data["chunk_number"] = merged_chunk_numbers
            item_data["chunk_id"] = merged_chunk_ids
            
            final_result.append(item_data)

        return final_result

        # TODO: Implémenter la récupération des données devis ici.
        # Exemple: appel API, requête base de données, etc.
        # raise NotImplementedError(
        #     "La logique d'extraction des données devis n'est pas encore implémentée. "
        #     "Veuillez implémenter _fetch_items() dans prix-extraction-devis/app/core/prix_extractor.py"
        # )

    async def extract_prix_for_category(
        self,
        request: RequestProcessus
    ) -> PrixExtractionResult:
        """
        Processus principal: extraction de prix devis pour une catégorie.

        1. Charge le prompt (ID=73)
        2. [TODO] Récupère les items à traiter via _fetch_items()
        3. Traite chaque item en parallèle via asyncio
        4. Pour chaque item: LLM call → stockage API
        5. Retourne les résultats individuels pour que le consumer publie vers prix-normalisation

        Args:
            request: RequestProcessus avec id_categorie et is_reset

        Returns:
            PrixExtractionResult avec le bilan du traitement et les chunk_results individuels
        """
        id_categorie = request.id_categorie

        # Initialiser le fichier de tracking
        self.tracking_file = utils.get_tracking_filepath(id_categorie, prefix="prix-extraction-devis")

        self._log("=" * 60)
        self._log("EXTRACTION PRIX DEVIS")
        self._log(f"Catégorie: {id_categorie}")
        self._log(f"Reset: {request.is_reset}")
        self._log(f"Provider LLM: {self.LLM_PROVIDER}")
        self._log(f"Model LLM: {self.GEMINI_MODEL}")
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

        # Récupérer les items à traiter
        # TODO: _fetch_items() doit être implémentée - voir la méthode pour les détails
        self._log("\n--- Récupération des items devis (TODO) ---")
        items = await self._fetch_items(id_categorie, category_name)

        if not items:
            self._log("⚠️ Aucun item à traiter")
            return PrixExtractionResult(
                id_categorie=id_categorie,
                total_chunks=0,
                processed=0,
                success=0,
                errors=0,
                status="completed"
            )

        # Récupérer les ids items déjà traités
        self._log("Récupération des ids items déjà traités...")
        ids_items_traites = await self.api_client.post(
            "prix",
            "process",
            "get",
            {"id_categorie": id_categorie, "type_extraction": self.TYPE_EXTRACTION}
        )

        # Filtrer les items déjà traités
        if ids_items_traites:
            items_filtres = []
            for item in items:
                # tronqué à 255 chars si nécessaire seulement pour la verification
                item_id = item["id"][:255]
                if item_id in ids_items_traites:
                    self._log(f"Item {item_id} déjà traité")
                else:
                    items_filtres.append(item)
            items = items_filtres

        total_items = len(items)
        self._log(f"📊 {total_items} items à traiter")
        self._log(f"Items: {json.dumps(items)}")
        # raise Exception("Test")
        # return None

        # Traitement parallèle de tous les items
        self._log(f"\n--- Traitement parallèle ({self.MAX_PARALLEL_ITEMS} max simultanés) ---")
        start_time = time.time()

        tasks = [
            self._process_single_item(
                item=item,
                item_index=i,
                total_items=total_items,
                id_categorie=id_categorie,
                category_name=category_name
            )
            for i, item in enumerate(items)
        ]
        self._log(f"tasks: {tasks}")
        # raise Exception("Test")
        # return None

        results: List[ItemResult] = await asyncio.gather(*tasks, return_exceptions=True)

        # Flush tous les logs bufferisés des items (écriture groupée par item)
        for item_id_key in list(self._item_log_buffers.keys()):
            self._flush_item_logs(item_id_key)

        elapsed = time.time() - start_time

        # Collecter et compter les résultats — toute exception lève immédiatement
        success_count = 0
        skipped_count = 0
        error_count = 0
        item_results: List[ItemResult] = []
        for r in results:
            if isinstance(r, Exception):
                # Propager l'exception : arrêt immédiat du traitement de la catégorie
                self._log(f"❌ Exception critique: {r}")
                raise r
            elif isinstance(r, ItemResult):
                item_results.append(r)
                if r.status == "success":
                    success_count += 1
                elif r.status == "skipped":
                    skipped_count += 1
                else:
                    error_count += 1
                    self._log(f"❌ Item en erreur: {r.item_id} — {r.error_message}")
                    raise Exception(f"Item {r.item_id} en erreur: {r.error_message}")
            else:
                raise Exception(f"Résultat inattendu: {type(r)} — {r}")

        # Sauvegarde batch des IDs traités (success et skipped séparément)
        success_ids = [r.item_id for r in item_results if r.status == "success"]
        skipped_ids = [r.item_id for r in item_results if r.status == "skipped"]

        self._log(f"\n--- TYPE_EXTRACTION {self.TYPE_EXTRACTION} ---")

        if success_ids:
            self._log(f"\n--- Sauvegarde batch de {len(success_ids)} ID(s) success devis ---")
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
                self._log(f"✅ Batch save OK: {nb} ID(s) success enregistré(s) dans extraction_prix_ia")
            else:
                self._log(f"⚠️ Batch save: réponse inattendue: {save_result}")
                raise Exception(f"Batch save: réponse inattendue: {save_result}")

        if skipped_ids:
            self._log(f"--- Sauvegarde batch de {len(skipped_ids)} ID(s) skipped devis ---")
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

        if not success_ids and not skipped_ids:
            self._log("ℹ️ Aucun ID devis à sauvegarder")

        self._log("\n" + "=" * 60)
        self._log("EXTRACTION TERMINÉE")
        self._log(f"Total items: {total_items}")
        self._log(f"Succès: {success_count}")
        self._log(f"Skipped: {skipped_count}")
        self._log(f"Erreurs: {error_count}")
        self._log(f"Durée: {elapsed:.1f}s")
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
            total_chunks=total_items,
            processed=success_count + error_count,
            success=success_count,
            errors=error_count,
            status="completed" if error_count == 0 else "completed_with_errors",
            item_results=item_results
        )

    async def close(self):
        """Ferme les connexions"""
        await self.api_client.close()