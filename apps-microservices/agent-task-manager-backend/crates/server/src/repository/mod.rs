//! DATA tier. Every function takes `&mut PgConnection` (never the pool) so the service layer owns
//! the transaction boundary (§4: one transaction per command).

pub mod access;
pub mod projector;
pub mod reads;

/// Non-projection storage: event log, sequence numbers, notifications, accounts, sessions,
/// idempotency keys, lease timing and the claim / sweeper scans.
pub mod store {
    use serde_json::Value;
    use sqlx::PgConnection;
    use time::OffsetDateTime;
    use uuid::Uuid;

    use crate::actor::Actor;

    /// Reserve `n` gapless sequence numbers on the project row. The row lock serializes writers
    /// per project, so seq order equals commit order (§6). Returns the LAST reserved seq.
    pub async fn reserve_seqs(
        conn: &mut PgConnection,
        project_id: Uuid,
        n: i64,
        at: OffsetDateTime,
    ) -> Result<Option<i64>, sqlx::Error> {
        sqlx::query_scalar!(
            r#"UPDATE projects SET event_seq = event_seq + $2, updated_at = $3
               WHERE id = $1 RETURNING event_seq"#,
            project_id,
            n,
            at
        )
        .fetch_optional(&mut *conn)
        .await
    }

    #[allow(clippy::too_many_arguments)]
    pub async fn insert_event(
        conn: &mut PgConnection,
        project_id: Uuid,
        seq: i64,
        task_id: Option<Uuid>,
        event_type: &str,
        actor_id: Uuid,
        payload: &Value,
        trace_id: Option<&str>,
        at: OffsetDateTime,
    ) -> Result<(), sqlx::Error> {
        sqlx::query!(
            r#"INSERT INTO events (project_id, seq, task_id, type, actor_id, payload, trace_id, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)"#,
            project_id,
            seq,
            task_id,
            event_type,
            actor_id,
            payload,
            trace_id,
            at
        )
        .execute(&mut *conn)
        .await?;
        Ok(())
    }

    /// `pg_notify` is transactional: delivered only if the command commits.
    pub async fn pg_notify(
        conn: &mut PgConnection,
        channel: &str,
        payload: &str,
    ) -> Result<(), sqlx::Error> {
        sqlx::query!("SELECT pg_notify($1, $2)", channel, payload)
            .execute(&mut *conn)
            .await?;
        Ok(())
    }

    /// Heartbeat: volatile timing fields only (§3), no event.
    pub async fn touch_lease(
        conn: &mut PgConnection,
        task_id: Uuid,
        expires_at: OffsetDateTime,
        at: OffsetDateTime,
    ) -> Result<(), sqlx::Error> {
        sqlx::query!(
            "UPDATE leases SET expires_at = $2, last_heartbeat_at = $3 WHERE task_id = $1",
            task_id,
            expires_at,
            at
        )
        .execute(&mut *conn)
        .await?;
        Ok(())
    }

    pub async fn insert_project(
        conn: &mut PgConnection,
        id: Uuid,
        name: &str,
        workflow: &Value,
        at: OffsetDateTime,
    ) -> Result<(), sqlx::Error> {
        sqlx::query!(
            r#"INSERT INTO projects (id, name, workflow, event_seq, created_at, updated_at)
               VALUES ($1, $2, $3, 0, $4, $4)"#,
            id,
            name,
            workflow,
            at
        )
        .execute(&mut *conn)
        .await?;
        Ok(())
    }

    pub struct NewActor<'a> {
        pub id: Uuid,
        pub kind: &'a str,
        pub name: &'a str,
        pub model: Option<&'a str>,
        pub roles: Vec<String>,
        pub token_hash: Option<String>,
        pub password_hash: Option<String>,
        pub login: Option<&'a str>,
        pub gateway_subject: Option<&'a str>,
    }

    pub async fn insert_actor(conn: &mut PgConnection, a: NewActor<'_>) -> Result<(), sqlx::Error> {
        sqlx::query!(
            r#"INSERT INTO actors (id, kind, name, model, roles, token_hash, password_hash, login,
                   gateway_subject)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)"#,
            a.id,
            a.kind,
            a.name,
            a.model,
            &a.roles,
            a.token_hash,
            a.password_hash,
            a.login,
            a.gateway_subject
        )
        .execute(&mut *conn)
        .await?;
        Ok(())
    }

    pub async fn actor_by_token_hash(
        conn: &mut PgConnection,
        hash: &str,
    ) -> Result<Option<Actor>, sqlx::Error> {
        let r = sqlx::query!(
            "SELECT id, kind, name, roles, model FROM actors WHERE token_hash = $1",
            hash
        )
        .fetch_optional(&mut *conn)
        .await?;
        Ok(r.map(|r| Actor::from_row(r.id, &r.kind, r.name, &r.roles, r.model)))
    }

    pub async fn actor_by_gateway_subject(
        conn: &mut PgConnection,
        subject: &str,
    ) -> Result<Option<Actor>, sqlx::Error> {
        let r = sqlx::query!(
            "SELECT id, kind, name, roles, model FROM actors WHERE gateway_subject = $1",
            subject
        )
        .fetch_optional(&mut *conn)
        .await?;
        Ok(r.map(|r| Actor::from_row(r.id, &r.kind, r.name, &r.roles, r.model)))
    }

    pub async fn actor_by_session(
        conn: &mut PgConnection,
        session_hash: &str,
        now: OffsetDateTime,
    ) -> Result<Option<Actor>, sqlx::Error> {
        let r = sqlx::query!(
            r#"SELECT a.id, a.kind, a.name, a.roles, a.model FROM sessions s
               JOIN actors a ON a.id = s.actor_id
               WHERE s.token_hash = $1 AND s.expires_at > $2"#,
            session_hash,
            now
        )
        .fetch_optional(&mut *conn)
        .await?;
        Ok(r.map(|r| Actor::from_row(r.id, &r.kind, r.name, &r.roles, r.model)))
    }

    pub async fn human_credentials(
        conn: &mut PgConnection,
        login: &str,
    ) -> Result<Option<(Actor, String)>, sqlx::Error> {
        let r = sqlx::query!(
            r#"SELECT id, kind, name, roles, model, password_hash AS "password_hash!"
               FROM actors WHERE login = $1 AND kind = 'human' AND password_hash IS NOT NULL"#,
            login
        )
        .fetch_optional(&mut *conn)
        .await?;
        Ok(r.map(|r| {
            (
                Actor::from_row(r.id, &r.kind, r.name, &r.roles, r.model),
                r.password_hash,
            )
        }))
    }

    pub async fn count_humans(conn: &mut PgConnection) -> Result<i64, sqlx::Error> {
        sqlx::query_scalar!(r#"SELECT count(*) AS "n!" FROM actors WHERE kind = 'human'"#)
            .fetch_one(&mut *conn)
            .await
    }

    pub async fn insert_session(
        conn: &mut PgConnection,
        hash: &str,
        actor_id: Uuid,
        expires_at: OffsetDateTime,
    ) -> Result<(), sqlx::Error> {
        sqlx::query!(
            "INSERT INTO sessions (token_hash, actor_id, expires_at) VALUES ($1, $2, $3)",
            hash,
            actor_id,
            expires_at
        )
        .execute(&mut *conn)
        .await?;
        Ok(())
    }

    pub async fn delete_session(conn: &mut PgConnection, hash: &str) -> Result<(), sqlx::Error> {
        sqlx::query!("DELETE FROM sessions WHERE token_hash = $1", hash)
            .execute(&mut *conn)
            .await?;
        Ok(())
    }

    /// Presence: at most one write per actor every 5 s.
    pub async fn touch_actor(
        conn: &mut PgConnection,
        id: Uuid,
        now: OffsetDateTime,
    ) -> Result<(), sqlx::Error> {
        sqlx::query!(
            r#"UPDATE actors SET last_seen_at = $2
               WHERE id = $1
                 AND (last_seen_at IS NULL OR last_seen_at < $2::timestamptz - interval '5 seconds')"#,
            id,
            now
        )
        .execute(&mut *conn)
        .await?;
        Ok(())
    }

    /// Serialize concurrent requests carrying the same (actor, idempotency key).
    pub async fn lock_idempotency_key(
        conn: &mut PgConnection,
        actor_id: Uuid,
        key: &str,
    ) -> Result<(), sqlx::Error> {
        let lock_key = format!("{actor_id}:{key}");
        sqlx::query!(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            lock_key
        )
        .execute(&mut *conn)
        .await?;
        Ok(())
    }

    pub async fn idempotent_response(
        conn: &mut PgConnection,
        actor_id: Uuid,
        key: &str,
    ) -> Result<Option<Value>, sqlx::Error> {
        sqlx::query_scalar!(
            "SELECT response FROM idempotency_keys WHERE actor_id = $1 AND key = $2",
            actor_id,
            key
        )
        .fetch_optional(&mut *conn)
        .await
    }

    pub async fn store_idempotent_response(
        conn: &mut PgConnection,
        actor_id: Uuid,
        key: &str,
        response: &Value,
        at: OffsetDateTime,
    ) -> Result<(), sqlx::Error> {
        sqlx::query!(
            r#"INSERT INTO idempotency_keys (actor_id, key, response, created_at)
               VALUES ($1, $2, $3, $4)"#,
            actor_id,
            key,
            response,
            at
        )
        .execute(&mut *conn)
        .await?;
        Ok(())
    }

    pub async fn purge(conn: &mut PgConnection, now: OffsetDateTime) -> Result<(), sqlx::Error> {
        sqlx::query!(
            "DELETE FROM idempotency_keys WHERE created_at < $1",
            now - time::Duration::hours(24)
        )
        .execute(&mut *conn)
        .await?;
        sqlx::query!("DELETE FROM sessions WHERE expires_at < $1", now)
            .execute(&mut *conn)
            .await?;
        Ok(())
    }

    /// Unpaused leases past their expiry (sweeper scan).
    pub async fn expired_leases(
        conn: &mut PgConnection,
        now: OffsetDateTime,
        limit: i64,
    ) -> Result<Vec<Uuid>, sqlx::Error> {
        sqlx::query_scalar!(
            r#"SELECT task_id FROM leases WHERE NOT paused AND expires_at <= $1
               ORDER BY expires_at LIMIT $2"#,
            now,
            limit
        )
        .fetch_all(&mut *conn)
        .await
    }

    /// Lock one expired task without waiting: a busy row is retried on the next sweep.
    pub async fn try_lock_task(
        conn: &mut PgConnection,
        task_id: Uuid,
    ) -> Result<bool, sqlx::Error> {
        let row = sqlx::query_scalar!(
            "SELECT id FROM tasks WHERE id = $1 FOR UPDATE SKIP LOCKED",
            task_id
        )
        .fetch_optional(&mut *conn)
        .await?;
        Ok(row.is_some())
    }

    /// The reference claim query (§7): best claimable ready task, skipping rows locked by
    /// concurrent claimers. `$3` is the server clock (one clock for every lease decision).
    pub async fn claim_candidate(
        conn: &mut PgConnection,
        project_id: Uuid,
        actor_id: Uuid,
        now: OffsetDateTime,
    ) -> Result<Option<Uuid>, sqlx::Error> {
        sqlx::query_scalar!(
            r#"SELECT t.id FROM tasks t
               WHERE t.project_id = $1 AND t.state = 'ready' AND NOT t.spec_outdated
                 AND NOT EXISTS (
                   SELECT 1 FROM task_links l JOIN tasks b ON b.id = l.from_id
                   WHERE l.to_id = t.id AND l.kind = 'blocks' AND b.state <> 'done')
                 AND (t.preferred_actor_id IS NULL OR t.preferred_until < $3 OR t.preferred_actor_id = $2)
               ORDER BY t.priority DESC, t.created_at
               FOR UPDATE OF t SKIP LOCKED
               LIMIT 1"#,
            project_id,
            actor_id,
            now
        )
        .fetch_optional(&mut *conn)
        .await
    }

    /// Best unclaimed review that the actor did not implement.
    pub async fn review_candidate(
        conn: &mut PgConnection,
        project_id: Uuid,
        actor_id: Uuid,
    ) -> Result<Option<Uuid>, sqlx::Error> {
        sqlx::query_scalar!(
            r#"SELECT t.id FROM tasks t
               WHERE t.project_id = $1 AND t.state = 'in_review'
                 AND NOT EXISTS (SELECT 1 FROM leases l WHERE l.task_id = t.id)
                 AND NOT EXISTS (SELECT 1 FROM attempts a
                                 WHERE a.task_id = t.id AND a.ended_at IS NULL AND a.actor_id = $2)
               ORDER BY t.priority DESC, t.created_at
               FOR UPDATE OF t SKIP LOCKED
               LIMIT 1"#,
            project_id,
            actor_id
        )
        .fetch_optional(&mut *conn)
        .await
    }

    /// Claimable tasks for `list_ready` (no locking).
    pub async fn ready_task_ids(
        conn: &mut PgConnection,
        project_id: Uuid,
        actor_id: Uuid,
        now: OffsetDateTime,
        reviewer: bool,
        limit: i64,
    ) -> Result<Vec<Uuid>, sqlx::Error> {
        if reviewer {
            return sqlx::query_scalar!(
                r#"SELECT t.id FROM tasks t
                   WHERE t.project_id = $1 AND t.state = 'in_review'
                     AND NOT EXISTS (SELECT 1 FROM leases l WHERE l.task_id = t.id)
                     AND NOT EXISTS (SELECT 1 FROM attempts a
                                     WHERE a.task_id = t.id AND a.ended_at IS NULL AND a.actor_id = $2)
                   ORDER BY t.priority DESC, t.created_at LIMIT $3"#,
                project_id,
                actor_id,
                limit
            )
            .fetch_all(&mut *conn)
            .await;
        }
        sqlx::query_scalar!(
            r#"SELECT t.id FROM tasks t
               WHERE t.project_id = $1 AND t.state = 'ready' AND NOT t.spec_outdated
                 AND NOT EXISTS (
                   SELECT 1 FROM task_links l JOIN tasks b ON b.id = l.from_id
                   WHERE l.to_id = t.id AND l.kind = 'blocks' AND b.state <> 'done')
                 AND (t.preferred_actor_id IS NULL OR t.preferred_until < $3 OR t.preferred_actor_id = $2)
               ORDER BY t.priority DESC, t.created_at LIMIT $4"#,
            project_id,
            actor_id,
            now,
            limit
        )
        .fetch_all(&mut *conn)
        .await
    }

    /// Non-terminal tasks pinned to a spec, locked in id order (spec approval fan-out).
    pub async fn lock_spec_tasks(
        conn: &mut PgConnection,
        spec_id: Uuid,
    ) -> Result<Vec<Uuid>, sqlx::Error> {
        sqlx::query_scalar!(
            r#"SELECT id FROM tasks
               WHERE spec_id = $1 AND state NOT IN ('done', 'failed', 'cancelled')
               ORDER BY id FOR UPDATE"#,
            spec_id
        )
        .fetch_all(&mut *conn)
        .await
    }

    /// Lock rows that a new row will reference by foreign key (no deadlock with the project row).
    pub async fn key_share_tasks(
        conn: &mut PgConnection,
        ids: &[Uuid],
    ) -> Result<Vec<(Uuid, Uuid)>, sqlx::Error> {
        if ids.is_empty() {
            return Ok(Vec::new());
        }
        let rows = sqlx::query!(
            "SELECT id, project_id FROM tasks WHERE id = ANY($1) ORDER BY id FOR KEY SHARE",
            ids
        )
        .fetch_all(&mut *conn)
        .await?;
        Ok(rows.into_iter().map(|r| (r.id, r.project_id)).collect())
    }

    /// Serialize proposals and approvals of one spec. `NO KEY UPDATE` does not block the
    /// foreign-key checks of concurrent task inserts.
    pub async fn lock_spec(
        conn: &mut PgConnection,
        spec_id: Uuid,
    ) -> Result<Option<(Uuid, String)>, sqlx::Error> {
        let r = sqlx::query!(
            "SELECT project_id, title FROM specs WHERE id = $1 FOR NO KEY UPDATE",
            spec_id
        )
        .fetch_optional(&mut *conn)
        .await?;
        Ok(r.map(|r| (r.project_id, r.title)))
    }

    pub async fn spec_project(
        conn: &mut PgConnection,
        spec_id: Uuid,
    ) -> Result<Option<(Uuid, String)>, sqlx::Error> {
        let r = sqlx::query!("SELECT project_id, title FROM specs WHERE id = $1", spec_id)
            .fetch_optional(&mut *conn)
            .await?;
        Ok(r.map(|r| (r.project_id, r.title)))
    }

    pub async fn spec_version_status(
        conn: &mut PgConnection,
        spec_id: Uuid,
        version: i32,
    ) -> Result<Option<String>, sqlx::Error> {
        sqlx::query_scalar!(
            "SELECT status FROM spec_versions WHERE spec_id = $1 AND version = $2",
            spec_id,
            version
        )
        .fetch_optional(&mut *conn)
        .await
    }

    pub async fn latest_spec_version(
        conn: &mut PgConnection,
        spec_id: Uuid,
    ) -> Result<i32, sqlx::Error> {
        let v = sqlx::query_scalar!(
            "SELECT max(version) FROM spec_versions WHERE spec_id = $1",
            spec_id
        )
        .fetch_one(&mut *conn)
        .await?;
        Ok(v.unwrap_or(0))
    }

    /// Project of a task, or `None` if the task does not exist.
    pub async fn task_project(
        conn: &mut PgConnection,
        task_id: Uuid,
    ) -> Result<Option<Uuid>, sqlx::Error> {
        sqlx::query_scalar!("SELECT project_id FROM tasks WHERE id = $1", task_id)
            .fetch_optional(&mut *conn)
            .await
    }

    /// Short history used to explain a failed task in the human question.
    pub async fn attempt_summary(
        conn: &mut PgConnection,
        task_id: Uuid,
    ) -> Result<Vec<String>, sqlx::Error> {
        let rows = sqlx::query!(
            r#"SELECT at.n, a.name, at.outcome, at.handoff_note FROM attempts at
               JOIN actors a ON a.id = at.actor_id WHERE at.task_id = $1 ORDER BY at.n"#,
            task_id
        )
        .fetch_all(&mut *conn)
        .await?;
        Ok(rows
            .into_iter()
            .map(|r| {
                format!(
                    "#{} by {}: {}{}",
                    r.n,
                    r.name,
                    r.outcome.unwrap_or_else(|| "open".into()),
                    r.handoff_note
                        .map(|n| format!(" — {n}"))
                        .unwrap_or_default()
                )
            })
            .collect())
    }
}

use serde::{Deserialize, Serialize};
use serde_json::Value;
use time::OffsetDateTime;
use utoipa::ToSchema;
use uuid::Uuid;

/// A row of the append-only `events` table, as sent over SSE and `/events`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct StoredEvent {
    pub project_id: Uuid,
    pub seq: i64,
    pub task_id: Option<Uuid>,
    #[serde(rename = "type")]
    pub event_type: String,
    pub actor_id: Uuid,
    #[schema(value_type = Object)]
    pub payload: Value,
    pub trace_id: Option<String>,
    #[serde(with = "time::serde::rfc3339")]
    pub created_at: OffsetDateTime,
}

/// Hex SHA-256 of a secret (lease tokens, bearer tokens, session cookies). Secrets are never
/// stored or logged in clear.
pub fn sha256_hex(secret: &str) -> String {
    use sha2::{Digest, Sha256};
    hex::encode(Sha256::digest(secret.as_bytes()))
}

/// 32 random bytes, hex encoded (§8 token format).
pub fn random_token() -> String {
    use rand::RngCore;
    let mut bytes = [0u8; 32];
    rand::rng().fill_bytes(&mut bytes);
    hex::encode(bytes)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tokens_are_32_random_bytes_and_hash_deterministically() {
        let a = random_token();
        assert_eq!(a.len(), 64);
        assert_ne!(a, random_token());
        assert_eq!(sha256_hex(&a), sha256_hex(&a));
        assert_ne!(sha256_hex(&a), a);
    }
}
