use actix_web::{delete, get, web, HttpResponse};
use serde_json::json;

use crate::services::product_service::ProductService;

/// GET /produits/{product_id}/caracteristiques — Get product characteristics.
#[utoipa::path(
    get,
    path = "/produits/{product_id}/caracteristiques",
    params(("product_id" = String, Path, description = "Product ID")),
    responses(
        (status = 200, description = "Product characteristics")
    ),
    tag = "Product"
)]
#[get("/produits/{product_id}/caracteristiques")]
pub async fn get_product_caracteristiques(
    path: web::Path<String>,
) -> HttpResponse {
    let product_id = path.into_inner();
    let caracs = ProductService::get_caracteristiques(&product_id).await;
    HttpResponse::Ok().json(json!({
        "id_produit": product_id,
        "caracteristiques": caracs,
    }))
}

/// DELETE /produits/{product_id} — Delete a product.
#[utoipa::path(
    delete,
    path = "/produits/{product_id}",
    params(("product_id" = String, Path, description = "Product ID")),
    responses(
        (status = 200, description = "Product deleted")
    ),
    tag = "Product"
)]
#[delete("/produits/{product_id}")]
pub async fn delete_product(path: web::Path<String>) -> HttpResponse {
    let product_id = path.into_inner();
    let (success, message) = ProductService::delete_product(&product_id).await;
    if success {
        HttpResponse::Ok().json(json!({ "success": true, "message": message }))
    } else {
        HttpResponse::NotFound().json(json!({ "success": false, "message": message }))
    }
}
