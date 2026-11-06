//! OpenAPI document (`GET /api/openapi.json`, `atb-server dump-openapi`). The frontend generates
//! its types from it with openapi-typescript; API types are never hand-written.

use utoipa::OpenApi;

use super::{dto, rest, sse};
use crate::error::ErrorBody;
use crate::repository::StoredEvent;
use crate::repository::reads::{
    ActorView, AttemptView, CurrentLease, LeaseView, LinkView, ProjectView, QuestionView,
    SpecVersionView, SpecView, TaskRef, TaskView,
};
use crate::service::auth::{CreatedActor, NewActorInput, NewActorKind};
use crate::service::commands::{ClaimRole, CommandResult, NewTaskInput, SpecInput};
use crate::service::queries::{Board, TaskContext};
use crate::service::rebuild::{RebuildReport, TableDiff};

#[derive(OpenApi)]
#[openapi(
    info(
        title = "Agent Task Board API",
        version = "0.1.0",
        description = "Real-time task board for LLM agents and humans. Errors: {code, message, details}."
    ),
    paths(
        rest::login, rest::logout, rest::me,
        rest::list_projects, rest::create_project, rest::get_project, rest::board, rest::events,
        rest::ready, rest::claim_in_project, rest::create_task, rest::list_specs, rest::create_spec,
        rest::rebuild_check,
        rest::get_spec, rest::propose_version, rest::approve_version,
        rest::get_task, rest::patch_task, rest::timeline, rest::claim_task, rest::heartbeat,
        rest::report, rest::ask, rest::release, rest::submit_for_test, rest::repin, rest::cancel,
        rest::add_link,
        rest::list_questions, rest::answer,
        rest::list_actors, rest::create_actor,
        sse::project_stream, sse::global_stream,
    ),
    components(schemas(
        ErrorBody, StoredEvent, ProjectView, TaskView, LeaseView, LinkView, TaskRef, QuestionView,
        AttemptView, SpecView, SpecVersionView, ActorView, CurrentLease, Board, TaskContext,
        CommandResult, ClaimRole, NewTaskInput, SpecInput, NewActorInput, NewActorKind,
        CreatedActor, RebuildReport, TableDiff, rest::SpecDetail,
        dto::LoginInput, dto::MeView, dto::CreateProjectInput, dto::ClaimInput,
        dto::TaskClaimInput, dto::LeaseInput, dto::ReportInput, dto::AskInput, dto::ReleaseInput,
        dto::SubmitInput, dto::RepinInput, dto::CancelInput, dto::PatchTaskInput, dto::LinkInput,
        dto::AnswerInput,
    )),
    tags(
        (name = "auth"), (name = "projects"), (name = "tasks"), (name = "specs"),
        (name = "questions"), (name = "actors"), (name = "realtime"), (name = "ops")
    )
)]
pub struct ApiDoc;

pub fn json() -> String {
    ApiDoc::openapi()
        .to_pretty_json()
        .unwrap_or_else(|_| "{}".into())
}
