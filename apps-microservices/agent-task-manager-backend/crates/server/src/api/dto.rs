//! Request bodies and query strings of the REST API (responses are the service/repository read
//! models). All validated by serde + the service layer; unknown fields are rejected.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use utoipa::{IntoParams, ToSchema};
use uuid::Uuid;

use crate::service::commands::ClaimRole;

#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct LoginInput {
    pub login: String,
    pub password: String,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct MeView {
    pub id: Uuid,
    pub kind: String,
    pub name: String,
    pub roles: Vec<String>,
    pub model: Option<String>,
}

#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CreateProjectInput {
    pub name: String,
    /// Workflow config (§5). Defaults: every gate on, LEASE_TTL_SECS / PREFERRED_GRACE_SECS.
    #[schema(value_type = Option<Object>)]
    pub workflow: Option<Value>,
}

#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ClaimInput {
    pub role: ClaimRole,
    /// Omit to let the server pick the best claimable task.
    pub task_id: Option<Uuid>,
}

#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct TaskClaimInput {
    pub role: ClaimRole,
}

#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct LeaseInput {
    pub lease_token: Option<String>,
}

#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ReportInput {
    pub lease_token: Option<String>,
    /// thought | action | progress | assumption
    pub kind: String,
    /// At most 4 KB.
    pub body: String,
}

#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct AskInput {
    pub lease_token: Option<String>,
    pub question: String,
    pub blocking: bool,
    #[schema(value_type = Option<Object>)]
    pub options: Option<Value>,
    /// Required when blocking.
    pub handoff_note: Option<String>,
}

#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ReleaseInput {
    pub lease_token: Option<String>,
    pub handoff_note: String,
}

#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SubmitInput {
    pub lease_token: Option<String>,
    pub commit_sha: String,
    pub branch: Option<String>,
}

#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct RepinInput {
    pub lease_token: Option<String>,
    pub to_version: Option<i32>,
}

#[derive(Debug, Default, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CancelInput {
    pub reason: Option<String>,
}

#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PatchTaskInput {
    pub expected_version: i32,
    pub title: Option<String>,
    pub priority: Option<i32>,
}

#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct LinkInput {
    pub to_id: Uuid,
    /// blocks | discovered_from | related
    pub kind: String,
}

#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct AnswerInput {
    pub answer: String,
}

#[derive(Debug, Deserialize, IntoParams)]
#[into_params(parameter_in = Query)]
pub struct EventsQuery {
    /// Return events with seq > after.
    pub after: Option<i64>,
    pub limit: Option<i64>,
}

#[derive(Debug, Deserialize, IntoParams)]
#[into_params(parameter_in = Query)]
pub struct StreamQuery {
    /// Resume after this seq (alternative to the Last-Event-ID header).
    pub after: Option<i64>,
}

#[derive(Debug, Deserialize, IntoParams)]
#[into_params(parameter_in = Query)]
pub struct GlobalStreamQuery {
    /// Comma-separated: questions, reviews.
    pub topics: Option<String>,
}

#[derive(Debug, Deserialize, IntoParams)]
#[into_params(parameter_in = Query)]
pub struct QuestionsQuery {
    pub project_id: Option<Uuid>,
    /// open | answered | withdrawn
    pub status: Option<String>,
    pub limit: Option<i64>,
}

#[derive(Debug, Deserialize, IntoParams)]
#[into_params(parameter_in = Query)]
pub struct ReadyQuery {
    pub role: Option<ClaimRole>,
    pub limit: Option<i64>,
}

#[derive(Debug, Deserialize, IntoParams)]
#[into_params(parameter_in = Query)]
pub struct TimelineQuery {
    pub limit: Option<i64>,
}
