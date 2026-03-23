use serde_json::{json, Value};
use tracing::{error, info, warn};

use crate::infrastructure::clients::CLIENTS;

/// Node service for CRUD operations on graph nodes, mirroring Python's node_service.py.
pub struct NodeService;

impl NodeService {
    /// Format a node ID based on the label convention: "{label_lower}_{id}"
    fn format_node_id(label: &str, id: &str) -> String {
        let prefix = label.to_lowercase();
        if id.starts_with(&format!("{}_", prefix)) {
            id.to_string()
        } else {
            format!("{}_{}", prefix, id)
        }
    }

    /// Update a node's properties by label and ID.
    pub async fn update_node(
        label: &str,
        id: &str,
        properties: &Value,
    ) -> (bool, Option<Value>, Option<String>) {
        let formatted_id = Self::format_node_id(label, id);
        let id_field = Self::get_id_field(label);

        // Build SET clause from properties
        let props = match properties.as_object() {
            Some(obj) => obj,
            None => return (false, None, Some("Properties must be an object".into())),
        };

        let set_clauses: Vec<String> = props
            .keys()
            .enumerate()
            .map(|(i, key)| format!("n.{} = $prop_{}", key, i))
            .collect();

        if set_clauses.is_empty() {
            return (false, None, Some("No properties to update".into()));
        }

        let query = format!(
            "MATCH (n:{} {{{}: $id}}) SET {} RETURN n {{.*}} AS node",
            label,
            id_field,
            set_clauses.join(", ")
        );

        let mut params = json!({ "id": formatted_id });
        if let Some(obj) = params.as_object_mut() {
            for (i, (_, value)) in props.iter().enumerate() {
                obj.insert(format!("prop_{}", i), value.clone());
            }
        }

        let results = CLIENTS.execute_cypher(&query, &params).await;

        if let Some(first) = results.first() {
            (true, first.get("node").cloned(), None)
        } else {
            (
                false,
                None,
                Some(format!("Node {}:{} not found", label, formatted_id)),
            )
        }
    }

    /// Get the schema (node labels and their properties).
    pub async fn get_schema(label: &str) -> Value {
        let query = if label.is_empty() || label == "*" {
            "CALL db.schema.nodeTypeProperties() YIELD nodeType, propertyName, propertyTypes \
             RETURN nodeType, collect({name: propertyName, types: propertyTypes}) AS properties"
                .to_string()
        } else {
            format!(
                "CALL db.schema.nodeTypeProperties() YIELD nodeType, propertyName, propertyTypes \
                 WHERE nodeType CONTAINS '{}' \
                 RETURN nodeType, collect({{name: propertyName, types: propertyTypes}}) AS properties",
                label
            )
        };

        let results = CLIENTS.execute_cypher(&query, &json!({})).await;
        json!(results)
    }

    /// Get a single node by label and ID.
    pub async fn get_node(label: &str, id: &str) -> Option<Value> {
        let formatted_id = Self::format_node_id(label, id);
        let id_field = Self::get_id_field(label);

        let query = format!(
            "MATCH (n:{} {{{}: $id}}) RETURN n {{.*}} AS node",
            label, id_field
        );

        let params = json!({ "id": formatted_id });
        let results = CLIENTS.execute_cypher(&query, &params).await;

        results.first().and_then(|r| r.get("node").cloned())
    }

    /// Get the ID field name for a given label.
    fn get_id_field(label: &str) -> String {
        match label {
            "Produit" => "id_produit".to_string(),
            "Fournisseur" => "id_fournisseur".to_string(),
            "CaracteristiqueTechnique" => "id_source_caracteristique".to_string(),
            "Categorie" => "id_categorie".to_string(),
            "Pays" => "id_pays".to_string(),
            "ZoneGeo" => "id_dept".to_string(),
            _ => format!("id_{}", label.to_lowercase()),
        }
    }
}
