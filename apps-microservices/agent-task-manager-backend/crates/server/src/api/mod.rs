//! PRESENTATION tier: REST + SSE + MCP behind one auth middleware, one error mapping.

pub mod auth;
pub mod dto;
pub mod mcp;
pub mod openapi;
pub mod rest;
pub mod sse;
pub mod sso;

use axum::Router;
use axum::http::{HeaderName, HeaderValue, Method, Request, header};
use axum::middleware::from_fn_with_state;
use axum::routing::{get, post, put};
use tower_http::cors::{AllowOrigin, CorsLayer};
use tower_http::limit::RequestBodyLimitLayer;
use tower_http::request_id::{MakeRequestUuid, PropagateRequestIdLayer, SetRequestIdLayer};
use tower_http::trace::TraceLayer;

use crate::state::AppState;

/// 256 KB request bodies (§12).
pub const MAX_BODY_BYTES: usize = 256 * 1024;

pub fn router(st: AppState) -> Router {
    let public = Router::new()
        .route("/healthz", get(rest::healthz))
        .route("/readyz", get(rest::readyz))
        .route("/metrics", get(rest::metrics))
        .route(
            "/api/openapi.json",
            get(|| async {
                (
                    [(header::CONTENT_TYPE, "application/json")],
                    openapi::json(),
                )
            }),
        )
        .route("/api/auth/login", post(rest::login))
        .route("/api/auth/logout", post(rest::logout))
        .route("/api/auth/methods", get(rest::auth_methods))
        .route("/api/auth/sso/start", get(sso::start))
        .route("/api/auth/sso/callback", get(sso::callback));

    let protected = Router::new()
        .route("/api/auth/me", get(rest::me))
        .route(
            "/api/projects",
            get(rest::list_projects).post(rest::create_project),
        )
        .route("/api/projects/{id}", get(rest::get_project))
        .route("/api/projects/{id}/board", get(rest::board))
        .route("/api/projects/{id}/events", get(rest::events))
        .route("/api/projects/{id}/stream", get(sse::project_stream))
        .route("/api/projects/{id}/ready", get(rest::ready))
        .route("/api/projects/{id}/claim", post(rest::claim_in_project))
        .route("/api/projects/{id}/tasks", post(rest::create_task))
        .route(
            "/api/projects/{id}/specs",
            get(rest::list_specs).post(rest::create_spec),
        )
        .route("/api/projects/{id}/rebuild-check", get(rest::rebuild_check))
        .route("/api/specs/{id}", get(rest::get_spec))
        .route("/api/specs/{id}/versions", post(rest::propose_version))
        .route(
            "/api/specs/{id}/versions/{version}/approve",
            post(rest::approve_version),
        )
        .route(
            "/api/tasks/{id}",
            get(rest::get_task).patch(rest::patch_task),
        )
        .route("/api/tasks/{id}/timeline", get(rest::timeline))
        .route("/api/tasks/{id}/claim", post(rest::claim_task))
        .route("/api/tasks/{id}/heartbeat", post(rest::heartbeat))
        .route("/api/tasks/{id}/report", post(rest::report))
        .route("/api/tasks/{id}/ask", post(rest::ask))
        .route("/api/tasks/{id}/release", post(rest::release))
        .route(
            "/api/tasks/{id}/submit-for-test",
            post(rest::submit_for_test),
        )
        .route("/api/tasks/{id}/repin", post(rest::repin))
        .route("/api/tasks/{id}/cancel", post(rest::cancel))
        .route("/api/tasks/{id}/links", post(rest::add_link))
        .route("/api/questions", get(rest::list_questions))
        .route("/api/questions/{id}/answer", post(rest::answer))
        .route(
            "/api/actors",
            get(rest::list_actors).post(rest::create_actor),
        )
        .route("/api/access", get(rest::access_overview))
        .route("/api/access/users/{id}", get(rest::access_user))
        .route("/api/access/users/{id}/level", put(rest::access_set_level))
        .route(
            "/api/access/users/{id}/permissions/{permission}",
            put(rest::access_set_user_permission),
        )
        .route("/api/access/teams/{id}", get(rest::access_team))
        .route(
            "/api/access/teams/{id}/permissions/{permission}",
            put(rest::access_set_team_permission),
        )
        .route("/api/stream", get(sse::global_stream))
        .nest_service("/mcp", mcp::service(st.clone()))
        .layer(from_fn_with_state(st.clone(), auth::require_actor));

    let x_request_id = HeaderName::from_static("x-request-id");
    let mut app = public
        .merge(protected)
        .layer(RequestBodyLimitLayer::new(MAX_BODY_BYTES))
        .layer(
            TraceLayer::new_for_http().make_span_with(|req: &Request<_>| {
                let request_id = req
                    .headers()
                    .get("x-request-id")
                    .and_then(|v| v.to_str().ok())
                    .unwrap_or("-")
                    .to_string();
                let trace_id = req
                    .headers()
                    .get("x-trace-id")
                    .and_then(|v| v.to_str().ok())
                    .unwrap_or("-")
                    .to_string();
                tracing::info_span!(
                    "http",
                    method = %req.method(),
                    path = %req.uri().path(),
                    request_id = %request_id,
                    trace_id = %trace_id,
                    actor_id = tracing::field::Empty,
                )
            }),
        )
        .layer(PropagateRequestIdLayer::new(x_request_id.clone()))
        .layer(SetRequestIdLayer::new(x_request_id, MakeRequestUuid));

    if !st.cfg.cors_origins.is_empty() {
        let origins: Vec<HeaderValue> = st
            .cfg
            .cors_origins
            .iter()
            .filter_map(|o| HeaderValue::from_str(o).ok())
            .collect();
        app = app.layer(
            CorsLayer::new()
                .allow_origin(AllowOrigin::list(origins))
                .allow_credentials(true)
                .allow_methods([
                    Method::GET,
                    Method::POST,
                    Method::PUT,
                    Method::PATCH,
                    Method::OPTIONS,
                ])
                .allow_headers([
                    header::CONTENT_TYPE,
                    header::AUTHORIZATION,
                    HeaderName::from_static("idempotency-key"),
                    HeaderName::from_static("last-event-id"),
                    HeaderName::from_static("x-trace-id"),
                ]),
        );
    }
    app.with_state(st)
}
