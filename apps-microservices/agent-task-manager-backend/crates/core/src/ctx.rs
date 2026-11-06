//! Decision context: everything the decider needs besides the task aggregate itself.

use time::OffsetDateTime;

use crate::model::{AcRef, Caller, Id, TaskState};
use crate::workflow::WorkflowConfig;

#[derive(Debug, Clone, PartialEq)]
pub struct Ctx {
    pub now: OffsetDateTime,
    pub caller: Caller,
    pub workflow: WorkflowConfig,
    /// States of the tasks that `block` this one.
    pub blockers: Vec<TaskState>,
    /// The approved version of the task's spec, if any.
    pub approved_spec_version: Option<i32>,
    /// Acceptance criteria of the pinned spec version (review checks).
    pub acceptance_criteria: Vec<AcRef>,
    /// Existing `blocks` edges of the project (cycle check).
    pub block_edges: Vec<(Id, Id)>,
    /// Actor id used as `asked_by` for system-opened questions.
    pub system_actor_id: Id,
}

impl Ctx {
    pub fn new(now: OffsetDateTime, caller: Caller, workflow: WorkflowConfig) -> Self {
        let system_actor_id = caller.id;
        Self {
            now,
            caller,
            workflow,
            blockers: Vec::new(),
            approved_spec_version: None,
            acceptance_criteria: Vec::new(),
            block_edges: Vec::new(),
            system_actor_id,
        }
    }
}
