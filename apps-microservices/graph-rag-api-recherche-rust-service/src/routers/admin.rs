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
    let results = CLIENTS.execute_cypher(&request.query, &params).await;
    HttpResponse::Ok().json(json!({
        "success": true,
        "data": results,
    }))
}

/// GET /admin/categories/count — Count categories.
#[utoipa::path(
    get,
    path = "/admin/categories/count",
    responses(
        (status = 200, description = "Category counts")
    ),
    tag = "Admin"
)]
#[get("/admin/categories/count")]
pub async fn get_categories_count() -> HttpResponse {
    let query = r#"
        MATCH (p:Produit)
        WHERE p.id_categorie IS NOT NULL
        RETURN p.id_categorie AS id_categorie, count(p) AS count
        ORDER BY count DESC
    "#;
    let results = CLIENTS.execute_cypher(query, &json!({})).await;
    HttpResponse::Ok().json(results)
}
