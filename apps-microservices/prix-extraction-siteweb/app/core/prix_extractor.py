"""
Module principal de traitement: extraction de prix depuis les chunks Milvus via LLM.
Traitement parallèle asynchrone avec asyncio.
"""
import time
import logging
import asyncio
from typing import Dict, List, Any, Optional

from app.core.api_client import HelloProAPIClient, GeminiProvider, DeepSeek
from app.core.search import call_search_api_async
from app.core import utils
from app.schemas.prix_extraction import (
    RequestProcessus,
    ItemResult,
    PrixExtractionResult
)
from app.core.credentials import settings


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class PrixExtractor:
    """Extracteur de prix via RAG (Milvus) + LLM (Gemini/DeepSeek)"""
    
    # ID du prompt statique
    PROMPT_ID = settings.PROMPT_ID  # "140"
    
    # Modèle Gemini par défaut
    GEMINI_MODEL = settings.GEMINI_MODEL_NAME
    
    # Nombre max de traitements parallèles pour les chunks
    MAX_PARALLEL_CHUNKS = 5
    
    def __init__(self, api_client: Optional[HelloProAPIClient] = None):
        self.api_client = api_client or HelloProAPIClient()
        self.tracking_file = None
        self.prompt_config = None  # Sera chargé lors du premier traitement
        self._semaphore = asyncio.Semaphore(self.MAX_PARALLEL_CHUNKS)

    
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
                self._log("ERREUR: Impossible de charger le prompt d'extraction de prix")
                raise Exception(f"Impossible de charger le prompt ID={self.PROMPT_ID}")
            self._log(f"Prompt chargé (ID: {self.PROMPT_ID})")

    def _build_prompt(self, chunk_content: str, category_name: str = "") -> str:
        """
        Construit le prompt final en injectant le contenu du chunk dans le template.
        
        Args:
            chunk_content: Le contenu du chunk Milvus
            category_name: Le nom de la catégorie (optionnel)
            
        Returns:
            Le prompt final à envoyer au LLM
        """
        prompt_text = self.prompt_config.get("contenu_prompt", "")
        
        # Remplacer les placeholders si présents
        prompt_text = prompt_text.replace("{CHUNK_CONTENT}", chunk_content)
        prompt_text = prompt_text.replace("{CONTENU}", chunk_content)
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
                model="deepseek-chat",
                input_token=input_tokens,
                output_token=output_tokens,
                id_process=id_categorie,
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

    async def _process_single_chunk(
        self, 
        chunk: Dict[str, Any], 
        chunk_index: int,
        total_chunks: int,
        id_categorie: str,
        category_name: str = ""
    ) -> ItemResult:
        """
        Traite un seul chunk Milvus: LLM call + stockage.
        
        Args:
            chunk: Les données du chunk Milvus
            chunk_index: Index du chunk (pour les logs)
            total_chunks: Nombre total de chunks (pour les logs)
            id_categorie: ID de la catégorie
            category_name: Nom de la catégorie
            
        Returns:
            ItemResult avec le résultat du traitement
        """
        async with self._semaphore:
            chunk_id = str(chunk.get("id", chunk.get("chunk_id", f"unknown_{chunk_index}")))
            chunk_content = chunk.get("content", chunk.get("text", chunk.get("document", "")))
            chunk_metadata = chunk.get("metadata", {})
            
            self._log(f"[{chunk_index + 1}/{total_chunks}] Traitement chunk {chunk_id}")
            
            try:
                # 1. Construire le prompt avec le contenu du chunk
                prompt_text = self._build_prompt(chunk_content, category_name)
                
                # 2. Appeler le LLM
                result = await self._call_llm(prompt_text, id_categorie)
                
                # Vérifier si c'est une erreur (format Gemini avec "code")
                if "code" in result:
                    self._log(f"[{chunk_index + 1}/{total_chunks}] ❌ Erreur LLM chunk {chunk_id}: {result.get('error')}")
                    return ItemResult(
                        item_id=chunk_id,
                        source=settings.MILVUS_SOURCE,
                        content=chunk_content,
                        status="error",
                        error_message=str(result.get("error", "Erreur LLM inconnue"))
                    )
                
                # 3. Extraire la réponse
                response_text = result.get("message", "")
                self._log(f"[{chunk_index + 1}/{total_chunks}] Réponse LLM reçue ({len(response_text)} chars)")
                
                # Tenter d'extraire le JSON de la réponse
                prix_data = utils.extract_json_from_text(response_text)
                
                # 4. Stocker le résultat via l'API HelloPro (chunk ID + résultat du prompt)
                save_data = {
                    "id_categorie": id_categorie,
                    "chunk_id": chunk_id,
                    "source": settings.MILVUS_SOURCE,
                    "llm_response": response_text,
                    "prix_data": prix_data,
                    "chunk_metadata": chunk_metadata
                }
                
                save_result = await self.api_client.post(
                    "prix",
                    "extraction_siteweb",
                    "save",
                    save_data
                )

                
                if save_result:
                    self._log(f"[{chunk_index + 1}/{total_chunks}] ✅ Résultat sauvegardé pour chunk {chunk_id}")
                else:
                    self._log(f"[{chunk_index + 1}/{total_chunks}] ⚠️ Échec sauvegarde chunk {chunk_id}")
                

                
                return ItemResult(
                    item_id=chunk_id,
                    source=settings.MILVUS_SOURCE,
                    content=chunk_content,
                    prix_data=prix_data,
                    status="success"
                )
                
            except Exception as e:
                self._log(f"[{chunk_index + 1}/{total_chunks}] ❌ Exception chunk {chunk_id}: {e}")
                return ItemResult(
                    item_id=chunk_id,
                    source=settings.MILVUS_SOURCE,
                    content=chunk_content if chunk_content else "",
                    status="error",
                    error_message=str(e)
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
        self._log(f"Provider LLM: {settings.LLM_PROVIDER}")
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
                "extraction_siteweb",
                "reset",
                {"id_categorie": id_categorie}
            )
        
        # Charger le prompt
        await self._load_prompt(id_categorie)
        
        # Recherche RAG dans Milvus
        self._log(f"\n--- Recherche Milvus (source={settings.MILVUS_SOURCE}, top_k={settings.MILVUS_TOP_K}) ---")
        chunks = await call_search_api_async(
            prompt=category_name,
            num_results=settings.MILVUS_TOP_K,
            source=settings.MILVUS_SOURCE
        )
        
        if not chunks:
            self._log("⚠️ Aucun résultat de recherche Milvus")
            return PrixExtractionResult(
                id_categorie=id_categorie,
                total_chunks=0,
                processed=0,
                success=0,
                errors=0,
                status="completed"
            )
        
        total_chunks = len(chunks)
        self._log(f"📊 {total_chunks} chunks trouvés dans Milvus")
        
        # Traitement parallèle de tous les chunks
        self._log(f"\n--- Traitement parallèle ({self.MAX_PARALLEL_CHUNKS} max simultanés) ---")
        start_time = time.time()
        
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
        
        results: List[ChunkResult] = await asyncio.gather(*tasks, return_exceptions=True)
        
        elapsed = time.time() - start_time
        
        # Collecter et compter les résultats
        success_count = 0
        error_count = 0
        item_results: List[ItemResult] = []
        for r in results:
            if isinstance(r, Exception):
                error_count += 1
                self._log(f"❌ Exception non gérée: {r}")
            elif isinstance(r, ItemResult):
                item_results.append(r)
                if r.status == "success":
                    success_count += 1
                else:
                    error_count += 1
            else:
                error_count += 1
        
        self._log("\n" + "=" * 60)
        self._log("EXTRACTION TERMINÉE")
        self._log(f"Total chunks: {total_chunks}")
        self._log(f"Succès: {success_count}")
        self._log(f"Erreurs: {error_count}")
        self._log(f"Durée: {elapsed:.1f}s")
        self._log("=" * 60)
        
        return PrixExtractionResult(
            id_categorie=id_categorie,
            total_chunks=total_chunks,
            processed=success_count + error_count,
            success=success_count,
            errors=error_count,
            status="completed" if error_count == 0 else "completed_with_errors",
            item_results=item_results
        )
    
    async def close(self):
        """Ferme les connexions"""
        await self.api_client.close()
