//! Transaction script shared by every command: idempotency, events, projections, notify.

use atb_core::DomainEvent;
use futures::future::BoxFuture;
use serde::Serialize;
use serde::de::DeserializeOwned;
use sqlx::PgConnection;
use time::OffsetDateTime;
use uuid::Uuid;

use crate::actor::Actor;
use crate::error::{AppError, AppResult};
use crate::metrics::Metrics;
use crate::realtime::Notifier;
use crate::repository::{StoredEvent, projector, store};
use crate::state::AppState;

const MAX_KEY_LEN: usize = 200;

/// Run `f` in one transaction. With an idempotency key, a repeated (actor, key) returns the first
/// successful response without running `f` again (AC-1.6). The key is locked with an advisory
/// lock BEFORE any task row, so concurrent duplicates serialize instead of both applying.
pub async fn run<T, F>(state: &AppState, actor: &Actor, key: Option<&str>, f: F) -> AppResult<T>
where
    T: Serialize + DeserializeOwned + Send,
    F: for<'c> FnOnce(&'c mut PgConnection) -> BoxFuture<'c, AppResult<T>>,
{
    Metrics::inc(&state.metrics.commands_total);
    let key = match key.map(str::trim) {
        Some(k) if k.is_empty() || k.len() > MAX_KEY_LEN => {
            return Err(AppError::BadRequest(
                "idempotency_key must be 1..200 characters".into(),
            ));
        }
        other => other,
    };
    let mut tx = state.pool.begin().await?;
    if let Some(k) = key {
        store::lock_idempotency_key(&mut tx, actor.id, k).await?;
        if let Some(previous) = store::idempotent_response(&mut tx, actor.id, k).await? {
            tx.rollback().await?;
            return Ok(serde_json::from_value(previous)?);
        }
    }
    let out = match f(&mut tx).await {
        Ok(out) => out,
        Err(e) => {
            Metrics::inc(&state.metrics.command_errors_total);
            return Err(e);
        }
    };
    if let Some(k) = key {
        let response = serde_json::to_value(&out)?;
        store::store_idempotent_response(&mut tx, actor.id, k, &response, super::now()).await?;
    }
    tx.commit().await?;
    Ok(out)
}

pub struct Emit<'a> {
    pub project_id: Uuid,
    pub actor_id: Uuid,
    pub trace_id: Option<&'a str>,
    pub at: OffsetDateTime,
}

/// Append `events` to the project log with gapless seqs, project them, and notify.
/// The caller must already hold its task row locks (tasks before the project row, §4).
pub async fn persist(
    conn: &mut PgConnection,
    notifier: &dyn Notifier,
    emit: &Emit<'_>,
    events: &[DomainEvent],
) -> AppResult<Vec<StoredEvent>> {
    if events.is_empty() {
        return Ok(Vec::new());
    }
    let n = events.len() as i64;
    let last = store::reserve_seqs(conn, emit.project_id, n, emit.at)
        .await?
        .ok_or_else(|| AppError::not_found("project"))?;
    let first = last - n + 1;
    let meta = projector::Meta {
        project_id: emit.project_id,
        actor_id: emit.actor_id,
        at: emit.at,
        trace_id: emit.trace_id,
    };
    let mut stored = Vec::with_capacity(events.len());
    for (i, ev) in events.iter().enumerate() {
        let seq = first + i as i64;
        let payload = ev.payload();
        store::insert_event(
            conn,
            emit.project_id,
            seq,
            ev.task_id(),
            ev.event_type(),
            emit.actor_id,
            &payload,
            emit.trace_id,
            emit.at,
        )
        .await?;
        projector::project(conn, ev, &meta).await?;
        stored.push(StoredEvent {
            project_id: emit.project_id,
            seq,
            task_id: ev.task_id(),
            event_type: ev.event_type().to_string(),
            actor_id: emit.actor_id,
            payload,
            trace_id: emit.trace_id.map(str::to_string),
            created_at: emit.at,
        });
    }
    notifier.notify(conn, emit.project_id, first, last).await?;
    Ok(stored)
}
