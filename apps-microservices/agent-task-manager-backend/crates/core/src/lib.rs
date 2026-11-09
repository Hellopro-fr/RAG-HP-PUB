//! Agent Task Board — pure domain tier.
//!
//! No IO, no async, no database. The server loads a [`TaskSnapshot`] and a [`Ctx`], calls
//! [`decide`], persists the returned [`DomainEvent`]s and their projections in one transaction.

pub mod access;
pub mod apply;
pub mod command;
pub mod ctx;
pub mod decide;
pub mod error;
pub mod event;
pub mod graph;
pub mod invariants;
pub mod model;
pub mod project_access;
pub mod workflow;

pub use apply::{apply, apply_all};
pub use command::{Command, NewTask};
pub use ctx::Ctx;
pub use decide::{decide, decide_create};
pub use error::DomainError;
pub use event::DomainEvent;
pub use model::*;
pub use workflow::{ReviewGate, TestGate, WorkflowConfig};
