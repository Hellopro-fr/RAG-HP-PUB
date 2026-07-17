"""
Module principal de traitement: extraction de prix depuis les données message via LLM.
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
from app.schemas.produit_prix_payload import ProduitPrixPayload
from app.core.credentials import settings


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class PrixExtractor:
    """Extracteur de prix depuis les données message via LLM (Gemini/DeepSeek)"""

    _current_item_id = contextvars.ContextVar('current_item_id', default=None)

    # ID du prompt statique - Message
    PROMPT_ID = settings.PROMPT_ID  # "142"

    # ID process
    ID_PROCESS = "37"

    # Type extraction (2 = message)
    TYPE_EXTRACTION = "2"

    # Provider LLM forcé (ne dépend pas de la variable d'env globale LLM_PROVIDER)
    LLM_PROVIDER = "gemini"

    # Modèle Gemini par défaut
    GEMINI_MODEL = settings.GEMINI_MODEL_NAME

    # Nombre max de traitements parallèles pour les items
    MAX_PARALLEL_ITEMS = 5

    ETAPE = "9"

    def __init__(self, api_client: Optional[HelloProAPIClient] = None, on_batch_publish=None):
        self.api_client = api_client or HelloProAPIClient()
        self.tracking_file = None
        self.prompt_config = None  # Sera chargé lors du premier traitement
        self.info_q1 = ""  # Sera chargé lors du traitement (Question 1)
        self._semaphore = asyncio.Semaphore(self.MAX_PARALLEL_ITEMS)
        # Callback pour publier les résultats après chaque batch
        self._on_batch_publish = on_batch_publish
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
                self._log("ERREUR: Impossible de charger le prompt d'extraction de prix message")
                raise Exception(f"Impossible de charger le prompt ID={self.PROMPT_ID}")
            self._log(f"Prompt chargé (ID: {self.PROMPT_ID})")

    def _build_prompt(self, item_content: str, category_name: str = "") -> str:
        """
        Construit le prompt final en injectant le contenu de l'item dans le template.

        Args:
            item_content: Le contenu JSON du message à traiter
            category_name: Le nom de la catégorie (optionnel)

        Returns:
            Le prompt final à envoyer au LLM
        """
        prompt_text = self.prompt_config.get("contenu_prompt", "")

        # Remplacer les placeholders si présents
        prompt_text = prompt_text.replace("{json_message}", item_content)
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
                origine="prix-extraction-message",
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
                origine="prix-extraction-message",
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
        id_categorie: str,
        category_name: str,
        item_metadata: dict
    ):
        """
        Valide les données extraites par le LLM et construit un ProduitPrixPayload.

        Args:
            prix_data     : Données JSON extraites par le LLM depuis le message
            item_id       : ID du message source (stocké en tant que id_lead)
            id_categorie  : ID de la catégorie
            category_name : Nom de la catégorie
            item_metadata : Métadonnées de l'item message

        Returns:
            ProduitPrixPayload validé, ou None si les données sont insuffisantes.
        """
        if not prix_data or not isinstance(prix_data, dict):
            self._log(f"⚠️ Pas de données prix pour item {item_id}")
            return None
        try:
            payload = ProduitPrixPayload(
                source="message",
                id_lead=item_id,
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
                source_chunk_id=prix_data.get("source_chunk_id") or None,
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
                id_fournisseur=prix_data.get("id_fournisseur") or item_metadata.get("id_fournisseur") or None,
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
        Traite un seul item message: LLM call + validation payload.

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
            validation du payload échoue.
        """
        async with self._semaphore:
            item_id = str(item.get("id_lead", item.get("id", f"item_{item_index}")))
            #Ajouter id_fournisseur sur id_lead si n'est pas vide
            if item.get("id_fournisseur") and item.get("id_fournisseur") != "" and item.get("id_fournisseur") is not None:
                item_id = f"{item_id}_{item.get('id_fournisseur')}"
            item_content = utils.to_json_string(item)

            # Activer le contexte item pour bufferiser les logs
            token = self._current_item_id.set(item_id)

            self._log(f"[{item_index + 1}/{total_items}] Traitement item {item_id}")
            self._log(f"[{item_index + 1}/{total_items}] item_content: {item_content}")

            # Pré-filtre : si le texte ne contient aucune mention de prix, skip sans appeler le LLM
            if not re.search(r'€|\d+\s*(euros?|€|EUR)|\d[\d\s.,]*\s*H\.?T\.?|\d[\d\s.,]*\s*TTC|prix\s+de\s+\d+', item_content, re.IGNORECASE):
                self._log(f"[{item_index + 1}/{total_items}] ⏭️ Item {item_id} — aucune mention de prix (€/euro/EUR) → skip")
                self._flush_item_logs(item_id)
                self._current_item_id.reset(token)
                return ItemResult(
                    item_id=item_id,
                    source="message",
                    content=item_content,
                    prix_data=None,
                    status="skipped"
                )

            # 1. Construire le prompt avec le contenu JSON du message
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
            self._log(f"[{item_index + 1}/{total_items}] Réponse LLM reçue ({response_text})")

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
                    source="message",
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
                    id_categorie=id_categorie,
                    category_name=category_name,
                    item_metadata=item.get("metadata", {})
                )
                if payload is None:
                    self._flush_item_logs(item_id)
                    self._current_item_id.reset(token)
                    raise ValueError(
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
                source="message",
                content=item_content,
                prix_data=prix_data,
                status="success"
            )

    async def _fetch_items(self, id_categorie: str, category_name: str) -> List[Dict[str, Any]]:
        """
        Récupère les messages à traiter pour cette catégorie via l'API.

        Returns:
            Liste d'objets message, chacun contenant:
            - 'id': id_lead (identifiant unique)
            - et les données complètes du message (corps_messages, info_lead, etc.)
        """
        data_messages = await self.api_client.post(
            "prix",
            "messages",
            "get",
            {"id_categorie": id_categorie}
        )
        messages = data_messages.get("messages", [])
        if not messages:
            return []

        return messages

    async def extract_prix_for_category(
        self,
        request: RequestProcessus
    ) -> PrixExtractionResult:
        """
        Processus principal: extraction de prix message pour une catégorie.

        1. Charge le prompt (ID=142)
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
        self.tracking_file = utils.get_tracking_filepath(id_categorie, prefix="prix-extraction-message")

        self._log("=" * 60)
        self._log("EXTRACTION PRIX MESSAGE")
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

        # Récupérer les items message à traiter
        self._log("\n--- Récupération des messages ---")
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

        total_items = len(items)
        self._log(f"📊 {total_items} items à traiter")

        BATCH_SIZE = 50
        start_time = time.time()
        success_count = 0
        skipped_count = 0
        error_count = 0
        all_item_results: List[ItemResult] = []

        # Traitement par lot de 50 items
        for batch_start in range(0, total_items, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, total_items)
            batch_items = items[batch_start:batch_end]
            batch_num = (batch_start // BATCH_SIZE) + 1
            total_batches = (total_items + BATCH_SIZE - 1) // BATCH_SIZE

            self._log(f"\n--- Lot [{batch_num}/{total_batches}] items {batch_start + 1}-{batch_end}/{total_items} ({self.MAX_PARALLEL_ITEMS} max simultanés) ---")

            tasks = [
                self._process_single_item(
                    item=item,
                    item_index=batch_start + i,
                    total_items=total_items,
                    id_categorie=id_categorie,
                    category_name=category_name
                )
                for i, item in enumerate(batch_items)
            ]

            results: List[ItemResult] = await asyncio.gather(*tasks, return_exceptions=True)

            # Flush tous les logs bufferisés des items
            for item_id_key in list(self._item_log_buffers.keys()):
                self._flush_item_logs(item_id_key)

            # Collecter les résultats du lot
            batch_item_results: List[ItemResult] = []
            for r in results:
                if isinstance(r, Exception):
                    self._log(f"❌ Exception critique: {r}")
                    raise r
                elif isinstance(r, ItemResult):
                    batch_item_results.append(r)
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

            all_item_results.extend(batch_item_results)

            # Sauvegarde batch des IDs traités (success et skipped séparément)
            success_ids = [r.item_id for r in batch_item_results if r.status == "success"]
            skipped_ids = [r.item_id for r in batch_item_results if r.status == "skipped"]

            if success_ids:
                self._log(f"--- Sauvegarde batch de {len(success_ids)} ID(s) success message ---")
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
                self._log(f"--- Sauvegarde batch de {len(skipped_ids)} ID(s) skipped message ---")
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
                # Publier les résultats du batch vers embedding
                if self._on_batch_publish:
                    published = await self._on_batch_publish(batch_item_results, id_categorie)
                    self._log(f"📤 {published} message(s) publié(s) vers embedding")
            else:
                self._log(f"ℹ️ Aucun ID à sauvegarder pour lot [{batch_num}/{total_batches}]")

        elapsed = time.time() - start_time
        item_results = all_item_results

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
