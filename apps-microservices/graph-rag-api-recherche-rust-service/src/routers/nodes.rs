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
    tag = "Admin"
)]
#[put("/nodes/{label}/{id}")]
pub async fn update_node(
    path: web::Path<(String, String)>,
    body: web::Json<NodeUpdateRequest>,
) -> HttpResponse {
    let (label, id) = path.into_inner();
    let (success, data, _error) = NodeService::update_node(&label, &id, &body.properties).await;
    if success {
        HttpResponse::Ok().json(json!({
            "message": format!("Node {} {} updated successfully.", label, id),
            "node": data,
        }))
    } else {
        HttpResponse::NotFound().json(json!({
            "detail": format!("Node {} with ID {} not found.", label, id)
        }))
    }
}

/// GET /nodes/{label} — Get schema for a node label.
#[utoipa::path(
    get,
    path = "/nodes/{label}",
    params(("label" = String, Path, description = "Node label")),
    responses(
        (status = 200, description = "Node schema")
    ),
    tag = "Admin"
)]
#[get("/nodes/{label}")]
pub async fn get_schema(path: web::Path<String>) -> HttpResponse {
    let label = path.into_inner();
    let schema = NodeService::get_schema(&label).await;
    HttpResponse::Ok().json(json!({
        "label": label,
        "schema": schema,
    }))
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
    tag = "Admin"
)]
#[get("/nodes/{label}/{id}")]
pub async fn get_node(path: web::Path<(String, String)>) -> HttpResponse {
    let (label, id) = path.into_inner();
    match NodeService::get_node(&label, &id).await {
        Some(node) => HttpResponse::Ok().json(json!({
            "code": 200,
            "data": {
                "label": label,
                "id": id,
                "node": node,
            },
        })),
        None => HttpResponse::Ok().json(json!({
            "code": 404,
            "data": {
                "label": label,
                "id": id,
                "node": null,
            },
        })),
    }
}
