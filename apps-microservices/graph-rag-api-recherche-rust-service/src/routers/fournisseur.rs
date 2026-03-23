use actix_web::{get, web, HttpResponse};
use serde_json::json;

use crate::services::fournisseur_service::FournisseurService;

/// GET /fournisseur/{id_fournisseur} —
/// Get geographic coverage by fournisseur ID.
#[utoipa::path(
    get,
    path = "/fournisseur/{id_fournisseur}",
    params(("id_fournisseur" = String, Path, description = "Fournisseur ID")),
    responses(
        (status = 200, description = "Fournisseur geographic coverage")
    ),
    tag = "Fournisseur"
)]
#[get("/fournisseur/{id_fournisseur}")]
pub async fn get_couverture_by_fournisseur(
    path: web::Path<String>,
) -> HttpResponse {
    let id_fournisseur = path.into_inner();
    match FournisseurService::get_couverture_by_fournisseur(&id_fournisseur).await {
        Some(response) => HttpResponse::Ok().json(response),
        None => HttpResponse::NotFound().json(json!({
            "detail": format!("Fournisseur with ID '{}' not found.", id_fournisseur)
        })),
    }
}

/// GET /fournisseur/produit/{id_produit} —
/// Get geographic coverage by product ID.
#[utoipa::path(
    get,
    path = "/fournisseur/produit/{id_produit}",
    params(("id_produit" = String, Path, description = "Product ID")),
    responses(
        (status = 200, description = "Fournisseur geographic coverage for product")
    ),
    tag = "Fournisseur"
)]
#[get("/fournisseur/produit/{id_produit}")]
pub async fn get_couverture_by_produit(
    path: web::Path<String>,
) -> HttpResponse {
    let id_produit = path.into_inner();
    match FournisseurService::get_couverture_by_produit(&id_produit).await {
        Some(response) => HttpResponse::Ok().json(response),
        None => HttpResponse::NotFound().json(json!({
            "detail": format!("Geo coverage not found for product '{}'.", id_produit)
        })),
    }
}
