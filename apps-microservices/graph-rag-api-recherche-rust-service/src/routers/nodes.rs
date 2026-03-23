use actix_web::{get, put, web, HttpResponse};
use serde_json::json;

use crate::domain::models::NodeUpdateRequest;
use crate::services::node_service::NodeService;

/// PUT /nodes/{label}/{id} — Update a node's properties.
#[utoipa::path(
    put,
    path = "/nodes/{label}/{id}",
    params(
        ("label" = String, Path, description = "Node label"),
        ("id" = String, Path, description = "Node ID")
    ),
    request_body = NodeUpdateRequest,
    responses(
        (status = 200, description = "Updated node")
    ),
    tag = "Nodes"
)]
#[put("/nodes/{label}/{id}")]
pub async fn update_node(
    path: web::Path<(String, String)>,
    body: web::Json<NodeUpdateRequest>,
) -> HttpResponse {
    let (label, id) = path.into_inner();
    let (success, data, error) = NodeService::update_node(&label, &id, &body.properties).await;
    if success {
        HttpResponse::Ok().json(json!({ "success": true, "data": data }))
    } else {
        HttpResponse::BadRequest().json(json!({ "success": false, "error": error }))
    }
}

/// GET /nodes/{label}/schema — Get schema for a node label.
#[utoipa::path(
    get,
    path = "/nodes/{label}/schema",
    params(("label" = String, Path, description = "Node label")),
    responses(
        (status = 200, description = "Node schema")
    ),
    tag = "Nodes"
)]
#[get("/nodes/{label}/schema")]
pub async fn get_schema(path: web::Path<String>) -> HttpResponse {
    let label = path.into_inner();
    let schema = NodeService::get_schema(&label).await;
    HttpResponse::Ok().json(json!({ "schema": schema }))
}

/// GET /nodes/{label}/{id} — Get a specific node.
#[utoipa::path(
    get,
    path = "/nodes/{label}/{id}",
    params(
        ("label" = String, Path, description = "Node label"),
        ("id" = String, Path, description = "Node ID")
    ),
    responses(
        (status = 200, description = "Node data")
    ),
    tag = "Nodes"
)]
#[get("/nodes/{label}/{id}")]
pub async fn get_node(path: web::Path<(String, String)>) -> HttpResponse {
    let (label, id) = path.into_inner();
    match NodeService::get_node(&label, &id).await {
        Some(node) => HttpResponse::Ok().json(json!({ "success": true, "data": node })),
        None => HttpResponse::NotFound().json(json!({
            "success": false,
            "error": format!("Node {}:{} not found", label, id)
        })),
    }
}
