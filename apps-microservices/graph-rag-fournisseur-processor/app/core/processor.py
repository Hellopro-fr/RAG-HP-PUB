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

    # 2. For each dept, create Departement node and COUVRE_ZONE relationship
    if dept_data and isinstance(dept_data, list):
        for dept in dept_data:
            if not isinstance(dept, dict):
                continue

            id_dept = dept.get("id_dept", "")
            nom_dept = dept.get("nom_dept", "")
            couvre_tous = dept.get("couvre_tous", True)
            couvre_categorie = dept.get("couvre_categorie", [])
            ne_couvre_pas_categorie = dept.get("ne_couvre_pas_categorie", [])

            if not id_dept:
                logging.warning(f"Skipping dept without id_dept: {dept}")
                continue

            dept_graph_id = f"id_dept_{id_dept}"

            # Build relationship properties based on all_couverture
            rel_props = {"couvre_tous": couvre_tous}
            if not couvre_tous:
                # Add couvre and ne_couvre_pas lists when not covering all
                if couvre_categorie and isinstance(couvre_categorie, list):
                    rel_props["couvre"] = couvre_categorie
                if ne_couvre_pas_categorie and isinstance(
                    ne_couvre_pas_categorie, list
                ):
                    rel_props["ne_couvre_pas"] = ne_couvre_pas_categorie

            # Create Departement node and COUVRE_ZONE relationship with properties
            dept_query = """
            MATCH (f:Fournisseur {id: $fournisseur_id})
            MERGE (d:ZoneGeo {id: $dept_id})
            SET d.id_dept = $raw_dept_id, d.nom_dept = $nom_dept
            MERGE (f)-[r:COUVRE_ZONE]->(d)
            SET r += $rel_props
            """
            dept_params = {
                "fournisseur_id": graph_id,
                "dept_id": dept_graph_id,
                "raw_dept_id": id_dept,
                "nom_dept": nom_dept,
                "rel_props": rel_props,
            }
            all_statements.append({"query": dept_query, "parameters": dept_params})

    # 3. For each pays, create Pays node and COUVRE relationship
    if pays_data and isinstance(pays_data, list):
        for pays in pays_data:
            if not isinstance(pays, dict):
                continue

            id_pays = pays.get("id_pays", "")
            nom_pays = pays.get("nom_pays", "")
            code_iso = pays.get("code_iso", "")
            couvre_tous = pays.get("couvre_tous", True)
            couvre_categorie = pays.get("couvre_categorie", [])
            ne_couvre_pas_categorie = pays.get("ne_couvre_pas_categorie", [])

            if not id_pays:
                logging.warning(f"Skipping pays without id_pays: {pays}")
                continue

            rel_props = {"couvre_tous": couvre_tous}
            if not couvre_tous:
                if couvre_categorie and isinstance(couvre_categorie, list):
                    rel_props["couvre"] = couvre_categorie
                if ne_couvre_pas_categorie and isinstance(
                    ne_couvre_pas_categorie, list
                ):
                    rel_props["ne_couvre_pas"] = ne_couvre_pas_categorie

            pays_graph_id = f"id_pays_{id_pays}"

            # Create Pays node and COUVRE relationship
            pays_query = """
            MATCH (f:Fournisseur {id: $fournisseur_id})
            MERGE (p:Pays {id: $pays_id})
            SET p.id_pays = $raw_pays_id, p.nom_pays = $nom_pays, p.code_iso = $code_iso
            MERGE (f)-[r:COUVRE_PAYS]->(p)
            SET r += $rel_props
            """
            pays_params = {
                "fournisseur_id": graph_id,
                "pays_id": pays_graph_id,
                "raw_pays_id": id_pays,
                "nom_pays": nom_pays,
                "code_iso": code_iso,
                "rel_props": rel_props,
            }
            all_statements.append({"query": pays_query, "parameters": pays_params})

    return all_statements


def get_graph_id_from_data(fournisseur_data: Dict[str, Any]) -> str:
    """Extract graph_id from fournisseur data for deadlock detection."""
    id_fournisseur = fournisseur_data.get("id_fournisseur", "unknown")
    return f"id_fournisseur_{id_fournisseur}"
