import logging
from typing import Dict, Any, List


def prepare_fournisseur_statements(
    fournisseur_data: Dict[str, Any], database: str = "neo4j", origin: str = "bo"
) -> List[Dict[str, Any]]:
    """
    Prepare a list of Cypher statements for the Fournisseur ingestion process.
    Does NOT execute them.

    Includes:
    1. Fournisseur node MERGE statement
    2. ZoneGeo node MERGE and COURVE relationship for each dept

    Returns:
        List of {query, parameters} dicts
    """
    all_statements = []

    # Extract fournisseur ID and build graph_id
    id_fournisseur = fournisseur_data.get("id_fournisseur", "unknown")
    graph_id = f"id_fournisseur_{id_fournisseur}"

    # Prepare props: exclude 'dept' and 'pays' from main properties
    props = fournisseur_data.copy()
    props["id"] = graph_id
    dept_data = props.pop("dept", [])
    pays_data = props.pop("pays", [])

    # 1. Create/Merge Fournisseur node
    fournisseur_query = """
    MERGE (f:Fournisseur {id: $fournisseur_id})
    SET f += $props
    """
    fournisseur_params = {
        "fournisseur_id": graph_id,
        "props": props,
    }
    all_statements.append(
        {"query": fournisseur_query, "parameters": fournisseur_params}
    )

    logging.debug(
        f"Preparing Fournisseur ingestion for graph_id: {graph_id} with {len(dept_data)} dept entries"
    )

    # 2. For each dept, create ZoneGeo and COURVE relationship
    if dept_data and isinstance(dept_data, list):
        for dept in dept_data:
            if not isinstance(dept, dict):
                continue

            id_zone = dept.get("id_zone", "")
            nom_zone = dept.get("nom_zone", "")
            list_dept = dept.get("list_dept", [])

            if not id_zone:
                logging.warning(f"Skipping dept without id_zone: {dept}")
                continue

            zone_graph_id = f"id_zone_{id_zone}"

            # Create ZoneGeo node and COURVE relationship
            zone_query = """
            MATCH (f:Fournisseur {id: $fournisseur_id})
            MERGE (z:ZoneGeo {id: $zone_id})
            SET z.id_zone = $raw_zone_id, z.nom_zone = $nom_zone, z.list_dept = $list_dept
            MERGE (f)-[:COUVRE_ZONE]->(z)
            """
            zone_params = {
                "fournisseur_id": graph_id,
                "zone_id": zone_graph_id,
                "raw_zone_id": id_zone,
                "nom_zone": nom_zone,
                "list_dept": list_dept if isinstance(list_dept, list) else [],
            }
            all_statements.append({"query": zone_query, "parameters": zone_params})

    # 3. For each pays, create Pays node and COUVRE relationship
    if pays_data and isinstance(pays_data, list):
        for pays in pays_data:
            if not isinstance(pays, dict):
                continue

            id_pays = pays.get("id_pays", "")
            nom_pays = pays.get("nom_pays", "")
            code_iso = pays.get("code_iso", "")
            partiel = pays.get("partiel", False)

            if not id_pays:
                logging.warning(f"Skipping pays without id_pays: {pays}")
                continue

            pays_graph_id = f"id_pays_{id_pays}"

            # Create Pays node and COUVRE relationship
            pays_query = """
            MATCH (f:Fournisseur {id: $fournisseur_id})
            MERGE (p:Pays {id: $pays_id})
            SET p.id_pays = $raw_pays_id, p.nom_pays = $nom_pays, p.code_iso = $code_iso
            MERGE (f)-[r:COUVRE_PAYS]->(p)
            SET r.partiel = $partiel
            """
            pays_params = {
                "fournisseur_id": graph_id,
                "pays_id": pays_graph_id,
                "raw_pays_id": id_pays,
                "nom_pays": nom_pays,
                "code_iso": code_iso,
                "partiel": partiel,
            }
            all_statements.append({"query": pays_query, "parameters": pays_params})

    return all_statements


def get_graph_id_from_data(fournisseur_data: Dict[str, Any]) -> str:
    """Extract graph_id from fournisseur data for deadlock detection."""
    id_fournisseur = fournisseur_data.get("id_fournisseur", "unknown")
    return f"id_fournisseur_{id_fournisseur}"
