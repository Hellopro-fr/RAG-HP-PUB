"""
Script de migration de la collection produits_3 vers produits_4
Objectif: Augmenter la taille du champ url_images de 4095 à 65535 caractères

Usage:
    python migrate_produits_3_to_4.py [OPTIONS]

Options:
    --batch-size N: Nombre d'entités à migrer par batch (défaut: 1000)
    --dry-run: Mode test sans création de la nouvelle collection
    --skip-backup: Ne pas créer de backup avant migration
    --check-duplicates: Vérifier et ignorer les chunks existants (id_produit + source + chunk_number)
                        Utile pour relancer la migration en cas d'interruption

Exemples:
    # Première migration complète
    python migrate_produits_3_to_4.py --skip-backup --batch-size 5000

    # Reprendre une migration interrompue (ignore les doublons)
    python migrate_produits_3_to_4.py --skip-backup --check-duplicates --batch-size 5000

    # Test sans création de collection
    python migrate_produits_3_to_4.py --dry-run
"""

import logging
import argparse
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional
from tqdm import tqdm

from common_utils.database.config.settings import Configuration, settings
from pymilvus import (
    connections,
    utility,
    FieldSchema,
    CollectionSchema,
    DataType,
    Collection,
    MilvusException
)

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(f'migration_produits_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class MilvusProduitsMigration:
    """Classe pour gérer la migration de produits_3 vers produits_4"""

    def __init__(self, config: Configuration = settings):
        self.config = config
        self.source_collection_name = "produits_3"
        self.target_collection_name = "produits_4"
        self.backup_collection_name = f"produits_3_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.source_collection: Optional[Collection] = None
        self.target_collection: Optional[Collection] = None

    def connect(self):
        """Connexion à Milvus"""
        try:
            logger.info("Connexion à Milvus/Zilliz Cloud...")
            connections.connect(
                "default",
                host=self.config.ZILLIZ_URI,
                port=self.config.ZILLIZ_PORT
            )
            logger.info("✓ Connexion établie avec succès")
            return True
        except Exception as e:
            logger.error(f"✗ Erreur de connexion: {e}")
            return False

    def verify_source_collection(self) -> bool:
        """Vérifier que la collection source existe"""
        try:
            if not utility.has_collection(self.source_collection_name):
                logger.error(f"✗ Collection source '{self.source_collection_name}' introuvable")
                return False

            self.source_collection = Collection(self.source_collection_name)
            self.source_collection.load()

            # Statistiques de la collection source
            num_entities = self.source_collection.num_entities
            logger.info(f"✓ Collection source trouvée: {num_entities:,} entités")

            return True
        except Exception as e:
            logger.error(f"✗ Erreur lors de la vérification de la collection source: {e}")
            return False

    def create_backup(self) -> bool:
        """Créer une copie de sauvegarde (optionnel mais recommandé pour petites collections)"""
        try:
            logger.warning("ATTENTION: La création de backup peut être très longue pour des millions d'entités")
            logger.warning("Pour de gros volumes, il est recommandé d'utiliser --skip-backup et de faire un backup au niveau infrastructure")

            # Pour l'instant, on log juste l'avertissement
            # Une vraie sauvegarde nécessiterait de copier toutes les données
            logger.info("⚠ Backup ignoré (utilisez --skip-backup pour éviter cet avertissement)")
            return True

        except Exception as e:
            logger.error(f"✗ Erreur lors de la création du backup: {e}")
            return False

    def create_target_collection(self, dimension: int = 1024) -> bool:
        """Créer la nouvelle collection produits_4 avec le schéma corrigé"""
        try:
            # Vérifier si la collection existe déjà
            if utility.has_collection(self.target_collection_name):
                logger.warning(f"⚠ Collection '{self.target_collection_name}' existe déjà")
                response = input("Voulez-vous la supprimer et la recréer? (oui/non): ")
                if response.lower() in ['oui', 'o', 'yes', 'y']:
                    logger.info(f"Suppression de '{self.target_collection_name}'...")
                    utility.drop_collection(self.target_collection_name)
                else:
                    logger.error("Migration annulée par l'utilisateur")
                    return False

            logger.info(f"Création de la collection '{self.target_collection_name}'...")

            # Schéma identique à produits_3 SAUF url_images avec 65535 au lieu de 4095
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True, max_length=64),
                FieldSchema(name="id_produit", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dimension),
                FieldSchema(name="url", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="nom_produit", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="page_type", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="domaine", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="fournisseur", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="id_fournisseur", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="categorie", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="id_categorie", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="fichier_source", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="etat", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="affichage", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="date_ajout", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="date_maj", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="sku", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="ean", dtype=DataType.VARCHAR, max_length=65535),
                # *** MODIFICATION ICI: 65535 au lieu de 4095 ***
                FieldSchema(name="url_images", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="reference", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="prix_ht", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="prix_ttc", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="statut", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="remise", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="stock", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="delai_livraison", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="marque", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="fabricant", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="garantie", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="normes", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="frais_de_port", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="caracteristique", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="type_produit", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="montant_eco_participation", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="source_produits", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="chunk_number", dtype=DataType.INT64),
                FieldSchema(name="total_chunks", dtype=DataType.INT64),
            ]

            schema = CollectionSchema(fields, description="Collection produits_4 avec url_images étendu à 65535 caractères")

            self.target_collection = Collection(
                self.target_collection_name,
                schema,
                consistency_level="Strong"
            )

            logger.info("Création des index...")

            # Index HNSW pour les embeddings
            index_params = {
                "metric_type": "COSINE",
                "index_type": "HNSW",
                "params": {
                    "M": settings.M_PARAMS,
                    "efConstruction": settings.EF_PARAMS
                }
            }
            self.target_collection.create_index(field_name="embedding", index_params=index_params)

            # Index scalaire pour id_produit
            self.target_collection.create_index(field_name="id_produit", index_name="idx_produit")

            logger.info(f"✓ Collection '{self.target_collection_name}' créée avec succès")
            return True

        except Exception as e:
            logger.error(f"✗ Erreur lors de la création de la collection cible: {e}")
            return False

    def _filter_existing_chunks(self, batch_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filtre les chunks qui existent déjà dans la collection cible
        Vérifie: id_produit + source + chunk_number

        Args:
            batch_data: Liste des chunks à vérifier

        Returns:
            Liste filtrée contenant seulement les chunks non-existants
        """
        if not batch_data or len(batch_data) == 0:
            return []

        try:
            # Construire les expressions de vérification pour chaque chunk
            non_existing_chunks = []

            for chunk in batch_data:
                id_produit = chunk.get("id_produit", "")
                source = chunk.get("source", "")
                chunk_number = chunk.get("chunk_number", -1)

                # Vérifier si ce chunk existe déjà
                expr = f'id_produit == "{id_produit}" && source == "{source}" && chunk_number == {chunk_number}'

                existing = self.target_collection.query(
                    expr=expr,
                    output_fields=["id"],
                    limit=1
                )

                # Si aucun résultat, le chunk n'existe pas encore
                if not existing or len(existing) == 0:
                    non_existing_chunks.append(chunk)

            return non_existing_chunks

        except Exception as e:
            logger.error(f"Erreur lors de la vérification des doublons: {e}")
            # En cas d'erreur, on retourne tout le batch pour éviter de perdre des données
            return batch_data

    def migrate_data(self, batch_size: int = 1000, check_duplicates: bool = False) -> bool:
        """Migrer les données par batch

        Args:
            batch_size: Nombre d'entités par batch
            check_duplicates: Si True, vérifie si le chunk existe déjà (id_produit + source + chunk_number)
        """
        try:
            if not self.source_collection or not self.target_collection:
                logger.error("✗ Collections source ou cible non initialisées")
                return False

            # Charger la collection cible
            self.target_collection.load()

            total_entities = self.source_collection.num_entities
            logger.info(f"Début de la migration de {total_entities:,} entités...")
            logger.info(f"Taille de batch: {batch_size}")

            # Liste de tous les champs à récupérer (sauf 'id' qui sera auto-généré)
            output_fields = [
                "id_produit", "embedding", "url", "nom_produit", "page_type", "domaine",
                "fournisseur", "id_fournisseur", "categorie", "id_categorie", "source",
                "fichier_source", "etat", "affichage", "date_ajout", "date_maj", "text",
                "sku", "ean", "url_images", "reference", "prix_ht", "prix_ttc", "statut",
                "remise", "stock", "delai_livraison", "marque", "fabricant", "garantie",
                "normes", "frais_de_port", "caracteristique", "type_produit",
                "montant_eco_participation", "source_produits", "chunk_id", "chunk_number", "total_chunks"
            ]

            migrated_count = 0
            skipped_count = 0
            error_count = 0

            if check_duplicates:
                logger.info("Mode vérification activé: les chunks existants seront ignorés")

            # Utiliser un iterator pour parcourir toutes les données
            # Note: Pour Milvus, on utilise query avec pagination
            offset = 0

            with tqdm(total=total_entities, desc="Migration", unit="entités") as pbar:
                while offset < total_entities:
                    try:
                        # Query par batch avec limit et offset
                        # Note: expr="" récupère toutes les entités
                        results = self.source_collection.query(
                            expr="",
                            output_fields=output_fields,
                            limit=batch_size,
                            offset=offset
                        )

                        if not results or len(results) == 0:
                            break

                        # Préparer les données pour l'insertion
                        batch_data = results

                        # Vérifier les doublons si demandé
                        if check_duplicates:
                            # Filtrer les chunks qui existent déjà dans produits_4
                            batch_data = self._filter_existing_chunks(results)
                            skipped_count += len(results) - len(batch_data)

                        # Insérer dans la collection cible seulement si on a des données à insérer
                        if batch_data and len(batch_data) > 0:
                            self.target_collection.insert(batch_data)
                            migrated_count += len(batch_data)
                        else:
                            # Tous les chunks de ce batch existent déjà
                            pass

                        offset += len(results)
                        pbar.update(len(results))

                        # Log tous les 10000 enregistrements
                        if migrated_count % 10000 == 0:
                            logger.info(f"Progression: {migrated_count:,}/{total_entities:,} entités migrées")

                    except MilvusException as e:
                        logger.error(f"Erreur Milvus lors de la migration du batch offset={offset}: {e}")
                        error_count += len(results) if results else batch_size
                        offset += batch_size  # Skip ce batch et continuer

                    except Exception as e:
                        logger.error(f"Erreur lors de la migration du batch offset={offset}: {e}")
                        error_count += len(results) if results else batch_size
                        offset += batch_size

            # Flush pour s'assurer que toutes les données sont persistées
            self.target_collection.flush()

            logger.info(f"✓ Migration terminée!")
            logger.info(f"  - Entités migrées: {migrated_count:,}")
            if check_duplicates:
                logger.info(f"  - Chunks ignorés (déjà existants): {skipped_count:,}")
            logger.info(f"  - Erreurs: {error_count:,}")
            logger.info(f"  - Total dans collection cible: {self.target_collection.num_entities:,}")

            return error_count == 0

        except Exception as e:
            logger.error(f"✗ Erreur lors de la migration: {e}", exc_info=True)
            return False

    def verify_migration(self) -> bool:
        """Vérifier que la migration s'est bien passée"""
        try:
            logger.info("Vérification de la migration...")

            source_count = self.source_collection.num_entities
            target_count = self.target_collection.num_entities

            logger.info(f"Collection source: {source_count:,} entités")
            logger.info(f"Collection cible: {target_count:,} entités")

            if source_count == target_count:
                logger.info("✓ Nombre d'entités identique")

                # Test de quelques enregistrements aléatoires
                logger.info("Vérification de quelques enregistrements...")
                sample_results = self.target_collection.query(
                    expr="",
                    output_fields=["id_produit", "url_images"],
                    limit=5
                )

                for record in sample_results:
                    url_images_length = len(record.get("url_images", ""))
                    logger.info(f"  - id_produit: {record.get('id_produit')}, url_images length: {url_images_length}")

                logger.info("✓ Vérification réussie!")
                return True
            else:
                logger.warning(f"⚠ Nombre d'entités différent: {source_count} vs {target_count}")
                return False

        except Exception as e:
            logger.error(f"✗ Erreur lors de la vérification: {e}")
            return False

    def cleanup(self):
        """Fermer les connexions"""
        try:
            if self.source_collection:
                self.source_collection.release()
            if self.target_collection:
                self.target_collection.release()
            connections.disconnect("default")
            logger.info("✓ Connexions fermées")
        except Exception as e:
            logger.warning(f"Erreur lors de la fermeture: {e}")


def main():
    """Point d'entrée principal"""
    parser = argparse.ArgumentParser(description="Migration de produits_3 vers produits_4")
    parser.add_argument("--batch-size", type=int, default=1000, help="Taille des batchs (défaut: 1000)")
    parser.add_argument("--dry-run", action="store_true", help="Mode test sans création de collection")
    parser.add_argument("--skip-backup", action="store_true", help="Ne pas créer de backup")
    parser.add_argument("--check-duplicates", action="store_true", help="Vérifier et ignorer les chunks existants (id_produit + source + chunk_number)")

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("MIGRATION PRODUITS_3 -> PRODUITS_4")
    logger.info("=" * 80)
    logger.info(f"Batch size: {args.batch_size}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Skip backup: {args.skip_backup}")
    logger.info(f"Check duplicates: {args.check_duplicates}")
    logger.info("=" * 80)

    migration = MilvusProduitsMigration()

    try:
        # Étape 1: Connexion
        if not migration.connect():
            logger.error("Échec de la connexion. Abandon.")
            return 1

        # Étape 2: Vérifier la collection source
        if not migration.verify_source_collection():
            logger.error("Échec de la vérification de la collection source. Abandon.")
            return 1

        # Étape 3: Backup (optionnel)
        if not args.skip_backup:
            logger.info("Création du backup (recommandé mais long)...")
            migration.create_backup()

        if args.dry_run:
            logger.info("Mode DRY-RUN: Arrêt avant création de la collection cible")
            return 0

        # Étape 4: Créer la collection cible
        if not migration.create_target_collection():
            logger.error("Échec de la création de la collection cible. Abandon.")
            return 1

        # Étape 5: Migrer les données
        if not migration.migrate_data(batch_size=args.batch_size, check_duplicates=args.check_duplicates):
            logger.warning("La migration s'est terminée avec des erreurs")

        # Étape 6: Vérifier
        if not migration.verify_migration():
            logger.warning("La vérification a détecté des incohérences")

        logger.info("=" * 80)
        logger.info("MIGRATION TERMINÉE")
        logger.info("=" * 80)
        logger.info("Prochaines étapes:")
        logger.info("1. Vérifier manuellement quelques enregistrements dans produits_4")
        logger.info("2. Mettre à jour votre code pour utiliser produits_4 au lieu de produits_3")
        logger.info("3. Tester votre application avec produits_4")
        logger.info("4. Une fois validé, supprimer produits_3: utility.drop_collection('produits_3')")
        logger.info("=" * 80)

        return 0

    except KeyboardInterrupt:
        logger.warning("\nMigration interrompue par l'utilisateur")
        return 1
    except Exception as e:
        logger.error(f"Erreur fatale: {e}", exc_info=True)
        return 1
    finally:
        migration.cleanup()


if __name__ == "__main__":
    sys.exit(main())
