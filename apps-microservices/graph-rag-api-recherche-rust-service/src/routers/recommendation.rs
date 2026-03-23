use actix_web::{post, web, HttpResponse};

use crate::domain::models::{
    ComplexFilterRequest, MatchingPayloadIdProduit, MatchingPayload,
};
use crate::services::recommendation_service::RecommendationService;

/// POST /produits/filter — Complex filter with scoring.
#[utoipa::path(
    post,
    path = "/produits/filter",
    request_body = ComplexFilterRequest,
    responses(
        (status = 200, description = "Filtered and scored products")
    ),
    tag = "Recommendation"
)]
#[post("/produits/filter")]
pub async fn filter_handler(body: web::Json<ComplexFilterRequest>) -> HttpResponse {
    let request = body.into_inner();
    let result = RecommendationService::get_products_by_complex_filters(&request, None).await;
    HttpResponse::Ok().json(result)
}

/// POST /produits/filter-by-caracteristique — Filter by characteristics with scoring.
#[utoipa::path(
    post,
    path = "/produits/filter-by-caracteristique",
    request_body = MatchingPayload,
    responses(
        (status = 200, description = "Matching response with scored products")
    ),
    tag = "Recommendation"
)]
#[post("/produits/filter-by-caracteristique")]
pub async fn filter_by_caracteristique_handler(
    body: web::Json<MatchingPayload>,
) -> HttpResponse {
    let request = body.into_inner();
    let as_matching = MatchingPayloadIdProduit {
        liste_caracteristique: request.liste_caracteristique,
        top_k: request.top_k,
        id_categorie: request.id_categorie,
        id_produit: None,
        options: request.options,
        champs_sortie: request.champs_sortie,
        metadonnee_utilisateurs: None,
        scoring: None,
        rerank: None,
    };
    let result = RecommendationService::get_products_by_caracteristique_filters(&as_matching).await;
    HttpResponse::Ok().json(result)
}

/// POST /produits/{product_id}/score — Calculate score of specific product against complex filters.
#[utoipa::path(
    post,
    path = "/produits/{product_id}/score",
    params(("product_id" = String, Path, description = "Product ID")),
    request_body = ComplexFilterRequest,
    responses(
        (status = 200, description = "Scored product result")
    ),
    tag = "Recommendation"
)]
#[post("/produits/{product_id}/score")]
pub async fn score_specific_product(
    path: web::Path<String>,
    body: web::Json<ComplexFilterRequest>,
) -> HttpResponse {
    let product_id = path.into_inner();
    let request = body.into_inner();
    let result = RecommendationService::get_products_by_complex_filters(&request, Some(&product_id)).await;
    HttpResponse::Ok().json(result)
}

/// POST /produits/matching — Product matching with optional reranking.
#[utoipa::path(
    post,
    path = "/produits/matching",
    request_body = MatchingPayloadIdProduit,
    responses(
        (status = 200, description = "Matching response with ranked products")
    ),
    tag = "Recommendation"
)]
#[post("/produits/matching")]
pub async fn matching_handler(body: web::Json<MatchingPayloadIdProduit>) -> HttpResponse {
    let request = body.into_inner();

    let use_rerank = request
        .rerank
        .as_ref()
        .map(|r| r.use_rerank)
        .unwrap_or(false);

    let result = if use_rerank {
        RecommendationService::get_products_by_caracteristique_filters_rerank(&request).await
    } else {
        RecommendationService::get_products_by_caracteristique_filters(&request).await
    };

    HttpResponse::Ok().json(result)
}
