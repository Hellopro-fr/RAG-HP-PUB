//! REST handlers (§8). Humans run the same commands as agents through these endpoints; every
//! mutation goes through `service::tx::run` (one transaction, optional `Idempotency-Key`).

use atb_core::{ActivityKind, LinkKind, WorkflowConfig};
use axum::extract::{Path, Query, State};
use axum::http::{HeaderMap, HeaderValue, StatusCode, header};
use axum::response::{IntoResponse, Response};
use axum::{Extension, Json};
use serde_json::Value;
use uuid::Uuid;

use super::auth::{SESSION_COOKIE, session_cookie};
use super::dto::*;
use crate::actor::Actor;
use crate::error::{AppError, AppResult, ErrorBody};
use crate::repository::StoredEvent;
use crate::repository::reads::{
    self, ActorView, ProjectView, QuestionView, SpecVersionView, SpecView, TaskView,
};
use crate::service::auth::{CreatedActor, NewActorInput};
use crate::service::commands::{self, CommandResult, NewTaskInput, SpecInput, TaskCmd};
use crate::service::queries::{self, Board, TaskContext};
use crate::service::rebuild::{self, RebuildReport};
use crate::service::{auth as auth_svc, now, tx};
use crate::state::AppState;

fn header_str(headers: &HeaderMap, name: &str) -> Option<String> {
    headers
        .get(name)
        .and_then(|v| v.to_str().ok())
        .map(|v| v.trim().to_string())
        .filter(|v| !v.is_empty())
}

fn idem(headers: &HeaderMap) -> Option<String> {
    header_str(headers, "idempotency-key")
}

fn trace(headers: &HeaderMap) -> Option<String> {
    header_str(headers, "x-trace-id")
}

async fn task_cmd(
    st: AppState,
    actor: Actor,
    headers: HeaderMap,
    task_id: Uuid,
    cmd: TaskCmd,
) -> AppResult<Json<CommandResult>> {
    let key = idem(&headers);
    let trace_id = trace(&headers);
    let st2 = st.clone();
    let a = actor.clone();
    let out = tx::run(&st, &actor, key.as_deref(), move |c| {
        Box::pin(async move {
            commands::task_command(c, &st2, &a, task_id, cmd, trace_id.as_deref()).await
        })
    })
    .await?;
    Ok(Json(out))
}

fn parse_activity(kind: &str) -> AppResult<ActivityKind> {
    serde_json::from_value(Value::String(kind.to_string())).map_err(|_| {
        AppError::BadRequest("kind must be thought, action, progress or assumption".into())
    })
}

// --- ops ---------------------------------------------------------------------------------------

pub async fn healthz() -> &'static str {
    "ok"
}

pub async fn readyz(State(st): State<AppState>) -> Response {
    match sqlx::query("SELECT 1").execute(&st.pool).await {
        Ok(_) => (StatusCode::OK, "ready").into_response(),
        Err(_) => (StatusCode::SERVICE_UNAVAILABLE, "database unavailable").into_response(),
    }
}

pub async fn metrics(State(st): State<AppState>) -> Response {
    (
        [(header::CONTENT_TYPE, "text/plain; version=0.0.4")],
        st.metrics.render(),
    )
        .into_response()
}

// --- auth --------------------------------------------------------------------------------------

#[utoipa::path(post, path = "/api/auth/login", tag = "auth", request_body = LoginInput,
    responses((status = 200, body = MeView), (status = 401, body = ErrorBody)))]
pub async fn login(
    State(st): State<AppState>,
    Json(input): Json<LoginInput>,
) -> AppResult<Response> {
    let mut conn = st.pool.acquire().await?;
    let (actor, token, expires_at) = auth_svc::login(
        &mut conn,
        &input.login,
        &input.password,
        st.cfg.session_ttl_hours,
    )
    .await?;
    let max_age = (expires_at - now()).whole_seconds().max(0);
    let secure = if st.cfg.cookie_secure { "; Secure" } else { "" };
    let cookie = format!(
        "{SESSION_COOKIE}={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={max_age}{secure}"
    );
    let mut res = Json(me_view(&actor)).into_response();
    res.headers_mut().insert(
        header::SET_COOKIE,
        HeaderValue::from_str(&cookie).map_err(|e| AppError::Internal(e.into()))?,
    );
    Ok(res)
}

#[utoipa::path(post, path = "/api/auth/logout", tag = "auth", responses((status = 204)))]
pub async fn logout(State(st): State<AppState>, headers: HeaderMap) -> AppResult<Response> {
    if let Some(token) = session_cookie(&headers) {
        let mut conn = st.pool.acquire().await?;
        auth_svc::logout(&mut conn, &token).await?;
    }
    let mut res = StatusCode::NO_CONTENT.into_response();
    res.headers_mut().insert(
        header::SET_COOKIE,
        HeaderValue::from_static("atb_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"),
    );
    Ok(res)
}

fn me_view(a: &Actor) -> MeView {
    MeView {
        id: a.id,
        kind: a.kind.as_str().to_string(),
        name: a.name.clone(),
        roles: a.roles.iter().map(|r| r.as_str().to_string()).collect(),
        model: a.model.clone(),
    }
}

#[utoipa::path(get, path = "/api/auth/me", tag = "auth", responses((status = 200, body = MeView)))]
pub async fn me(Extension(actor): Extension<Actor>) -> Json<MeView> {
    Json(me_view(&actor))
}

// --- projects ----------------------------------------------------------------------------------

#[utoipa::path(get, path = "/api/projects", tag = "projects",
    responses((status = 200, body = Vec<ProjectView>)))]
pub async fn list_projects(State(st): State<AppState>) -> AppResult<Json<Vec<ProjectView>>> {
    let mut conn = st.pool.acquire().await?;
    Ok(Json(reads::projects(&mut conn).await?))
}

#[utoipa::path(post, path = "/api/projects", tag = "projects", request_body = CreateProjectInput,
    responses((status = 201, body = ProjectView), (status = 422, body = ErrorBody)))]
pub async fn create_project(
    State(st): State<AppState>,
    Extension(actor): Extension<Actor>,
    headers: HeaderMap,
    Json(input): Json<CreateProjectInput>,
) -> AppResult<(StatusCode, Json<ProjectView>)> {
    let workflow: Option<WorkflowConfig> = match input.workflow {
        Some(v) => Some(
            serde_json::from_value(v)
                .map_err(|e| AppError::BadRequest(format!("invalid workflow: {e}")))?,
        ),
        None => None,
    };
    let st2 = st.clone();
    let a = actor.clone();
    let out = tx::run(&st, &actor, idem(&headers).as_deref(), move |c| {
        Box::pin(async move { commands::create_project(c, &st2, &a, &input.name, workflow).await })
    })
    .await?;
    Ok((StatusCode::CREATED, Json(out)))
}

#[utoipa::path(get, path = "/api/projects/{id}", params(("id" = Uuid, Path)), tag = "projects",
    responses((status = 200, body = ProjectView), (status = 404, body = ErrorBody)))]
pub async fn get_project(
    State(st): State<AppState>,
    Path(id): Path<Uuid>,
) -> AppResult<Json<ProjectView>> {
    let mut conn = st.pool.acquire().await?;
    reads::project(&mut conn, id)
        .await?
        .map(Json)
        .ok_or_else(|| AppError::not_found("project"))
}

#[utoipa::path(get, path = "/api/projects/{id}/board", params(("id" = Uuid, Path)), tag = "projects",
    responses((status = 200, body = Board), (status = 404, body = ErrorBody)))]
pub async fn board(State(st): State<AppState>, Path(id): Path<Uuid>) -> AppResult<Json<Board>> {
    Ok(Json(queries::board(&st, id).await?))
}

#[utoipa::path(get, path = "/api/projects/{id}/events", tag = "projects", params(("id" = Uuid, Path), EventsQuery),
    responses((status = 200, body = Vec<StoredEvent>)))]
pub async fn events(
    State(st): State<AppState>,
    Path(id): Path<Uuid>,
    Query(q): Query<EventsQuery>,
) -> AppResult<Json<Vec<StoredEvent>>> {
    let mut conn = st.pool.acquire().await?;
    reads::project(&mut conn, id)
        .await?
        .ok_or_else(|| AppError::not_found("project"))?;
    let limit = q.limit.unwrap_or(500).clamp(1, 5000);
    Ok(Json(
        reads::events_after(&mut conn, id, q.after.unwrap_or(0), limit).await?,
    ))
}

#[utoipa::path(get, path = "/api/projects/{id}/ready", tag = "projects", params(("id" = Uuid, Path), ReadyQuery),
    responses((status = 200, body = Vec<TaskView>)))]
pub async fn ready(
    State(st): State<AppState>,
    Extension(actor): Extension<Actor>,
    Path(id): Path<Uuid>,
    Query(q): Query<ReadyQuery>,
) -> AppResult<Json<Vec<TaskView>>> {
    let mut conn = st.pool.acquire().await?;
    let role = q.role.unwrap_or(commands::ClaimRole::Implementer);
    Ok(Json(
        queries::list_ready(&mut conn, &actor, id, role, q.limit.unwrap_or(10)).await?,
    ))
}

#[utoipa::path(post, path = "/api/projects/{id}/claim", params(("id" = Uuid, Path)), tag = "tasks", request_body = ClaimInput,
    responses((status = 200, body = CommandResult), (status = 409, body = ErrorBody)))]
pub async fn claim_in_project(
    State(st): State<AppState>,
    Extension(actor): Extension<Actor>,
    headers: HeaderMap,
    Path(id): Path<Uuid>,
    Json(input): Json<ClaimInput>,
) -> AppResult<Json<CommandResult>> {
    claim(st, actor, headers, id, input.role, input.task_id).await
}

async fn claim(
    st: AppState,
    actor: Actor,
    headers: HeaderMap,
    project_id: Uuid,
    role: commands::ClaimRole,
    task_id: Option<Uuid>,
) -> AppResult<Json<CommandResult>> {
    let trace_id = trace(&headers);
    let st2 = st.clone();
    let a = actor.clone();
    let out = tx::run(&st, &actor, idem(&headers).as_deref(), move |c| {
        Box::pin(async move {
            commands::claim(c, &st2, &a, project_id, role, task_id, trace_id.as_deref()).await
        })
    })
    .await?;
    Ok(Json(out))
}

#[utoipa::path(post, path = "/api/projects/{id}/tasks", params(("id" = Uuid, Path)), tag = "tasks", request_body = NewTaskInput,
    responses((status = 201, body = CommandResult), (status = 422, body = ErrorBody)))]
pub async fn create_task(
    State(st): State<AppState>,
    Extension(actor): Extension<Actor>,
    headers: HeaderMap,
    Path(id): Path<Uuid>,
    Json(input): Json<NewTaskInput>,
) -> AppResult<(StatusCode, Json<CommandResult>)> {
    let trace_id = trace(&headers);
    let st2 = st.clone();
    let a = actor.clone();
    let out = tx::run(&st, &actor, idem(&headers).as_deref(), move |c| {
        Box::pin(
            async move { commands::create_task(c, &st2, &a, id, input, trace_id.as_deref()).await },
        )
    })
    .await?;
    Ok((StatusCode::CREATED, Json(out)))
}

#[utoipa::path(get, path = "/api/projects/{id}/specs", params(("id" = Uuid, Path)), tag = "specs",
    responses((status = 200, body = Vec<SpecView>)))]
pub async fn list_specs(
    State(st): State<AppState>,
    Path(id): Path<Uuid>,
) -> AppResult<Json<Vec<SpecView>>> {
    let mut conn = st.pool.acquire().await?;
    Ok(Json(reads::specs(&mut conn, Some(id), None).await?))
}

#[utoipa::path(post, path = "/api/projects/{id}/specs", params(("id" = Uuid, Path)), tag = "specs", request_body = SpecInput,
    responses((status = 201, body = CommandResult), (status = 422, body = ErrorBody)))]
pub async fn create_spec(
    State(st): State<AppState>,
    Extension(actor): Extension<Actor>,
    headers: HeaderMap,
    Path(id): Path<Uuid>,
    Json(input): Json<SpecInput>,
) -> AppResult<(StatusCode, Json<CommandResult>)> {
    let st2 = st.clone();
    let a = actor.clone();
    let out = tx::run(&st, &actor, idem(&headers).as_deref(), move |c| {
        Box::pin(async move { commands::create_spec(c, &st2, &a, id, input).await })
    })
    .await?;
    Ok((StatusCode::CREATED, Json(out)))
}

#[utoipa::path(get, path = "/api/projects/{id}/rebuild-check", params(("id" = Uuid, Path)), tag = "ops",
    responses((status = 200, body = RebuildReport), (status = 403, body = ErrorBody)))]
pub async fn rebuild_check(
    State(st): State<AppState>,
    Extension(actor): Extension<Actor>,
    Path(id): Path<Uuid>,
) -> AppResult<Json<RebuildReport>> {
    if !actor.is_admin() {
        return Err(AppError::Forbidden("admins only".into()));
    }
    Ok(Json(rebuild::check_project(&st.pool, id).await?))
}

// --- specs -------------------------------------------------------------------------------------

#[derive(serde::Serialize, utoipa::ToSchema)]
pub struct SpecDetail {
    pub spec: SpecView,
    pub versions: Vec<SpecVersionView>,
}

#[utoipa::path(get, path = "/api/specs/{id}", params(("id" = Uuid, Path)), tag = "specs",
    responses((status = 200, body = SpecDetail), (status = 404, body = ErrorBody)))]
pub async fn get_spec(
    State(st): State<AppState>,
    Path(id): Path<Uuid>,
) -> AppResult<Json<SpecDetail>> {
    let mut conn = st.pool.acquire().await?;
    let spec = reads::specs(&mut conn, None, Some(id))
        .await?
        .pop()
        .ok_or_else(|| AppError::not_found("spec"))?;
    let versions = reads::spec_versions(&mut conn, id, None).await?;
    Ok(Json(SpecDetail { spec, versions }))
}

#[utoipa::path(post, path = "/api/specs/{id}/versions", params(("id" = Uuid, Path)), tag = "specs", request_body = SpecInput,
    responses((status = 201, body = CommandResult)))]
pub async fn propose_version(
    State(st): State<AppState>,
    Extension(actor): Extension<Actor>,
    headers: HeaderMap,
    Path(id): Path<Uuid>,
    Json(input): Json<SpecInput>,
) -> AppResult<(StatusCode, Json<CommandResult>)> {
    let st2 = st.clone();
    let a = actor.clone();
    let out = tx::run(&st, &actor, idem(&headers).as_deref(), move |c| {
        Box::pin(async move { commands::propose_version(c, &st2, &a, id, input).await })
    })
    .await?;
    Ok((StatusCode::CREATED, Json(out)))
}

#[utoipa::path(post, path = "/api/specs/{id}/versions/{version}/approve", params(("id" = Uuid, Path), ("version" = i32, Path)), tag = "specs",
    responses((status = 200, body = CommandResult), (status = 403, body = ErrorBody)))]
pub async fn approve_version(
    State(st): State<AppState>,
    Extension(actor): Extension<Actor>,
    headers: HeaderMap,
    Path((id, version)): Path<(Uuid, i32)>,
) -> AppResult<Json<CommandResult>> {
    let st2 = st.clone();
    let a = actor.clone();
    let out = tx::run(&st, &actor, idem(&headers).as_deref(), move |c| {
        Box::pin(async move { commands::approve_version(c, &st2, &a, id, version).await })
    })
    .await?;
    Ok(Json(out))
}

// --- tasks -------------------------------------------------------------------------------------

#[utoipa::path(get, path = "/api/tasks/{id}", params(("id" = Uuid, Path)), tag = "tasks",
    responses((status = 200, body = TaskContext), (status = 404, body = ErrorBody)))]
pub async fn get_task(
    State(st): State<AppState>,
    Path(id): Path<Uuid>,
) -> AppResult<Json<TaskContext>> {
    let mut conn = st.pool.acquire().await?;
    Ok(Json(queries::task_context(&mut conn, id).await?))
}

#[utoipa::path(patch, path = "/api/tasks/{id}", params(("id" = Uuid, Path)), tag = "tasks", request_body = PatchTaskInput,
    responses((status = 200, body = CommandResult), (status = 409, body = ErrorBody)))]
pub async fn patch_task(
    State(st): State<AppState>,
    Extension(actor): Extension<Actor>,
    headers: HeaderMap,
    Path(id): Path<Uuid>,
    Json(input): Json<PatchTaskInput>,
) -> AppResult<Json<CommandResult>> {
    let cmd = TaskCmd::Update {
        expected_version: input.expected_version,
        title: input.title,
        priority: input.priority,
    };
    task_cmd(st, actor, headers, id, cmd).await
}

#[utoipa::path(get, path = "/api/tasks/{id}/timeline", tag = "tasks", params(("id" = Uuid, Path), TimelineQuery),
    responses((status = 200, body = Vec<StoredEvent>)))]
pub async fn timeline(
    State(st): State<AppState>,
    Path(id): Path<Uuid>,
    Query(q): Query<TimelineQuery>,
) -> AppResult<Json<Vec<StoredEvent>>> {
    let mut conn = st.pool.acquire().await?;
    Ok(Json(
        queries::timeline(&mut conn, id, q.limit.unwrap_or(500)).await?,
    ))
}

#[utoipa::path(post, path = "/api/tasks/{id}/claim", params(("id" = Uuid, Path)), tag = "tasks", request_body = TaskClaimInput,
    responses((status = 200, body = CommandResult), (status = 409, body = ErrorBody)))]
pub async fn claim_task(
    State(st): State<AppState>,
    Extension(actor): Extension<Actor>,
    headers: HeaderMap,
    Path(id): Path<Uuid>,
    Json(input): Json<TaskClaimInput>,
) -> AppResult<Json<CommandResult>> {
    let project_id = {
        let mut conn = st.pool.acquire().await?;
        crate::repository::store::task_project(&mut conn, id)
            .await?
            .ok_or_else(|| AppError::not_found("task"))?
    };
    claim(st, actor, headers, project_id, input.role, Some(id)).await
}

#[utoipa::path(post, path = "/api/tasks/{id}/heartbeat", params(("id" = Uuid, Path)), tag = "tasks", request_body = LeaseInput,
    responses((status = 200, body = CommandResult), (status = 409, body = ErrorBody)))]
pub async fn heartbeat(
    State(st): State<AppState>,
    Extension(actor): Extension<Actor>,
    headers: HeaderMap,
    Path(id): Path<Uuid>,
    Json(input): Json<LeaseInput>,
) -> AppResult<Json<CommandResult>> {
    task_cmd(
        st,
        actor,
        headers,
        id,
        TaskCmd::Heartbeat {
            lease_token: input.lease_token,
        },
    )
    .await
}

#[utoipa::path(post, path = "/api/tasks/{id}/report", params(("id" = Uuid, Path)), tag = "tasks", request_body = ReportInput,
    responses((status = 200, body = CommandResult), (status = 409, body = ErrorBody)))]
pub async fn report(
    State(st): State<AppState>,
    Extension(actor): Extension<Actor>,
    headers: HeaderMap,
    Path(id): Path<Uuid>,
    Json(input): Json<ReportInput>,
) -> AppResult<Json<CommandResult>> {
    let cmd = TaskCmd::Report {
        lease_token: input.lease_token,
        kind: parse_activity(&input.kind)?,
        body: input.body,
    };
    task_cmd(st, actor, headers, id, cmd).await
}

#[utoipa::path(post, path = "/api/tasks/{id}/ask", params(("id" = Uuid, Path)), tag = "tasks", request_body = AskInput,
    responses((status = 200, body = CommandResult), (status = 409, body = ErrorBody)))]
pub async fn ask(
    State(st): State<AppState>,
    Extension(actor): Extension<Actor>,
    headers: HeaderMap,
    Path(id): Path<Uuid>,
    Json(input): Json<AskInput>,
) -> AppResult<Json<CommandResult>> {
    let cmd = TaskCmd::Ask {
        lease_token: input.lease_token,
        question: input.question,
        blocking: input.blocking,
        options: input.options,
        handoff_note: input.handoff_note,
    };
    task_cmd(st, actor, headers, id, cmd).await
}

#[utoipa::path(post, path = "/api/tasks/{id}/release", params(("id" = Uuid, Path)), tag = "tasks", request_body = ReleaseInput,
    responses((status = 200, body = CommandResult), (status = 409, body = ErrorBody)))]
pub async fn release(
    State(st): State<AppState>,
    Extension(actor): Extension<Actor>,
    headers: HeaderMap,
    Path(id): Path<Uuid>,
    Json(input): Json<ReleaseInput>,
) -> AppResult<Json<CommandResult>> {
    let cmd = TaskCmd::Release {
        lease_token: input.lease_token,
        handoff_note: input.handoff_note,
    };
    task_cmd(st, actor, headers, id, cmd).await
}

#[utoipa::path(post, path = "/api/tasks/{id}/submit-for-test", params(("id" = Uuid, Path)), tag = "tasks", request_body = SubmitInput,
    responses((status = 200, body = CommandResult), (status = 409, body = ErrorBody)))]
pub async fn submit_for_test(
    State(st): State<AppState>,
    Extension(actor): Extension<Actor>,
    headers: HeaderMap,
    Path(id): Path<Uuid>,
    Json(input): Json<SubmitInput>,
) -> AppResult<Json<CommandResult>> {
    let cmd = TaskCmd::SubmitForTest {
        lease_token: input.lease_token,
        commit_sha: input.commit_sha,
        branch: input.branch,
    };
    task_cmd(st, actor, headers, id, cmd).await
}

#[utoipa::path(post, path = "/api/tasks/{id}/repin", params(("id" = Uuid, Path)), tag = "tasks", request_body = RepinInput,
    responses((status = 200, body = CommandResult), (status = 409, body = ErrorBody)))]
pub async fn repin(
    State(st): State<AppState>,
    Extension(actor): Extension<Actor>,
    headers: HeaderMap,
    Path(id): Path<Uuid>,
    Json(input): Json<RepinInput>,
) -> AppResult<Json<CommandResult>> {
    let cmd = TaskCmd::Repin {
        lease_token: input.lease_token,
        to_version: input.to_version,
    };
    task_cmd(st, actor, headers, id, cmd).await
}

#[utoipa::path(post, path = "/api/tasks/{id}/cancel", params(("id" = Uuid, Path)), tag = "tasks", request_body = CancelInput,
    responses((status = 200, body = CommandResult), (status = 403, body = ErrorBody)))]
pub async fn cancel(
    State(st): State<AppState>,
    Extension(actor): Extension<Actor>,
    headers: HeaderMap,
    Path(id): Path<Uuid>,
    input: Option<Json<CancelInput>>,
) -> AppResult<Json<CommandResult>> {
    let reason = input.and_then(|Json(i)| i.reason);
    task_cmd(st, actor, headers, id, TaskCmd::Cancel { reason }).await
}

#[utoipa::path(post, path = "/api/tasks/{id}/links", params(("id" = Uuid, Path)), tag = "tasks", request_body = LinkInput,
    responses((status = 200, body = CommandResult), (status = 409, body = ErrorBody)))]
pub async fn add_link(
    State(st): State<AppState>,
    Extension(actor): Extension<Actor>,
    headers: HeaderMap,
    Path(id): Path<Uuid>,
    Json(input): Json<LinkInput>,
) -> AppResult<Json<CommandResult>> {
    let kind = LinkKind::parse(&input.kind).ok_or_else(|| {
        AppError::BadRequest("kind must be blocks, discovered_from or related".into())
    })?;
    let st2 = st.clone();
    let a = actor.clone();
    let out = tx::run(&st, &actor, idem(&headers).as_deref(), move |c| {
        Box::pin(async move { commands::add_link(c, &st2, &a, id, input.to_id, kind).await })
    })
    .await?;
    Ok(Json(out))
}

// --- questions ---------------------------------------------------------------------------------

#[utoipa::path(get, path = "/api/questions", tag = "questions", params(QuestionsQuery),
    responses((status = 200, body = Vec<QuestionView>)))]
pub async fn list_questions(
    State(st): State<AppState>,
    Query(q): Query<QuestionsQuery>,
) -> AppResult<Json<Vec<QuestionView>>> {
    let mut conn = st.pool.acquire().await?;
    let limit = q.limit.unwrap_or(200).clamp(1, 1000);
    Ok(Json(
        reads::questions(&mut conn, q.project_id, None, q.status.as_deref(), limit).await?,
    ))
}

#[utoipa::path(post, path = "/api/questions/{id}/answer", params(("id" = Uuid, Path)), tag = "questions", request_body = AnswerInput,
    responses((status = 200, body = CommandResult), (status = 403, body = ErrorBody)))]
pub async fn answer(
    State(st): State<AppState>,
    Extension(actor): Extension<Actor>,
    headers: HeaderMap,
    Path(id): Path<Uuid>,
    Json(input): Json<AnswerInput>,
) -> AppResult<Json<CommandResult>> {
    let st2 = st.clone();
    let a = actor.clone();
    let out = tx::run(&st, &actor, idem(&headers).as_deref(), move |c| {
        Box::pin(async move { commands::answer(c, &st2, &a, id, input.answer).await })
    })
    .await?;
    Ok(Json(out))
}

// --- actors ------------------------------------------------------------------------------------

#[utoipa::path(get, path = "/api/actors", tag = "actors",
    responses((status = 200, body = Vec<ActorView>)))]
pub async fn list_actors(State(st): State<AppState>) -> AppResult<Json<Vec<ActorView>>> {
    let mut conn = st.pool.acquire().await?;
    Ok(Json(reads::actor_views(&mut conn, now()).await?))
}

#[utoipa::path(post, path = "/api/actors", tag = "actors", request_body = NewActorInput,
    responses((status = 201, body = CreatedActor), (status = 403, body = ErrorBody)))]
pub async fn create_actor(
    State(st): State<AppState>,
    Extension(actor): Extension<Actor>,
    Json(input): Json<NewActorInput>,
) -> AppResult<(StatusCode, Json<CreatedActor>)> {
    let mut conn = st.pool.acquire().await?;
    Ok((
        StatusCode::CREATED,
        Json(auth_svc::create_actor(&mut conn, &actor, input).await?),
    ))
}
