//! Domain errors. Mapped to HTTP statuses and MCP errors in one place (`atb-server::api::error`).

use thiserror::Error;

#[derive(Debug, Clone, PartialEq, Eq, Error)]
pub enum DomainError {
    /// Missing, wrong or expired lease token — even from the same actor.
    #[error("stale lease: {0}")]
    StaleLease(String),
    /// A guard of the state machine is not satisfied. `guard` names it, `hint` says how to fix it.
    #[error("guard failed ({guard}): {hint}")]
    GuardFailed { guard: &'static str, hint: String },
    /// The caller's kind or roles do not allow this command.
    #[error("forbidden: {0}")]
    Forbidden(String),
    /// Input is malformed (empty handoff note, oversize body, invalid workflow...).
    #[error("invalid input ({field}): {hint}")]
    Invalid { field: &'static str, hint: String },
    /// Optimistic concurrency conflict on a UI mutation.
    #[error("version conflict: expected {expected}, current {current}")]
    VersionConflict { expected: i32, current: i32 },
}

impl DomainError {
    pub fn guard(guard: &'static str, hint: impl Into<String>) -> Self {
        Self::GuardFailed {
            guard,
            hint: hint.into(),
        }
    }

    pub fn invalid(field: &'static str, hint: impl Into<String>) -> Self {
        Self::Invalid {
            field,
            hint: hint.into(),
        }
    }

    pub fn code(&self) -> &'static str {
        match self {
            DomainError::StaleLease(_) => "stale_lease",
            DomainError::GuardFailed { .. } => "guard_failed",
            DomainError::Forbidden(_) => "forbidden",
            DomainError::Invalid { .. } => "invalid_input",
            DomainError::VersionConflict { .. } => "version_conflict",
        }
    }
}
