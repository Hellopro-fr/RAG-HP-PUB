//! APPLICATION tier: one transaction per command, decision via `atb-core`, persistence via the
//! repository, wake-up via the notifier. REST handlers and MCP tools call the same functions.

pub mod access;
pub mod auth;
pub mod commands;
pub mod queries;
pub mod ratelimit;
pub mod rebuild;
pub mod sweeper;
pub mod tx;
pub mod updates;

use time::OffsetDateTime;

/// The single clock for every lease decision, truncated to Postgres' microsecond precision so a
/// value read back from the database equals the one that was written.
pub fn now() -> OffsetDateTime {
    let t = OffsetDateTime::now_utc();
    t.replace_nanosecond(t.nanosecond() / 1_000 * 1_000)
        .unwrap_or(t)
}
