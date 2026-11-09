//! MCP agent interface (§7): rmcp Streamable HTTP server mounted at `/mcp`, stateless (no MCP
//! session: all state is in Postgres, so any replica can serve any call, behind the gateway too).
//!
//! The caller is resolved by the axum auth middleware; tools read the [`Actor`] from the HTTP
//! request parts that rmcp injects into the request context. Every tool returns a one-line
//! summary plus compact JSON (long fields truncated, ids always included). Errors are tool-level
//! results that tell the agent what to do next.

use crate::scope::Scope;
use crate::service::project_access::{self, Target};
use atb_core::project_access::ProjectRole;
use std::sync::Arc;

use atb_core::{ActivityKind, LinkKind};
use axum::http::request::Parts;
use rmcp::handler::server::wrapper::Parameters;
use rmcp::model::{CallToolResult, ContentBlock, Implementation, ServerCapabilities, ServerConfig};
use rmcp::service::RequestContext;
use rmcp::transport::streamable_http_server::session::never::NeverSessionManager;
use rmcp::transport::streamable_http_server::{StreamableHttpServerConfig, StreamableHttpService};
use rmcp::{ErrorData, RoleServer, ServerHandler, tool, tool_handler, tool_router};
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};
use uuid::Uuid;

use crate::actor::Actor;
use crate::error::AppError;
use crate::service::commands::{self, ClaimRole, CommandResult, NewTaskInput, SpecInput, TaskCmd};
use crate::service::{queries, tx, updates};
use crate::state::AppState;

/// The agent protocol, sent as the MCP server `instructions` (§7).
pub const INSTRUCTIONS: &str = "You coordinate with other agents through this task board.
1. Find work with list_ready, then claim. Read the whole context returned (spec, acceptance
   criteria, handoff note, answered questions) before acting.
2. Heartbeat at least every lease_ttl/3 seconds. If your lease is lost, stop working on the task.
3. Report meaningful steps (kind=progress or action). When you proceed on an unconfirmed
   assumption, report it with kind=assumption.
4. If the spec is ambiguous or a requirement looks wrong, ask with blocking=true and a
   handoff note. Do not guess.
5. Never modify files under the spec's protected paths. If an acceptance test looks wrong,
   ask; never edit, skip or weaken it.
6. Work you discover outside your task goes into create_task(discovered_from=<your task>),
   not into your current change.
7. Before release or submit_for_test, leave a handoff note: what is done, what is left, where.";

const MAX_FIELD_CHARS: usize = 1500;

#[derive(Clone)]
pub struct BoardMcp {
    st: AppState,
}

pub fn service(st: AppState) -> StreamableHttpService<BoardMcp, NeverSessionManager> {
    let mut config =
        StreamableHttpServerConfig::default().with_allowed_hosts(st.cfg.mcp_allowed_hosts.clone());
    config.legacy_session_mode = false;
    config.json_response = true;
    StreamableHttpService::new(
        move || Ok(BoardMcp { st: st.clone() }),
        Arc::new(NeverSessionManager::default()),
        config,
    )
}

// ------------------------------------------------------------------------------------------------
// Tool inputs
// ------------------------------------------------------------------------------------------------

#[derive(Debug, Deserialize, JsonSchema)]
pub struct ListReadyArgs {
    pub project_id: Uuid,
    /// implementer (default) or reviewer
    pub role: Option<ClaimRoleArg>,
    /// Default 10, max 100.
    pub limit: Option<i64>,
}

#[derive(Debug, Clone, Copy, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum ClaimRoleArg {
    Implementer,
    Reviewer,
}

impl From<ClaimRoleArg> for ClaimRole {
    fn from(r: ClaimRoleArg) -> Self {
        match r {
            ClaimRoleArg::Implementer => ClaimRole::Implementer,
            ClaimRoleArg::Reviewer => ClaimRole::Reviewer,
        }
    }
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct GetTaskArgs {
    pub task_id: Uuid,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct ClaimArgs {
    pub project_id: Uuid,
    /// implementer (default) or reviewer
    pub role: Option<ClaimRoleArg>,
    /// Omit to get the best claimable task (priority, then age).
    pub task_id: Option<Uuid>,
    pub idempotency_key: Option<String>,
    pub trace_id: Option<String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct HeartbeatArgs {
    pub task_id: Uuid,
    pub lease_token: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct ReportArgs {
    pub task_id: Uuid,
    pub lease_token: String,
    /// thought | action | progress | assumption
    pub kind: String,
    /// At most 4 KB.
    pub body: String,
    pub trace_id: Option<String>,
    pub idempotency_key: Option<String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct AskArgs {
    pub task_id: Uuid,
    pub lease_token: String,
    pub question: String,
    /// true: the task moves to input_required and your lease is released.
    pub blocking: bool,
    /// Optional choices, e.g. ["json", "csv"].
    pub options: Option<Value>,
    /// Required when blocking: what is done, what is left, where.
    pub handoff_note: Option<String>,
    pub idempotency_key: Option<String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct AnswerArgs {
    pub question_id: Uuid,
    pub answer: String,
    pub idempotency_key: Option<String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct WaitArgs {
    pub project_id: Uuid,
    /// Last cursor you received (0 the first time).
    pub cursor: i64,
    /// Seconds to wait, at most 25.
    pub timeout_s: Option<u64>,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct CreateTaskArgs {
    pub project_id: Uuid,
    pub title: String,
    pub spec_id: Uuid,
    pub spec_version: Option<i32>,
    pub parent_id: Option<Uuid>,
    pub blocked_by: Option<Vec<Uuid>>,
    /// The task you were working on when you found this work.
    pub discovered_from: Option<Uuid>,
    pub priority: Option<i32>,
    pub idempotency_key: Option<String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct ProposeSpecArgs {
    /// Existing spec to version. Omit to create a new spec (then project_id and title are required).
    pub spec_id: Option<Uuid>,
    pub project_id: Option<Uuid>,
    pub title: Option<String>,
    pub body_md: String,
    /// [{"id":"AC-1","text":"WHEN ... THE SYSTEM SHALL ...","verify":{"kind":"command","command":"..."}}]
    pub acceptance_criteria: Value,
    pub protected_paths: Option<Vec<String>>,
    pub idempotency_key: Option<String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct RepinArgs {
    pub task_id: Uuid,
    pub lease_token: Option<String>,
    pub idempotency_key: Option<String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct SubmitArgs {
    pub task_id: Uuid,
    pub lease_token: String,
    pub commit_sha: String,
    pub branch: Option<String>,
    pub idempotency_key: Option<String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct ReleaseArgs {
    pub task_id: Uuid,
    pub lease_token: String,
    /// What is done, what is left, where.
    pub handoff_note: String,
    pub idempotency_key: Option<String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct LinkArgs {
    pub from_id: Uuid,
    pub to_id: Uuid,
    /// blocks | discovered_from | related
    pub kind: String,
}

// ------------------------------------------------------------------------------------------------
// Output helpers
// ------------------------------------------------------------------------------------------------

/// Cut long strings so a tool result stays small; ids are short and never cut.
fn truncate(v: &mut Value) {
    match v {
        Value::String(s) if s.chars().count() > MAX_FIELD_CHARS => {
            let cut: String = s.chars().take(MAX_FIELD_CHARS).collect();
            *s = format!("{cut}…[truncated]");
        }
        Value::Array(items) => items.iter_mut().for_each(truncate),
        Value::Object(map) => map.values_mut().for_each(truncate),
        _ => {}
    }
}

fn ok(summary: String, mut body: Value) -> Result<CallToolResult, ErrorData> {
    truncate(&mut body);
    let json = serde_json::to_string(&body).unwrap_or_else(|_| "{}".into());
    Ok(CallToolResult::success(vec![ContentBlock::text(format!(
        "{summary}\n{json}"
    ))]))
}

/// Errors are tool results the agent can act on: code, message, how to fix.
fn fail(e: AppError) -> Result<CallToolResult, ErrorData> {
    let body = e.body();
    let text = format!(
        "error {}: {}\n{}",
        body.code,
        body.message,
        serde_json::to_string(
            &json!({ "code": body.code, "message": body.message, "details": body.details })
        )
        .unwrap_or_default()
    );
    Ok(CallToolResult::error(vec![ContentBlock::text(text)]))
}

fn actor_of(ctx: &RequestContext<RoleServer>) -> Result<Actor, AppError> {
    ctx.extensions
        .get::<Parts>()
        .and_then(|p| p.extensions.get::<Actor>())
        .cloned()
        .ok_or(AppError::Unauthorized)
}

/// Compact command summary: ids, state, token, the event types that happened.
fn command_body(r: &CommandResult) -> Value {
    json!({
        "task_id": r.task_id,
        "state": r.state,
        "version": r.version,
        "lease_token": r.lease_token,
        "lease_expires_at": r.lease_expires_at.and_then(|t| t.format(&time::format_description::well_known::Rfc3339).ok()),
        "question_id": r.question_id,
        "spec_id": r.spec_id,
        "spec_version": r.spec_version,
        "events": r.events.iter().map(|e| json!({"seq": e.seq, "type": e.event_type})).collect::<Vec<_>>(),
    })
}

impl BoardMcp {
    /// The project check of every tool (the REST routes get it from `api::guard`).
    async fn guard(
        &self,
        ctx: &RequestContext<RoleServer>,
        target: Target,
        min: ProjectRole,
    ) -> Result<(), AppError> {
        let scope = ctx
            .extensions
            .get::<Parts>()
            .and_then(|p| p.extensions.get::<Scope>())
            .cloned()
            .ok_or(AppError::Unauthorized)?;
        project_access::require_pooled(&self.st, &scope, target, min).await?;
        Ok(())
    }

    async fn task_cmd(
        &self,
        ctx: &RequestContext<RoleServer>,
        task_id: Uuid,
        key: Option<String>,
        trace_id: Option<String>,
        cmd: TaskCmd,
    ) -> Result<CommandResult, AppError> {
        let actor = actor_of(ctx)?;
        self.guard(ctx, Target::Task(task_id), ProjectRole::Editor)
            .await?;
        let st = self.st.clone();
        let a = actor.clone();
        tx::run(&self.st, &actor, key.as_deref(), move |c| {
            Box::pin(async move {
                commands::task_command(c, &st, &a, task_id, cmd, trace_id.as_deref()).await
            })
        })
        .await
    }
}

// ------------------------------------------------------------------------------------------------
// Tools
// ------------------------------------------------------------------------------------------------

#[tool_router]
impl BoardMcp {
    #[tool(
        description = "List claimable tasks in a project, priority then age. role=implementer (default) lists ready tasks you may claim; role=reviewer lists unclaimed reviews you did not implement."
    )]
    async fn list_ready(
        &self,
        Parameters(a): Parameters<ListReadyArgs>,
        ctx: RequestContext<RoleServer>,
    ) -> Result<CallToolResult, ErrorData> {
        let run = async {
            let actor = actor_of(&ctx)?;
            self.guard(&ctx, Target::Project(a.project_id), ProjectRole::Viewer)
                .await?;
            let mut conn = self.st.pool.acquire().await?;
            let role = a.role.map(Into::into).unwrap_or(ClaimRole::Implementer);
            queries::list_ready(&mut conn, &actor, a.project_id, role, a.limit.unwrap_or(10)).await
        };
        match run.await {
            Ok(tasks) => {
                let items: Vec<Value> = tasks
                    .iter()
                    .map(|t| json!({"task_id": t.id, "title": t.title, "priority": t.priority, "state": t.state, "attempt_count": t.attempt_count}))
                    .collect();
                ok(
                    format!("{} claimable task(s); claim one to start", items.len()),
                    json!({ "tasks": items }),
                )
            }
            Err(e) => fail(e),
        }
    }

    #[tool(
        description = "Full context of a task: spec version and acceptance criteria, blockers, questions and answers, last handoff note, last 20 activities, attempts. Read it all before acting."
    )]
    async fn get_task(
        &self,
        Parameters(a): Parameters<GetTaskArgs>,
        ctx: RequestContext<RoleServer>,
    ) -> Result<CallToolResult, ErrorData> {
        let run = async {
            actor_of(&ctx)?;
            self.guard(&ctx, Target::Task(a.task_id), ProjectRole::Viewer)
                .await?;
            let mut conn = self.st.pool.acquire().await?;
            queries::task_context(&mut conn, a.task_id).await
        };
        match run.await {
            Ok(c) => ok(
                format!(
                    "task {} \"{}\" is {}",
                    c.task.id, c.task.title, c.task.state
                ),
                serde_json::to_value(&c).unwrap_or_default(),
            ),
            Err(e) => fail(e),
        }
    }

    #[tool(
        description = "Atomically claim a task. Without task_id the server picks the best claimable one. Returns lease_token (present it on every later write) and the full task context. Heartbeat at least every lease_ttl/3 seconds."
    )]
    async fn claim(
        &self,
        Parameters(a): Parameters<ClaimArgs>,
        ctx: RequestContext<RoleServer>,
    ) -> Result<CallToolResult, ErrorData> {
        let run = async {
            let actor = actor_of(&ctx)?;
            self.guard(&ctx, Target::Project(a.project_id), ProjectRole::Editor)
                .await?;
            let st = self.st.clone();
            let ac = actor.clone();
            let role = a.role.map(Into::into).unwrap_or(ClaimRole::Implementer);
            let trace_id = a.trace_id.clone();
            let res = tx::run(&self.st, &actor, a.idempotency_key.as_deref(), move |c| {
                Box::pin(async move {
                    commands::claim(
                        c,
                        &st,
                        &ac,
                        a.project_id,
                        role,
                        a.task_id,
                        trace_id.as_deref(),
                    )
                    .await
                })
            })
            .await?;
            let mut conn = self.st.pool.acquire().await?;
            let context = match res.task_id {
                Some(id) => Some(queries::task_context(&mut conn, id).await?),
                None => None,
            };
            Ok::<_, AppError>((res, context))
        };
        match run.await {
            Ok((res, context)) => {
                let mut body = command_body(&res);
                body["context"] = serde_json::to_value(&context).unwrap_or_default();
                ok(
                    format!(
                        "claimed task {}; keep the lease_token, heartbeat regularly",
                        res.task_id.map(|t| t.to_string()).unwrap_or_default()
                    ),
                    body,
                )
            }
            Err(e) => fail(e),
        }
    }

    #[tool(
        description = "Extend your lease. Call at least every lease_ttl/3 seconds while working. A stale_lease error means you lost the task: stop working on it."
    )]
    async fn heartbeat(
        &self,
        Parameters(a): Parameters<HeartbeatArgs>,
        ctx: RequestContext<RoleServer>,
    ) -> Result<CallToolResult, ErrorData> {
        let cmd = TaskCmd::Heartbeat {
            lease_token: Some(a.lease_token),
        };
        match self.task_cmd(&ctx, a.task_id, None, None, cmd).await {
            Ok(r) => ok("lease extended".into(), command_body(&r)),
            Err(e) => fail(e),
        }
    }

    #[tool(
        description = "Report a meaningful step. kind=progress or action for steps; kind=assumption when you proceed on an unconfirmed assumption; kind=thought for reasoning. Body at most 4 KB."
    )]
    async fn report(
        &self,
        Parameters(a): Parameters<ReportArgs>,
        ctx: RequestContext<RoleServer>,
    ) -> Result<CallToolResult, ErrorData> {
        let kind: ActivityKind = match serde_json::from_value(Value::String(a.kind.clone())) {
            Ok(k) => k,
            Err(_) => {
                return fail(AppError::BadRequest(
                    "kind must be thought, action, progress or assumption".into(),
                ));
            }
        };
        let cmd = TaskCmd::Report {
            lease_token: Some(a.lease_token),
            kind,
            body: a.body,
        };
        match self
            .task_cmd(&ctx, a.task_id, a.idempotency_key, a.trace_id, cmd)
            .await
        {
            Ok(r) => ok("reported".into(), command_body(&r)),
            Err(e) => fail(e),
        }
    }

    #[tool(
        description = "Ask a question. blocking=true when the spec is ambiguous or a requirement looks wrong: the task moves to input_required, your lease is released, and once answered only you may reclaim it for a short grace period. A handoff_note is required when blocking. Do not guess."
    )]
    async fn ask(
        &self,
        Parameters(a): Parameters<AskArgs>,
        ctx: RequestContext<RoleServer>,
    ) -> Result<CallToolResult, ErrorData> {
        let blocking = a.blocking;
        let cmd = TaskCmd::Ask {
            lease_token: Some(a.lease_token),
            question: a.question,
            blocking,
            options: a.options,
            handoff_note: a.handoff_note,
        };
        match self
            .task_cmd(&ctx, a.task_id, a.idempotency_key, None, cmd)
            .await
        {
            Ok(r) => ok(
                if blocking {
                    "question asked; your lease is released. Call wait_for_updates for the answer, then claim again".into()
                } else {
                    "question recorded; keep working".into()
                },
                command_body(&r),
            ),
            Err(e) => fail(e),
        }
    }

    #[tool(description = "Answer an open question. Any actor except the asker may answer.")]
    async fn answer(
        &self,
        Parameters(a): Parameters<AnswerArgs>,
        ctx: RequestContext<RoleServer>,
    ) -> Result<CallToolResult, ErrorData> {
        let run = async {
            let actor = actor_of(&ctx)?;
            self.guard(&ctx, Target::Question(a.question_id), ProjectRole::Editor)
                .await?;
            crate::service::access::require(
                &self.st,
                &actor,
                atb_core::access::Permission::QuestionsAnswer,
            )
            .await?;
            let st = self.st.clone();
            let ac = actor.clone();
            tx::run(&self.st, &actor, a.idempotency_key.as_deref(), move |c| {
                Box::pin(
                    async move { commands::answer(c, &st, &ac, a.question_id, a.answer).await },
                )
            })
            .await
        };
        match run.await {
            Ok(r) => ok("answered".into(), command_body(&r)),
            Err(e) => fail(e),
        }
    }

    #[tool(
        description = "Long-poll for events relevant to you (your tasks, answers to your questions, tasks becoming ready) after cursor. Returns at once if there are some, otherwise when one arrives or after timeout_s (max 25). Pass the returned cursor back next time."
    )]
    async fn wait_for_updates(
        &self,
        Parameters(a): Parameters<WaitArgs>,
        ctx: RequestContext<RoleServer>,
    ) -> Result<CallToolResult, ErrorData> {
        let run = async {
            let actor = actor_of(&ctx)?;
            self.guard(&ctx, Target::Project(a.project_id), ProjectRole::Viewer)
                .await?;
            updates::wait_for_updates(
                &self.st,
                &actor,
                a.project_id,
                a.cursor,
                a.timeout_s.unwrap_or(updates::MAX_WAIT_SECS),
            )
            .await
        };
        match run.await {
            Ok(u) => ok(
                if u.events.is_empty() {
                    format!("no relevant update; cursor={}", u.cursor)
                } else {
                    format!("{} relevant update(s); cursor={}", u.events.len(), u.cursor)
                },
                serde_json::to_value(&u).unwrap_or_default(),
            ),
            Err(e) => fail(e),
        }
    }

    #[tool(
        description = "Create a task. Work you discover outside your task goes here with discovered_from=<your task>, not into your current change. blocked_by lists tasks that must be done first."
    )]
    async fn create_task(
        &self,
        Parameters(a): Parameters<CreateTaskArgs>,
        ctx: RequestContext<RoleServer>,
    ) -> Result<CallToolResult, ErrorData> {
        let run = async {
            let actor = actor_of(&ctx)?;
            self.guard(&ctx, Target::Project(a.project_id), ProjectRole::Editor)
                .await?;
            let st = self.st.clone();
            let ac = actor.clone();
            let input = NewTaskInput {
                title: a.title,
                spec_id: a.spec_id,
                spec_version: a.spec_version,
                parent_id: a.parent_id,
                blocked_by: a.blocked_by.unwrap_or_default(),
                discovered_from: a.discovered_from,
                priority: a.priority,
            };
            tx::run(&self.st, &actor, a.idempotency_key.as_deref(), move |c| {
                Box::pin(async move {
                    commands::create_task(c, &st, &ac, a.project_id, input, None).await
                })
            })
            .await
        };
        match run.await {
            Ok(r) => ok(
                format!(
                    "task {} created ({})",
                    r.task_id.map(|t| t.to_string()).unwrap_or_default(),
                    r.state.clone().unwrap_or_default()
                ),
                command_body(&r),
            ),
            Err(e) => fail(e),
        }
    }

    #[tool(
        description = "Propose a spec version (a new spec when spec_id is omitted). Agents may propose; only humans approve. Acceptance criteria: [{id, text, verify:{kind: command|human, command?}}]."
    )]
    async fn propose_spec_version(
        &self,
        Parameters(a): Parameters<ProposeSpecArgs>,
        ctx: RequestContext<RoleServer>,
    ) -> Result<CallToolResult, ErrorData> {
        let run = async {
            let actor = actor_of(&ctx)?;
            let target = match (a.spec_id, a.project_id) {
                (Some(spec), _) => Target::Spec(spec),
                (None, Some(project)) => Target::Project(project),
                (None, None) => {
                    return Err(AppError::BadRequest(
                        "spec_id or project_id is required".into(),
                    ));
                }
            };
            self.guard(&ctx, target, ProjectRole::Editor).await?;
            let st = self.st.clone();
            let ac = actor.clone();
            let input = SpecInput {
                title: a.title,
                body_md: a.body_md,
                acceptance_criteria: a.acceptance_criteria,
                protected_paths: a.protected_paths.unwrap_or_default(),
                test_ref: None,
            };
            let (spec_id, project_id) = (a.spec_id, a.project_id);
            tx::run(&self.st, &actor, a.idempotency_key.as_deref(), move |c| {
                Box::pin(async move {
                    match (spec_id, project_id) {
                        (Some(s), _) => commands::propose_version(c, &st, &ac, s, input).await,
                        (None, Some(p)) => commands::create_spec(c, &st, &ac, p, input).await,
                        (None, None) => Err(AppError::BadRequest(
                            "give spec_id, or project_id and title for a new spec".into(),
                        )),
                    }
                })
            })
            .await
        };
        match run.await {
            Ok(r) => ok(
                format!(
                    "spec {} version {} proposed; a human must approve it",
                    r.spec_id.map(|s| s.to_string()).unwrap_or_default(),
                    r.spec_version.unwrap_or_default()
                ),
                command_body(&r),
            ),
            Err(e) => fail(e),
        }
    }

    #[tool(
        description = "Repin a spec_outdated task to the approved spec version (an explicit, recorded action). Pass your lease_token if you hold the task."
    )]
    async fn repin(
        &self,
        Parameters(a): Parameters<RepinArgs>,
        ctx: RequestContext<RoleServer>,
    ) -> Result<CallToolResult, ErrorData> {
        let cmd = TaskCmd::Repin {
            lease_token: a.lease_token,
            to_version: None,
        };
        match self
            .task_cmd(&ctx, a.task_id, a.idempotency_key, None, cmd)
            .await
        {
            Ok(r) => ok(
                "repinned to the approved spec version; re-read the spec".into(),
                command_body(&r),
            ),
            Err(e) => fail(e),
        }
    }

    #[tool(
        description = "Submit your commit. Leave a handoff note first (report). The server runs the acceptance checks; you never self-report a passing test."
    )]
    async fn submit_for_test(
        &self,
        Parameters(a): Parameters<SubmitArgs>,
        ctx: RequestContext<RoleServer>,
    ) -> Result<CallToolResult, ErrorData> {
        let cmd = TaskCmd::SubmitForTest {
            lease_token: Some(a.lease_token),
            commit_sha: a.commit_sha,
            branch: a.branch,
        };
        match self
            .task_cmd(&ctx, a.task_id, a.idempotency_key, None, cmd)
            .await
        {
            Ok(r) => ok(
                format!(
                    "submitted; task is now {}",
                    r.state.clone().unwrap_or_default()
                ),
                command_body(&r),
            ),
            Err(e) => fail(e),
        }
    }

    #[tool(
        description = "Release the task back to ready. A handoff_note is required: what is done, what is left, where."
    )]
    async fn release(
        &self,
        Parameters(a): Parameters<ReleaseArgs>,
        ctx: RequestContext<RoleServer>,
    ) -> Result<CallToolResult, ErrorData> {
        let cmd = TaskCmd::Release {
            lease_token: Some(a.lease_token),
            handoff_note: a.handoff_note,
        };
        match self
            .task_cmd(&ctx, a.task_id, a.idempotency_key, None, cmd)
            .await
        {
            Ok(r) => ok(
                "released; the task is ready for anyone".into(),
                command_body(&r),
            ),
            Err(e) => fail(e),
        }
    }

    #[tool(
        description = "Link two tasks of a project. kind=blocks means from_id must be done before to_id can be claimed (cycles are rejected); discovered_from and related are informative."
    )]
    async fn link_tasks(
        &self,
        Parameters(a): Parameters<LinkArgs>,
        ctx: RequestContext<RoleServer>,
    ) -> Result<CallToolResult, ErrorData> {
        let run = async {
            let actor = actor_of(&ctx)?;
            self.guard(&ctx, Target::Task(a.from_id), ProjectRole::Editor)
                .await?;
            self.guard(&ctx, Target::Task(a.to_id), ProjectRole::Editor)
                .await?;
            let kind = LinkKind::parse(&a.kind).ok_or_else(|| {
                AppError::BadRequest("kind must be blocks, discovered_from or related".into())
            })?;
            let st = self.st.clone();
            let ac = actor.clone();
            tx::run(&self.st, &actor, None, move |c| {
                Box::pin(
                    async move { commands::add_link(c, &st, &ac, a.from_id, a.to_id, kind).await },
                )
            })
            .await
        };
        match run.await {
            Ok(r) => ok("linked".into(), command_body(&r)),
            Err(e) => fail(e),
        }
    }
}

#[tool_handler]
impl ServerHandler for BoardMcp {
    fn get_info(&self) -> ServerConfig {
        ServerConfig::new(ServerCapabilities::builder().enable_tools().build())
            .with_server_info(Implementation::new(
                "agent-task-board",
                env!("CARGO_PKG_VERSION"),
            ))
            .with_instructions(INSTRUCTIONS)
    }
}
