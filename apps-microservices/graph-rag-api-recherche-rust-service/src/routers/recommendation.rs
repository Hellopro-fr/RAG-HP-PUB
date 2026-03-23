use actix_web::{get, post, web, HttpResponse};
use serde_json::json;

use crate::domain::models::{
    ComplexFilterRequest, MatchingPayloadIdProduit,
};
use crate::services::recommendation_service::RecommendationService;

/// POST /filter — Complex filter with scoring.
#[utoipa::path(
    post,
    path = "/filter",
    request_body = ComplexFilterRequest,
    responses(
        (status = 200, description = "Filtered and scored products")
    ),
    tag = "Recommendation"
)]
#[post("/filter")]
pub async fn filter_handler(body: web::Json<ComplexFilterRequest>) -> HttpResponse {
    let request = body.into_inner();
    let result = RecommendationService::get_products_by_complex_filters(&request, None).await;
    HttpResponse::Ok().json(result)
}

/// POST /filter-by-caracteristique — Filter by characteristics with scoring.
#[utoipa::path(
    post,
    path = "/filter-by-caracteristique",
    request_body = MatchingPayloadIdProduit,
    responses(
        (status = 200, description = "Matching response with scored products")
    ),
    tag = "Recommendation"
)]
#[post("/filter-by-caracteristique")]
pub async fn filter_by_caracteristique_handler(
    body: web::Json<MatchingPayloadIdProduit>,
) -> HttpResponse {
    let request = body.into_inner();
    let result = RecommendationService::get_products_by_caracteristique_filters(&request).await;
    HttpResponse::Ok().json(result)
}

/// POST /matching — Product matching with optional reranking.
#[utoipa::path(
    post,
    path = "/matching",
    request_body = MatchingPayloadIdProduit,
    responses(
        (status = 200, description = "Matching response with ranked products")
    ),
    tag = "Recommendation"
)]
#[post("/matching")]
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
