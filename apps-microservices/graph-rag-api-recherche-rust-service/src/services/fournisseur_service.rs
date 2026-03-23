use serde_json::{json, Value};
use tracing::{error, info, warn};

use crate::infrastructure::clients::CLIENTS;

/// Fournisseur (Supplier) geographic coverage service, mirroring Python's fournisseur_service.py.
pub struct FournisseurService;

impl FournisseurService {
    /// Get geographic coverage for a supplier by fournisseur ID.
    pub async fn get_couverture_by_fournisseur(id_fournisseur: &str) -> Value {
        let query = r#"
            MATCH (f:Fournisseur {id_fournisseur: $id_fournisseur})
            OPTIONAL MATCH (f)-[r_pays:COUVRE_PAYS]->(pays:Pays)
            OPTIONAL MATCH (f)-[r_zone:COUVRE_ZONE]->(zone:ZoneGeo)
            WITH f,
                 collect(DISTINCT {
                     id_pays: pays.id_pays,
                     nom: pays.nom,
                     partiel: r_pays.partiel,
                     couvre_tous: r_pays.couvre_tous,
                     couvre: r_pays.couvre,
                     ne_couvre_pas: r_pays.ne_couvre_pas
                 }) AS pays_coverage,
                 collect(DISTINCT {
                     id_dept: zone.id_dept,
                     nom: zone.nom,
                     couvre_tous: r_zone.couvre_tous,
                     couvre: r_zone.couvre,
                     ne_couvre_pas: r_zone.ne_couvre_pas
                 }) AS zone_coverage
            RETURN {
                id_fournisseur: f.id_fournisseur,
                nom: f.nom,
                pays: pays_coverage,
                zones: zone_coverage
            } AS couverture
        "#;

        let params = json!({ "id_fournisseur": id_fournisseur });

        let results = CLIENTS.execute_cypher(query, &params).await;

        if let Some(first) = results.first() {
            first.get("couverture").cloned().unwrap_or(json!(null))
        } else {
            json!(null)
        }
    }

    /// Get geographic coverage for a supplier by product ID.
    pub async fn get_couverture_by_produit(id_produit: &str) -> Value {
        let query = r#"
            MATCH (p:Produit {id_produit: $id_produit})-[:EST_PROPOSE_PAR]->(f:Fournisseur)
            OPTIONAL MATCH (f)-[r_pays:COUVRE_PAYS]->(pays:Pays)
            OPTIONAL MATCH (f)-[r_zone:COUVRE_ZONE]->(zone:ZoneGeo)
            WITH f,
                 collect(DISTINCT {
                     id_pays: pays.id_pays,
                     nom: pays.nom,
                     partiel: r_pays.partiel,
                     couvre_tous: r_pays.couvre_tous,
                     couvre: r_pays.couvre,
                     ne_couvre_pas: r_pays.ne_couvre_pas
                 }) AS pays_coverage,
                 collect(DISTINCT {
                     id_dept: zone.id_dept,
                     nom: zone.nom,
                     couvre_tous: r_zone.couvre_tous,
                     couvre: r_zone.couvre,
                     ne_couvre_pas: r_zone.ne_couvre_pas
                 }) AS zone_coverage
            RETURN {
                id_fournisseur: f.id_fournisseur,
                nom: f.nom,
                pays: pays_coverage,
                zones: zone_coverage
            } AS couverture
        "#;

        let params = json!({ "id_produit": id_produit });

        let results = CLIENTS.execute_cypher(query, &params).await;

        if let Some(first) = results.first() {
            first.get("couverture").cloned().unwrap_or(json!(null))
        } else {
            json!(null)
        }
    }
}
