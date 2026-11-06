//! AC-1.8: rebuild a project's projections from its event log and compare them with the live
//! tables. Runs on a dedicated connection: TEMP tables with the projection names shadow the live
//! ones (`pg_temp` is searched first), so the very same projector SQL writes into them. Nothing
//! is committed.

use atb_core::DomainEvent;
use serde::Serialize;
use sqlx::{AssertSqlSafe, Connection, PgConnection, PgPool, Row};
use utoipa::ToSchema;
use uuid::Uuid;

use crate::error::{AppError, AppResult};
use crate::repository::{projector, reads};

/// (table, compared columns, public-side scope). Volatile timing fields are excluded:
/// `leases.expires_at` and `leases.last_heartbeat_at` (§3).
const TABLES: &[(&str, &str, &str)] = &[
    (
        "specs",
        "id, project_id, title, approved_version, created_at, updated_at",
        "project_id = $1",
    ),
    (
        "spec_versions",
        "spec_id, version, body_md, acceptance_criteria, protected_paths, test_ref, status, \
         author_id, approved_by, approved_at, created_at, updated_at",
        "spec_id IN (SELECT id FROM public.specs WHERE project_id = $1)",
    ),
    (
        "tasks",
        "id, project_id, parent_id, title, spec_id, spec_version, state, priority, version, \
         spec_outdated, preferred_actor_id, preferred_until, attempt_count, rejection_count, \
         created_by, created_at, updated_at",
        "project_id = $1",
    ),
    (
        "task_links",
        "from_id, to_id, kind, created_at",
        "to_id IN (SELECT id FROM public.tasks WHERE project_id = $1)",
    ),
    (
        "leases",
        "task_id, actor_id, kind, token_hash, paused, created_at, updated_at",
        "task_id IN (SELECT id FROM public.tasks WHERE project_id = $1)",
    ),
    (
        "attempts",
        "id, task_id, n, actor_id, actor_model, started_at, ended_at, outcome, commit_sha, \
         branch, handoff_note, trace_id, created_at, updated_at",
        "task_id IN (SELECT id FROM public.tasks WHERE project_id = $1)",
    ),
    (
        "questions",
        "id, task_id, asked_by, body, options, blocking, status, answered_by, answer, \
         answered_at, created_at, updated_at",
        "task_id IN (SELECT id FROM public.tasks WHERE project_id = $1)",
    ),
];

#[derive(Debug, Serialize, ToSchema)]
pub struct TableDiff {
    pub table: String,
    pub live_rows: i64,
    pub rebuilt_rows: i64,
    /// Rows present live but not produced by the replay.
    pub only_live: i64,
    /// Rows produced by the replay but absent live.
    pub only_rebuilt: i64,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct RebuildReport {
    pub project_id: Uuid,
    pub events: i64,
    pub tables: Vec<TableDiff>,
    pub ok: bool,
}

pub async fn check_project(pool: &PgPool, project_id: Uuid) -> AppResult<RebuildReport> {
    // A NEW connection, never a pooled one: a pooled connection may hold prepared statements
    // already bound to the live tables, which would make the replay write into them.
    let mut conn = PgConnection::connect_with(&pool.connect_options()).await?;
    let mut tx = conn.begin().await?;
    for (table, _, _) in TABLES {
        // Audited: `table` comes from the TABLES constant, never from input.
        sqlx::query(AssertSqlSafe(format!(
            "CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING DEFAULTS INCLUDING INDEXES) \
             ON COMMIT DROP"
        )))
        .execute(&mut *tx)
        .await?;
    }
    let mut after = 0;
    let mut events = 0;
    loop {
        let batch = reads::events_after(&mut tx, project_id, after, 1000).await?;
        if batch.is_empty() {
            break;
        }
        for stored in batch {
            after = stored.seq;
            events += 1;
            let ev = DomainEvent::from_stored(&stored.event_type, stored.payload.clone()).map_err(
                |e| AppError::Internal(anyhow::anyhow!("event {} unreadable: {e}", stored.seq)),
            )?;
            let meta = projector::Meta {
                project_id,
                actor_id: stored.actor_id,
                at: stored.created_at,
                trace_id: stored.trace_id.as_deref(),
            };
            projector::project(&mut tx, &ev, &meta).await?;
        }
    }
    let mut tables = Vec::new();
    for (table, cols, scope) in TABLES {
        let live = format!("SELECT {cols} FROM public.{table} WHERE {scope}");
        let rebuilt = format!("SELECT {cols} FROM pg_temp.{table}");
        let sql = format!(
            "SELECT (SELECT count(*) FROM ({live}) a) AS live_rows,
                    (SELECT count(*) FROM ({rebuilt}) b) AS rebuilt_rows,
                    (SELECT count(*) FROM (({live}) EXCEPT ALL ({rebuilt})) c) AS only_live,
                    (SELECT count(*) FROM (({rebuilt}) EXCEPT ALL ({live})) d) AS only_rebuilt"
        );
        // Audited: only TABLES constants are interpolated; the project id is a bind parameter.
        let row = sqlx::query(AssertSqlSafe(sql))
            .bind(project_id)
            .fetch_one(&mut *tx)
            .await?;
        tables.push(TableDiff {
            table: (*table).to_string(),
            live_rows: row.try_get("live_rows")?,
            rebuilt_rows: row.try_get("rebuilt_rows")?,
            only_live: row.try_get("only_live")?,
            only_rebuilt: row.try_get("only_rebuilt")?,
        });
    }
    tx.rollback().await?;
    let ok = tables
        .iter()
        .all(|t| t.only_live == 0 && t.only_rebuilt == 0);
    Ok(RebuildReport {
        project_id,
        events,
        tables,
        ok,
    })
}
