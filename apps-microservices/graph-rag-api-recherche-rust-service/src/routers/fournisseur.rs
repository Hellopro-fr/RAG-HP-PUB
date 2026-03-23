use actix_web::{get, web, HttpResponse};
use serde_json::json;

use crate::services::fournisseur_service::FournisseurService;

/// GET /fournisseurs/{fournisseur_id}/couverture —
/// Get geographic coverage by fournisseur ID.
#[utoipa::path(
    get,
    path = "/fournisseurs/{fournisseur_id}/couverture",
    params(("fournisseur_id" = String, Path, description = "Fournisseur ID")),
    responses(
        (status = 200, description = "Fournisseur geographic coverage")
    ),
    tag = "Fournisseur"
)]
#[get("/fournisseurs/{fournisseur_id}/couverture")]
pub async fn get_couverture_by_fournisseur(
    path: web::Path<String>,
) -> HttpResponse {
    let fournisseur_id = path.into_inner();
    let couverture = FournisseurService::get_couverture_by_fournisseur(&fournisseur_id).await;
    HttpResponse::Ok().json(json!({
        "id_fournisseur": fournisseur_id,
        "couverture": couverture,
    }))
}

/// GET /fournisseurs/produit/{produit_id}/couverture —
/// Get geographic coverage by product ID.
#[utoipa::path(
    get,
    path = "/fournisseurs/produit/{produit_id}/couverture",
    params(("produit_id" = String, Path, description = "Product ID")),
    responses(
        (status = 200, description = "Fournisseur geographic coverage for product")
    ),
    tag = "Fournisseur"
)]
#[get("/fournisseurs/produit/{produit_id}/couverture")]
pub async fn get_couverture_by_produit(
    path: web::Path<String>,
) -> HttpResponse {
    let produit_id = path.into_inner();
    let couverture = FournisseurService::get_couverture_by_produit(&produit_id).await;
    HttpResponse::Ok().json(json!({
        "id_produit": produit_id,
        "couverture": couverture,
    }))
}
