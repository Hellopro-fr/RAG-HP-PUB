use actix_web::{get, post, web, HttpResponse};
use serde_json::json;

use crate::domain::models::CypherQueryRequest;
use crate::infrastructure::clients::CLIENTS;

/// POST /admin/cypher — Execute a raw Cypher query.
#[utoipa::path(
    post,
    path = "/admin/cypher",
    request_body = CypherQueryRequest,
    responses(
        (status = 200, description = "Cypher query results")
    ),
    tag = "Admin"
)]
#[post("/admin/cypher")]
pub async fn execute_cypher(body: web::Json<CypherQueryRequest>) -> HttpResponse {
    let request = body.into_inner();
    let params = request.params.unwrap_or(json!({}));
    let start = std::time::Instant::now();
    let results = CLIENTS.execute_cypher(&request.query, &params).await;
    let duration = start.elapsed().as_secs_f64();
    let record_count = results.len();
    HttpResponse::Ok().json(json!({
        "results": results,
        "info": {
            "execution_time_seconds": (duration * 10000.0).round() / 10000.0,
            "query_time": 0,
            "record_count": record_count,
        },
    }))
}

/// GET /admin/count — Count distinct fournisseurs and produits per categorie.
#[utoipa::path(
    get,
    path = "/admin/count",
    responses(
        (status = 200, description = "Category counts")
    ),
    tag = "Admin"
)]
#[get("/admin/count")]
pub async fn get_categories_count() -> HttpResponse {
    let query = r#"
        MATCH (p:Produit)-[:EST_PROPOSE_PAR]-(f:Fournisseur)
        WHERE p.est_actif = true
        RETURN p.id_categorie AS Categorie, count(DISTINCT f) AS Nb_Fournisseurs, count(DISTINCT p) AS Nb_produits
        ORDER BY Categorie ASC
    "#;
    let results = CLIENTS.execute_cypher(query, &json!({})).await;
    let response: Vec<serde_json::Value> = results
        .iter()
        .map(|record| {
            json!({
                "id_categorie": record.get("Categorie"),
                "fournisseur": record.get("Nb_Fournisseurs").and_then(|v| v.as_i64()).unwrap_or(0),
                "produit": record.get("Nb_produits").and_then(|v| v.as_i64()).unwrap_or(0),
            })
        })
        .collect();
    HttpResponse::Ok().json(response)
}
