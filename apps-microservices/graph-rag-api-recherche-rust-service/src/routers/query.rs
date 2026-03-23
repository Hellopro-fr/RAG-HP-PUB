use actix_web::{post, web, HttpResponse};
use serde_json::json;

use crate::domain::models::QueryRequest;
use crate::services::rag_service::AgenticRAGService;

/// POST /query — Intelligent search using RAG pipeline.
#[utoipa::path(
    post,
    path = "/query",
    request_body = QueryRequest,
    responses(
        (status = 200, description = "Query response with answer and sources")
    ),
    tag = "Query"
)]
#[post("/query")]
pub async fn query_handler(body: web::Json<QueryRequest>) -> HttpResponse {
    let request = body.into_inner();
    let start = std::time::Instant::now();

    let response = AgenticRAGService::process_query(
        &request.query,
        request.strategy.as_deref(),
        request.use_reranking,
        request.top_k,
        request.threshold,
    )
    .await;

    let mut resp = serde_json::to_value(&response).unwrap_or(json!({}));
    if let Some(obj) = resp.as_object_mut() {
        obj.insert(
            "processing_time".to_string(),
            json!(start.elapsed().as_secs_f64()),
        );
    }

    HttpResponse::Ok().json(resp)
}
