use serde_json::{json, Value};
use std::collections::HashMap;
use tracing::{error, info, warn};

use crate::infrastructure::clients::CLIENTS;
use crate::infrastructure::llm_service::LlmService;
use crate::services::rag_components;

/// CypherBuilderService: translates natural language queries into Cypher queries.
/// Mirrors Python's cypher_builder.py.
pub struct CypherBuilderService;

/// Relationship direction definitions for graph traversal.
const RELATIONSHIP_DIRECTIONS: &[(&str, &str, &str)] = &[
    ("Produit", "A_POUR_CARACTERISTIQUE", "CaracteristiqueTechnique"),
    ("Produit", "EST_PROPOSE_PAR", "Fournisseur"),
    ("Produit", "APPARTIENT_A", "Categorie"),
    ("Fournisseur", "COUVRE_PAYS", "Pays"),
    ("Fournisseur", "COUVRE_ZONE", "ZoneGeo"),
    ("Fournisseur", "COUVRE", "Reponse"),
    ("Reponse", "PROPOSE", "Question"),
    ("CaracteristiqueTechnique", "EQUIVAUT_A", "Reponse"),
];

impl CypherBuilderService {
    /// Extract entities from a query using LLM.
    pub async fn extract_entities(query: &str) -> Vec<Value> {
        let prompt = rag_components::ENTITY_EXTRACTION_PROMPT.replace("{query}", query);

        match LlmService::generate_answer(&prompt).await {
            Ok(response) => {
                // Try to parse the JSON response
                let cleaned = response
                    .trim()
                    .trim_start_matches("```json")
                    .trim_start_matches("```")
                    .trim_end_matches("```")
                    .trim();

                match serde_json::from_str::<Value>(cleaned) {
                    Ok(json) => {
                        if let Some(entities) = json.get("entities").and_then(|e| e.as_array()) {
                            entities.clone()
                        } else {
                            vec![]
                        }
                    }
                    Err(e) => {
                        warn!("Failed to parse entity extraction response: {}", e);
                        vec![]
                    }
                }
            }
            Err(e) => {
                error!("Entity extraction failed: {}", e);
                vec![]
            }
        }
    }

    /// Perform semantic expansion of entities using vector search.
    pub async fn semantic_expansion(
        entities: &[Value],
        top_k: i32,
        threshold: f32,
    ) -> Vec<Value> {
        let mut expanded = vec![];

        for entity in entities {
            let entity_text = entity
                .get("value")
                .and_then(|v| v.as_str())
                .unwrap_or("");

            if entity_text.is_empty() {
                continue;
            }

            let entity_type = entity
                .get("type")
                .and_then(|v| v.as_str())
                .unwrap_or("Produit");

            // Get embedding for the entity
            let embedding = CLIENTS.get_embedding_vector(entity_text).await;
            if embedding.is_empty() {
                continue;
            }

            // Search similar entities in Milvus
            let similar = CLIENTS
                .search_milvus_entities(embedding, entity_type, top_k, threshold)
                .await;

            for result in similar {
                expanded.push(json!({
                    "type": entity_type,
                    "value": result.id,
                    "distance": result.distance,
                    "source": "semantic_expansion"
                }));
            }
        }

        expanded
    }

    /// Build a WHERE clause from extracted entities.
    pub fn build_where_clause(entities: &[Value]) -> (String, HashMap<String, Value>) {
        let mut conditions = vec![];
        let mut params = HashMap::new();
        let mut param_idx = 0;

        for entity in entities {
            let entity_type = entity
                .get("type")
                .and_then(|v| v.as_str())
                .unwrap_or("");
            let entity_value = entity.get("value").and_then(|v| v.as_str()).unwrap_or("");

            if entity_value.is_empty() {
                continue;
            }

            match entity_type {
                "Produit" => {
                    let param_name = format!("p_val_{}", param_idx);
                    conditions.push(format!(
                        "(toLower(p.nom_produit) CONTAINS toLower(${})\
                         OR toLower(p.titre) CONTAINS toLower(${}))",
                        param_name, param_name
                    ));
                    params.insert(param_name, json!(entity_value));
                    param_idx += 1;
                }
                "Caractéristique" | "Caracteristique" => {
                    let param_name = format!("c_val_{}", param_idx);
                    conditions.push(format!(
                        "toLower(c.label) CONTAINS toLower(${})",
                        param_name
                    ));
                    params.insert(param_name, json!(entity_value));

                    // If there's an associated value
                    if let Some(valeur) = entity.get("valeur").and_then(|v| v.as_str()) {
                        let val_param = format!("cv_val_{}", param_idx);
                        conditions.push(format!(
                            "(c.valeur = ${} OR c.valeur_canonique = ${})",
                            val_param, val_param
                        ));
                        params.insert(val_param, json!(valeur));
                    }
                    param_idx += 1;
                }
                "Catégorie" | "Categorie" => {
                    let param_name = format!("cat_val_{}", param_idx);
                    conditions.push(format!(
                        "toLower(cat.nom) CONTAINS toLower(${})",
                        param_name
                    ));
                    params.insert(param_name, json!(entity_value));
                    param_idx += 1;
                }
                _ => {}
            }
        }

        let where_str = if conditions.is_empty() {
            String::new()
        } else {
            format!("WHERE {}", conditions.join(" AND "))
        };

        (where_str, params)
    }

    /// Build a complete Cypher query from entities.
    pub fn build_cypher_query(entities: &[Value], top_k: i32) -> (String, Value) {
        let (where_clause, params_map) = Self::build_where_clause(entities);

        let has_product = entities
            .iter()
            .any(|e| e.get("type").and_then(|t| t.as_str()) == Some("Produit"));
        let has_carac = entities.iter().any(|e| {
            let t = e.get("type").and_then(|t| t.as_str()).unwrap_or("");
            t == "Caractéristique" || t == "Caracteristique"
        });

        let query = if has_carac {
            format!(
                "MATCH (p:Produit)-[:A_POUR_CARACTERISTIQUE]->(c:CaracteristiqueTechnique)\n\
                 {}\n\
                 RETURN p {{.*}} AS product_data, \
                 collect(c {{.*}}) AS caracteristiques\n\
                 ORDER BY p.nom_produit\n\
                 LIMIT $top_k",
                where_clause
            )
        } else if has_product {
            format!(
                "MATCH (p:Produit)\n\
                 {}\n\
                 RETURN p {{.*}} AS product_data\n\
                 ORDER BY p.nom_produit\n\
                 LIMIT $top_k",
                where_clause
            )
        } else {
            format!(
                "MATCH (p:Produit)\n\
                 RETURN p {{.*}} AS product_data\n\
                 ORDER BY p.nom_produit\n\
                 LIMIT $top_k"
            )
        };

        let mut params = json!({ "top_k": top_k });
        if let Some(obj) = params.as_object_mut() {
            for (k, v) in params_map {
                obj.insert(k, v);
            }
        }

        (query, params)
    }
}
