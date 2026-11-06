//! The ONE place where domain and infrastructure errors become HTTP responses and MCP results.
//! Every error carries a stable `code`, a message that tells the caller what to do next, and
//! optional `details`.

use atb_core::DomainError;
use axum::Json;
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use serde::Serialize;
use serde_json::{Value, json};
use utoipa::ToSchema;

#[derive(Debug, thiserror::Error)]
pub enum AppError {
    #[error(transparent)]
    Domain(#[from] DomainError),
    #[error("not found: {0}")]
    NotFound(String),
    #[error("authentication required")]
    Unauthorized,
    #[error("forbidden: {0}")]
    Forbidden(String),
    #[error("rate limited: {0}")]
    RateLimited(String),
    #[error("invalid input: {0}")]
    BadRequest(String),
    /// 409 with the current state of the resource in `details` (UI optimistic concurrency).
    #[error("{message}")]
    Conflict {
        code: &'static str,
        message: String,
        details: Value,
    },
    #[error("internal error")]
    Internal(#[source] anyhow::Error),
}

impl From<sqlx::Error> for AppError {
    fn from(e: sqlx::Error) -> Self {
        AppError::Internal(e.into())
    }
}

impl From<anyhow::Error> for AppError {
    fn from(e: anyhow::Error) -> Self {
        AppError::Internal(e)
    }
}

impl From<serde_json::Error> for AppError {
    fn from(e: serde_json::Error) -> Self {
        AppError::Internal(e.into())
    }
}

/// Error body of every REST response (§8).
#[derive(Debug, Serialize, ToSchema)]
pub struct ErrorBody {
    pub code: String,
    pub message: String,
    #[schema(value_type = Object)]
    pub details: Value,
}

impl AppError {
    pub fn not_found(what: impl Into<String>) -> Self {
        AppError::NotFound(what.into())
    }

    pub fn code(&self) -> &'static str {
        match self {
            AppError::Domain(d) => d.code(),
            AppError::NotFound(_) => "not_found",
            AppError::Unauthorized => "unauthorized",
            AppError::Forbidden(_) => "forbidden",
            AppError::RateLimited(_) => "rate_limited",
            AppError::BadRequest(_) => "invalid_input",
            AppError::Conflict { code, .. } => code,
            AppError::Internal(_) => "internal",
        }
    }

    pub fn status(&self) -> StatusCode {
        match self {
            AppError::Domain(DomainError::StaleLease(_))
            | AppError::Domain(DomainError::GuardFailed { .. })
            | AppError::Domain(DomainError::VersionConflict { .. })
            | AppError::Conflict { .. } => StatusCode::CONFLICT,
            AppError::Domain(DomainError::Forbidden(_)) | AppError::Forbidden(_) => {
                StatusCode::FORBIDDEN
            }
            AppError::Domain(DomainError::Invalid { .. }) | AppError::BadRequest(_) => {
                StatusCode::UNPROCESSABLE_ENTITY
            }
            AppError::NotFound(_) => StatusCode::NOT_FOUND,
            AppError::Unauthorized => StatusCode::UNAUTHORIZED,
            AppError::RateLimited(_) => StatusCode::TOO_MANY_REQUESTS,
            AppError::Internal(_) => StatusCode::INTERNAL_SERVER_ERROR,
        }
    }

    /// Human/agent readable message. Internal errors never leak their cause.
    pub fn message(&self) -> String {
        match self {
            AppError::Internal(_) => "internal error; retry with the same idempotency_key".into(),
            other => other.to_string(),
        }
    }

    pub fn details(&self) -> Value {
        match self {
            AppError::Domain(DomainError::GuardFailed { guard, hint }) => {
                json!({ "guard": guard, "how_to_fix": hint })
            }
            AppError::Domain(DomainError::Invalid { field, hint }) => {
                json!({ "field": field, "how_to_fix": hint })
            }
            AppError::Domain(DomainError::VersionConflict { expected, current }) => {
                json!({ "expected_version": expected, "current_version": current })
            }
            AppError::Domain(DomainError::StaleLease(_)) => json!({
                "how_to_fix": "stop working on this task; call list_ready and claim again"
            }),
            AppError::RateLimited(_) => json!({ "how_to_fix": "slow down and retry later" }),
            AppError::Conflict { details, .. } => details.clone(),
            _ => json!({}),
        }
    }

    pub fn body(&self) -> ErrorBody {
        ErrorBody {
            code: self.code().to_string(),
            message: self.message(),
            details: self.details(),
        }
    }
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        if let AppError::Internal(e) = &self {
            tracing::error!(error = ?e, "internal error");
        }
        (self.status(), Json(self.body())).into_response()
    }
}

pub type AppResult<T> = Result<T, AppError>;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stale_lease_maps_to_409_with_a_next_step() {
        let e = AppError::from(DomainError::StaleLease("expired".into()));
        assert_eq!(e.status(), StatusCode::CONFLICT);
        assert_eq!(e.code(), "stale_lease");
        assert!(
            e.details()["how_to_fix"]
                .as_str()
                .unwrap()
                .contains("claim")
        );
    }

    #[test]
    fn internal_errors_do_not_leak_their_cause() {
        let e = AppError::Internal(anyhow::anyhow!("password=secret"));
        assert!(!e.message().contains("secret"));
    }
}
