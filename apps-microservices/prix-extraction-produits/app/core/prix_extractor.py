"""
Module principal de traitement: extraction de prix depuis les données produits via l'API BO.
Pas de traitement LLM - les données sont récupérées directement et publiées vers prix-normalisation.
"""
import time
import logging
from typing import Dict, List, Any, Optional

from app.core.api_client import HelloProAPIClient
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
    """
    Extracteur de prix depuis les données produits via l'API BO (get_produit_prix).
    Aucun traitement LLM : les données sont récupérées, validées, puis transmises
    directement au service prix-normalisation.
    """

    ETAPE = "10"

    # Type extraction (3 = produits)
    TYPE_EXTRACTION = "3"

    def __init__(self, api_client: Optional[HelloProAPIClient] = None):
        self.api_client = api_client or HelloProAPIClient()
        self.tracking_file = None

    def _log(self, message: str):
        """Écrit dans le fichier de tracking et les logs"""
        if self.tracking_file:
            utils.write_log(self.tracking_file, message)
        logger.info(message)

    async def _fetch_items(self, id_categorie: str ) -> List[Dict[str, Any]]:
        """
        Récupère les produits avec prix via l'API BO.

        Appelle api_client.post("prix", "produits", "get") → get_produit_prix() (BO/api/v2/prix.php).

        Chaque produit retourné contient :
            - date_prix, id_produit, nom_produit, description_produit
            - domaine, id_fournisseur, fournisseur
            - structure_prix (fixe / promotionnel / fourchette / à_partir_de)
            - valeur_prix, devise, taxe

        Returns:
            Liste de dicts représentant les produits à publier.
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

    def _validate_and_build_payload(
        self,
        produit: Dict[str, Any],
        id_categorie: str,
        category_name: str
    ) -> Optional[ProduitPrixPayload]:
        """
        Valide un produit et construit le payload à publier vers prix-normalisation.

        Args:
            produit: Données brutes du produit (issues de get_produit_prix)
            id_categorie: ID de la catégorie (pour le tracking)
            category_name: Nom de la catégorie

        Returns:
            ProduitPrixPayload validé, ou None si données insuffisantes.
        """
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
                valeur_reponse_q1=None,                             # non applicable ici
                description_produit=str(produit.get("description_produit", "")).strip(),
                nom_produit=str(produit.get("nom_produit", "")).strip(),
                structure_prix=produit.get("structure_prix") or None,
                valeur_prix=str(produit.get("valeur_prix", "")).strip(),
                prix_original=str(produit.get("prix_original", "")).strip(),
                unite=None,                                         # non disponible dans get_produit_prix
                devise=produit.get("devise") or None,
                taxe=produit.get("taxe") or None,
                type_transaction=None,                              # non applicable ici
                perimetre=None,                                     # non applicable ici
                id_fournisseur=str(produit.get("id_fournisseur", "")) or None,
                fournisseur=produit.get("fournisseur") or None,
            )
            return payload
        except Exception as e:
            id_produit = produit.get("id_produit", "?")
            self._log(f"⚠️ Validation échouée pour produit {id_produit}: {e}")
            return None

    async def extract_prix_for_category(
        self,
        request: RequestProcessus
    ) -> PrixExtractionResult:
        """
        Processus principal: extraction directe de prix produits pour une catégorie.

        1. Récupère les produits via l'API BO (get_produit_prix)
        2. Valide chaque produit avec ProduitPrixPayload
        3. Retourne les ItemResult pour que le consumer publie vers prix-normalisation
           (aucun appel LLM)

        Args:
            request: RequestProcessus avec id_categorie et is_reset

        Returns:
            PrixExtractionResult contenant la liste des item_results individuels
        """
        id_categorie = request.id_categorie

        # Initialiser le fichier de tracking
        self.tracking_file = utils.get_tracking_filepath(id_categorie, prefix="prix-extraction-produits")

        self._log("=" * 60)
        self._log("EXTRACTION PRIX PRODUITS (sans LLM)")
        self._log(f"Catégorie: {id_categorie}")
        self._log(f"Reset: {request.is_reset}")
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

        start_time = time.time()
        success_count = 0
        error_count = 0
        item_results: List[ItemResult] = []

        for i, produit in enumerate(items):
            id_produit = str(produit.get("id_produit", f"item_{i}"))
            self._log(f"[{i + 1}/{total_items}] Traitement produit {id_produit}")

            # Valider et construire le payload
            payload = self._validate_and_build_payload(produit, id_categorie , category_name)

            if payload is None:
                # Validation échouée — la raison est déjà loggée dans _validate_and_build_payload
                raise ValueError(f"Validation du payload échouée (champs obligatoires manquants ou invalides) : Catégorie {id_categorie} - Produits {id_produit} - Data : {produit} ")
                continue

            # Produit valide → créer un ItemResult success avec prix_data = payload
            success_count += 1
            self._log(f"[{i + 1}/{total_items}] ✅ Produit {id_produit} validé")
            item_results.append(ItemResult(
                item_id=id_produit,
                source="produits",
                content=str(payload.description_produit),
                prix_data=payload.dict(),
                status="success"
            ))

        elapsed = time.time() - start_time

        # Sauvegarde en batch des IDs produits traités avec succès
        # Appelle save_process_prix() (BO/api/v2/prix.php) via prix/process/save
        # type_extraction = 3 pour les produits
        successful_ids = [
            r.item_id
            for r in item_results
            if r.status == "success"
        ]

        if successful_ids:
            self._log(f"\n--- Sauvegarde batch de {len(successful_ids)} ID(s) produit ---")            
            save_result = await self.api_client.post(
                "prix",
                "process",
                "save",
                {
                    "id_categorie":    id_categorie,
                    "type_extraction": self.TYPE_EXTRACTION,
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
            self._log("ℹ️ Aucun ID produit à sauvegarder (aucun succès)")

        self._log("\n" + "=" * 60)
        self._log("EXTRACTION TERMINÉE")
        self._log(f"Total produits: {total_items}")
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
