use serde_json::{json, Value};
use tracing::{error, info};

use crate::infrastructure::clients::CLIENTS;

/// Product service for characteristics and deletion, mirroring Python's product_service.py.
pub struct ProductService;

impl ProductService {
    /// Get characteristics for a product by ID.
    pub async fn get_caracteristiques(id_produit: &str) -> Vec<Value> {
        let query = r#"
            MATCH (p:Produit {id_produit: $id_produit})-[:A_POUR_CARACTERISTIQUE]->(c:CaracteristiqueTechnique)
            RETURN c {
                .id_source_caracteristique,
                .label,
                .valeur,
                .valeur_min,
                .valeur_max,
                .unite,
                .unite_canonique,
                .valeur_canonique,
                .valeur_min_canonique,
                .valeur_max_canonique,
                .type_donnee,
                .id_source_valeur
            } AS caracteristique
            ORDER BY c.label
        "#;

        let formatted_id = if id_produit.starts_with("id_produit_") {
            id_produit.to_string()
        } else {
            format!("id_produit_{}", id_produit)
        };

        let params = json!({ "id_produit": formatted_id });
        let results = CLIENTS.execute_cypher(query, &params).await;

        results
            .into_iter()
            .filter_map(|r| r.get("caracteristique").cloned())
            .collect()
    }

    /// Delete a product and its relationships.
    pub async fn delete_product(id_produit: &str) -> (bool, String) {
        let formatted_id = if id_produit.starts_with("id_produit_") {
            id_produit.to_string()
        } else {
            format!("id_produit_{}", id_produit)
        };

        let query = r#"
            MATCH (p:Produit {id_produit: $id_produit})
            OPTIONAL MATCH (p)-[r]-()
            DELETE r, p
            RETURN count(p) AS deleted_count
        "#;

        let params = json!({ "id_produit": formatted_id });

        match CLIENTS.execute_cypher(query, &params).await.first() {
            Some(result) => {
                let count = result
                    .get("deleted_count")
                    .and_then(|v| v.as_i64())
                    .unwrap_or(0);
                if count > 0 {
                    (true, format!("Product {} deleted successfully", id_produit))
                } else {
                    (false, format!("Product {} not found", id_produit))
                }
            }
            None => (false, "Failed to execute delete query".to_string()),
        }
    }
}
