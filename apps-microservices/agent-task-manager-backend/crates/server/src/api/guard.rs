//! One project check for every project-scoped REST route, so no handler can forget it.
//!
//! The project comes from the matched route (`/api/projects/{id}…`, `/api/tasks/{id}…`,
//! `/api/specs/{id}…`, `/api/questions/{id}…`); reads need viewer, writes need editor.
//! Owner-only actions (visibility, members) are checked again by their handlers. Lists that span
//! projects (`/api/projects`, `/api/questions`, `/api/stream`, `/api/actors`) filter instead.

use atb_core::project_access::ProjectRole;
use axum::extract::{MatchedPath, RawPathParams, Request, State};
use axum::http::Method;
use axum::middleware::Next;
use axum::response::Response;
use uuid::Uuid;

use crate::error::AppError;
use crate::scope::Scope;
use crate::service::project_access::{self, Target};
use crate::state::AppState;

fn target_of(pattern: &str, params: &RawPathParams) -> Option<Result<Target, AppError>> {
    let make: fn(Uuid) -> Target = if pattern.starts_with("/api/projects/{id}") {
        Target::Project
    } else if pattern.starts_with("/api/tasks/{id}") {
        Target::Task
    } else if pattern.starts_with("/api/specs/{id}") {
        Target::Spec
    } else if pattern.starts_with("/api/questions/{id}") {
        Target::Question
    } else {
        return None;
    };
    let raw = params.iter().find(|(k, _)| *k == "id").map(|(_, v)| v)?;
    Some(
        Uuid::parse_str(raw)
            .map(make)
            .map_err(|_| AppError::not_found("project")),
    )
}

pub async fn project_guard(
    State(st): State<AppState>,
    matched: MatchedPath,
    params: RawPathParams,
    req: Request,
    next: Next,
) -> Result<Response, AppError> {
    let Some(target) = target_of(matched.as_str(), &params) else {
        return Ok(next.run(req).await);
    };
    let target = target?;
    let scope = req
        .extensions()
        .get::<Scope>()
        .cloned()
        .ok_or(AppError::Unauthorized)?;
    let min = if matches!(*req.method(), Method::GET | Method::HEAD) {
        ProjectRole::Viewer
    } else {
        ProjectRole::Editor
    };
    project_access::require_pooled(&st, &scope, target, min).await?;
    Ok(next.run(req).await)
}
