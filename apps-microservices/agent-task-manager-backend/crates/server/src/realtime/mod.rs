//! Realtime fan-out (§6). NOTIFY is only a wake-up signal; the `events` table is the log.

pub mod hub;

use futures::future::BoxFuture;
use sqlx::PgConnection;
use uuid::Uuid;

pub use hub::Hub;

/// Postgres channel carrying `<project_id>:<first_seq>:<last_seq>` after each command.
pub const CHANNEL: &str = "board";

/// Wake-up signal sent inside the command transaction, so it is delivered only on commit.
pub trait Notifier: Send + Sync {
    fn notify<'a>(
        &'a self,
        conn: &'a mut PgConnection,
        project_id: Uuid,
        first_seq: i64,
        last_seq: i64,
    ) -> BoxFuture<'a, Result<(), sqlx::Error>>;
}

/// `pg_notify` in the command transaction. TODO(phase-3): Redis notifier behind the same trait.
pub struct PgNotifier;

impl Notifier for PgNotifier {
    fn notify<'a>(
        &'a self,
        conn: &'a mut PgConnection,
        project_id: Uuid,
        first_seq: i64,
        last_seq: i64,
    ) -> BoxFuture<'a, Result<(), sqlx::Error>> {
        Box::pin(async move {
            let payload = format!("{project_id}:{first_seq}:{last_seq}");
            crate::repository::store::pg_notify(conn, CHANNEL, &payload).await
        })
    }
}

/// Parse a notification payload.
pub fn parse_payload(payload: &str) -> Option<(Uuid, i64, i64)> {
    let mut parts = payload.split(':');
    let project = parts.next()?.parse().ok()?;
    let first = parts.next()?.parse().ok()?;
    let last = parts.next()?.parse().ok()?;
    (first <= last).then_some((project, first, last))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn payload_round_trip_and_rejects_garbage() {
        let id = Uuid::now_v7();
        assert_eq!(parse_payload(&format!("{id}:3:5")), Some((id, 3, 5)));
        assert_eq!(parse_payload(&format!("{id}:5:3")), None);
        assert_eq!(parse_payload("nope"), None);
    }
}
