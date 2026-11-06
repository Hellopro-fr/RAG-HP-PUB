//! `wait_for_updates` (§7): long-poll for events relevant to the caller, capped at 25 s.

use std::collections::HashSet;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use tokio::sync::broadcast::error::RecvError;
use utoipa::ToSchema;
use uuid::Uuid;

use super::ratelimit::Bucket;
use crate::actor::Actor;
use crate::error::{AppError, AppResult};
use crate::repository::{StoredEvent, reads};
use crate::state::AppState;

pub const MAX_WAIT_SECS: u64 = 25;

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct Updates {
    /// Pass this back as `cursor` on the next call.
    pub cursor: i64,
    pub events: Vec<StoredEvent>,
    pub timed_out: bool,
}

/// What the caller cares about: tasks it holds or worked on, its questions.
struct Interest {
    me: Uuid,
    tasks: HashSet<Uuid>,
    questions: HashSet<Uuid>,
}

impl Interest {
    /// Relevant: events on my tasks, answers to my questions, tasks becoming ready. My own events
    /// only update the interest sets (an agent never wakes itself up).
    fn relevant(&mut self, ev: &StoredEvent) -> bool {
        let p = &ev.payload;
        let uuid = |key: &str| {
            p.get(key)
                .and_then(|v| v.as_str())
                .and_then(|s| s.parse().ok())
        };
        if ev.actor_id == self.me {
            if let (Some(task), "lease.claimed") = (ev.task_id, ev.event_type.as_str()) {
                self.tasks.insert(task);
            }
            if ev.event_type == "question.asked"
                && let Some(q) = uuid("question_id")
            {
                self.questions.insert(q);
            }
            return false;
        }
        match ev.event_type.as_str() {
            "question.answered" => uuid("question_id").is_some_and(|q| self.questions.contains(&q)),
            "task.state_changed" if p.get("to").and_then(|v| v.as_str()) == Some("ready") => true,
            "task.created" if p.get("state").and_then(|v| v.as_str()) == Some("ready") => true,
            _ => ev.task_id.is_some_and(|t| self.tasks.contains(&t)),
        }
    }
}

pub async fn wait_for_updates(
    st: &AppState,
    actor: &Actor,
    project_id: Uuid,
    cursor: i64,
    timeout_secs: u64,
) -> AppResult<Updates> {
    if !st
        .limiter
        .allow(actor.id, Bucket::Wait, st.cfg.max_waits_per_min)
    {
        return Err(AppError::RateLimited(format!(
            "at most {} wait_for_updates per minute",
            st.cfg.max_waits_per_min
        )));
    }
    let timeout = Duration::from_secs(timeout_secs.clamp(0, MAX_WAIT_SECS));
    // Subscribe BEFORE scanning the table so nothing committed in between is missed.
    let mut rx = st.hub.subscribe();
    let mut cursor = cursor.max(0);
    let mut interest = {
        let mut conn = st.pool.acquire().await?;
        reads::project_seq(&mut conn, project_id)
            .await?
            .ok_or_else(|| AppError::not_found("project"))?;
        let (tasks, questions) = reads::actor_interest(&mut conn, project_id, actor.id).await?;
        Interest {
            me: actor.id,
            tasks: tasks.into_iter().collect(),
            questions: questions.into_iter().collect(),
        }
    };
    let mut found = scan(st, project_id, &mut cursor, &mut interest).await?;
    if !found.is_empty() {
        return Ok(Updates {
            cursor,
            events: found,
            timed_out: false,
        });
    }
    let deadline = tokio::time::Instant::now() + timeout;
    loop {
        tokio::select! {
            _ = tokio::time::sleep_until(deadline) => {
                return Ok(Updates { cursor, events: found, timed_out: true });
            }
            msg = rx.recv() => match msg {
                Ok(ev) if ev.project_id == project_id && ev.seq > cursor => {
                    if ev.seq > cursor + 1 {
                        // The hub skipped ahead of us: read the gap from the table.
                        found = scan(st, project_id, &mut cursor, &mut interest).await?;
                    } else {
                        cursor = ev.seq;
                        if interest.relevant(&ev) {
                            found.push((*ev).clone());
                        }
                    }
                    if !found.is_empty() {
                        return Ok(Updates { cursor, events: found, timed_out: false });
                    }
                }
                Ok(_) => {}
                Err(RecvError::Lagged(_)) => {
                    found = scan(st, project_id, &mut cursor, &mut interest).await?;
                    if !found.is_empty() {
                        return Ok(Updates { cursor, events: found, timed_out: false });
                    }
                }
                Err(RecvError::Closed) => {
                    return Ok(Updates { cursor, events: found, timed_out: true });
                }
            }
        }
    }
}

/// Read every event after `cursor` from the table, advance the cursor, keep the relevant ones.
async fn scan(
    st: &AppState,
    project_id: Uuid,
    cursor: &mut i64,
    interest: &mut Interest,
) -> AppResult<Vec<StoredEvent>> {
    let mut conn = st.pool.acquire().await?;
    let mut found = Vec::new();
    loop {
        let batch = reads::events_after(&mut conn, project_id, *cursor, 500).await?;
        let full = batch.len() == 500;
        for ev in batch {
            *cursor = ev.seq;
            if interest.relevant(&ev) {
                found.push(ev);
            }
        }
        if !full {
            return Ok(found);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn ev(actor: Uuid, task: Option<Uuid>, ty: &str, payload: serde_json::Value) -> StoredEvent {
        StoredEvent {
            project_id: Uuid::now_v7(),
            seq: 1,
            task_id: task,
            event_type: ty.into(),
            actor_id: actor,
            payload,
            trace_id: None,
            created_at: time::OffsetDateTime::UNIX_EPOCH,
        }
    }

    #[test]
    fn relevance_rules() {
        let me = Uuid::now_v7();
        let other = Uuid::now_v7();
        let mine = Uuid::now_v7();
        let q = Uuid::now_v7();
        let mut i = Interest {
            me,
            tasks: HashSet::new(),
            questions: HashSet::new(),
        };
        // My own claim and question only teach the interest sets.
        assert!(!i.relevant(&ev(me, Some(mine), "lease.claimed", json!({}))));
        assert!(!i.relevant(&ev(
            me,
            Some(mine),
            "question.asked",
            json!({"question_id": q})
        )));
        assert!(i.relevant(&ev(other, Some(mine), "activity.reported", json!({}))));
        assert!(i.relevant(&ev(
            other,
            Some(mine),
            "question.answered",
            json!({"question_id": q})
        )));
        assert!(i.relevant(&ev(
            other,
            Some(Uuid::now_v7()),
            "task.state_changed",
            json!({"to": "ready"})
        )));
        assert!(!i.relevant(&ev(
            other,
            Some(Uuid::now_v7()),
            "task.state_changed",
            json!({"to": "working"})
        )));
    }
}
