//! Read access: aggregate snapshots for the decider (optionally `FOR UPDATE`), decision context,
//! and the read models returned by the API.

use atb_core::{
    AcRef, Attempt, Lease, LeaseKind, QuestionRef, TaskSnapshot, TaskState, WorkflowConfig,
};
use serde::Serialize;
use serde_json::Value;
use sqlx::PgConnection;
use time::OffsetDateTime;
use utoipa::ToSchema;
use uuid::Uuid;

use super::StoredEvent;

// ------------------------------------------------------------------------------------------------
// Aggregate snapshots
// ------------------------------------------------------------------------------------------------

struct TaskRow {
    id: Uuid,
    project_id: Uuid,
    title: String,
    priority: i32,
    state: String,
    version: i32,
    spec_id: Uuid,
    spec_version: i32,
    spec_outdated: bool,
    preferred_actor_id: Option<Uuid>,
    preferred_until: Option<OffsetDateTime>,
    attempt_count: i32,
    rejection_count: i32,
}

/// Load the task aggregate, locking the task row `FOR UPDATE` when `lock` is set.
pub async fn load_snapshot(
    conn: &mut PgConnection,
    task_id: Uuid,
    lock: bool,
) -> Result<Option<TaskSnapshot>, sqlx::Error> {
    let row = if lock {
        sqlx::query_as!(
            TaskRow,
            r#"SELECT id, project_id, title, priority, state, version, spec_id, spec_version,
                   spec_outdated, preferred_actor_id, preferred_until, attempt_count, rejection_count
               FROM tasks WHERE id = $1 FOR UPDATE"#,
            task_id
        )
        .fetch_optional(&mut *conn)
        .await?
    } else {
        sqlx::query_as!(
            TaskRow,
            r#"SELECT id, project_id, title, priority, state, version, spec_id, spec_version,
                   spec_outdated, preferred_actor_id, preferred_until, attempt_count, rejection_count
               FROM tasks WHERE id = $1"#,
            task_id
        )
        .fetch_optional(&mut *conn)
        .await?
    };
    let Some(t) = row else { return Ok(None) };
    let lease = sqlx::query!(
        "SELECT actor_id, kind, token_hash, expires_at, paused FROM leases WHERE task_id = $1",
        task_id
    )
    .fetch_optional(&mut *conn)
    .await?
    .map(|l| Lease {
        actor_id: l.actor_id,
        kind: LeaseKind::parse(&l.kind).unwrap_or(LeaseKind::Work),
        token_hash: l.token_hash,
        expires_at: l.expires_at,
        paused: l.paused,
    });
    let attempt = sqlx::query!(
        r#"SELECT id, n, actor_id, actor_model, commit_sha, branch
           FROM attempts WHERE task_id = $1 AND ended_at IS NULL"#,
        task_id
    )
    .fetch_optional(&mut *conn)
    .await?
    .map(|a| Attempt {
        id: a.id,
        n: a.n,
        actor_id: a.actor_id,
        actor_model: a.actor_model,
        commit_sha: a.commit_sha,
        branch: a.branch,
    });
    Ok(Some(TaskSnapshot {
        id: t.id,
        project_id: t.project_id,
        title: t.title,
        priority: t.priority,
        state: TaskState::parse(&t.state).unwrap_or(TaskState::Draft),
        version: t.version,
        spec_id: t.spec_id,
        spec_version: t.spec_version,
        spec_outdated: t.spec_outdated,
        preferred_actor_id: t.preferred_actor_id,
        preferred_until: t.preferred_until,
        attempt_count: t.attempt_count,
        rejection_count: t.rejection_count,
        lease,
        attempt,
    }))
}

// ------------------------------------------------------------------------------------------------
// Decision context
// ------------------------------------------------------------------------------------------------

pub async fn project_workflow(
    conn: &mut PgConnection,
    project_id: Uuid,
) -> Result<Option<WorkflowConfig>, sqlx::Error> {
    let row = sqlx::query_scalar!("SELECT workflow FROM projects WHERE id = $1", project_id)
        .fetch_optional(&mut *conn)
        .await?;
    Ok(row.and_then(|v| serde_json::from_value(v).ok()))
}

pub async fn blocker_states(
    conn: &mut PgConnection,
    task_id: Uuid,
) -> Result<Vec<TaskState>, sqlx::Error> {
    let rows = sqlx::query_scalar!(
        r#"SELECT b.state FROM task_links l JOIN tasks b ON b.id = l.from_id
           WHERE l.to_id = $1 AND l.kind = 'blocks'"#,
        task_id
    )
    .fetch_all(&mut *conn)
    .await?;
    Ok(rows.iter().filter_map(|s| TaskState::parse(s)).collect())
}

pub async fn approved_spec_version(
    conn: &mut PgConnection,
    spec_id: Uuid,
) -> Result<Option<i32>, sqlx::Error> {
    let v = sqlx::query_scalar!("SELECT approved_version FROM specs WHERE id = $1", spec_id)
        .fetch_optional(&mut *conn)
        .await?;
    Ok(v.flatten())
}

pub async fn acceptance_criteria(
    conn: &mut PgConnection,
    spec_id: Uuid,
    version: i32,
) -> Result<Vec<AcRef>, sqlx::Error> {
    let acs = sqlx::query_scalar!(
        "SELECT acceptance_criteria FROM spec_versions WHERE spec_id = $1 AND version = $2",
        spec_id,
        version
    )
    .fetch_optional(&mut *conn)
    .await?;
    Ok(parse_acs(acs.as_ref()))
}

/// `[{id, text, verify: {kind}}]` → references used by the review guards.
pub fn parse_acs(acs: Option<&Value>) -> Vec<AcRef> {
    acs.and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|ac| {
                    Some(AcRef {
                        id: ac.get("id")?.as_str()?.to_string(),
                        human_only: ac.pointer("/verify/kind").and_then(Value::as_str)
                            == Some("human"),
                    })
                })
                .collect()
        })
        .unwrap_or_default()
}

pub async fn project_block_edges(
    conn: &mut PgConnection,
    project_id: Uuid,
) -> Result<Vec<(Uuid, Uuid)>, sqlx::Error> {
    let rows = sqlx::query!(
        r#"SELECT l.from_id, l.to_id FROM task_links l JOIN tasks t ON t.id = l.to_id
           WHERE t.project_id = $1 AND l.kind = 'blocks'"#,
        project_id
    )
    .fetch_all(&mut *conn)
    .await?;
    Ok(rows.into_iter().map(|r| (r.from_id, r.to_id)).collect())
}

pub async fn link_exists(
    conn: &mut PgConnection,
    from: Uuid,
    to: Uuid,
    kind: &str,
) -> Result<bool, sqlx::Error> {
    let found = sqlx::query_scalar!(
        r#"SELECT EXISTS (SELECT 1 FROM task_links WHERE from_id = $1 AND to_id = $2 AND kind = $3)
           AS "e!""#,
        from,
        to,
        kind
    )
    .fetch_one(&mut *conn)
    .await?;
    Ok(found)
}

/// The question to answer: its task id and the decider's view of it.
pub async fn question_ref(
    conn: &mut PgConnection,
    question_id: Uuid,
) -> Result<Option<(Uuid, QuestionRef)>, sqlx::Error> {
    let row = sqlx::query!(
        "SELECT task_id, asked_by, blocking, status FROM questions WHERE id = $1",
        question_id
    )
    .fetch_optional(&mut *conn)
    .await?;
    Ok(row.map(|q| {
        (
            q.task_id,
            QuestionRef {
                id: question_id,
                asked_by: q.asked_by,
                blocking: q.blocking,
                open: q.status == "open",
            },
        )
    }))
}

// ------------------------------------------------------------------------------------------------
// Events
// ------------------------------------------------------------------------------------------------

pub async fn events_after(
    conn: &mut PgConnection,
    project_id: Uuid,
    after: i64,
    limit: i64,
) -> Result<Vec<StoredEvent>, sqlx::Error> {
    sqlx::query_as!(
        StoredEvent,
        r#"SELECT project_id, seq, task_id, type AS event_type, actor_id, payload, trace_id, created_at
           FROM events WHERE project_id = $1 AND seq > $2 ORDER BY seq LIMIT $3"#,
        project_id,
        after,
        limit
    )
    .fetch_all(&mut *conn)
    .await
}

pub async fn events_between(
    conn: &mut PgConnection,
    project_id: Uuid,
    after: i64,
    up_to: i64,
) -> Result<Vec<StoredEvent>, sqlx::Error> {
    sqlx::query_as!(
        StoredEvent,
        r#"SELECT project_id, seq, task_id, type AS event_type, actor_id, payload, trace_id, created_at
           FROM events WHERE project_id = $1 AND seq > $2 AND seq <= $3 ORDER BY seq"#,
        project_id,
        after,
        up_to
    )
    .fetch_all(&mut *conn)
    .await
}

pub async fn task_events(
    conn: &mut PgConnection,
    task_id: Uuid,
    limit: i64,
) -> Result<Vec<StoredEvent>, sqlx::Error> {
    sqlx::query_as!(
        StoredEvent,
        r#"SELECT project_id, seq, task_id, type AS event_type, actor_id, payload, trace_id, created_at
           FROM events WHERE task_id = $1 ORDER BY seq LIMIT $2"#,
        task_id,
        limit
    )
    .fetch_all(&mut *conn)
    .await
}

pub async fn recent_activity(
    conn: &mut PgConnection,
    task_id: Uuid,
    limit: i64,
) -> Result<Vec<StoredEvent>, sqlx::Error> {
    let mut rows = sqlx::query_as!(
        StoredEvent,
        r#"SELECT project_id, seq, task_id, type AS event_type, actor_id, payload, trace_id, created_at
           FROM events WHERE task_id = $1 AND type = 'activity.reported'
           ORDER BY seq DESC LIMIT $2"#,
        task_id,
        limit
    )
    .fetch_all(&mut *conn)
    .await?;
    rows.reverse();
    Ok(rows)
}

pub async fn project_seq(
    conn: &mut PgConnection,
    project_id: Uuid,
) -> Result<Option<i64>, sqlx::Error> {
    sqlx::query_scalar!("SELECT event_seq FROM projects WHERE id = $1", project_id)
        .fetch_optional(&mut *conn)
        .await
}

// ------------------------------------------------------------------------------------------------
// Read models
// ------------------------------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, serde::Deserialize, ToSchema)]
pub struct ProjectView {
    pub id: Uuid,
    pub name: String,
    #[schema(value_type = Object)]
    pub workflow: Value,
    pub event_seq: i64,
    #[serde(with = "time::serde::rfc3339")]
    pub created_at: OffsetDateTime,
}

pub async fn projects(conn: &mut PgConnection) -> Result<Vec<ProjectView>, sqlx::Error> {
    sqlx::query_as!(
        ProjectView,
        "SELECT id, name, workflow, event_seq, created_at FROM projects ORDER BY created_at"
    )
    .fetch_all(&mut *conn)
    .await
}

pub async fn project(
    conn: &mut PgConnection,
    id: Uuid,
) -> Result<Option<ProjectView>, sqlx::Error> {
    sqlx::query_as!(
        ProjectView,
        "SELECT id, name, workflow, event_seq, created_at FROM projects WHERE id = $1",
        id
    )
    .fetch_optional(&mut *conn)
    .await
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct LeaseView {
    pub actor_id: Uuid,
    pub actor_name: String,
    pub kind: String,
    #[serde(with = "time::serde::rfc3339")]
    pub expires_at: OffsetDateTime,
    pub paused: bool,
    #[serde(with = "time::serde::rfc3339::option")]
    pub last_heartbeat_at: Option<OffsetDateTime>,
}

/// A task as shown on the board (§10): state, holder with lease, derived badges.
#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct TaskView {
    pub id: Uuid,
    pub project_id: Uuid,
    pub parent_id: Option<Uuid>,
    pub title: String,
    pub state: String,
    pub priority: i32,
    pub version: i32,
    pub spec_id: Uuid,
    pub spec_version: i32,
    pub spec_outdated: bool,
    pub preferred_actor_id: Option<Uuid>,
    #[serde(with = "time::serde::rfc3339::option")]
    pub preferred_until: Option<OffsetDateTime>,
    pub attempt_count: i32,
    pub rejection_count: i32,
    /// Derived: a `blocks` predecessor is not done.
    pub blocked: bool,
    pub open_questions: i64,
    pub blocking_questions: i64,
    pub lease: Option<LeaseView>,
    #[serde(with = "time::serde::rfc3339")]
    pub created_at: OffsetDateTime,
    #[serde(with = "time::serde::rfc3339")]
    pub updated_at: OffsetDateTime,
}

/// Board tasks of a project, or one task by id (exactly one filter is set).
pub async fn task_views(
    conn: &mut PgConnection,
    project_id: Option<Uuid>,
    task_id: Option<Uuid>,
) -> Result<Vec<TaskView>, sqlx::Error> {
    let rows = sqlx::query!(
        r#"SELECT t.id, t.project_id, t.parent_id, t.title, t.state, t.priority, t.version, t.spec_id,
               t.spec_version, t.spec_outdated, t.preferred_actor_id, t.preferred_until,
               t.attempt_count, t.rejection_count, t.created_at, t.updated_at,
               EXISTS (SELECT 1 FROM task_links bl JOIN tasks b ON b.id = bl.from_id
                       WHERE bl.to_id = t.id AND bl.kind = 'blocks' AND b.state <> 'done') AS "blocked!",
               (SELECT count(*) FROM questions q WHERE q.task_id = t.id AND q.status = 'open') AS "open_questions!",
               (SELECT count(*) FROM questions q
                 WHERE q.task_id = t.id AND q.status = 'open' AND q.blocking) AS "blocking_questions!",
               l.actor_id AS "lease_actor_id?", a.name AS "lease_actor_name?", l.kind AS "lease_kind?",
               l.expires_at AS "lease_expires_at?", l.paused AS "lease_paused?",
               l.last_heartbeat_at AS "lease_heartbeat_at?"
           FROM tasks t
           LEFT JOIN leases l ON l.task_id = t.id
           LEFT JOIN actors a ON a.id = l.actor_id
           WHERE ($1::uuid IS NULL OR t.project_id = $1) AND ($2::uuid IS NULL OR t.id = $2)
           ORDER BY t.priority DESC, t.created_at"#,
        project_id,
        task_id
    )
    .fetch_all(&mut *conn)
    .await?;
    Ok(rows
        .into_iter()
        .map(|r| TaskView {
            lease: match (r.lease_actor_id, r.lease_kind, r.lease_expires_at) {
                (Some(actor_id), Some(kind), Some(expires_at)) => Some(LeaseView {
                    actor_id,
                    actor_name: r.lease_actor_name.unwrap_or_default(),
                    kind,
                    expires_at,
                    paused: r.lease_paused.unwrap_or(false),
                    last_heartbeat_at: r.lease_heartbeat_at,
                }),
                _ => None,
            },
            id: r.id,
            project_id: r.project_id,
            parent_id: r.parent_id,
            title: r.title,
            state: r.state,
            priority: r.priority,
            version: r.version,
            spec_id: r.spec_id,
            spec_version: r.spec_version,
            spec_outdated: r.spec_outdated,
            preferred_actor_id: r.preferred_actor_id,
            preferred_until: r.preferred_until,
            attempt_count: r.attempt_count,
            rejection_count: r.rejection_count,
            blocked: r.blocked,
            open_questions: r.open_questions,
            blocking_questions: r.blocking_questions,
            created_at: r.created_at,
            updated_at: r.updated_at,
        })
        .collect())
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct TaskRef {
    pub id: Uuid,
    pub title: String,
    pub state: String,
}

pub async fn blockers(conn: &mut PgConnection, task_id: Uuid) -> Result<Vec<TaskRef>, sqlx::Error> {
    sqlx::query_as!(
        TaskRef,
        r#"SELECT b.id, b.title, b.state FROM task_links l JOIN tasks b ON b.id = l.from_id
           WHERE l.to_id = $1 AND l.kind = 'blocks' ORDER BY b.created_at"#,
        task_id
    )
    .fetch_all(&mut *conn)
    .await
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct LinkView {
    pub from_id: Uuid,
    pub to_id: Uuid,
    pub kind: String,
}

/// All links of a project (DAG view, board badges) or touching one task.
pub async fn links(
    conn: &mut PgConnection,
    project_id: Option<Uuid>,
    task_id: Option<Uuid>,
) -> Result<Vec<LinkView>, sqlx::Error> {
    sqlx::query_as!(
        LinkView,
        r#"SELECT l.from_id, l.to_id, l.kind FROM task_links l JOIN tasks t ON t.id = l.to_id
           WHERE ($1::uuid IS NULL OR t.project_id = $1)
             AND ($2::uuid IS NULL OR l.from_id = $2 OR l.to_id = $2)
           ORDER BY l.created_at"#,
        project_id,
        task_id
    )
    .fetch_all(&mut *conn)
    .await
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct QuestionView {
    pub id: Uuid,
    pub task_id: Uuid,
    pub task_title: String,
    pub project_id: Uuid,
    pub asked_by: Uuid,
    pub asked_by_name: String,
    pub body: String,
    #[schema(value_type = Option<Object>)]
    pub options: Option<Value>,
    pub blocking: bool,
    pub status: String,
    pub answered_by: Option<Uuid>,
    pub answer: Option<String>,
    #[serde(with = "time::serde::rfc3339::option")]
    pub answered_at: Option<OffsetDateTime>,
    #[serde(with = "time::serde::rfc3339")]
    pub created_at: OffsetDateTime,
}

/// Questions, open first then blocking first then oldest; filtered by project, task or status.
pub async fn questions(
    conn: &mut PgConnection,
    project_id: Option<Uuid>,
    task_id: Option<Uuid>,
    status: Option<&str>,
    limit: i64,
) -> Result<Vec<QuestionView>, sqlx::Error> {
    sqlx::query_as!(
        QuestionView,
        r#"SELECT q.id, q.task_id, t.title AS task_title, t.project_id, q.asked_by,
               a.name AS asked_by_name, q.body, q.options, q.blocking, q.status, q.answered_by,
               q.answer, q.answered_at, q.created_at
           FROM questions q JOIN tasks t ON t.id = q.task_id JOIN actors a ON a.id = q.asked_by
           WHERE ($1::uuid IS NULL OR t.project_id = $1)
             AND ($2::uuid IS NULL OR q.task_id = $2)
             AND ($3::text IS NULL OR q.status = $3)
           ORDER BY (q.status = 'open') DESC, q.blocking DESC, q.created_at
           LIMIT $4"#,
        project_id,
        task_id,
        status,
        limit
    )
    .fetch_all(&mut *conn)
    .await
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct AttemptView {
    pub id: Uuid,
    pub n: i32,
    pub actor_id: Uuid,
    pub actor_name: String,
    pub actor_model: Option<String>,
    #[serde(with = "time::serde::rfc3339")]
    pub started_at: OffsetDateTime,
    #[serde(with = "time::serde::rfc3339::option")]
    pub ended_at: Option<OffsetDateTime>,
    pub outcome: Option<String>,
    pub commit_sha: Option<String>,
    pub branch: Option<String>,
    pub handoff_note: Option<String>,
    pub trace_id: Option<String>,
}

pub async fn attempts(
    conn: &mut PgConnection,
    task_id: Uuid,
) -> Result<Vec<AttemptView>, sqlx::Error> {
    sqlx::query_as!(
        AttemptView,
        r#"SELECT at.id, at.n, at.actor_id, a.name AS actor_name, at.actor_model, at.started_at,
               at.ended_at, at.outcome, at.commit_sha, at.branch, at.handoff_note, at.trace_id
           FROM attempts at JOIN actors a ON a.id = at.actor_id
           WHERE at.task_id = $1 ORDER BY at.n"#,
        task_id
    )
    .fetch_all(&mut *conn)
    .await
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct SpecVersionView {
    pub spec_id: Uuid,
    pub version: i32,
    pub body_md: String,
    #[schema(value_type = Object)]
    pub acceptance_criteria: Value,
    pub protected_paths: Vec<String>,
    pub test_ref: Option<String>,
    pub status: String,
    pub author_id: Uuid,
    pub approved_by: Option<Uuid>,
    #[serde(with = "time::serde::rfc3339::option")]
    pub approved_at: Option<OffsetDateTime>,
    #[serde(with = "time::serde::rfc3339")]
    pub created_at: OffsetDateTime,
}

pub async fn spec_versions(
    conn: &mut PgConnection,
    spec_id: Uuid,
    version: Option<i32>,
) -> Result<Vec<SpecVersionView>, sqlx::Error> {
    sqlx::query_as!(
        SpecVersionView,
        r#"SELECT spec_id, version, body_md, acceptance_criteria, protected_paths, test_ref, status,
               author_id, approved_by, approved_at, created_at
           FROM spec_versions WHERE spec_id = $1 AND ($2::int IS NULL OR version = $2)
           ORDER BY version"#,
        spec_id,
        version
    )
    .fetch_all(&mut *conn)
    .await
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct SpecView {
    pub id: Uuid,
    pub project_id: Uuid,
    pub title: String,
    pub approved_version: Option<i32>,
    pub latest_version: i32,
}

pub async fn specs(
    conn: &mut PgConnection,
    project_id: Option<Uuid>,
    spec_id: Option<Uuid>,
) -> Result<Vec<SpecView>, sqlx::Error> {
    sqlx::query_as!(
        SpecView,
        r#"SELECT s.id, s.project_id, s.title, s.approved_version,
               COALESCE((SELECT max(version) FROM spec_versions v WHERE v.spec_id = s.id), 0) AS "latest_version!"
           FROM specs s
           WHERE ($1::uuid IS NULL OR s.project_id = $1) AND ($2::uuid IS NULL OR s.id = $2)
           ORDER BY s.created_at"#,
        project_id,
        spec_id
    )
    .fetch_all(&mut *conn)
    .await
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct CurrentLease {
    pub task_id: Uuid,
    pub task_title: String,
    pub project_id: Uuid,
    pub kind: String,
    #[serde(with = "time::serde::rfc3339")]
    pub expires_at: OffsetDateTime,
    pub paused: bool,
    #[serde(with = "time::serde::rfc3339::option")]
    pub last_heartbeat_at: Option<OffsetDateTime>,
}

/// Actor with presence (§8, §10 /agents).
#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct ActorView {
    pub id: Uuid,
    pub kind: String,
    pub name: String,
    pub model: Option<String>,
    pub roles: Vec<String>,
    #[serde(with = "time::serde::rfc3339::option")]
    pub last_seen_at: Option<OffsetDateTime>,
    #[serde(with = "time::serde::rfc3339")]
    pub created_at: OffsetDateTime,
    pub leases: Vec<CurrentLease>,
    /// `activity.reported` events in the last hour.
    pub reports_last_hour: i64,
}

pub async fn actor_views(
    conn: &mut PgConnection,
    now: OffsetDateTime,
) -> Result<Vec<ActorView>, sqlx::Error> {
    let actors = sqlx::query!(
        r#"SELECT a.id, a.kind, a.name, a.model, a.roles, a.last_seen_at, a.created_at,
               (SELECT count(*) FROM events e
                 WHERE e.actor_id = a.id AND e.type = 'activity.reported'
                   AND e.created_at > $1) AS "reports!"
           FROM actors a WHERE a.kind <> 'system' ORDER BY a.kind, a.name"#,
        now - time::Duration::hours(1)
    )
    .fetch_all(&mut *conn)
    .await?;
    let leases = sqlx::query!(
        r#"SELECT l.actor_id, l.task_id, t.title, t.project_id, l.kind, l.expires_at, l.paused,
               l.last_heartbeat_at
           FROM leases l JOIN tasks t ON t.id = l.task_id ORDER BY l.created_at"#
    )
    .fetch_all(&mut *conn)
    .await?;
    Ok(actors
        .into_iter()
        .map(|a| ActorView {
            leases: leases
                .iter()
                .filter(|l| l.actor_id == a.id)
                .map(|l| CurrentLease {
                    task_id: l.task_id,
                    task_title: l.title.clone(),
                    project_id: l.project_id,
                    kind: l.kind.clone(),
                    expires_at: l.expires_at,
                    paused: l.paused,
                    last_heartbeat_at: l.last_heartbeat_at,
                })
                .collect(),
            id: a.id,
            kind: a.kind,
            name: a.name,
            model: a.model,
            roles: a.roles,
            last_seen_at: a.last_seen_at,
            created_at: a.created_at,
            reports_last_hour: a.reports,
        })
        .collect())
}

/// Task ids the actor holds or last worked on, and its open question ids (wait_for_updates).
pub async fn actor_interest(
    conn: &mut PgConnection,
    project_id: Uuid,
    actor_id: Uuid,
) -> Result<(Vec<Uuid>, Vec<Uuid>), sqlx::Error> {
    let tasks = sqlx::query_scalar!(
        r#"SELECT DISTINCT at.task_id AS "task_id!" FROM attempts at JOIN tasks t ON t.id = at.task_id
           WHERE at.actor_id = $1 AND t.project_id = $2
           UNION
           SELECT l.task_id FROM leases l JOIN tasks t ON t.id = l.task_id
           WHERE l.actor_id = $1 AND t.project_id = $2"#,
        actor_id,
        project_id
    )
    .fetch_all(&mut *conn)
    .await?;
    let questions = sqlx::query_scalar!(
        r#"SELECT q.id FROM questions q JOIN tasks t ON t.id = q.task_id
           WHERE q.asked_by = $1 AND t.project_id = $2"#,
        actor_id,
        project_id
    )
    .fetch_all(&mut *conn)
    .await?;
    Ok((tasks, questions))
}
