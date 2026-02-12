import logging
from typing import Optional, List, Dict, Any
from app.infrastructure.clients import clients
from app.domain.models import (
    FournisseurGeoResponse,
    PaysCouverture,
    DepartementCouverture,
)


class FournisseurService:
    async def get_geo_coverage(
        self, id_fournisseur: str
    ) -> Optional[FournisseurGeoResponse]:
        """
        Retrieves the geographical coverage (Pays and ZoneGeographique/Departements)
        for a specific supplier (Fournisseur) by its ID.
        """
        cypher_query = """
        MATCH (f:Fournisseur {id_fournisseur: $id_fournisseur})
        
        // Collect related Pays
        OPTIONAL MATCH (f)-[r_pays:COUVRE_PAYS]->(p:Pays)
        WITH f, collect({
            id_pays: p.id_pays,
            nom_pays: p.nom_pays,
            couvre_partiel: coalesce(r_pays.partiel, false)
        }) as pays_list
        
        // Collect related ZoneGeographique (Departements)
        OPTIONAL MATCH (f)-[:COUVRE_ZONE]->(z:ZoneGeographique)
        WITH pays_list, collect({
            id_dept: z.id_zone, 
            nom_dept: z.nom_zone
        }) as dept_list
        
        RETURN pays_list, dept_list
        """

        try:
            results = await clients.execute_cypher(
                cypher_query, {"id_fournisseur": id_fournisseur}
            )

            # Check if we got any results. Since we match on specific ID,
            # if no supplier found, the query likely returns empty or nulls depending on structure,
            # but 'MATCH (f...)' requires f to exist. If f doesn't exist, it returns nothing.
            if not results:
                logging.info(f"Fournisseur with ID '{id_fournisseur}' not found.")
                return None

            record = results[0]

            # Parse Pays
            pays_data = []
            for p in record.get("pays_list", []):
                if p.get(
                    "id_pays"
                ):  # Filter out nulls if OPTIONAL MATCH failed completely
                    pays_data.append(
                        PaysCouverture(
                            id_pays=str(p["id_pays"]),
                            nom_pays=p["nom_pays"],
                            couvre_partiel=p["couvre_partiel"],
                        )
                    )

            # Parse Departements
            dept_data = []
            for d in record.get("dept_list", []):
                if d.get("id_dept"):  # Filter out nulls
                    dept_data.append(
                        DepartementCouverture(
                            id_dept=str(d["id_dept"]),
                            nom_dept=d["nom_dept"],
                        )
                    )

            return FournisseurGeoResponse(pays=pays_data, departements=dept_data)

        except Exception as e:
            logging.error(
                f"Error retrieving geo coverage for assistant {id_fournisseur}: {e}",
                exc_info=True,
            )
            raise e


fournisseur_service = FournisseurService()
