//! Domain vocabulary shared by the decider, the projector and the API layer.

use serde::{Deserialize, Serialize};
use time::OffsetDateTime;
use uuid::Uuid;

pub type Id = Uuid;

/// Hex-encoded SHA-256 of a lease token. The raw token never enters the domain or the event log.
pub type TokenHash = String;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TaskState {
    Draft,
    Ready,
    Working,
    InputRequired,
    Testing,
    InReview,
    Done,
    Failed,
    Cancelled,
}

impl TaskState {
    pub const ALL: [TaskState; 9] = [
        TaskState::Draft,
        TaskState::Ready,
        TaskState::Working,
        TaskState::InputRequired,
        TaskState::Testing,
        TaskState::InReview,
        TaskState::Done,
        TaskState::Failed,
        TaskState::Cancelled,
    ];

    pub fn is_terminal(self) -> bool {
        matches!(
            self,
            TaskState::Done | TaskState::Failed | TaskState::Cancelled
        )
    }

    pub fn as_str(self) -> &'static str {
        match self {
            TaskState::Draft => "draft",
            TaskState::Ready => "ready",
            TaskState::Working => "working",
            TaskState::InputRequired => "input_required",
            TaskState::Testing => "testing",
            TaskState::InReview => "in_review",
            TaskState::Done => "done",
            TaskState::Failed => "failed",
            TaskState::Cancelled => "cancelled",
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        Self::ALL.into_iter().find(|st| st.as_str() == s)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ActorKind {
    Agent,
    Human,
    Verifier,
    System,
}

impl ActorKind {
    pub fn as_str(self) -> &'static str {
        match self {
            ActorKind::Agent => "agent",
            ActorKind::Human => "human",
            ActorKind::Verifier => "verifier",
            ActorKind::System => "system",
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        [Self::Agent, Self::Human, Self::Verifier, Self::System]
            .into_iter()
            .find(|k| k.as_str() == s)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Role {
    Admin,
    Planner,
    Implementer,
    Reviewer,
}

impl Role {
    pub fn as_str(self) -> &'static str {
        match self {
            Role::Admin => "admin",
            Role::Planner => "planner",
            Role::Implementer => "implementer",
            Role::Reviewer => "reviewer",
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        [
            Self::Admin,
            Self::Planner,
            Self::Implementer,
            Self::Reviewer,
        ]
        .into_iter()
        .find(|r| r.as_str() == s)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum LeaseKind {
    Work,
    Review,
}

impl LeaseKind {
    pub fn as_str(self) -> &'static str {
        match self {
            LeaseKind::Work => "work",
            LeaseKind::Review => "review",
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "work" => Some(Self::Work),
            "review" => Some(Self::Review),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum LinkKind {
    Blocks,
    DiscoveredFrom,
    Related,
}

impl LinkKind {
    pub fn as_str(self) -> &'static str {
        match self {
            LinkKind::Blocks => "blocks",
            LinkKind::DiscoveredFrom => "discovered_from",
            LinkKind::Related => "related",
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "blocks" => Some(Self::Blocks),
            "discovered_from" => Some(Self::DiscoveredFrom),
            "related" => Some(Self::Related),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AttemptOutcome {
    Released,
    Expired,
    Rejected,
    Approved,
}

impl AttemptOutcome {
    pub fn as_str(self) -> &'static str {
        match self {
            AttemptOutcome::Released => "released",
            AttemptOutcome::Expired => "expired",
            AttemptOutcome::Rejected => "rejected",
            AttemptOutcome::Approved => "approved",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ActivityKind {
    Thought,
    Action,
    Progress,
    Assumption,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ReviewVerdict {
    Approved,
    ChangesRequested,
}

/// Who is issuing a command.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Caller {
    pub id: Id,
    pub kind: ActorKind,
    pub roles: Vec<Role>,
    pub model: Option<String>,
}

impl Caller {
    pub fn has_role(&self, role: Role) -> bool {
        self.roles.contains(&role) || self.roles.contains(&Role::Admin)
    }

    pub fn is_human(&self) -> bool {
        self.kind == ActorKind::Human
    }
}

/// Current lease on a task. `expires_at` is a volatile timing field (excluded from rebuild checks).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Lease {
    pub actor_id: Id,
    pub kind: LeaseKind,
    pub token_hash: TokenHash,
    #[serde(with = "time::serde::rfc3339")]
    pub expires_at: OffsetDateTime,
    pub paused: bool,
}

/// The task's open (not yet ended) attempt, if any.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Attempt {
    pub id: Id,
    pub n: i32,
    pub actor_id: Id,
    pub actor_model: Option<String>,
    pub commit_sha: Option<String>,
    pub branch: Option<String>,
}

/// The task aggregate the decider reasons about: the task row plus its lease and open attempt.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TaskSnapshot {
    pub id: Id,
    pub project_id: Id,
    pub title: String,
    pub priority: i32,
    pub state: TaskState,
    pub version: i32,
    pub spec_id: Id,
    pub spec_version: i32,
    pub spec_outdated: bool,
    pub preferred_actor_id: Option<Id>,
    #[serde(with = "time::serde::rfc3339::option")]
    pub preferred_until: Option<OffsetDateTime>,
    pub attempt_count: i32,
    pub rejection_count: i32,
    pub lease: Option<Lease>,
    pub attempt: Option<Attempt>,
}

/// A reference to an acceptance criterion of the pinned spec version.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AcRef {
    pub id: String,
    /// `verify.kind == human`: only a human may pass it.
    pub human_only: bool,
}

/// A question as seen by the task decider when it is answered.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct QuestionRef {
    pub id: Id,
    pub asked_by: Id,
    pub blocking: bool,
    pub open: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CriterionVerdict {
    pub ac_id: String,
    pub pass: bool,
    #[serde(default)]
    pub note: Option<String>,
}
