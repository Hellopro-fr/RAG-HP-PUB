use regex::Regex;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::time::Instant;
use tracing::{error, info, warn};

use crate::domain::models::*;
use crate::infrastructure::clients::CLIENTS;
use crate::infrastructure::gemini_client::GEMINI_CLIENT;
use crate::infrastructure::hellopro_api_client::HELLOPRO_CLIENT;

/// Recommendation Service: implements V4 Hybrid Recommendation Logic.
/// This is the Rust port of Python's recommendation_service.py (2414 lines).
pub struct RecommendationService;

// =========================================================================
// Centralized Cypher Query Constants
// =========================================================================

/// CYPHER_STEP1_TARGET: match a specific target product
const CYPHER_STEP1_TARGET: &str = r#"
    MATCH (p:Produit)
    WHERE toString(p.id) = $target_product_id AND p.est_actif = true
    WITH p, $filters AS active_filters
"#;

/// CYPHER_STEP1_ANCHOR: anchor traversal using filters
const CYPHER_STEP1_ANCHOR: &str = r#"
    UNWIND $filters AS f
    MATCH (pc:CaracteristiqueTechnique)
    WHERE toString(pc.id_source_caracteristique) = f.cid
    MATCH (p:Produit)-[:A_POUR_CARACTERISTIQUE]->(pc)

    WHERE ($id_categorie IS NULL OR p.id_categorie = $id_categorie) AND p.est_actif = true

    WITH DISTINCT p, $filters AS active_filters
"#;

// Note: CYPHER_STEP2_SCORING is extremely long (600+ lines of Cypher).
// It is loaded as a static string constant to be combined with Step 1.
const CYPHER_STEP2_SCORING: &str = include_str!("cypher_step2_scoring.cypher");

impl RecommendationService {
    // =====================================================================
    // Helper Methods
    // =====================================================================

    fn extract_scalar(value: &Value) -> Value {
        match value {
            Value::Array(arr) if !arr.is_empty() => arr[0].clone(),
            _ => value.clone(),
        }
    }

    /// Get characteristic labels from the graph DB.
    async fn get_characteristic_labels(char_ids: &[String]) -> HashMap<String, String> {
        if char_ids.is_empty() {
            return HashMap::new();
        }
        let query = r#"
            MATCH (c:CaracteristiqueTechnique)
            WHERE c.id_source_caracteristique IN $ids
            RETURN DISTINCT c.id_source_caracteristique as id, c.label as label
        "#;
        let params = json!({ "ids": char_ids });
        let results = CLIENTS.execute_cypher(query, &params).await;
        let mut map = HashMap::new();
        for row in results {
            if let (Some(id), Some(label)) = (
                row.get("id").and_then(|v| v.as_str()),
                row.get("label").and_then(|v| v.as_str()),
            ) {
                map.insert(id.to_string(), label.to_string());
            }
        }
        map
    }

    /// Normalize a single constraint's numeric values in parallel.
    async fn normalize_single_constraint(
        c: &Value,
        label: &str,
    ) -> Value {
        let unit = c.get("unite").and_then(|u| u.as_str()).unwrap_or("");
        let char_id = c
            .get("id_caracteristique")
            .map(|v| v.to_string().trim_matches('"').to_string())
            .unwrap_or_default();

        let mut target_num: Option<Value> = None;
        let mut blocking_num: Option<Value> = None;

        // Normalize target numeric
        if let Some(raw_target) = c.get("valeurs_cibles") {
            if raw_target.is_object() {
                let mut norm = json!({"unit": null, "min": null, "max": null, "exact": null});
                for k in &["min", "max", "exact"] {
                    if let Some(val) = raw_target.get(k) {
                        if !val.is_null() {
                            let v = Self::extract_scalar(val);
                            let val_str = match &v {
                                Value::Number(n) => n.to_string(),
                                Value::String(s) => s.clone(),
                                _ => v.to_string(),
                            };
                            if let Some(result) = CLIENTS
                                .normalize_quantity(&val_str, Some(unit), label)
                                .await
                            {
                                norm[k] = json!(result.valeur_canonique);
                                norm["unit"] = json!(result.unite_canonique);
                            }
                        }
                    }
                }
                if !norm["unit"].is_null() {
                    target_num = Some(norm);
                }
            }
        }

        // Normalize blocking numeric
        if let Some(raw_blocking) = c.get("valeurs_bloquantes") {
            if raw_blocking.is_object() {
                let mut norm = json!({"unit": null, "min": null, "max": null, "exact": null});
                for k in &["min", "max", "exact"] {
                    if let Some(val) = raw_blocking.get(k) {
                        if !val.is_null() {
                            let v = Self::extract_scalar(val);
                            let val_str = match &v {
                                Value::Number(n) => n.to_string(),
                                Value::String(s) => s.clone(),
                                _ => v.to_string(),
                            };
                            if let Some(result) = CLIENTS
                                .normalize_quantity(&val_str, Some(unit), label)
                                .await
                            {
                                norm[k] = json!(result.valeur_canonique);
                                norm["unit"] = json!(result.unite_canonique);
                            }
                        }
                    }
                }
                if !norm["unit"].is_null() {
                    blocking_num = Some(norm);
                }
            }
        }

        // Build target_list / blocking_list
        let target_list = match c.get("valeurs_cibles") {
            Some(Value::Array(arr)) => arr
                .iter()
                .map(|x| json!(x.to_string().trim_matches('"')))
                .collect::<Vec<_>>(),
            _ => vec![],
        };
        let blocking_list = match c.get("valeurs_bloquantes") {
            Some(Value::Array(arr)) => arr
                .iter()
                .map(|x| json!(x.to_string().trim_matches('"')))
                .collect::<Vec<_>>(),
            _ => vec![],
        };

        json!({
            "id_caracteristique": char_id,
            "target_list": target_list,
            "blocking_list": blocking_list,
            "target_numeric": target_num,
            "blocking_numeric": blocking_num,
        })
    }

    // =====================================================================
    // Normalize constraints for UNWIND (ComplexFilterRequest)
    // =====================================================================

    async fn normalize_constraints_for_unwind(
        request: &ComplexFilterRequest,
    ) -> Vec<Value> {
        let all_char_ids: Vec<String> = request
            .ids
            .values()
            .flat_map(|constraints| {
                constraints
                    .iter()
                    .map(|c| c.id_caracteristique.to_string().trim_matches('"').to_string())
            })
            .collect();

        let label_map = Self::get_characteristic_labels(&all_char_ids).await;

        let mut flat_filters = vec![];
        for (rid, constraints) in &request.ids {
            let mut group_constraints = vec![];
            for c in constraints {
                let char_id = c.id_caracteristique.to_string().trim_matches('"').to_string();
                let label = label_map.get(&char_id).map(|s| s.as_str()).unwrap_or("dimensionless");
                let c_val = serde_json::to_value(c).unwrap_or(json!({}));
                let normalized = Self::normalize_single_constraint(&c_val, label).await;
                group_constraints.push(normalized);
            }
            flat_filters.push(json!({
                "rid": rid,
                "constraints": group_constraints,
            }));
        }
        flat_filters
    }

    // =====================================================================
    // Normalize constraints for Caracteristique (MatchingPayload)
    // =====================================================================

    async fn normalize_constraints_for_caracteristique(
        request: &MatchingPayloadIdProduit,
    ) -> Vec<Value> {
        let all_char_ids: Vec<String> = request
            .liste_caracteristique
            .iter()
            .map(|c| c.id_caracteristique.to_string().trim_matches('"').to_string())
            .collect();

        let label_map = Self::get_characteristic_labels(&all_char_ids).await;

        let score_options = request.options.as_ref().and_then(|o| o.score.as_ref());
        let critique_weight = score_options.and_then(|s| s.critique).unwrap_or(5);
        let secondaire_weight = score_options.and_then(|s| s.secondaire).unwrap_or(1);

        let mut grouped: HashMap<String, Value> = HashMap::new();

        for c in &request.liste_caracteristique {
            let cid = c.id_caracteristique.to_string().trim_matches('"').to_string();
            let label = label_map.get(&cid).map(|s| s.as_str()).unwrap_or("dimensionless");
            let c_val = serde_json::to_value(c).unwrap_or(json!({}));
            let mut normalized = Self::normalize_single_constraint(&c_val, label).await;

            let poids_carac = c.poids_caracteristique.as_deref().unwrap_or("critique");
            let c_weight = if poids_carac == "secondaire" {
                secondaire_weight
            } else {
                critique_weight
            };
            let q_weight = c.poids_question.unwrap_or(1);

            if let Some(obj) = normalized.as_object_mut() {
                obj.insert("c_weight".to_string(), json!(c_weight));
            }

            let entry = grouped.entry(cid.clone()).or_insert_with(|| {
                json!({ "cid": cid, "q_weight": q_weight, "constraints": [] })
            });
            if let Some(constraints) = entry.get_mut("constraints").and_then(|c| c.as_array_mut()) {
                constraints.push(normalized);
            }
        }

        grouped.into_values().collect()
    }

    // =====================================================================
    // Scoring Parameters
    // =====================================================================

    fn extract_scoring_params(request: &MatchingPayloadIdProduit) -> Value {
        let s = request.get_scoring();
        json!({
            "blocked_val": s.v_blocked.unwrap_or(-2.0),
            "different_val": s.v_different.unwrap_or(-0.3),
            "z_unmatched": s.z_unmatched.unwrap_or(0.0),
            "e_unmatched": s.e_unmatched.unwrap_or(0.9),
            "g_unknown_score": s.g_unknown_score.unwrap_or(0.8),
            "c_unknown_score": s.c_unknown_score.unwrap_or(0.0),
            "t_unmatched": s.t_unmatched.unwrap_or(0.2),
            "absolute_threshold": s.absolute_threshold.unwrap_or(0.3),
            "relative_tolerance": s.relative_tolerance.unwrap_or(0.1),
            "max_per_supplier_primary": s.max_per_supplier_primary.unwrap_or(10),
            "max_per_supplier_extended": s.max_per_supplier_extended.unwrap_or(20),
            "score_step": s.score_step.unwrap_or(0.1),
            "diversity_lambda": s.diversity_lambda.unwrap_or(0.7),
        })
    }

    // =====================================================================
    // Build Cypher Query
    // =====================================================================

    fn build_cypher_query(
        request: &MatchingPayloadIdProduit,
        target_product_id: Option<&str>,
    ) -> String {
        let step1 = if target_product_id.is_some() {
            CYPHER_STEP1_TARGET
        } else {
            CYPHER_STEP1_ANCHOR
        };

        let mut query = format!("{}\n{}", step1, CYPHER_STEP2_SCORING);

        // Ensure required output fields
        let mut champs = request.champs_sortie.clone().unwrap_or_default();
        if !champs.is_empty() {
            if !champs.contains(&"id_produit".to_string()) {
                champs.push("id_produit".to_string());
            }
            if !champs.contains(&"id_fournisseur".to_string()) {
                champs.push("id_fournisseur".to_string());
            }
        }

        // Build projection
        let projection = if !champs.is_empty() {
            let fields: Vec<String> = champs.iter().map(|f| format!(".{}", f)).collect();
            format!("{{ {} }}", fields.join(", "))
        } else {
            "{.*}".to_string()
        };

        query = query.replace("TOP_P_PROJECTION_PLACEHOLDER", &projection);
        query = query.replace("PROJECTION_PLACEHOLDER", &projection);
        query
    }

    // =====================================================================
    // Build Cypher Params
    // =====================================================================

    fn build_cypher_params(
        request: &MatchingPayloadIdProduit,
        flat_filters: &[Value],
        weights_map: &Value,
        scoring_params: &Value,
        top_k: i32,
        target_product_id: Option<&str>,
    ) -> Value {
        let user_meta = request.metadonnee_utilisateurs.as_ref();
        let user_cp = user_meta.and_then(|m| m.cp.as_deref());
        let user_dept = user_cp.filter(|cp| cp.len() >= 2).map(|cp| &cp[..2]);
        let user_id_pays = user_meta.and_then(|m| m.id_pays.as_ref());
        let user_typologie = user_meta.and_then(|m| m.typologie.as_ref());

        let target_id = request.id_produit.as_ref().map(|id| {
            format!("id_produit_{}", id.to_string().trim_matches('"'))
        });

        json!({
            "filters": flat_filters,
            "weights": weights_map,
            "id_categorie": request.id_categorie.as_ref().map(|v| v.to_string().trim_matches('"').to_string()),
            "top_k": top_k,
            "target_product_id": target_id,
            "blocked_val": scoring_params["blocked_val"],
            "different_val": scoring_params["different_val"],
            "user_dept": user_dept,
            "user_id_pays": user_id_pays,
            "z_unmatched": scoring_params["z_unmatched"],
            "e_unmatched": scoring_params["e_unmatched"],
            "g_unknown_score": scoring_params["g_unknown_score"],
            "c_unknown_score": scoring_params["c_unknown_score"],
            "user_typologie": user_typologie,
            "t_unmatched": scoring_params["t_unmatched"],
            "absolute_threshold": scoring_params["absolute_threshold"],
            "relative_tolerance": scoring_params["relative_tolerance"],
            "max_per_supplier_primary": scoring_params["max_per_supplier_primary"],
            "max_per_supplier_extended": scoring_params["max_per_supplier_extended"],
            "score_step": scoring_params["score_step"],
            "diversity_lambda": scoring_params["diversity_lambda"],
        })
    }

    // =====================================================================
    // Parse Matching Results
    // =====================================================================

    fn convert_to_caracteristique_matching(
        details: &[Value],
        blocked_val: f64,
        different_val: f64,
    ) -> Vec<CaracteristiqueMatching> {
        let mut caracs = vec![];
        for detail in details {
            let q_weight = detail.get("q_weight").and_then(|v| v.as_i64()).unwrap_or(1) as i32;
            let constraints = detail.get("constraints").and_then(|c| c.as_array());
            if let Some(constraints) = constraints {
                for constraint in constraints {
                    let cid = constraint.get("cid").and_then(|v| v.as_str()).unwrap_or("0");
                    let c_score = constraint.get("score").and_then(|v| v.as_f64()).unwrap_or(0.0);
                    let c_weight = constraint.get("c_weight_sum").and_then(|v| v.as_i64()).unwrap_or(1) as i32;
                    let matched_nodes = constraint.get("matched_nodes").and_then(|v| v.as_array());

                    let statut = if c_score >= 0.8 {
                        1 // Matche
                    } else if (c_score - blocked_val).abs() < f64::EPSILON {
                        3 // Bloquant
                    } else if (c_score - different_val).abs() < f64::EPSILON {
                        2 // Ecart
                    } else if matched_nodes.map(|n| n.is_empty()).unwrap_or(true) {
                        4 // Non renseigné
                    } else {
                        2 // Ecart
                    };

                    let mut valeur = None;
                    let mut valeur_min = None;
                    let mut valeur_max = None;
                    let mut unite = None;
                    let mut type_carac = 2;
                    let mut id_valeurs = vec![];

                    if let Some(nodes) = matched_nodes {
                        if !nodes.is_empty() {
                            // Pick best-scoring node
                            let node = nodes
                                .iter()
                                .max_by(|a, b| {
                                    let sa = a.get("node_score").and_then(|v| v.as_f64()).unwrap_or(0.0);
                                    let sb = b.get("node_score").and_then(|v| v.as_f64()).unwrap_or(0.0);
                                    sa.partial_cmp(&sb).unwrap_or(std::cmp::Ordering::Equal)
                                })
                                .unwrap();

                            let type_donnee = node.get("type_donnee").and_then(|v| v.as_str()).unwrap_or("");
                            if type_donnee != "text" {
                                valeur = node.get("valeur").and_then(|v| v.as_str()).map(|s| s.to_string());
                                valeur_min = node.get("valeur_min").and_then(|v| v.as_str()).map(|s| s.to_string());
                                valeur_max = node.get("valeur_max").and_then(|v| v.as_str()).map(|s| s.to_string());
                            }
                            unite = node
                                .get("unite")
                                .or_else(|| node.get("unite_canonique"))
                                .and_then(|v| v.as_str())
                                .map(|s| s.to_string());

                            type_carac = if type_donnee == "numeric" || type_donnee == "numeric_range" { 1 } else { 2 };

                            if let Some(id_val) = node.get("id_source_valeur").and_then(|v| v.as_i64()) {
                                id_valeurs.push(id_val);
                            }
                        }
                    }

                    caracs.push(CaracteristiqueMatching {
                        statut_matching: statut,
                        id_caracteristique: cid.parse::<i64>().unwrap_or(0),
                        type_caracteristique: type_carac,
                        valeur,
                        valeur_min,
                        valeur_max,
                        unite,
                        id_valeur: id_valeurs,
                        poids: c_weight,
                        bareme: c_score,
                        poids_question: q_weight,
                    });
                }
            }
        }
        caracs
    }

    fn parse_matching_results(
        results: &[Value],
        request: &MatchingPayloadIdProduit,
        blocked_val: f64,
        different_val: f64,
    ) -> (Vec<Produit>, Vec<Produit>) {
        let mut liste_produit = vec![];
        let mut top_produit = vec![];
        let has_champs = request.champs_sortie.as_ref().map(|c| !c.is_empty()).unwrap_or(false);

        if results.is_empty() {
            return (liste_produit, top_produit);
        }

        // Extract top_p from first result
        if let Some(raw_top_p) = results[0].get("top_p").and_then(|v| v.as_array()) {
            for (idx, entry) in raw_top_p.iter().enumerate() {
                if let Some(product_data) = entry.get("product_data") {
                    let details = entry.get("details").and_then(|v| v.as_array()).cloned().unwrap_or_default();
                    let caracs = Self::convert_to_caracteristique_matching(&details, blocked_val, different_val);

                    top_produit.push(Produit {
                        rang: (idx + 1) as i32,
                        id_produit: product_data.get("id_produit").map(|v| v.to_string().trim_matches('"').to_string()).unwrap_or_default(),
                        score: entry.get("score").and_then(|v| v.as_f64()).unwrap_or(0.0),
                        caracteristique: Some(caracs),
                        info_produit: if has_champs { Some(product_data.clone()) } else { None },
                        coeff_geo: entry.get("zone_score").and_then(|v| v.as_f64()).unwrap_or(1.0),
                        coeff_type_frns: entry.get("typo_score").and_then(|v| v.as_f64()).unwrap_or(1.0),
                        coeff_etat_score: entry.get("etat_score").and_then(|v| v.as_f64()).unwrap_or(1.0),
                        coeff_caracteristique: entry.get("global_score").and_then(|v| v.as_f64()).unwrap_or(0.0),
                        llm_response: None,
                    });
                }
            }
        }

        // Build liste_produit
        for (idx, rec) in results.iter().enumerate() {
            if let Some(product_data) = rec.get("product_data") {
                let details = rec.get("details").and_then(|v| v.as_array()).cloned().unwrap_or_default();
                let caracs = Self::convert_to_caracteristique_matching(&details, blocked_val, different_val);

                liste_produit.push(Produit {
                    rang: (idx + 1) as i32,
                    id_produit: product_data.get("id_produit").map(|v| v.to_string().trim_matches('"').to_string()).unwrap_or_default(),
                    score: rec.get("final_score").and_then(|v| v.as_f64()).unwrap_or(0.0),
                    caracteristique: Some(caracs),
                    info_produit: if has_champs { Some(product_data.clone()) } else { None },
                    coeff_geo: rec.get("zone_score").and_then(|v| v.as_f64()).unwrap_or(1.0),
                    coeff_type_frns: rec.get("typo_score").and_then(|v| v.as_f64()).unwrap_or(1.0),
                    coeff_etat_score: rec.get("etat_score").and_then(|v| v.as_f64()).unwrap_or(1.0),
                    coeff_caracteristique: rec.get("global_score").and_then(|v| v.as_f64()).unwrap_or(0.0),
                    llm_response: None,
                });
            }
        }

        (liste_produit, top_produit)
    }

    // =====================================================================
    // Complex Filters (V1 flow)
    // =====================================================================

    pub async fn get_products_by_complex_filters(
        request: &ComplexFilterRequest,
        target_product_id: Option<&str>,
    ) -> ResultProduct {
        let start = Instant::now();
        let flat_filters = Self::normalize_constraints_for_unwind(request).await;

        let all_rids: Vec<String> = flat_filters
            .iter()
            .filter_map(|f| f.get("rid").and_then(|v| v.as_str()).map(String::from))
            .collect();
        let weights_map = Self::get_question_weights(&all_rids).await;

        let blocked_val = request.blocked_val;
        let different_val = request.different_val;

        // Build the Cypher query with anchor traversal + classic scoring
        let projection = if let Some(ref fields) = request.output_fields {
            if !fields.is_empty() {
                let f: Vec<String> = fields.iter().map(|f| format!(".{}", f)).collect();
                format!("{{ {} }}", f.join(", "))
            } else {
                "{.*}".to_string()
            }
        } else {
            "{.*}".to_string()
        };

        // Simplified query for complex filters (V1)
        let cypher_query = format!(
            r#"
            UNWIND $filters AS f
            MATCH (r:Reponse {{id_reponse: f.rid}})
            MATCH (r)<-[:EQUIVAUT_A|COUVRE]-(intermediate)<-[:A_POUR_CARACTERISTIQUE|EST_PROPOSE_PAR]-(p:Produit)

            WHERE ($target_product_id IS NULL OR p.id_produit = $target_product_id)
              AND ($id_categorie IS NULL OR p.id_categorie = $id_categorie)

            WITH DISTINCT p, $filters AS active_filters
            UNWIND active_filters AS f
            OPTIONAL MATCH (p)-[:A_POUR_CARACTERISTIQUE]->(pc:CaracteristiqueTechnique)-[:EQUIVAUT_A]->(r:Reponse {{id_reponse: f.rid}})

            WITH p, f, collect(pc) AS pcs
            WITH p, f, [c IN f.constraints | {{
                cid: c.id_caracteristique,
                conf: c,
                matches: [pc IN pcs WHERE toString(pc.id_source_caracteristique) = toString(c.id_caracteristique)]
            }}] AS constraint_data

            WITH p, f, [item IN constraint_data | {{
                cid: item.cid,
                score: CASE
                    WHEN ANY(pc IN item.matches WHERE (size(item.conf.blocking_list) > 0 AND (toString(pc.id_source_valeur) IN item.conf.blocking_list OR toString(pc.valeur) IN item.conf.blocking_list))) THEN $blocked_val
                    WHEN ANY(pc IN item.matches WHERE (size(item.conf.target_list) > 0 AND (toString(pc.id_source_valeur) IN item.conf.target_list OR toString(pc.valeur) IN item.conf.target_list))) THEN 1.0
                    WHEN size(item.matches) > 0 THEN $different_val
                    ELSE 0.1
                END,
                has_pc: size(item.matches) > 0
            }}] AS char_results

            WITH p, f.rid AS rid, char_results,
                [res IN char_results | res.score] AS raw_scores
            WITH p, rid, char_results,
                CASE WHEN $blocked_val IN raw_scores THEN $blocked_val ELSE apoc.coll.max(raw_scores) END AS rid_score,
                coalesce($weights[rid], 1.0) as weight
            WITH p, collect({{rid: rid, score: rid_score, weight: weight}}) AS details
            WITH p, details,
                reduce(s = 0.0, d IN details | s + (d.score * d.weight)) AS numerator,
                reduce(w = 0.0, d IN details | w + d.weight) AS denominator
            WITH p, details, (numerator / denominator) AS global_score
            ORDER BY global_score DESC
            LIMIT $top_k
            WITH collect({{node: p, details: details, global_score: global_score}}) AS all_products
            WITH all_products,
                [fournisseur_id IN apoc.coll.toSet([prod IN all_products | prod.node.id_fournisseur]) |
                    head([prod IN all_products WHERE prod.node.id_fournisseur = fournisseur_id | prod])
                ] AS top_per_fournisseur
            WITH all_products, top_per_fournisseur
            UNWIND top_per_fournisseur AS p_top
            WITH all_products, p_top ORDER BY p_top.global_score DESC LIMIT 4
            WITH all_products, p_top.node AS top_node, p_top.global_score AS top_score, p_top.details AS top_details
            WITH all_products, top_node {projection} AS top_product_data, top_score, top_details
            WITH all_products, collect({{product_data: top_product_data, score: top_score, details: top_details}}) AS top_p
            UNWIND all_products AS prod
            WITH prod.node AS p_node, prod.details AS details, prod.global_score AS global_score, top_p
            RETURN p_node {projection} AS product_data, details, global_score, top_p
            "#,
            projection = projection
        );

        let params = json!({
            "filters": flat_filters,
            "weights": weights_map,
            "id_categorie": request.id_categorie.as_ref().map(|v| v.to_string().trim_matches('"').to_string()),
            "top_k": request.top_k,
            "target_product_id": target_product_id,
            "blocked_val": blocked_val,
            "different_val": different_val,
        });

        let results = CLIENTS.execute_cypher(&cypher_query, &params).await;

        let mut scored_products = vec![];
        let mut top_p = vec![];

        if !results.is_empty() {
            if let Some(raw_top_p) = results[0].get("top_p").and_then(|v| v.as_array()) {
                for entry in raw_top_p {
                    if let Some(pd) = entry.get("product_data") {
                        top_p.push(ScoredProduct {
                            data: pd.clone(),
                            score: entry.get("score").and_then(|v| v.as_f64()).unwrap_or(0.0),
                            details: entry.get("details").and_then(|v| v.as_array()).cloned().unwrap_or_default(),
                            info: Some(json!({"weights": weights_map})),
                        });
                    }
                }
            }

            for rec in &results {
                if let Some(pd) = rec.get("product_data") {
                    scored_products.push(ScoredProduct {
                        data: pd.clone(),
                        score: rec.get("global_score").and_then(|v| v.as_f64()).unwrap_or(0.0),
                        details: rec.get("details").and_then(|v| v.as_array()).cloned().unwrap_or_default(),
                        info: Some(json!({"weights": weights_map})),
                    });
                }
            }
        }

        let total_time = start.elapsed().as_secs_f64();
        ResultProduct {
            data: scored_products,
            info: Some(json!({
                "total_time": total_time,
                "count": results.len(),
                "version": "v4_classic_inverted_rust",
            })),
            top_p: Some(top_p),
        }
    }

    /// Get question weights from the graph DB.
    async fn get_question_weights(rids: &[String]) -> Value {
        if rids.is_empty() {
            return json!({});
        }
        let query = r#"
            MATCH (r:Reponse)<-[:PROPOSE]-(q:Question)
            WHERE r.id_reponse IN $rids
            RETURN r.id_reponse as rid, q.ordre as ordre
        "#;
        let params = json!({ "rids": rids });
        let results = CLIENTS.execute_cypher(query, &params).await;

        let mut rid_to_order: HashMap<String, i64> = HashMap::new();
        for row in &results {
            if let (Some(rid), Some(ordre)) = (
                row.get("rid").and_then(|v| v.as_str()),
                row.get("ordre").and_then(|v| v.as_i64()),
            ) {
                rid_to_order.insert(rid.to_string(), ordre);
            }
        }

        let mut unique_orders: Vec<i64> = rid_to_order.values().cloned().collect();
        unique_orders.sort();
        unique_orders.dedup();
        let total = unique_orders.len() as i64;

        let order_to_weight: HashMap<i64, i64> = unique_orders
            .iter()
            .enumerate()
            .map(|(i, &order)| (order, total - i as i64))
            .collect();

        let mut weights = serde_json::Map::new();
        for (rid, order) in &rid_to_order {
            let weight = order_to_weight.get(order).copied().unwrap_or(1);
            weights.insert(rid.clone(), json!(weight));
        }
        Value::Object(weights)
    }

    // =====================================================================
    // Caracteristique Filters (V4 flow)
    // =====================================================================

    pub async fn get_products_by_caracteristique_filters(
        request: &MatchingPayloadIdProduit,
    ) -> MatchingResponse {
        let start = Instant::now();

        let flat_filters = Self::normalize_constraints_for_caracteristique(request).await;
        let weights_map: Value = flat_filters
            .iter()
            .filter_map(|f| {
                let cid = f.get("cid").and_then(|v| v.as_str())?;
                let qw = f.get("q_weight")?;
                Some((cid.to_string(), qw.clone()))
            })
            .collect::<serde_json::Map<String, Value>>()
            .into();

        let scoring_params = Self::extract_scoring_params(request);
        let blocked_val = scoring_params["blocked_val"].as_f64().unwrap_or(-2.0);
        let different_val = scoring_params["different_val"].as_f64().unwrap_or(-0.3);

        let target_product_id = request.id_produit.as_ref().map(|v| v.to_string().trim_matches('"').to_string());
        let cypher_query = Self::build_cypher_query(request, target_product_id.as_deref());
        let params = Self::build_cypher_params(
            request, &flat_filters, &weights_map, &scoring_params,
            request.top_k, target_product_id.as_deref(),
        );

        match CLIENTS.execute_cypher(&cypher_query, &params).await {
            results if !results.is_empty() => {
                let (liste_produit, top_produit) =
                    Self::parse_matching_results(&results, request, blocked_val, different_val);
                MatchingResponse {
                    top_produit,
                    liste_produit,
                    ecarts: None,
                    temps_de_traitement: start.elapsed().as_secs_f64(),
                }
            }
            _ => MatchingResponse {
                top_produit: vec![],
                liste_produit: vec![],
                ecarts: None,
                temps_de_traitement: start.elapsed().as_secs_f64(),
            },
        }
    }

    // =====================================================================
    // Enrich & Rerank with LLM
    // =====================================================================

    async fn enrich_and_rerank_with_llm(
        top_produit: &[Produit],
        liste_produit: &[Produit],
        id_categorie: &str,
        parcours: &str,
        id_prompt: i32,
        request: &MatchingPayloadIdProduit,
    ) -> (Vec<Produit>, Vec<Produit>, Vec<Produit>) {
        let all_produits: Vec<&Produit> = top_produit.iter().chain(liste_produit.iter()).collect();
        if all_produits.is_empty() {
            return (vec![], vec![], vec![]);
        }

        let id_produits: Vec<String> = all_produits.iter().map(|p| p.id_produit.clone()).collect();
        let produit_map: HashMap<String, &Produit> =
            all_produits.iter().map(|p| (p.id_produit.clone(), *p)).collect();

        // Fetch data in parallel
        let (products_info, all_caracs, category_caracs) = tokio::join!(
            HELLOPRO_CLIENT.fetch_products_info(id_categorie, &id_produits),
            HELLOPRO_CLIENT.fetch_all_product_caracteristiques(&id_produits),
            HELLOPRO_CLIENT.fetch_category_caracteristiques(id_categorie),
        );

        // Build liste_carac_id from request
        let liste_carac_id: Vec<String> = request
            .liste_caracteristique
            .iter()
            .map(|c| c.id_caracteristique.to_string().trim_matches('"').to_string())
            .collect();

        // Format products for LLM
        let html_tag_re = Regex::new(r"<[^>]+>").unwrap();
        let whitespace_re = Regex::new(r"\s+").unwrap();
        let mut formatted_products = vec![];

        for id_produit in &id_produits {
            let info_produit = products_info
                .get(id_produit)
                .and_then(|v| v.get("produit"))
                .cloned()
                .unwrap_or(json!({}));
            let info_fournisseur = products_info
                .get(id_produit)
                .and_then(|v| v.get("vendeur"))
                .cloned()
                .unwrap_or(json!({}));
            let caracs = all_caracs.get(id_produit).cloned().unwrap_or_default();

            let produit_obj = produit_map.get(id_produit);
            let etat_label = if produit_obj.map(|p| p.coeff_etat_score == 1.0).unwrap_or(false) {
                "Client"
            } else {
                "Prospect"
            };

            let description_raw = info_produit
                .get("description_produit")
                .and_then(|v| v.as_str())
                .unwrap_or("");
            let description_no_html = html_tag_re.replace_all(description_raw, "");
            let description = whitespace_re
                .replace_all(&description_no_html.replace('\u{a0}', " "), " ")
                .trim()
                .to_string();

            let titre = info_produit
                .get("titre_produit")
                .or_else(|| info_produit.get("nom_produit"))
                .or_else(|| info_produit.get("titre"))
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();

            let filtered_caracs: Vec<Value> = caracs
                .iter()
                .filter(|c| {
                    c.get("id_caracteristique")
                        .map(|v| {
                            let s = v.to_string().trim_matches('"').to_string();
                            liste_carac_id.contains(&s)
                        })
                        .unwrap_or(false)
                })
                .map(|c| {
                    json!({
                        "nom": c.get("nom_caracteristique").or_else(|| c.get("label")).and_then(|v| v.as_str()).unwrap_or(""),
                        "valeur": c.get("valeur").and_then(|v| v.as_str()).unwrap_or(""),
                        "unite": c.get("unite").and_then(|v| v.as_str()).unwrap_or(""),
                    })
                })
                .collect();

            formatted_products.push(json!({
                "id_produit": id_produit,
                "titre": titre,
                "description": description,
                "fournisseur": {
                    "nom": info_fournisseur.get("nom").and_then(|v| v.as_str()).unwrap_or(""),
                    "id_fournisseur": info_fournisseur.get("id").map(|v| v.to_string().trim_matches('"').to_string()).unwrap_or_default(),
                    "type": etat_label,
                },
                "caracteristiques": filtered_caracs,
            }));
        }

        // Build LLM prompt variables
        let besoin_acheteur = if parcours.is_empty() { "Non renseigné" } else { parcours };

        // Build CARACTERISTIQUES_CRITIQUES
        let category_carac_map: HashMap<String, &Value> = category_caracs
            .iter()
            .filter_map(|c| {
                c.get("id_caracteristique")
                    .map(|v| (v.to_string().trim_matches('"').to_string(), c))
            })
            .collect();

        let mut critiques_lines = vec![];
        for carac in &request.liste_caracteristique {
            let cid = carac.id_caracteristique.to_string().trim_matches('"').to_string();
            let poids_c = carac.poids_caracteristique.as_deref().unwrap_or("critique");
            if poids_c != "critique" {
                continue;
            }
            let poids_q = carac.poids_question.unwrap_or(1);
            let unite = carac.unite.as_deref().unwrap_or("");
            let cat_def = category_carac_map.get(&cid).copied();
            let nom = cat_def
                .and_then(|c| c.get("nom").and_then(|v| v.as_str()))
                .unwrap_or(&format!("Caractéristique #{}", cid))
                .to_string();

            let mut valeur_parts = vec![];
            if let Some(cibles) = &carac.valeurs_cibles {
                match cibles {
                    Value::Object(obj) => {
                        for k in &["min", "max", "exact"] {
                            if let Some(v) = obj.get(*k) {
                                if !v.is_null() {
                                    valeur_parts.push(format!("{}: {} {}", k, v, unite).trim().to_string());
                                }
                            }
                        }
                    }
                    Value::Array(arr) => {
                        let vals: Vec<String> = arr.iter().map(|v| v.to_string().trim_matches('"').to_string()).collect();
                        valeur_parts.push(vals.join(", "));
                    }
                    _ => {}
                }
            }

            let valeur_str = if valeur_parts.is_empty() { "Non spécifié".to_string() } else { valeur_parts.join(", ") };
            critiques_lines.push(format!("🔴 {} (poids: {}) : {}", nom, poids_q, valeur_str));
        }

        let caracteristiques_critiques = critiques_lines.join("\n");
        let liste_produits_json = serde_json::to_string(&formatted_products).unwrap_or_default();

        // Fetch system prompt
        let prompt_data = HELLOPRO_CLIENT.fetch_prompt(&id_prompt.to_string()).await;
        let (system_prompt_template, temperature) = if let Some(ref pd) = prompt_data {
            if let Some(content) = pd.get("contenu_prompt").and_then(|v| v.as_str()) {
                let temp = pd.get("temperature").and_then(|v| v.as_f64());
                (content.to_string(), temp)
            } else {
                (Self::default_system_prompt(), None)
            }
        } else {
            (Self::default_system_prompt(), None)
        };

        let system_prompt = system_prompt_template
            .replace("{besoin_acheteur}", besoin_acheteur)
            .replace("{caracteristiques_critiques}", &caracteristiques_critiques)
            .replace("{liste_produits_json}", &liste_produits_json);

        // Call Gemini
        let llm_response = GEMINI_CLIENT.generate_rerank_response(&system_prompt, temperature).await;
        if llm_response.is_none() {
            return (top_produit.to_vec(), liste_produit.to_vec(), vec![]);
        }
        let llm_response = llm_response.unwrap();

        // Reorder based on LLM response
        Self::reorder_from_llm(&llm_response, &produit_map)
    }

    fn reorder_from_llm(
        llm_response: &Value,
        produit_map: &HashMap<String, &Produit>,
    ) -> (Vec<Produit>, Vec<Produit>, Vec<Produit>) {
        let llm_top = llm_response.get("top_produits").and_then(|v| v.as_array()).cloned().unwrap_or_default();
        let llm_autres = llm_response.get("autres_produits").and_then(|v| v.as_array()).cloned().unwrap_or_default();
        let llm_ecartes = llm_response.get("produits_ecartes").and_then(|v| v.as_array()).cloned().unwrap_or_default();

        let mut score_map: HashMap<String, f64> = HashMap::new();
        let mut response_map: HashMap<String, Value> = HashMap::new();
        for entry in llm_top.iter().chain(llm_autres.iter()).chain(llm_ecartes.iter()) {
            if let Some(pid) = entry.get("id_produit").and_then(|v| v.as_str()) {
                response_map.insert(pid.to_string(), entry.clone());
                if let Some(score) = entry.get("score").and_then(|v| v.as_f64()) {
                    score_map.insert(pid.to_string(), score);
                }
            }
        }

        let build = |entries: &[Value], map: &HashMap<String, &Produit>| -> Vec<Produit> {
            entries
                .iter()
                .enumerate()
                .filter_map(|(idx, e)| {
                    let pid = e.get("id_produit").and_then(|v| v.as_str())?;
                    let p = map.get(pid)?;
                    Some(Produit {
                        rang: (idx + 1) as i32,
                        id_produit: p.id_produit.clone(),
                        score: score_map.get(pid).copied().unwrap_or(p.score),
                        caracteristique: p.caracteristique.clone(),
                        info_produit: p.info_produit.clone(),
                        coeff_geo: p.coeff_geo,
                        coeff_type_frns: p.coeff_type_frns,
                        coeff_etat_score: p.coeff_etat_score,
                        coeff_caracteristique: p.coeff_caracteristique,
                        llm_response: response_map.get(pid).cloned(),
                    })
                })
                .collect()
        };

        let reranked_top = build(&llm_top, produit_map);
        let mut reranked_liste = build(&llm_autres, produit_map);
        let ecarts = build(&llm_ecartes, produit_map);

        // Any products not mentioned by LLM go into liste
        let all_llm_ids: std::collections::HashSet<String> = llm_top
            .iter()
            .chain(llm_autres.iter())
            .chain(llm_ecartes.iter())
            .filter_map(|e| e.get("id_produit").and_then(|v| v.as_str()).map(String::from))
            .collect();

        for (pid, p) in produit_map {
            if !all_llm_ids.contains(pid) {
                reranked_liste.push(Produit {
                    rang: (reranked_liste.len() + 1) as i32,
                    id_produit: p.id_produit.clone(),
                    score: p.score,
                    caracteristique: p.caracteristique.clone(),
                    info_produit: p.info_produit.clone(),
                    coeff_geo: p.coeff_geo,
                    coeff_type_frns: p.coeff_type_frns,
                    coeff_etat_score: p.coeff_etat_score,
                    coeff_caracteristique: p.coeff_caracteristique,
                    llm_response: None,
                });
            }
        }

        (reranked_top, reranked_liste, ecarts)
    }

    // =====================================================================
    // Caracteristique Filters with Rerank
    // =====================================================================

    pub async fn get_products_by_caracteristique_filters_rerank(
        request: &MatchingPayloadIdProduit,
    ) -> MatchingResponse {
        let start = Instant::now();

        let flat_filters = Self::normalize_constraints_for_caracteristique(request).await;
        let weights_map: Value = flat_filters
            .iter()
            .filter_map(|f| {
                let cid = f.get("cid").and_then(|v| v.as_str())?;
                let qw = f.get("q_weight")?;
                Some((cid.to_string(), qw.clone()))
            })
            .collect::<serde_json::Map<String, Value>>()
            .into();

        let scoring_params = Self::extract_scoring_params(request);
        let blocked_val = scoring_params["blocked_val"].as_f64().unwrap_or(-2.0);
        let different_val = scoring_params["different_val"].as_f64().unwrap_or(-0.3);

        let target_product_id = request.id_produit.as_ref().map(|v| v.to_string().trim_matches('"').to_string());
        let cypher_query = Self::build_cypher_query(request, target_product_id.as_deref());

        let rerank_top_k = request.rerank.as_ref().map(|r| r.top_k).unwrap_or(request.top_k);
        let params = Self::build_cypher_params(
            request, &flat_filters, &weights_map, &scoring_params,
            rerank_top_k, target_product_id.as_deref(),
        );

        let results = CLIENTS.execute_cypher(&cypher_query, &params).await;

        let (liste_produit, top_produit) =
            Self::parse_matching_results(&results, request, blocked_val, different_val);

        let id_categorie = request.id_categorie.as_ref().map(|v| v.to_string().trim_matches('"').to_string()).unwrap_or_default();
        let parcours = request.rerank.as_ref().and_then(|r| r.parcours.as_deref()).unwrap_or("");
        let id_prompt = request.rerank.as_ref().and_then(|r| r.id_prompt).unwrap_or(112);

        let (reranked_top, reranked_liste, ecarts) = Self::enrich_and_rerank_with_llm(
            &top_produit, &liste_produit, &id_categorie, parcours, id_prompt, request,
        )
        .await;

        MatchingResponse {
            top_produit: reranked_top,
            liste_produit: reranked_liste,
            ecarts: if ecarts.is_empty() { None } else { Some(ecarts) },
            temps_de_traitement: start.elapsed().as_secs_f64(),
        }
    }

    // =====================================================================
    // Default System Prompt (fallback)
    // =====================================================================

    fn default_system_prompt() -> String {
        r#"## RÔLE ET OBJECTIF
Tu es un expert en matching acheteur-produit pour une marketplace B2B.
Tu reçois une liste de produits pré-sélectionnés par un système de scoring automatique
et la demande d'un acheteur professionnel. Tu produis un classement final fiable.

## FORMAT DE SORTIE
La réponse doit être un objet JSON valide uniquement:
{{
  "besoin_acheteur": "Reformulation synthétique du besoin.",
  "top_produits": [{{ "rang": 1, "id_produit": "X", "nom": "...", "score": 0.85, "completude": 4, "base_calcul": "X/Y", "decision": "VALIDE", "fournisseur_client": true, "justification": "..." }}],
  "autres_produits": [],
  "produits_ecartes": []
}}

DONNÉES D'ENTRÉE
[BESOIN_ACHETEUR]
{besoin_acheteur}
[CARACTERISTIQUES_CRITIQUES]
{caracteristiques_critiques}
[LISTE_PRODUITS]
{liste_produits_json}
"#.to_string()
    }
}
