"""
Module principal de traitement: extraction de prix depuis les données produits via LLM.
Traitement parallèle asynchrone avec asyncio.
"""
import time
import logging
import asyncio
import contextvars
from typing import Dict, List, Any, Optional

from app.core.api_client import HelloProAPIClient, DeepSeek
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
    """Extracteur de prix depuis les données produits via LLM (DeepSeek)"""

    _current_item_id = contextvars.ContextVar('current_item_id', default=None)

    # ID du prompt statique - Produits
    PROMPT_ID = settings.PROMPT_ID  # "124"

    # ID process
    ID_PROCESS = "37"

    # Type extraction (3 = produits)
    TYPE_EXTRACTION = "3"

    # Provider LLM forcé (DeepSeek pour l'extraction prix produits)
    LLM_PROVIDER = "deepseek"

    # Modèle Gemini (conservé pour compatibilité avec _call_llm)
    GEMINI_MODEL = settings.GEMINI_MODEL_NAME

    # Nombre max de traitements parallèles pour les items
    MAX_PARALLEL_ITEMS = 10

    ETAPE = "10"

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
                self._log("ERREUR: Impossible de charger le prompt d'extraction de prix produit")
                raise Exception(f"Impossible de charger le prompt ID={self.PROMPT_ID}")
            self._log(f"Prompt chargé (ID: {self.PROMPT_ID})")

    def _build_prompt(self, item_content: str, category_name: str = "") -> str:
        """
        Construit le prompt final en injectant le contenu de l'item dans le template.

        Args:
            item_content: Le contenu JSON du produit à traiter
            category_name: Le nom de la catégorie (optionnel)

        Returns:
            Le prompt final à envoyer au LLM
        """
        prompt_text = self.prompt_config.get("contenu_prompt", "")

        # Remplacer les placeholders si présents
        prompt_text = prompt_text.replace("{json_produit}", item_content)
        prompt_text = prompt_text.replace("{info_q1}", self.info_q1)
        prompt_text = prompt_text.replace("{nom_categorie}", category_name)

        return prompt_text

    async def _call_llm(self, prompt_text: str, id_categorie: str) -> Dict[str, Any]:
        """
        Appelle le LLM DeepSeek avec le prompt.

        Args:
            prompt_text: Le prompt à envoyer
            id_categorie: ID de la catégorie pour le tracking

        Returns:
            Dict avec le résultat du LLM (format normalisé {message, api_response})
        """
        provider = self.LLM_PROVIDER.lower()

        if provider == "deepseek":
            # Récupérer la température depuis le prompt config
            temperature = float(self.prompt_config.get("temperature", 0.1))
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
                origine="prix-extraction-produits",
                etat=1,
                temperature=temperature
            )

            # Normaliser le format de retour
            return {
                "message": result.get("content", ""),
                "api_response": {}
            }
        else:
            raise ValueError(f"Provider LLM inconnu: {provider}. Seul 'deepseek' est supporté.")

    def _convert_ttc_to_ht_if_needed(self, prix_data: dict) -> None:
        """
        Conversion de sécurité TTC→HT si taxe=TTC (taux 1.2 / TVA 20%).
        Safety net pour les cas que le LLM n'aurait pas convertis lui-même.
        Modifie prix_data in-place.
        """
        taxe = str(prix_data.get("taxe", "")).strip().upper()
        if taxe != "TTC":
            return

        valeur_str = str(prix_data.get("valeur_prix", "")).strip()
        if not valeur_str:
            return

        try:
            # Normaliser les séparateurs: espaces, virgules, points
            cleaned = valeur_str.replace(" ", "").replace("\u00a0", "")
            # Si contient à la fois . et , : le dernier est le séparateur décimal
            if "," in cleaned and "." in cleaned:
                if cleaned.rindex(",") > cleaned.rindex("."):
                    # Format FR "1.234,56" → "1234.56"
                    cleaned = cleaned.replace(".", "").replace(",", ".")
                else:
                    # Format US "1,234.56" → "1234.56"
                    cleaned = cleaned.replace(",", "")
            elif "," in cleaned:
                cleaned = cleaned.replace(",", ".")

            valeur_num = float(cleaned)
            valeur_ht = round(valeur_num / 1.2, 2)
            prix_data["valeur_prix"] = str(valeur_ht)
            prix_data["taxe"] = "HT"
            self._log(f"🔄 Conversion TTC→HT appliquée: {valeur_num} → {valeur_ht}")
        except (ValueError, TypeError) as e:
            self._log(f"⚠️ Conversion TTC→HT impossible pour valeur '{valeur_str}': {e}")

    def _validate_and_build_payload(
        self,
        llm_data: dict,
        produit: dict,
        id_categorie: str,
        category_name: str
    ) -> Optional[ProduitPrixPayload]:
        """
        Fusionne les données LLM (8 champs prix) avec les métadonnées produit,
        applique la conversion TTC→HT, puis valide le payload.

        Args:
            llm_data      : Données JSON extraites par le LLM (prompt 124)
            produit       : Données brutes du produit (issues de get_produit_prix)
            id_categorie  : ID de la catégorie
            category_name : Nom de la catégorie

        Returns:
            ProduitPrixPayload validé, ou None si les données sont insuffisantes.
        """
        if not llm_data or not isinstance(llm_data, dict):
            id_produit = produit.get("id_produit", "?")
            self._log(f"⚠️ Pas de données LLM pour produit {id_produit}")
            return None

        # Fusion: LLM → 8 champs prix ; produit → métadonnées
        merged = {
            "valeur_reponse_q1": llm_data.get("valeur_reponse_q1") or "",
            "structure_prix":    llm_data.get("structure_prix") or produit.get("structure_prix") or None,
            "valeur_prix":       str(llm_data.get("valeur_prix", "")).strip(),
            "unite":             llm_data.get("unite") or None,
            "devise":            llm_data.get("devise") or produit.get("devise") or None,
            "taxe":              llm_data.get("taxe") or produit.get("taxe") or None,
            "type_transaction":  llm_data.get("type_transaction") or None,
            "perimetre":         llm_data.get("perimetre") or None,
        }

        # Conversion de sécurité TTC→HT
        self._convert_ttc_to_ht_if_needed(merged)

        try:
            payload = ProduitPrixPayload(
                source="produit",
                date_prix=produit.get("date_prix") or None,
                id_categorie=id_categorie,
                nom_categorie=category_name,
                id_lead=None,                                       # non disponible pour les produits
                id_produit=str(produit.get("id_produit", "")),
                source_chunk_id=None,
                domaine=produit.get("domaine") or None,
                caracteristique=produit.get("caracteristique") or None,
                id_societe_ia=str(produit.get("id_societe_ia", "")) or None,
                description_produit=str(produit.get("description_produit", "")).strip(),
                nom_produit=str(produit.get("nom_produit", "")).strip(),
                prix_original=str(produit.get("prix_original", "")).strip(),
                id_fournisseur=str(produit.get("id_fournisseur", "")) or None,
                fournisseur=produit.get("fournisseur") or None,
                # Champs extraits / ajustés par le LLM
                valeur_reponse_q1=merged["valeur_reponse_q1"] or None,
                structure_prix=merged["structure_prix"],
                valeur_prix=merged["valeur_prix"],
                unite=merged["unite"],
                devise=merged["devise"],
                taxe=merged["taxe"],
                type_transaction=merged["type_transaction"],
                perimetre=merged["perimetre"],
            )
            return payload
        except Exception as e:
            id_produit = produit.get("id_produit", "?")
            self._log(f"⚠️ Validation échouée pour produit {id_produit}: {e}")
            return None

    async def _process_single_item(
        self,
        produit: Dict[str, Any],
        item_index: int,
        total_items: int,
        id_categorie: str,
        category_name: str = ""
    ) -> ItemResult:
        """
        Traite un seul produit: LLM call + validation payload.

        En cas d'erreur (LLM, JSON, validation), une exception est levée
        afin d'interrompre immédiatement le traitement de la catégorie.

        Args:
            produit      : Le produit à traiter (issu de get_produit_prix)
            item_index   : Index du produit (pour les logs)
            total_items  : Nombre total de produits
            id_categorie : ID de la catégorie
            category_name: Nom de la catégorie

        Returns:
            ItemResult avec status="success" et prix_data validé.
        """
        async with self._semaphore:
            item_id = str(produit.get("id_produit", f"item_{item_index}"))
            # Retirer les champs de pré-calcul algo pour ne pas biaiser le LLM
            # (structure_prix, valeur_prix, devise, taxe sont ré-extraits par le LLM lui-même).
            # Les valeurs d'origine restent dans `produit` pour la fusion finale.
            produit_for_llm = {
                k: v for k, v in produit.items()
                if k not in ("structure_prix", "valeur_prix", "devise", "taxe")
            }
            item_content = utils.to_json_string(produit_for_llm)

            # Activer le contexte item pour bufferiser les logs
            token = self._current_item_id.set(item_id)

            self._log(f"[{item_index + 1}/{total_items}] Traitement produit {item_id}")
            self._log(f"[{item_index + 1}/{total_items}] item_content: {item_content}")

            # 1. Construire le prompt avec le contenu JSON du produit
            prompt_text = self._build_prompt(item_content, category_name)

            # 2. Appeler le LLM (DeepSeek)
            result = await self._call_llm(prompt_text, id_categorie)

            # Vérifier si c'est une erreur (format Gemini avec "code")
            if "code" in result:
                error_msg = str(result.get("error", "Erreur LLM inconnue"))
                self._log(f"[{item_index + 1}/{total_items}] ❌ Erreur LLM produit {item_id}: {error_msg}")
                self._flush_item_logs(item_id)
                self._current_item_id.reset(token)
                raise Exception(f"Erreur LLM pour produit {item_id}: {error_msg}")

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
                raise Exception(f"Impossible d'extraire le JSON de la réponse LLM pour produit {item_id}")

            # Le LLM retourne un dict pour prompt 124 (1 produit = 1 prix)
            # Si le LLM retourne une liste, on prend le premier élément
            if isinstance(prix_data_raw, list):
                if len(prix_data_raw) == 0:
                    self._log(f"[{item_index + 1}/{total_items}] ⏭️ Produit {item_id} — aucun prix trouvé par le LLM")
                    self._flush_item_logs(item_id)
                    self._current_item_id.reset(token)
                    return ItemResult(
                        item_id=item_id,
                        source="produits",
                        content=item_content,
                        prix_data=None,
                        status="skipped"
                    )
                prix_data_raw = prix_data_raw[0]

            # 3b. Fusionner avec les métadonnées produit, convertir TTC→HT, valider
            payload = self._validate_and_build_payload(
                llm_data=prix_data_raw,
                produit=produit,
                id_categorie=id_categorie,
                category_name=category_name
            )
            if payload is None:
                self._flush_item_logs(item_id)
                self._current_item_id.reset(token)
                raise ValueError(
                    f"Validation du payload échouée (champs obligatoires manquants) : "
                    f"Catégorie {id_categorie} - Produit {item_id} - Data LLM : {prix_data_raw}"
                )

            self._log(f"[{item_index + 1}/{total_items}] ✅ Produit {item_id} validé")
            self._flush_item_logs(item_id)
            self._current_item_id.reset(token)
            return ItemResult(
                item_id=item_id,
                source="produits",
                content=item_content,
                prix_data=payload.dict(),
                status="success"
            )

    async def _fetch_items(self, id_categorie: str) -> List[Dict[str, Any]]:
        """
        Récupère les produits avec prix via l'API BO.

        Appelle api_client.post("prix", "produits", "get") → get_produit_prix() (BO/api/v2/prix.php).

        Chaque produit retourné contient :
            - date_prix, id_produit, nom_produit, description_produit
            - domaine, id_fournisseur, fournisseur
            - structure_prix (fixe / promotionnel / fourchette / à_partir_de)
            - valeur_prix, devise, taxe

        Returns:
            Liste de dicts représentant les produits à traiter.
            Retourne [] si erreur API ou aucun produit disponible.
        """
        response = await self.api_client.post(
            "prix",
            "produits",
            "get",
            {"id_categorie": id_categorie}
        )

        if not response or response.get("erreur"):
            self._log(f"⚠️ Réponse API invalide ou erreur: {response}")
            return []

        produits_dict = response.get("produits", {})

        if not produits_dict:
            self._log("⚠️ Aucun produit retourné par l'API")
            return []

        # Convertir le dict indexé par id_produit en liste plate
        items = list(produits_dict.values())
        self._log(f"📦 {len(items)} produits récupérés depuis l'API")
        return items

    async def extract_prix_for_category(
        self,
        request: RequestProcessus
    ) -> PrixExtractionResult:
        """
        Processus principal: extraction de prix produits via LLM pour une catégorie.

        1. Charge le prompt (ID=124)
        2. Récupère les produits à traiter via _fetch_items()
        3. Traite chaque produit en parallèle via asyncio (batches de 50, 5 max simultanés)
        4. Pour chaque produit: LLM call → fusion metadata → conversion TTC→HT → validation payload
        5. Publie les résultats de chaque batch via le callback on_batch_publish

        Args:
            request: RequestProcessus avec id_categorie et is_reset

        Returns:
            PrixExtractionResult avec le bilan du traitement et les item_results individuels
        """
        id_categorie = request.id_categorie

        # Initialiser le fichier de tracking
        self.tracking_file = utils.get_tracking_filepath(id_categorie, prefix="prix-extraction-produits")

        self._log("=" * 60)
        self._log("EXTRACTION PRIX PRODUITS (via LLM)")
        self._log(f"Catégorie: {id_categorie}")
        self._log(f"Reset: {request.is_reset}")
        self._log(f"Provider LLM: {self.LLM_PROVIDER}")
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

        # Récupérer les produits depuis l'API BO
        self._log("\n--- Récupération des produits via API BO ---")
        items = await self._fetch_items(id_categorie)

        if not items:
            self._log("⚠️ Aucun produit à traiter")
            return PrixExtractionResult(
                id_categorie=id_categorie,
                total_chunks=0,
                processed=0,
                success=0,
                errors=0,
                status="completed"
            )

        total_items = len(items)
        self._log(f"📊 {total_items} produits à traiter")

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

            self._log(f"\n--- Lot [{batch_num}/{total_batches}] produits {batch_start + 1}-{batch_end}/{total_items} ({self.MAX_PARALLEL_ITEMS} max simultanés) ---")

            tasks = [
                self._process_single_item(
                    produit=produit,
                    item_index=batch_start + i,
                    total_items=total_items,
                    id_categorie=id_categorie,
                    category_name=category_name
                )
                for i, produit in enumerate(batch_items)
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
                        self._log(f"❌ Produit en erreur: {r.item_id} — {r.error_message}")
                        raise Exception(f"Produit {r.item_id} en erreur: {r.error_message}")
                else:
                    raise Exception(f"Résultat inattendu: {type(r)} — {r}")

            all_item_results.extend(batch_item_results)

            # Sauvegarde batch des IDs traités (success et skipped séparément)
            success_ids = [r.item_id for r in batch_item_results if r.status == "success"]
            skipped_ids = [r.item_id for r in batch_item_results if r.status == "skipped"]

            if success_ids:
                self._log(f"--- Sauvegarde batch de {len(success_ids)} ID(s) success produit ---")
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
                self._log(f"--- Sauvegarde batch de {len(skipped_ids)} ID(s) skipped produit ---")
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
        self._log(f"Total produits: {total_items}")
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
