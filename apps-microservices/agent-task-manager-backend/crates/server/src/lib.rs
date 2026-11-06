//! Agent Task Board server — layered (N-tier):
//!
//! ```text
//! api (presentation: REST, SSE, MCP, auth middleware)
//!  └─> service (application: one transaction per command, queries, sweeper, wait_for_updates)
//!       ├─> atb_core (domain: pure decider, no IO)
//!       ├─> repository (data: sqlx, every fn takes &mut PgConnection)
//!       └─> realtime (Notifier + LISTEN fan-out hub)
//! ```

pub mod actor;
pub mod api;
pub mod config;
pub mod error;
pub mod metrics;
pub mod realtime;
pub mod repository;
pub mod service;
pub mod state;

pub use config::Config;
pub use state::AppState;

/// Embedded migrations (run by `atb-server migrate` with the owner role, and by `sqlx::test`).
pub static MIGRATOR: sqlx::migrate::Migrator = sqlx::migrate!("../../migrations");
