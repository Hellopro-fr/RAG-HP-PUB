"""
Module principal de traitement: extraction de prix depuis les données message via LLM.
Traitement parallèle asynchrone avec asyncio.
"""
import time
import logging
import asyncio
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

    # ID du prompt statique - Message
    PROMPT_ID = settings.PROMPT_ID  # "142"

    # Modèle Gemini par défaut
    GEMINI_MODEL = settings.GEMINI_MODEL_NAME

    # Nombre max de traitements parallèles pour les items
    MAX_PARALLEL_ITEMS = 5

    ETAPE = "9"

    def __init__(self, api_client: Optional[HelloProAPIClient] = None):
        self.api_client = api_client or HelloProAPIClient()
        self.tracking_file = None
        self.prompt_config = None  # Sera chargé lors du premier traitement
        self._semaphore = asyncio.Semaphore(self.MAX_PARALLEL_ITEMS)

    def _log(self, message: str):
        """Écrit dans le fichier de tracking et les logs"""
        if self.tracking_file:
            utils.write_log(self.tracking_file, message)
        logger.info(message)

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
            item_content: Le contenu de l'item à traiter
            category_name: Le nom de la catégorie (optionnel)

        Returns:
            Le prompt final à envoyer au LLM
        """
        prompt_text = self.prompt_config.get("contenu_prompt", "")

        # Remplacer les placeholders si présents
        prompt_text = prompt_text.replace("{ITEM_CONTENT}", item_content)
        prompt_text = prompt_text.replace("{CONTENU}", item_content)
        prompt_text = prompt_text.replace("{CATEGORIE}", category_name)

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
        provider = settings.LLM_PROVIDER.lower()

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
                input_token=usage_metadata.get("prompt_token_count", 0),
                output_token=usage_metadata.get("candidates_token_count", 0),
                id_process=id_categorie,
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
                model="deepseek-chat",
                input_token=input_tokens,
                output_token=output_tokens,
                id_process=id_categorie,
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
            item_id = str(item.get("id", item.get("item_id", f"item_{item_index}")))
            item_content = str(item.get("content", item.get("text", item.get("data", ""))))

            self._log(f"[{item_index + 1}/{total_items}] Traitement item {item_id}")

            # 1. Construire le prompt avec le contenu de l'item
            prompt_text = self._build_prompt(item_content, category_name)

            # 2. Appeler le LLM
            result = await self._call_llm(prompt_text, id_categorie)

            # Vérifier si c'est une erreur (format Gemini avec "code")
            if "code" in result:
                error_msg = str(result.get("error", "Erreur LLM inconnue"))
                self._log(f"[{item_index + 1}/{total_items}] ❌ Erreur LLM item {item_id}: {error_msg}")
                raise Exception(f"Erreur LLM pour item {item_id}: {error_msg}")

            # 3. Extraire la réponse
            response_text = result.get("message", "")
            self._log(f"[{item_index + 1}/{total_items}] Réponse LLM reçue ({len(response_text)} chars)")

            # Tenter d'extraire le JSON de la réponse
            prix_data_raw = utils.extract_json_from_text(response_text)
            if not prix_data_raw:
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
                raise Exception(f"Impossible d'extraire le JSON de la réponse LLM pour item {item_id}")

            # 3b. Valider et construire le payload structuré
            payload = self._validate_and_build_payload(
                prix_data=prix_data_raw,
                item_id=item_id,
                id_categorie=id_categorie,
                category_name=category_name,
                item_metadata=item.get("metadata", {})
            )
            if payload is None:
                raise ValueError(
                    f"Validation du payload échouée (champs obligatoires manquants) : "
                    f"Catégorie {id_categorie} - Item {item_id} - Data : {prix_data_raw}"
                )

            prix_data = payload.dict()

            self._log(f"[{item_index + 1}/{total_items}] ✅ Item {item_id} validé")
            return ItemResult(
                item_id=item_id,
                source="message",
                content=item_content,
                prix_data=prix_data,
                status="success"
            )

    async def _fetch_items(self, id_categorie: str, category_name: str) -> List[Dict[str, Any]]:
        """
        Récupère les items à traiter pour cette catégorie.

        Returns:
            Liste d'objets à traiter, chacun contenant au minimum:
            - 'id': identifiant unique de l'item
            - 'content': le contenu textuel à envoyer au LLM
            - 'metadata': (optionnel) données supplémentaires

        TODO: Implémenter la logique d'extraction des données message.
              Cette méthode doit retourner une liste de dictionnaires représentant
              les items à traiter. Exemple:
              [
                  {"id": "123", "content": "Texte du message...", "metadata": {...}},
                  {"id": "456", "content": "Autre message...", "metadata": {...}},
                  ...
              ]
        """
        # TODO: Implémenter la récupération des données message ici.
        # Exemple: appel API, requête base de données, etc.
        raise NotImplementedError(
            "La logique d'extraction des données message n'est pas encore implémentée. "
            "Veuillez implémenter _fetch_items() dans prix-extraction-message/app/core/prix_extractor.py"
        )

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
        self._log(f"Provider LLM: {settings.LLM_PROVIDER}")
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
                "extraction_message",
                "reset",
                {"id_categorie": id_categorie}
            )

        # Charger le prompt
        await self._load_prompt(id_categorie)

        # Récupérer les items à traiter
        # TODO: _fetch_items() doit être implémentée - voir la méthode pour les détails
        self._log("\n--- Récupération des items message (TODO) ---")
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

        results: List[ItemResult] = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed = time.time() - start_time

        # Collecter et compter les résultats — toute exception lève immédiatement
        success_count = 0
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
                else:
                    error_count += 1
                    self._log(f"❌ Item en erreur: {r.item_id} — {r.error_message}")
                    raise Exception(f"Item {r.item_id} en erreur: {r.error_message}")
            else:
                raise Exception(f"Résultat inattendu: {type(r)} — {r}")

        # Sauvegarde batch des IDs traités avec succès
        # type_extraction = 1 pour les messages
        successful_ids = [r.item_id for r in item_results if r.status == "success"]

        if successful_ids:
            self._log(f"\n--- Sauvegarde batch de {len(successful_ids)} ID(s) message ---")
            save_result = await self.api_client.post(
                "prix",
                "process",
                "save",
                {
                    "id_categorie":    id_categorie,
                    "type_extraction": "1",           # 1 = message
                    "id_cibles":       successful_ids  # liste d'IDs (batch)
                }
            )
            if save_result and not save_result.get("erreur"):
                nb = save_result.get("nb_insere", len(successful_ids))
                self._log(f"✅ Batch save OK: {nb} ID(s) enregistré(s) dans extraction_prix_ia")
            else:
                self._log(f"⚠️ Batch save: réponse inattendue: {save_result}")
                raise Exception(f"Batch save: réponse inattendue: {save_result}")
        else:
            self._log("ℹ️ Aucun ID message à sauvegarder (aucun succès)")

        self._log("\n" + "=" * 60)
        self._log("EXTRACTION TERMINÉE")
        self._log(f"Total items: {total_items}")
        self._log(f"Succès: {success_count}")
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
