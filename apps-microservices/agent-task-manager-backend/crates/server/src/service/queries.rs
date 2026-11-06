//! Read use cases (board, task context, timeline, inboxes, presence).

use serde::Serialize;
use serde_json::Value;
use sqlx::PgConnection;
use utoipa::ToSchema;
use uuid::Uuid;

use super::commands::ClaimRole;
use super::now;
use crate::actor::Actor;
use crate::error::{AppError, AppResult};
use crate::repository::StoredEvent;
use crate::repository::reads::{
    self, AttemptView, LinkView, ProjectView, QuestionView, SpecVersionView, TaskRef, TaskView,
};
use crate::repository::store;
use crate::state::AppState;

/// Board snapshot. `seq` is the project event counter at read time: open the SSE stream with
/// `after=seq` to receive exactly the changes that happen after this snapshot.
#[derive(Debug, Serialize, ToSchema)]
pub struct Board {
    pub project: ProjectView,
    pub seq: i64,
    pub tasks: Vec<TaskView>,
    pub links: Vec<LinkView>,
}

pub async fn board(st: &AppState, project_id: Uuid) -> AppResult<Board> {
    let mut tx = st.pool.begin().await?;
    // One consistent snapshot for the tasks AND the seq the client resumes from.
    sqlx::query("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        .execute(&mut *tx)
        .await?;
    let project = reads::project(&mut tx, project_id)
        .await?
        .ok_or_else(|| AppError::not_found("project"))?;
    let tasks = reads::task_views(&mut tx, Some(project_id), None).await?;
    let links = reads::links(&mut tx, Some(project_id), None).await?;
    tx.commit().await?;
    Ok(Board {
        seq: project.event_seq,
        project,
        tasks,
        links,
    })
}

/// Everything an agent needs before acting on a task (`get_task`, §7).
#[derive(Debug, Serialize, ToSchema)]
pub struct TaskContext {
    pub task: TaskView,
    pub spec: Option<SpecVersionView>,
    pub approved_spec_version: Option<i32>,
    pub blockers: Vec<TaskRef>,
    pub links: Vec<LinkView>,
    pub questions: Vec<QuestionView>,
    pub last_handoff_note: Option<String>,
    pub recent_activity: Vec<StoredEvent>,
    pub attempts: Vec<AttemptView>,
    /// TODO(phase-2): latest verifier run.
    #[schema(value_type = Option<Object>)]
    pub latest_test_run: Option<Value>,
    /// TODO(phase-2): latest review.
    #[schema(value_type = Option<Object>)]
    pub latest_review: Option<Value>,
}

pub async fn task_context(conn: &mut PgConnection, task_id: Uuid) -> AppResult<TaskContext> {
    let task = reads::task_views(conn, None, Some(task_id))
        .await?
        .pop()
        .ok_or_else(|| AppError::not_found("task"))?;
    let spec = reads::spec_versions(conn, task.spec_id, Some(task.spec_version))
        .await?
        .pop();
    let attempts = reads::attempts(conn, task_id).await?;
    let last_handoff_note = attempts.iter().rev().find_map(|a| a.handoff_note.clone());
    Ok(TaskContext {
        approved_spec_version: reads::approved_spec_version(conn, task.spec_id).await?,
        blockers: reads::blockers(conn, task_id).await?,
        links: reads::links(conn, None, Some(task_id)).await?,
        questions: reads::questions(conn, None, Some(task_id), None, 100).await?,
        recent_activity: reads::recent_activity(conn, task_id, 20).await?,
        last_handoff_note,
        attempts,
        spec,
        task,
        latest_test_run: None,
        latest_review: None,
    })
}

pub async fn timeline(
    conn: &mut PgConnection,
    task_id: Uuid,
    limit: i64,
) -> AppResult<Vec<StoredEvent>> {
    store::task_project(conn, task_id)
        .await?
        .ok_or_else(|| AppError::not_found("task"))?;
    Ok(reads::task_events(conn, task_id, limit.clamp(1, 2000)).await?)
}

/// Claimable tasks for `actor`, priority then age (`list_ready`, §7).
pub async fn list_ready(
    conn: &mut PgConnection,
    actor: &Actor,
    project_id: Uuid,
    role: ClaimRole,
    limit: i64,
) -> AppResult<Vec<TaskView>> {
    reads::project(conn, project_id)
        .await?
        .ok_or_else(|| AppError::not_found("project"))?;
    let ids = store::ready_task_ids(
        conn,
        project_id,
        actor.id,
        now(),
        role == ClaimRole::Reviewer,
        limit.clamp(1, 100),
    )
    .await?;
    let all = reads::task_views(conn, Some(project_id), None).await?;
    Ok(ids
        .iter()
        .filter_map(|id| all.iter().find(|t| t.id == *id).cloned())
        .collect())
}
