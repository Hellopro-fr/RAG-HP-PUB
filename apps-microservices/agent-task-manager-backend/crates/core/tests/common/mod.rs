//! Test harness for the decider: a task aggregate driven through `decide` + `apply`,
//! with invariants checked after every accepted command.
#![allow(dead_code)]

use atb_core::{
    AcRef, ActorKind, Caller, Command, Ctx, DomainError, DomainEvent, Id, LeaseKind, NewTask,
    ReviewGate, Role, TaskSnapshot, TaskState, TestGate, WorkflowConfig, apply_all, decide,
    decide_create, invariants,
};
use time::{Duration, OffsetDateTime, macros::datetime};
use uuid::Uuid;

pub const T0: OffsetDateTime = datetime!(2026-11-05 10:00:00 UTC);

pub fn agent(roles: &[Role], model: &str) -> Caller {
    Caller {
        id: Uuid::now_v7(),
        kind: ActorKind::Agent,
        roles: roles.to_vec(),
        model: Some(model.to_string()),
    }
}

pub fn implementer() -> Caller {
    agent(&[Role::Implementer], "model-a")
}

pub fn reviewer(model: &str) -> Caller {
    agent(&[Role::Reviewer], model)
}

pub fn human() -> Caller {
    Caller {
        id: Uuid::now_v7(),
        kind: ActorKind::Human,
        roles: vec![Role::Admin],
        model: None,
    }
}

pub fn system() -> Caller {
    Caller {
        id: Uuid::now_v7(),
        kind: ActorKind::System,
        roles: vec![],
        model: None,
    }
}

pub fn verifier() -> Caller {
    Caller {
        id: Uuid::now_v7(),
        kind: ActorKind::Verifier,
        roles: vec![],
        model: None,
    }
}

pub fn token() -> String {
    Uuid::now_v7().simple().to_string()
}

/// Workflow with every gate on.
pub fn gated() -> WorkflowConfig {
    WorkflowConfig {
        spec_gate: true,
        test_gate: TestGate::Command,
        review_gate: ReviewGate::AgentOrHuman,
        require_different_model: false,
        max_rejections: 3,
        lease_ttl_secs: 600,
        preferred_grace_secs: 120,
    }
}

pub struct World {
    pub task: TaskSnapshot,
    pub now: OffsetDateTime,
    pub wf: WorkflowConfig,
    pub blockers: Vec<TaskState>,
    pub approved: Option<i32>,
    pub acs: Vec<AcRef>,
    pub edges: Vec<(Id, Id)>,
}

impl World {
    /// A new task pinned to an approved spec version 1.
    pub fn new(wf: WorkflowConfig) -> Self {
        Self::with_approved(wf, Some(1))
    }

    pub fn with_approved(wf: WorkflowConfig, approved: Option<i32>) -> Self {
        let mut ctx = Ctx::new(T0, human(), wf.clone());
        ctx.approved_spec_version = approved;
        let new = NewTask {
            task_id: Uuid::now_v7(),
            project_id: Uuid::now_v7(),
            title: "Implement the thing".into(),
            spec_id: Uuid::now_v7(),
            spec_version: 1,
            parent_id: None,
            priority: 0,
            blocked_by: vec![],
            discovered_from: None,
        };
        let events = decide_create(&new, &ctx).expect("create");
        let task = atb_core::apply::create(&events[0]).expect("task.created");
        let task = apply_all(task, &events[1..]);
        invariants::check(&task).expect("invariants after create");
        Self {
            task,
            now: T0,
            wf,
            blockers: vec![],
            approved,
            acs: vec![
                AcRef {
                    id: "AC-1".into(),
                    human_only: false,
                },
                AcRef {
                    id: "AC-2".into(),
                    human_only: false,
                },
            ],
            edges: vec![],
        }
    }

    pub fn ctx(&self, caller: &Caller) -> Ctx {
        let mut ctx = Ctx::new(self.now, caller.clone(), self.wf.clone());
        ctx.blockers = self.blockers.clone();
        ctx.approved_spec_version = self.approved;
        ctx.acceptance_criteria = self.acs.clone();
        ctx.block_edges = self.edges.clone();
        ctx
    }

    /// Decide and, on success, apply the events and check invariants.
    pub fn run(&mut self, caller: &Caller, cmd: Command) -> Result<Vec<DomainEvent>, DomainError> {
        let events = decide(&self.task, &cmd, &self.ctx(caller))?;
        self.task = apply_all(self.task.clone(), &events);
        if let Err(why) = invariants::check(&self.task) {
            panic!(
                "invariant violated after {}: {why}\n{:#?}",
                cmd.name(),
                self.task
            );
        }
        Ok(events)
    }

    pub fn advance(&mut self, secs: i64) {
        self.now += Duration::seconds(secs);
    }

    pub fn state(&self) -> TaskState {
        self.task.state
    }

    /// Claim as `who`; returns the token hash.
    pub fn claim(&mut self, who: &Caller) -> String {
        let t = token();
        self.run(
            who,
            Command::Claim {
                kind: LeaseKind::Work,
                token_hash: t.clone(),
                attempt_id: Uuid::now_v7(),
            },
        )
        .expect("claim");
        t
    }

    pub fn submit(
        &mut self,
        who: &Caller,
        tok: &str,
        commit: &str,
    ) -> Result<Vec<DomainEvent>, DomainError> {
        self.run(
            who,
            Command::SubmitForTest {
                token_hash: Some(tok.to_string()),
                commit_sha: commit.into(),
                branch: Some("feature".into()),
                test_run_id: Uuid::now_v7(),
            },
        )
    }

    pub fn test_result(
        &mut self,
        passed: bool,
        violation: bool,
    ) -> Result<Vec<DomainEvent>, DomainError> {
        self.run(
            &verifier(),
            Command::CompleteTest {
                test_run_id: Uuid::now_v7(),
                passed,
                protected_path_violation: violation,
            },
        )
    }

    pub fn claim_review(&mut self, who: &Caller) -> Result<String, DomainError> {
        let t = token();
        self.run(
            who,
            Command::Claim {
                kind: LeaseKind::Review,
                token_hash: t.clone(),
                attempt_id: Uuid::now_v7(),
            },
        )?;
        Ok(t)
    }
}

pub fn types(events: &[DomainEvent]) -> Vec<&'static str> {
    events.iter().map(DomainEvent::event_type).collect()
}

pub fn guard_name(err: &DomainError) -> &'static str {
    match err {
        DomainError::GuardFailed { guard, .. } => guard,
        other => other.code(),
    }
}
