//! Write use cases. Each runs inside the transaction opened by `tx::run`.
//!
//! Lock order (deadlock freedom): idempotency advisory lock → spec row (`FOR NO KEY UPDATE`) →
//! task rows in id order (`FOR UPDATE`, or `FOR KEY SHARE` for rows only referenced by a foreign
//! key) → project row (sequence reservation in `tx::persist`). Nothing locks a task after the
//! project row.

use atb_core::{
    ActivityKind, Command, Ctx, DomainError, LeaseKind, LinkKind, NewTask, TaskSnapshot, TestGate,
    WorkflowConfig, apply_all, decide, decide_create,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sqlx::PgConnection;
use time::{Duration, OffsetDateTime};
use utoipa::ToSchema;
use uuid::Uuid;

use super::now;
use super::tx::{Emit, persist};
use crate::actor::{Actor, SYSTEM_ACTOR_ID};
use crate::error::{AppError, AppResult};
use crate::metrics::Metrics;
use crate::repository::reads::{self, ProjectView};
use crate::repository::{StoredEvent, random_token, sha256_hex, store};
use crate::state::AppState;

/// Result of every task command (REST and MCP). Stored verbatim for idempotent replays.
#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct CommandResult {
    pub task_id: Option<Uuid>,
    pub state: Option<String>,
    pub version: Option<i32>,
    /// Returned once, by `claim`. Present it on every later write (fencing).
    pub lease_token: Option<String>,
    #[serde(with = "time::serde::rfc3339::option")]
    pub lease_expires_at: Option<OffsetDateTime>,
    pub question_id: Option<Uuid>,
    pub spec_id: Option<Uuid>,
    pub spec_version: Option<i32>,
    pub events: Vec<StoredEvent>,
}

impl CommandResult {
    fn for_task(task: &TaskSnapshot, events: Vec<StoredEvent>) -> Self {
        Self {
            task_id: Some(task.id),
            state: Some(task.state.as_str().to_string()),
            version: Some(task.version),
            lease_token: None,
            lease_expires_at: task.lease.as_ref().map(|l| l.expires_at),
            question_id: None,
            spec_id: None,
            spec_version: None,
            events,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ClaimRole {
    Implementer,
    Reviewer,
}

/// A command on an existing task, as received from REST or MCP (raw lease token).
#[derive(Debug, Clone)]
pub enum TaskCmd {
    Heartbeat {
        lease_token: Option<String>,
    },
    Report {
        lease_token: Option<String>,
        kind: ActivityKind,
        body: String,
    },
    Ask {
        lease_token: Option<String>,
        question: String,
        blocking: bool,
        options: Option<Value>,
        handoff_note: Option<String>,
    },
    Release {
        lease_token: Option<String>,
        handoff_note: String,
    },
    SubmitForTest {
        lease_token: Option<String>,
        commit_sha: String,
        branch: Option<String>,
    },
    Repin {
        lease_token: Option<String>,
        to_version: Option<i32>,
    },
    Cancel {
        reason: Option<String>,
    },
    Update {
        expected_version: i32,
        title: Option<String>,
        priority: Option<i32>,
    },
}

fn hash(token: &Option<String>) -> Option<String> {
    token.as_deref().map(sha256_hex)
}

fn emit<'a>(
    project_id: Uuid,
    actor: &Actor,
    trace_id: Option<&'a str>,
    at: OffsetDateTime,
) -> Emit<'a> {
    Emit {
        project_id,
        actor_id: actor.id,
        trace_id,
        at,
    }
}

/// Decision context for `task` as seen by `actor` now.
pub async fn build_ctx(
    conn: &mut PgConnection,
    task: &TaskSnapshot,
    actor: &Actor,
    at: OffsetDateTime,
) -> AppResult<Ctx> {
    let workflow = reads::project_workflow(conn, task.project_id)
        .await?
        .ok_or_else(|| AppError::not_found("project"))?;
    let mut ctx = Ctx::new(at, actor.caller(), workflow);
    ctx.blockers = reads::blocker_states(conn, task.id).await?;
    ctx.approved_spec_version = reads::approved_spec_version(conn, task.spec_id).await?;
    ctx.acceptance_criteria =
        reads::acceptance_criteria(conn, task.spec_id, task.spec_version).await?;
    ctx.system_actor_id = SYSTEM_ACTOR_ID;
    Ok(ctx)
}

/// Turn a domain rejection into an API error; a version conflict carries the current task.
async fn rejected(conn: &mut PgConnection, task_id: Uuid, err: DomainError) -> AppError {
    if let DomainError::VersionConflict { expected, current } = err {
        let view = reads::task_views(conn, None, Some(task_id))
            .await
            .ok()
            .and_then(|mut v| v.pop());
        return AppError::Conflict {
            code: "version_conflict",
            message: format!(
                "the task changed (version {current}, you sent {expected}); reload and retry"
            ),
            details: json!({ "expected_version": expected, "current": view }),
        };
    }
    AppError::Domain(err)
}

/// `heartbeat`, `report`, `ask`, `release`, `submit_for_test`, `repin`, `cancel`, `patch`.
pub async fn task_command(
    conn: &mut PgConnection,
    st: &AppState,
    actor: &Actor,
    task_id: Uuid,
    cmd: TaskCmd,
    trace_id: Option<&str>,
) -> AppResult<CommandResult> {
    let at = now();
    let snap = reads::load_snapshot(conn, task_id, true)
        .await?
        .ok_or_else(|| AppError::not_found("task"))?;
    let ctx = build_ctx(conn, &snap, actor, at).await?;
    let mut question_id = None;
    let is_heartbeat = matches!(cmd, TaskCmd::Heartbeat { .. });
    let core = match cmd {
        TaskCmd::Heartbeat { lease_token } => Command::Heartbeat {
            token_hash: hash(&lease_token),
        },
        TaskCmd::Report {
            lease_token,
            kind,
            body,
        } => {
            if !st.limiter.allow(
                actor.id,
                super::ratelimit::Bucket::Report,
                st.cfg.max_reports_per_min,
            ) {
                return Err(AppError::RateLimited(format!(
                    "at most {} reports per minute",
                    st.cfg.max_reports_per_min
                )));
            }
            Command::Report {
                token_hash: hash(&lease_token),
                kind,
                body,
                trace_id: trace_id.map(str::to_string),
            }
        }
        TaskCmd::Ask {
            lease_token,
            question,
            blocking,
            options,
            handoff_note,
        } => {
            let id = Uuid::now_v7();
            question_id = Some(id);
            Command::Ask {
                token_hash: hash(&lease_token),
                question_id: id,
                body: question,
                blocking,
                options,
                handoff_note,
            }
        }
        TaskCmd::Release {
            lease_token,
            handoff_note,
        } => Command::Release {
            token_hash: hash(&lease_token),
            handoff_note,
        },
        TaskCmd::SubmitForTest {
            lease_token,
            commit_sha,
            branch,
        } => {
            if ctx.workflow.test_gate != TestGate::None {
                // TODO(phase-2): queue a test run for the verifier.
                return Err(AppError::BadRequest(
                    "this project's test gate needs the verifier, which arrives in phase 2; \
                     use a project with test_gate=none"
                        .into(),
                ));
            }
            Command::SubmitForTest {
                token_hash: hash(&lease_token),
                commit_sha,
                branch,
                test_run_id: Uuid::now_v7(),
            }
        }
        TaskCmd::Repin {
            lease_token,
            to_version,
        } => Command::Repin {
            token_hash: hash(&lease_token),
            to_version: to_version
                .or(ctx.approved_spec_version)
                .unwrap_or(snap.spec_version),
        },
        TaskCmd::Cancel { reason } => Command::Cancel { reason },
        TaskCmd::Update {
            expected_version,
            title,
            priority,
        } => Command::Update {
            expected_version,
            title,
            priority,
        },
    };
    let events = match decide(&snap, &core, &ctx) {
        Ok(ev) => ev,
        Err(e) => return Err(rejected(conn, task_id, e).await),
    };
    let stored = persist(
        conn,
        st.notifier.as_ref(),
        &emit(snap.project_id, actor, trace_id, at),
        &events,
    )
    .await?;
    let after = apply_all(snap, &events);
    let mut out = CommandResult::for_task(&after, stored);
    if is_heartbeat {
        let expires = at + Duration::seconds(ctx.workflow.lease_ttl_secs);
        store::touch_lease(conn, task_id, expires, at).await?;
        out.lease_expires_at = Some(expires);
    }
    out.question_id = question_id;
    Ok(out)
}

/// `claim`: atomic. Without `task_id`, picks the best claimable task with `SKIP LOCKED`.
pub async fn claim(
    conn: &mut PgConnection,
    st: &AppState,
    actor: &Actor,
    project_id: Uuid,
    role: ClaimRole,
    task_id: Option<Uuid>,
    trace_id: Option<&str>,
) -> AppResult<CommandResult> {
    let at = now();
    let kind = match role {
        ClaimRole::Implementer => LeaseKind::Work,
        ClaimRole::Reviewer => LeaseKind::Review,
    };
    let id = match task_id {
        Some(id) => id,
        None => {
            let candidate = match kind {
                LeaseKind::Work => store::claim_candidate(conn, project_id, actor.id, at).await?,
                LeaseKind::Review => store::review_candidate(conn, project_id, actor.id).await?,
            };
            candidate.ok_or_else(|| {
                AppError::Domain(DomainError::guard(
                    "nothing_to_claim",
                    "no claimable task right now; call wait_for_updates and retry",
                ))
            })?
        }
    };
    let snap = reads::load_snapshot(conn, id, true)
        .await?
        .filter(|t| t.project_id == project_id)
        .ok_or_else(|| AppError::not_found("task in this project"))?;
    let ctx = build_ctx(conn, &snap, actor, at).await?;
    let token = random_token();
    let cmd = Command::Claim {
        kind,
        token_hash: sha256_hex(&token),
        attempt_id: Uuid::now_v7(),
    };
    let events = decide(&snap, &cmd, &ctx).map_err(AppError::Domain)?;
    let stored = persist(
        conn,
        st.notifier.as_ref(),
        &emit(project_id, actor, trace_id, at),
        &events,
    )
    .await?;
    Metrics::inc(&st.metrics.claims_total);
    let after = apply_all(snap, &events);
    let mut out = CommandResult::for_task(&after, stored);
    out.lease_token = Some(token);
    Ok(out)
}

/// `answer`: any actor except the asker. A blocking answer returns the task to ready with a claim
/// preference for the asker.
pub async fn answer(
    conn: &mut PgConnection,
    st: &AppState,
    actor: &Actor,
    question_id: Uuid,
    answer: String,
) -> AppResult<CommandResult> {
    let at = now();
    let (task_id, _) = reads::question_ref(conn, question_id)
        .await?
        .ok_or_else(|| AppError::not_found("question"))?;
    let snap = reads::load_snapshot(conn, task_id, true)
        .await?
        .ok_or_else(|| AppError::not_found("task"))?;
    // Re-read under the task lock: a concurrent answer may have closed it.
    let (_, question) = reads::question_ref(conn, question_id)
        .await?
        .ok_or_else(|| AppError::not_found("question"))?;
    let ctx = build_ctx(conn, &snap, actor, at).await?;
    let events =
        decide(&snap, &Command::Answer { question, answer }, &ctx).map_err(AppError::Domain)?;
    let stored = persist(
        conn,
        st.notifier.as_ref(),
        &emit(snap.project_id, actor, None, at),
        &events,
    )
    .await?;
    let after = apply_all(snap, &events);
    let mut out = CommandResult::for_task(&after, stored);
    out.question_id = Some(question_id);
    Ok(out)
}

#[derive(Debug, Clone, Deserialize, ToSchema)]
pub struct NewTaskInput {
    pub title: String,
    pub spec_id: Uuid,
    /// Defaults to the approved version, else the latest.
    pub spec_version: Option<i32>,
    pub parent_id: Option<Uuid>,
    #[serde(default)]
    pub blocked_by: Vec<Uuid>,
    pub discovered_from: Option<Uuid>,
    pub priority: Option<i32>,
}

pub async fn create_task(
    conn: &mut PgConnection,
    st: &AppState,
    actor: &Actor,
    project_id: Uuid,
    input: NewTaskInput,
    trace_id: Option<&str>,
) -> AppResult<CommandResult> {
    let at = now();
    let workflow = reads::project_workflow(conn, project_id)
        .await?
        .ok_or_else(|| AppError::not_found("project"))?;
    let (spec_project, _) = store::spec_project(conn, input.spec_id)
        .await?
        .ok_or_else(|| AppError::not_found("spec"))?;
    if spec_project != project_id {
        return Err(AppError::BadRequest(
            "the spec belongs to another project".into(),
        ));
    }
    let approved = reads::approved_spec_version(conn, input.spec_id).await?;
    let latest = store::latest_spec_version(conn, input.spec_id).await?;
    let version = input.spec_version.or(approved).unwrap_or(latest);
    if version < 1 || version > latest {
        return Err(AppError::BadRequest(format!(
            "spec version {version} does not exist (latest is {latest})"
        )));
    }
    // Referenced tasks: KEY SHARE locks in id order, before the project row.
    let mut refs: Vec<Uuid> = input
        .blocked_by
        .iter()
        .copied()
        .chain(input.parent_id)
        .chain(input.discovered_from)
        .collect();
    refs.sort();
    refs.dedup();
    let found = store::key_share_tasks(conn, &refs).await?;
    for id in &refs {
        match found.iter().find(|(t, _)| t == id) {
            Some((_, p)) if *p == project_id => {}
            Some(_) => {
                return Err(AppError::BadRequest(format!(
                    "task {id} belongs to another project"
                )));
            }
            None => return Err(AppError::not_found(format!("task {id}"))),
        }
    }
    let mut ctx = Ctx::new(at, actor.caller(), workflow);
    ctx.approved_spec_version = approved;
    let new = NewTask {
        task_id: Uuid::now_v7(),
        project_id,
        title: input.title,
        spec_id: input.spec_id,
        spec_version: version,
        parent_id: input.parent_id,
        priority: input.priority.unwrap_or(0),
        blocked_by: input.blocked_by,
        discovered_from: input.discovered_from,
    };
    let events = decide_create(&new, &ctx).map_err(AppError::Domain)?;
    let stored = persist(
        conn,
        st.notifier.as_ref(),
        &emit(project_id, actor, trace_id, at),
        &events,
    )
    .await?;
    let created = atb_core::apply::create(&events[0])
        .ok_or_else(|| AppError::Internal(anyhow::anyhow!("task.created missing")))?;
    let after = apply_all(created, &events[1..]);
    Ok(CommandResult::for_task(&after, stored))
}

/// Add a link `from -> to`. A `blocks` link that would create a cycle is rejected (AC-1.5).
pub async fn add_link(
    conn: &mut PgConnection,
    st: &AppState,
    actor: &Actor,
    from: Uuid,
    to: Uuid,
    kind: LinkKind,
) -> AppResult<CommandResult> {
    let at = now();
    // Both rows FOR UPDATE, in id order.
    let (first, second) = if from < to { (from, to) } else { (to, from) };
    let a = reads::load_snapshot(conn, first, true).await?;
    let b = if first == second {
        a.clone()
    } else {
        reads::load_snapshot(conn, second, true).await?
    };
    let (Some(a), Some(b)) = (a, b) else {
        return Err(AppError::not_found("task"));
    };
    if a.project_id != b.project_id {
        return Err(AppError::BadRequest(
            "links must stay inside one project".into(),
        ));
    }
    let snap = if a.id == from { a } else { b };
    if reads::link_exists(conn, from, to, kind.as_str()).await? {
        return Err(AppError::Domain(DomainError::guard(
            "link_exists",
            "this link already exists",
        )));
    }
    let mut ctx = build_ctx(conn, &snap, actor, at).await?;
    ctx.block_edges = reads::project_block_edges(conn, snap.project_id).await?;
    let events = decide(&snap, &Command::AddLink { to, kind }, &ctx).map_err(AppError::Domain)?;
    let stored = persist(
        conn,
        st.notifier.as_ref(),
        &emit(snap.project_id, actor, None, at),
        &events,
    )
    .await?;
    Ok(CommandResult::for_task(&snap, stored))
}

/// Sweeper: expire one lease in its own transaction. `Ok(false)` when the row is busy or the
/// lease was renewed in the meantime.
pub async fn expire_lease(
    conn: &mut PgConnection,
    st: &AppState,
    task_id: Uuid,
) -> AppResult<bool> {
    if !store::try_lock_task(conn, task_id).await? {
        return Ok(false);
    }
    let at = now();
    let Some(snap) = reads::load_snapshot(conn, task_id, false).await? else {
        return Ok(false);
    };
    let system = Actor::system();
    let ctx = build_ctx(conn, &snap, &system, at).await?;
    let events = match decide(&snap, &Command::ExpireLease, &ctx) {
        Ok(ev) => ev,
        Err(DomainError::GuardFailed { .. }) => return Ok(false),
        Err(e) => return Err(AppError::Domain(e)),
    };
    persist(
        conn,
        st.notifier.as_ref(),
        &emit(snap.project_id, &system, None, at),
        &events,
    )
    .await?;
    Metrics::inc(&st.metrics.lease_expiries_total);
    Ok(true)
}

// ------------------------------------------------------------------------------------------------
// Projects and specs
// ------------------------------------------------------------------------------------------------

pub async fn create_project(
    conn: &mut PgConnection,
    st: &AppState,
    actor: &Actor,
    name: &str,
    workflow: Option<WorkflowConfig>,
) -> AppResult<ProjectView> {
    if !(actor.is_human() || actor.is_admin()) {
        return Err(AppError::Forbidden(
            "only humans and admins create projects".into(),
        ));
    }
    let name = name.trim();
    if name.is_empty() || name.chars().count() > 200 {
        return Err(AppError::BadRequest(
            "name must be 1..200 characters".into(),
        ));
    }
    let workflow = workflow.unwrap_or_else(|| WorkflowConfig {
        lease_ttl_secs: st.cfg.lease_ttl_secs,
        preferred_grace_secs: st.cfg.preferred_grace_secs,
        ..WorkflowConfig::default()
    });
    workflow.validate().map_err(AppError::Domain)?;
    let id = Uuid::now_v7();
    store::insert_project(conn, id, name, &serde_json::to_value(&workflow)?, now()).await?;
    reads::project(conn, id)
        .await?
        .ok_or_else(|| AppError::not_found("project"))
}

#[derive(Debug, Clone, Deserialize, ToSchema)]
pub struct SpecInput {
    /// Required when creating a spec; optional (renames) when proposing a version.
    pub title: Option<String>,
    pub body_md: String,
    /// `[{ "id": "AC-1", "text": "...", "verify": { "kind": "command", "command": "..." } }]`
    #[schema(value_type = Object)]
    pub acceptance_criteria: Value,
    #[serde(default)]
    pub protected_paths: Vec<String>,
    pub test_ref: Option<String>,
}

/// Validate the acceptance criterion format (§3).
pub fn validate_acs(acs: &Value) -> AppResult<()> {
    let items = acs
        .as_array()
        .ok_or_else(|| AppError::BadRequest("acceptance_criteria must be an array".into()))?;
    let mut ids = std::collections::HashSet::new();
    for ac in items {
        let id = ac.get("id").and_then(Value::as_str).unwrap_or("");
        let text = ac.get("text").and_then(Value::as_str).unwrap_or("");
        let kind = ac.pointer("/verify/kind").and_then(Value::as_str);
        if id.trim().is_empty() || text.trim().is_empty() {
            return Err(AppError::BadRequest(
                "each acceptance criterion needs a non-empty id and text".into(),
            ));
        }
        if !ids.insert(id.to_string()) {
            return Err(AppError::BadRequest(format!(
                "duplicate acceptance criterion {id}"
            )));
        }
        match kind {
            Some("human") => {}
            Some("command") => {
                let cmd = ac
                    .pointer("/verify/command")
                    .and_then(Value::as_str)
                    .unwrap_or("");
                if cmd.trim().is_empty() {
                    return Err(AppError::BadRequest(format!(
                        "{id}: verify.kind=command needs verify.command"
                    )));
                }
            }
            _ => {
                return Err(AppError::BadRequest(format!(
                    "{id}: verify.kind must be command or human"
                )));
            }
        }
    }
    Ok(())
}

/// Create a spec with its version 1 (draft).
pub async fn create_spec(
    conn: &mut PgConnection,
    st: &AppState,
    actor: &Actor,
    project_id: Uuid,
    input: SpecInput,
) -> AppResult<CommandResult> {
    if actor.kind == atb_core::ActorKind::Verifier {
        return Err(AppError::Forbidden("verifiers cannot write specs".into()));
    }
    let title = input.title.clone().unwrap_or_default();
    if title.trim().is_empty() {
        return Err(AppError::BadRequest("title is required".into()));
    }
    validate_acs(&input.acceptance_criteria)?;
    reads::project(conn, project_id)
        .await?
        .ok_or_else(|| AppError::not_found("project"))?;
    let spec_id = Uuid::now_v7();
    propose(
        conn,
        st,
        actor,
        project_id,
        spec_id,
        title.trim().to_string(),
        1,
        input,
    )
    .await
}

/// Propose a new version (agents may propose; only humans approve).
pub async fn propose_version(
    conn: &mut PgConnection,
    st: &AppState,
    actor: &Actor,
    spec_id: Uuid,
    input: SpecInput,
) -> AppResult<CommandResult> {
    if actor.kind == atb_core::ActorKind::Verifier {
        return Err(AppError::Forbidden("verifiers cannot write specs".into()));
    }
    validate_acs(&input.acceptance_criteria)?;
    let (project_id, title) = store::lock_spec(conn, spec_id)
        .await?
        .ok_or_else(|| AppError::not_found("spec"))?;
    let version = store::latest_spec_version(conn, spec_id).await? + 1;
    let title = input
        .title
        .clone()
        .filter(|t| !t.trim().is_empty())
        .unwrap_or(title);
    propose(conn, st, actor, project_id, spec_id, title, version, input).await
}

#[allow(clippy::too_many_arguments)]
async fn propose(
    conn: &mut PgConnection,
    st: &AppState,
    actor: &Actor,
    project_id: Uuid,
    spec_id: Uuid,
    title: String,
    version: i32,
    input: SpecInput,
) -> AppResult<CommandResult> {
    let at = now();
    let events = vec![atb_core::DomainEvent::SpecVersionProposed {
        spec_id,
        project_id,
        title,
        version,
        body_md: input.body_md,
        acceptance_criteria: input.acceptance_criteria,
        protected_paths: input.protected_paths,
        test_ref: input.test_ref,
        author_id: actor.id,
    }];
    let stored = persist(
        conn,
        st.notifier.as_ref(),
        &emit(project_id, actor, None, at),
        &events,
    )
    .await?;
    Ok(CommandResult {
        task_id: None,
        state: None,
        version: None,
        lease_token: None,
        lease_expires_at: None,
        question_id: None,
        spec_id: Some(spec_id),
        spec_version: Some(version),
        events: stored,
    })
}

/// Approve a spec version (human only). In the same transaction: draft tasks pinned to it become
/// ready, non-terminal tasks pinned to an older version become `spec_outdated` (AC-2.1/2.2).
pub async fn approve_version(
    conn: &mut PgConnection,
    st: &AppState,
    actor: &Actor,
    spec_id: Uuid,
    version: i32,
) -> AppResult<CommandResult> {
    if !actor.is_human() {
        return Err(AppError::Domain(DomainError::Forbidden(
            "spec approval is human-only".into(),
        )));
    }
    let at = now();
    let (project_id, _) = store::lock_spec(conn, spec_id)
        .await?
        .ok_or_else(|| AppError::not_found("spec"))?;
    match store::spec_version_status(conn, spec_id, version)
        .await?
        .as_deref()
    {
        Some("draft") => {}
        Some(other) => {
            return Err(AppError::Domain(DomainError::guard(
                "version_not_draft",
                format!("version {version} is {other}; only drafts can be approved"),
            )));
        }
        None => return Err(AppError::not_found("spec version")),
    }
    let mut events = vec![atb_core::DomainEvent::SpecVersionApproved {
        spec_id,
        version,
        approved_by: actor.id,
        approved_at: at,
    }];
    for task_id in store::lock_spec_tasks(conn, spec_id).await? {
        let Some(snap) = reads::load_snapshot(conn, task_id, false).await? else {
            continue;
        };
        let ctx = build_ctx(conn, &snap, actor, at).await?;
        events.extend(
            decide(&snap, &Command::SpecApproved { version }, &ctx).map_err(AppError::Domain)?,
        );
    }
    let stored = persist(
        conn,
        st.notifier.as_ref(),
        &emit(project_id, actor, None, at),
        &events,
    )
    .await?;
    Ok(CommandResult {
        task_id: None,
        state: None,
        version: None,
        lease_token: None,
        lease_expires_at: None,
        question_id: None,
        spec_id: Some(spec_id),
        spec_version: Some(version),
        events: stored,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn acceptance_criteria_format_is_enforced() {
        let ok = json!([
            {"id": "AC-1", "text": "x", "verify": {"kind": "command", "command": "cargo test"}},
            {"id": "AC-2", "text": "y", "verify": {"kind": "human"}}
        ]);
        assert!(validate_acs(&ok).is_ok());
        for bad in [
            json!({}),
            json!([{"id": "AC-1", "text": "x", "verify": {"kind": "command"}}]),
            json!([{"id": "AC-1", "text": "x", "verify": {"kind": "magic"}}]),
            json!([
                {"id": "AC-1", "text": "x", "verify": {"kind": "human"}},
                {"id": "AC-1", "text": "y", "verify": {"kind": "human"}}
            ]),
        ] {
            assert!(validate_acs(&bad).is_err(), "{bad}");
        }
    }
}
