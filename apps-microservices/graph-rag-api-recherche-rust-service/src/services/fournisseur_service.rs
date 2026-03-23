use serde_json::{json, Value};
use tracing::{error, info};

use crate::domain::models::{
    DepartementCouverture, FournisseurGeoResponse, PaysCouverture,
};
use crate::infrastructure::clients::CLIENTS;

/// Fournisseur (Supplier) geographic coverage service, mirroring Python's fournisseur_service.py.
pub struct FournisseurService;

impl FournisseurService {
    /// Get geographic coverage for a supplier by fournisseur ID.
    pub async fn get_couverture_by_fournisseur(
        id_fournisseur: &str,
    ) -> Option<FournisseurGeoResponse> {
        let query = r#"
            MATCH (f:Fournisseur {id_fournisseur: $id_fournisseur})

            // Collect related Pays
            OPTIONAL MATCH (f)-[r_pays:COUVRE_PAYS]->(p:Pays)
            WITH f, collect({
                id_pays: p.id_pays,
                nom_pays: p.nom_pays,
                couvre_partiel: coalesce(r_pays.partiel, false)
            }) as pays_list

            // Collect related ZoneGeo (Departements)
            OPTIONAL MATCH (f)-[:COUVRE_ZONE]->(z:ZoneGeo)
            WITH pays_list, collect({
                id_dept: z.id_dept,
                nom_dept: z.nom_dept
            }) as dept_list

            RETURN pays_list, dept_list
        "#;

        let params = json!({ "id_fournisseur": id_fournisseur });
        let results = CLIENTS.execute_cypher(query, &params).await;

        if results.is_empty() {
            info!("Fournisseur with ID '{}' not found.", id_fournisseur);
            return None;
        }

        let record = &results[0];
        Some(Self::parse_geo_response(record))
    }

    /// Get geographic coverage for a supplier by product ID.
    pub async fn get_couverture_by_produit(
        id_produit: &str,
    ) -> Option<FournisseurGeoResponse> {
        // 1. Get id_fournisseur from Product
        let query_product = r#"
            MATCH (p:Produit {id_produit: $id_produit})
            RETURN p.id_fournisseur as id_fournisseur
        "#;
        let params = json!({ "id_produit": id_produit });
        let results = CLIENTS.execute_cypher(query_product, &params).await;

        if results.is_empty() {
            info!("Product with ID '{}' not found.", id_produit);
            return None;
        }

        let id_fournisseur = results[0]
            .get("id_fournisseur")
            .and_then(|v| v.as_str())
            .or_else(|| results[0].get("id_fournisseur").and_then(|v| v.as_i64()).map(|_| ""))
            .unwrap_or("");

        if id_fournisseur.is_empty() {
            // Try as number
            if let Some(id_num) = results[0].get("id_fournisseur").and_then(|v| v.as_i64()) {
                let id_str = id_num.to_string();
                return Self::get_couverture_by_fournisseur(&id_str).await;
            }
            info!("Product '{}' has no associated 'id_fournisseur'.", id_produit);
            return None;
        }

        // 2. Use existing method to get coverage
        Self::get_couverture_by_fournisseur(id_fournisseur).await
    }

    fn parse_geo_response(record: &Value) -> FournisseurGeoResponse {
        // Parse Pays
        let pays = record
            .get("pays_list")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|p| {
                        let id_pays = p.get("id_pays")?;
                        if id_pays.is_null() {
                            return None;
                        }
                        Some(PaysCouverture {
                            id_pays: match id_pays {
                                Value::Number(n) => n.to_string(),
                                Value::String(s) => s.clone(),
                                _ => return None,
                            },
                            nom_pays: p
                                .get("nom_pays")
                                .and_then(|v| v.as_str())
                                .unwrap_or("")
                                .to_string(),
                            couvre_partiel: p
                                .get("couvre_partiel")
                                .and_then(|v| v.as_bool())
                                .unwrap_or(false),
                        })
                    })
                    .collect()
            })
            .unwrap_or_default();

        // Parse Departements
        let departements = record
            .get("dept_list")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|d| {
                        let id_dept = d.get("id_dept")?;
                        if id_dept.is_null() {
                            return None;
                        }
                        Some(DepartementCouverture {
                            id_dept: match id_dept {
                                Value::Number(n) => n.to_string(),
                                Value::String(s) => s.clone(),
                                _ => return None,
                            },
                            nom_dept: d
                                .get("nom_dept")
                                .and_then(|v| v.as_str())
                                .unwrap_or("")
                                .to_string(),
                        })
                    })
                    .collect()
            })
            .unwrap_or_default();

        FournisseurGeoResponse { pays, departements }
    }
}
