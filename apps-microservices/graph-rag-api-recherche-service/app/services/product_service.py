import logging
from typing import List, Optional, Any
from app.domain.models import CaracteristiqueResponse
from app.infrastructure.clients import clients


class ProductService:
    async def get_characteristics(
        self, product_id: str
    ) -> Optional[List[CaracteristiqueResponse]]:
        """
        Retrieves the technical characteristics for a specific product by its Business ID (id_produit).
        Only returns characteristics that have a non-null/non-empty value (scalar or range).
        """
        cypher_query = """
        MATCH (p:Produit {id_produit: $pid})
        OPTIONAL MATCH (p)-[:A_POUR_CARACTERISTIQUE]->(c:CaracteristiqueTechnique)
        WHERE (c.valeur IS NOT NULL AND toString(c.valeur) <> "") 
           OR c.valeur_min IS NOT NULL 
           OR c.valeur_max IS NOT NULL
        RETURN p, collect(c {.*}) as characteristics
        """

        try:
            results = await clients.execute_cypher(cypher_query, {"pid": product_id})

            if not results:
                logging.info(f"Product with ID '{product_id}' not found.")
                return None

            record = results[0]
            raw_chars = record.get("characteristics", [])

            characteristics = []
            for raw in raw_chars:
                try:
                    if not raw.get("nom") or not raw.get("label"):
                        continue

                    char = CaracteristiqueResponse(
                        nom=raw.get("nom"),
                        label=raw.get("label"),
                        valeur=raw.get("valeur"),
                        unite=raw.get("unite"),
                        type_donnee=raw.get("type_donnee"),
                        valeur_min=raw.get("valeur_min"),
                        valeur_max=raw.get("valeur_max"),
                        id_caracteristique=str(raw.get("id_source_caracteristique")),
                        id_valeur=str(raw.get("id_source_valeur", "N/A")),
                    )
                    characteristics.append(char)
                except Exception as e:
                    logging.warning(
                        f"Failed to parse characteristic for product {product_id}: {e}"
                    )
                    continue

            # Sort by ID if possible, else keep order
            characteristics.sort(
                key=lambda x: (
                    x.id_caracteristique
                    if x.id_caracteristique.isdigit()
                    else x.id_caracteristique
                )
            )
            return characteristics

        except Exception as e:
            logging.error(
                f"Error retrieving characteristics for product {product_id}: {e}",
                exc_info=True,
            )
            raise e

    async def delete_produit(self, product_id: str) -> Optional[dict]:
        """
        Deletes a product node by its ID and returns the deleted node's properties.
        """
        cypher_query = """
        MATCH (p:Produit {id_produit: $pid})
        WITH p, properties(p) as props
        DETACH DELETE p
        RETURN props
        """

        try:
            results = await clients.execute_cypher(cypher_query, {"pid": product_id})

            if not results:
                logging.info(f"Product with ID '{product_id}' not found for deletion.")
                return None

            return results[0].get("props")

        except Exception as e:
            logging.error(
                f"Error deleting product {product_id}: {e}",
                exc_info=True,
            )
            raise e


product_service = ProductService()
