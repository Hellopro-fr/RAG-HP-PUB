//! Domain events (§3). Every payload is self-contained: replaying the log rebuilds every projection,
//! except the volatile timing fields (`leases.expires_at`, `leases.last_heartbeat_at`, `actors.last_seen_at`).

use serde::{Deserialize, Serialize};
use serde_json::Value;
use time::OffsetDateTime;

use crate::model::{
    ActivityKind, AttemptOutcome, CriterionVerdict, Id, LeaseKind, LinkKind, ReviewVerdict,
    TaskState, TokenHash,
};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AttemptStarted {
    pub attempt_id: Id,
    pub n: i32,
    pub actor_model: Option<String>,
}

/// Commit pushed by the implementer when the task leaves `working` without a test run.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Submission {
    pub commit_sha: String,
    pub branch: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", content = "payload")]
pub enum DomainEvent {
    #[serde(rename = "task.created")]
    TaskCreated {
        task_id: Id,
        project_id: Id,
        title: String,
        spec_id: Id,
        spec_version: i32,
        parent_id: Option<Id>,
        priority: i32,
        state: TaskState,
        created_by: Id,
    },
    #[serde(rename = "task.updated")]
    TaskUpdated {
        task_id: Id,
        title: Option<String>,
        priority: Option<i32>,
    },
    #[serde(rename = "task.state_changed")]
    TaskStateChanged {
        task_id: Id,
        from: TaskState,
        to: TaskState,
        preferred_actor_id: Option<Id>,
        #[serde(with = "time::serde::rfc3339::option")]
        preferred_until: Option<OffsetDateTime>,
        submission: Option<Submission>,
    },
    #[serde(rename = "task.link_added")]
    TaskLinkAdded {
        from_id: Id,
        to_id: Id,
        kind: LinkKind,
    },
    #[serde(rename = "task.spec_outdated")]
    TaskSpecOutdated { task_id: Id, approved_version: i32 },
    #[serde(rename = "task.repinned")]
    TaskRepinned { task_id: Id, spec_version: i32 },
    #[serde(rename = "spec.version_proposed")]
    SpecVersionProposed {
        spec_id: Id,
        project_id: Id,
        title: String,
        version: i32,
        body_md: String,
        acceptance_criteria: Value,
        protected_paths: Vec<String>,
        test_ref: Option<String>,
        author_id: Id,
    },
    #[serde(rename = "spec.version_approved")]
    SpecVersionApproved {
        spec_id: Id,
        version: i32,
        approved_by: Id,
        #[serde(with = "time::serde::rfc3339")]
        approved_at: OffsetDateTime,
    },
    #[serde(rename = "lease.claimed")]
    LeaseClaimed {
        task_id: Id,
        actor_id: Id,
        kind: LeaseKind,
        token_hash: TokenHash,
        /// Volatile: kept for replay convenience, excluded from rebuild comparison.
        #[serde(with = "time::serde::rfc3339")]
        expires_at: OffsetDateTime,
        attempt: Option<AttemptStarted>,
    },
    #[serde(rename = "lease.released")]
    LeaseReleased {
        task_id: Id,
        actor_id: Id,
        kind: LeaseKind,
    },
    #[serde(rename = "lease.expired")]
    LeaseExpired {
        task_id: Id,
        actor_id: Id,
        kind: LeaseKind,
        handoff_note: String,
    },
    #[serde(rename = "activity.reported")]
    ActivityReported {
        task_id: Id,
        actor_id: Id,
        kind: ActivityKind,
        body: String,
        trace_id: Option<String>,
    },
    #[serde(rename = "question.asked")]
    QuestionAsked {
        question_id: Id,
        task_id: Id,
        asked_by: Id,
        body: String,
        options: Option<Value>,
        blocking: bool,
    },
    #[serde(rename = "question.answered")]
    QuestionAnswered {
        question_id: Id,
        task_id: Id,
        answered_by: Id,
        answer: String,
        #[serde(with = "time::serde::rfc3339")]
        answered_at: OffsetDateTime,
    },
    #[serde(rename = "test.requested")]
    TestRequested {
        test_run_id: Id,
        task_id: Id,
        attempt_id: Id,
        commit_sha: String,
        branch: Option<String>,
    },
    #[serde(rename = "test.completed")]
    TestCompleted {
        test_run_id: Id,
        task_id: Id,
        passed: bool,
        protected_path_violation: bool,
        /// Volatile: new lease expiry when a failed run hands the task back to its holder.
        #[serde(with = "time::serde::rfc3339::option")]
        resume_expires_at: Option<OffsetDateTime>,
    },
    #[serde(rename = "review.submitted")]
    ReviewSubmitted {
        review_id: Id,
        task_id: Id,
        attempt_id: Id,
        reviewer_id: Id,
        commit_sha: String,
        verdict: ReviewVerdict,
        per_criterion: Vec<CriterionVerdict>,
        comment: Option<String>,
    },
    #[serde(rename = "attempt.ended")]
    AttemptEnded {
        attempt_id: Id,
        task_id: Id,
        outcome: AttemptOutcome,
        handoff_note: Option<String>,
    },
}

impl DomainEvent {
    /// The `type` string stored in `events.type` and sent as the SSE `event:` field.
    pub fn event_type(&self) -> &'static str {
        match self {
            DomainEvent::TaskCreated { .. } => "task.created",
            DomainEvent::TaskUpdated { .. } => "task.updated",
            DomainEvent::TaskStateChanged { .. } => "task.state_changed",
            DomainEvent::TaskLinkAdded { .. } => "task.link_added",
            DomainEvent::TaskSpecOutdated { .. } => "task.spec_outdated",
            DomainEvent::TaskRepinned { .. } => "task.repinned",
            DomainEvent::SpecVersionProposed { .. } => "spec.version_proposed",
            DomainEvent::SpecVersionApproved { .. } => "spec.version_approved",
            DomainEvent::LeaseClaimed { .. } => "lease.claimed",
            DomainEvent::LeaseReleased { .. } => "lease.released",
            DomainEvent::LeaseExpired { .. } => "lease.expired",
            DomainEvent::ActivityReported { .. } => "activity.reported",
            DomainEvent::QuestionAsked { .. } => "question.asked",
            DomainEvent::QuestionAnswered { .. } => "question.answered",
            DomainEvent::TestRequested { .. } => "test.requested",
            DomainEvent::TestCompleted { .. } => "test.completed",
            DomainEvent::ReviewSubmitted { .. } => "review.submitted",
            DomainEvent::AttemptEnded { .. } => "attempt.ended",
        }
    }

    /// The task this event belongs to, if any (`events.task_id`).
    pub fn task_id(&self) -> Option<Id> {
        match self {
            DomainEvent::TaskCreated { task_id, .. }
            | DomainEvent::TaskUpdated { task_id, .. }
            | DomainEvent::TaskStateChanged { task_id, .. }
            | DomainEvent::TaskSpecOutdated { task_id, .. }
            | DomainEvent::TaskRepinned { task_id, .. }
            | DomainEvent::LeaseClaimed { task_id, .. }
            | DomainEvent::LeaseReleased { task_id, .. }
            | DomainEvent::LeaseExpired { task_id, .. }
            | DomainEvent::ActivityReported { task_id, .. }
            | DomainEvent::QuestionAsked { task_id, .. }
            | DomainEvent::QuestionAnswered { task_id, .. }
            | DomainEvent::TestRequested { task_id, .. }
            | DomainEvent::TestCompleted { task_id, .. }
            | DomainEvent::ReviewSubmitted { task_id, .. }
            | DomainEvent::AttemptEnded { task_id, .. } => Some(*task_id),
            DomainEvent::TaskLinkAdded { to_id, .. } => Some(*to_id),
            DomainEvent::SpecVersionProposed { .. } | DomainEvent::SpecVersionApproved { .. } => {
                None
            }
        }
    }

    /// Payload JSON only (without the `type` tag), as stored in `events.payload`.
    pub fn payload(&self) -> Value {
        match serde_json::to_value(self) {
            Ok(Value::Object(mut map)) => map.remove("payload").unwrap_or(Value::Null),
            _ => Value::Null,
        }
    }

    /// Rebuild an event from the stored `type` + `payload` columns.
    pub fn from_stored(event_type: &str, payload: Value) -> Result<Self, serde_json::Error> {
        serde_json::from_value(serde_json::json!({ "type": event_type, "payload": payload }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    #[test]
    fn stored_round_trip_keeps_type_and_payload() {
        let ev = DomainEvent::LeaseReleased {
            task_id: Uuid::now_v7(),
            actor_id: Uuid::now_v7(),
            kind: LeaseKind::Work,
        };
        let back = DomainEvent::from_stored(ev.event_type(), ev.payload()).unwrap();
        assert_eq!(back, ev);
        assert_eq!(ev.payload()["kind"], "work");
    }
}
