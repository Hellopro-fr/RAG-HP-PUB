//! The decider: the §4 state machine as a pure function.
//!
//! `decide` validates a command against the aggregate and the context and returns the events to
//! persist. It never mutates anything; the caller applies the events with [`crate::apply`].

use std::collections::HashSet;

use time::{Duration, OffsetDateTime};

use crate::command::{Command, MAX_REPORT_BYTES, NewTask};
use crate::ctx::Ctx;
use crate::error::DomainError;
use crate::event::{AttemptStarted, DomainEvent, Submission};
use crate::graph::would_create_cycle;
use crate::model::{
    ActorKind, AttemptOutcome, Id, Lease, LeaseKind, LinkKind, ReviewVerdict, Role, TaskSnapshot,
    TaskState,
};
use crate::workflow::{ReviewGate, TestGate};

type Decision = Result<Vec<DomainEvent>, DomainError>;

const MAX_TITLE_CHARS: usize = 500;
const MAX_NOTE_BYTES: usize = 16 * 1024;

/// Decide the events for a new task (§4: it starts in `ready` if its pinned spec version is
/// approved or `spec_gate` is off, otherwise in `draft`).
pub fn decide_create(new: &NewTask, ctx: &Ctx) -> Decision {
    forbid_kind(ctx, ActorKind::Verifier, "verifiers cannot create tasks")?;
    validate_title(&new.title)?;
    if new.spec_version < 1 {
        return Err(DomainError::invalid(
            "spec_version",
            "spec_version starts at 1",
        ));
    }
    if let Some(approved) = ctx.approved_spec_version
        && new.spec_version < approved
    {
        return Err(DomainError::guard(
            "spec_version_superseded",
            format!(
                "version {} is superseded; pin version {approved}",
                new.spec_version
            ),
        ));
    }
    let pinned_approved = ctx.approved_spec_version == Some(new.spec_version);
    let state = if pinned_approved || !ctx.workflow.spec_gate {
        TaskState::Ready
    } else {
        TaskState::Draft
    };
    let mut events = vec![DomainEvent::TaskCreated {
        task_id: new.task_id,
        project_id: new.project_id,
        title: new.title.trim().to_string(),
        spec_id: new.spec_id,
        spec_version: new.spec_version,
        parent_id: new.parent_id,
        priority: new.priority,
        state,
        created_by: ctx.caller.id,
    }];
    let mut seen = HashSet::new();
    for blocker in &new.blocked_by {
        if *blocker == new.task_id {
            return Err(DomainError::guard("cycle", "a task cannot block itself"));
        }
        if seen.insert(*blocker) {
            events.push(DomainEvent::TaskLinkAdded {
                from_id: *blocker,
                to_id: new.task_id,
                kind: LinkKind::Blocks,
            });
        }
    }
    if let Some(origin) = new.discovered_from {
        events.push(DomainEvent::TaskLinkAdded {
            from_id: new.task_id,
            to_id: origin,
            kind: LinkKind::DiscoveredFrom,
        });
    }
    Ok(events)
}

/// Decide the events for `cmd` on `task`.
pub fn decide(task: &TaskSnapshot, cmd: &Command, ctx: &Ctx) -> Decision {
    match cmd {
        Command::Claim {
            kind: LeaseKind::Work,
            token_hash,
            attempt_id,
        } => claim_work(task, ctx, token_hash, *attempt_id),
        Command::Claim {
            kind: LeaseKind::Review,
            token_hash,
            ..
        } => claim_review(task, ctx, token_hash),
        Command::Heartbeat { token_hash } => {
            leased_state(task, ctx, token_hash.as_deref(), "heartbeat")?;
            // Heartbeats only refresh timing fields; they are not events (§3).
            Ok(Vec::new())
        }
        Command::Report {
            token_hash,
            kind,
            body,
            trace_id,
        } => {
            leased_state(task, ctx, token_hash.as_deref(), "report")?;
            validate_body("body", body)?;
            Ok(vec![DomainEvent::ActivityReported {
                task_id: task.id,
                actor_id: ctx.caller.id,
                kind: *kind,
                body: body.clone(),
                trace_id: trace_id.clone(),
            }])
        }
        Command::Ask {
            token_hash,
            question_id,
            body,
            blocking,
            options,
            handoff_note,
        } => {
            check_lease(task, ctx, token_hash.as_deref(), LeaseKind::Work)?;
            require_state(task, TaskState::Working, "ask")?;
            validate_body("question", body)?;
            let note = if *blocking {
                Some(require_note(handoff_note.as_deref())?)
            } else {
                None
            };
            let mut events = vec![DomainEvent::QuestionAsked {
                question_id: *question_id,
                task_id: task.id,
                asked_by: ctx.caller.id,
                body: body.clone(),
                options: options.clone(),
                blocking: *blocking,
            }];
            if *blocking {
                events.extend(end_work(task, AttemptOutcome::Released, note));
                events.push(state_change(task, TaskState::InputRequired));
            }
            Ok(events)
        }
        Command::Answer { question, answer } => {
            if !question.open {
                return Err(DomainError::guard(
                    "question_not_open",
                    "this question is already answered or withdrawn",
                ));
            }
            if question.asked_by == ctx.caller.id {
                return Err(DomainError::Forbidden(
                    "the asker cannot answer its own question".into(),
                ));
            }
            validate_body("answer", answer)?;
            let mut events = vec![DomainEvent::QuestionAnswered {
                question_id: question.id,
                task_id: task.id,
                answered_by: ctx.caller.id,
                answer: answer.clone(),
                answered_at: ctx.now,
            }];
            if question.blocking && task.state == TaskState::InputRequired {
                events.push(DomainEvent::TaskStateChanged {
                    task_id: task.id,
                    from: task.state,
                    to: TaskState::Ready,
                    preferred_actor_id: Some(question.asked_by),
                    preferred_until: Some(grace_until(ctx)),
                    submission: None,
                });
            }
            Ok(events)
        }
        Command::Release {
            token_hash,
            handoff_note,
        } => {
            check_lease(task, ctx, token_hash.as_deref(), LeaseKind::Work)?;
            require_state(task, TaskState::Working, "release")?;
            let note = require_note(Some(handoff_note))?;
            let mut events = end_work(task, AttemptOutcome::Released, Some(note));
            events.push(state_change(task, TaskState::Ready));
            Ok(events)
        }
        Command::ExpireLease => expire_lease(task, ctx),
        Command::SubmitForTest {
            token_hash,
            commit_sha,
            branch,
            test_run_id,
        } => submit_for_test(
            task,
            ctx,
            token_hash.as_deref(),
            commit_sha,
            branch,
            *test_run_id,
        ),
        Command::CompleteTest {
            test_run_id,
            passed,
            protected_path_violation,
        } => complete_test(task, ctx, *test_run_id, *passed, *protected_path_violation),
        Command::SubmitReview { .. } => submit_review(task, cmd, ctx),
        Command::SpecApproved { version } => spec_approved(task, ctx, *version),
        Command::Repin {
            token_hash,
            to_version,
        } => repin(task, ctx, token_hash.as_deref(), *to_version),
        Command::Cancel { reason } => cancel(task, ctx, reason.as_deref()),
        Command::Update {
            expected_version,
            title,
            priority,
        } => {
            if !(ctx.caller.is_human() || ctx.caller.has_role(Role::Planner)) {
                return Err(DomainError::Forbidden(
                    "only humans and planners can edit tasks".into(),
                ));
            }
            if *expected_version != task.version {
                return Err(DomainError::VersionConflict {
                    expected: *expected_version,
                    current: task.version,
                });
            }
            if title.is_none() && priority.is_none() {
                return Err(DomainError::invalid("patch", "nothing to update"));
            }
            if let Some(t) = title {
                validate_title(t)?;
            }
            Ok(vec![DomainEvent::TaskUpdated {
                task_id: task.id,
                title: title.as_ref().map(|t| t.trim().to_string()),
                priority: *priority,
            }])
        }
        Command::AddLink { to, kind } => {
            forbid_kind(ctx, ActorKind::Verifier, "verifiers cannot link tasks")?;
            if task.id == *to {
                return Err(DomainError::guard("cycle", "a task cannot link to itself"));
            }
            if *kind == LinkKind::Blocks && would_create_cycle(&ctx.block_edges, task.id, *to) {
                return Err(DomainError::guard(
                    "cycle",
                    "this blocks link would create a cycle",
                ));
            }
            Ok(vec![DomainEvent::TaskLinkAdded {
                from_id: task.id,
                to_id: *to,
                kind: *kind,
            }])
        }
    }
}

// ---------------------------------------------------------------------------------------------
// Rows of the §4 table
// ---------------------------------------------------------------------------------------------

/// ready --claim (implementer)--> working (new attempt, work lease)
fn claim_work(task: &TaskSnapshot, ctx: &Ctx, token_hash: &str, attempt_id: Id) -> Decision {
    if !ctx.caller.has_role(Role::Implementer) {
        return Err(DomainError::Forbidden(
            "claiming work needs the implementer role".into(),
        ));
    }
    if task.state != TaskState::Ready {
        return Err(state_guard(task, "claim"));
    }
    if task.spec_outdated {
        return Err(DomainError::guard(
            "spec_outdated",
            "the pinned spec version is outdated; call repin first",
        ));
    }
    if ctx.blockers.iter().any(|s| *s != TaskState::Done) {
        return Err(DomainError::guard(
            "blocked",
            "a blocking task is not done yet; pick another task",
        ));
    }
    if task.lease.is_some() {
        return Err(DomainError::guard(
            "already_leased",
            "the task already has a lease",
        ));
    }
    if let (Some(pref), Some(until)) = (task.preferred_actor_id, task.preferred_until)
        && pref != ctx.caller.id
        && until > ctx.now
    {
        return Err(DomainError::guard(
            "preferred_actor",
            format!("reserved for actor {pref} until {until}; pick another task"),
        ));
    }
    Ok(vec![
        DomainEvent::TaskStateChanged {
            task_id: task.id,
            from: task.state,
            to: TaskState::Working,
            preferred_actor_id: None,
            preferred_until: None,
            submission: None,
        },
        DomainEvent::LeaseClaimed {
            task_id: task.id,
            actor_id: ctx.caller.id,
            kind: LeaseKind::Work,
            token_hash: token_hash.to_string(),
            expires_at: lease_expiry(ctx),
            attempt: Some(AttemptStarted {
                attempt_id,
                n: task.attempt_count + 1,
                actor_model: ctx.caller.model.clone(),
            }),
        },
    ])
}

/// in_review --claim (reviewer)--> in_review (review lease)
fn claim_review(task: &TaskSnapshot, ctx: &Ctx, token_hash: &str) -> Decision {
    if ctx.workflow.review_gate == ReviewGate::None {
        return Err(DomainError::guard(
            "no_review_gate",
            "this project has no review gate",
        ));
    }
    if !ctx.caller.has_role(Role::Reviewer) {
        return Err(DomainError::Forbidden(
            "reviewing needs the reviewer role".into(),
        ));
    }
    if ctx.workflow.review_gate == ReviewGate::HumanOnly && !ctx.caller.is_human() {
        return Err(DomainError::Forbidden(
            "this project requires human reviews".into(),
        ));
    }
    if task.state != TaskState::InReview {
        return Err(state_guard(task, "claim (reviewer)"));
    }
    if task.lease.is_some() {
        return Err(DomainError::guard(
            "already_leased",
            "another reviewer holds this review",
        ));
    }
    let attempt = task
        .attempt
        .as_ref()
        .ok_or_else(|| DomainError::guard("no_attempt", "the task has no attempt to review"))?;
    if attempt.actor_id == ctx.caller.id {
        return Err(DomainError::guard(
            "self_review",
            "the implementer of the attempt cannot review it",
        ));
    }
    if ctx.workflow.require_different_model && !ctx.caller.is_human() {
        let different = match (&ctx.caller.model, &attempt.actor_model) {
            (Some(a), Some(b)) => a != b,
            _ => false,
        };
        if !different {
            return Err(DomainError::guard(
                "same_model",
                "this project requires a reviewer on a different, declared model",
            ));
        }
    }
    Ok(vec![DomainEvent::LeaseClaimed {
        task_id: task.id,
        actor_id: ctx.caller.id,
        kind: LeaseKind::Review,
        token_hash: token_hash.to_string(),
        expires_at: lease_expiry(ctx),
        attempt: None,
    }])
}

/// working --lease expired--> ready ; in_review --review lease expired--> in_review
fn expire_lease(task: &TaskSnapshot, ctx: &Ctx) -> Decision {
    if ctx.caller.kind != ActorKind::System {
        return Err(DomainError::Forbidden(
            "only the sweeper expires leases".into(),
        ));
    }
    let lease = task
        .lease
        .as_ref()
        .ok_or_else(|| DomainError::guard("no_lease", "the task has no lease"))?;
    if lease.paused || lease.expires_at > ctx.now {
        return Err(DomainError::guard(
            "lease_not_expired",
            "the lease is still valid",
        ));
    }
    match (lease.kind, task.state) {
        (LeaseKind::Work, TaskState::Working) => {
            let n = task
                .attempt
                .as_ref()
                .map(|a| a.n)
                .unwrap_or(task.attempt_count);
            let note = format!(
                "Automatic handoff: the lease expired at {} without a heartbeat, so attempt #{n} \
                 by actor {} was ended. Read its reported activities before continuing.",
                lease.expires_at, lease.actor_id
            );
            let mut events = vec![DomainEvent::LeaseExpired {
                task_id: task.id,
                actor_id: lease.actor_id,
                kind: lease.kind,
                handoff_note: note.clone(),
            }];
            if let Some(att) = &task.attempt {
                events.push(DomainEvent::AttemptEnded {
                    attempt_id: att.id,
                    task_id: task.id,
                    outcome: AttemptOutcome::Expired,
                    handoff_note: Some(note),
                });
            }
            events.push(state_change(task, TaskState::Ready));
            Ok(events)
        }
        (LeaseKind::Review, TaskState::InReview) => Ok(vec![DomainEvent::LeaseExpired {
            task_id: task.id,
            actor_id: lease.actor_id,
            kind: lease.kind,
            handoff_note: "The review lease expired; the review is unclaimed again.".into(),
        }]),
        _ => Err(state_guard(task, "expire lease")),
    }
}

/// working --submit_for_test--> testing (lease paused, test run queued); skips disabled gates.
fn submit_for_test(
    task: &TaskSnapshot,
    ctx: &Ctx,
    token_hash: Option<&str>,
    commit_sha: &str,
    branch: &Option<String>,
    test_run_id: Id,
) -> Decision {
    let lease = check_lease(task, ctx, token_hash, LeaseKind::Work)?;
    require_state(task, TaskState::Working, "submit_for_test")?;
    let commit = commit_sha.trim();
    if commit.is_empty() || commit.len() > 64 {
        return Err(DomainError::invalid(
            "commit_sha",
            "commit_sha is required (max 64 characters)",
        ));
    }
    if task.spec_outdated {
        return Err(DomainError::guard(
            "spec_outdated",
            "the pinned spec version is outdated; call repin before submitting",
        ));
    }
    let attempt = task
        .attempt
        .as_ref()
        .ok_or_else(|| DomainError::guard("no_attempt", "no open attempt"))?;
    match ctx.workflow.test_gate {
        TestGate::Command | TestGate::Human => Ok(vec![
            DomainEvent::TestRequested {
                test_run_id,
                task_id: task.id,
                attempt_id: attempt.id,
                commit_sha: commit.to_string(),
                branch: branch.clone(),
            },
            state_change(task, TaskState::Testing),
        ]),
        TestGate::None => {
            let to = if ctx.workflow.review_gate == ReviewGate::None {
                TaskState::Done
            } else {
                TaskState::InReview
            };
            let mut events = vec![
                DomainEvent::TaskStateChanged {
                    task_id: task.id,
                    from: task.state,
                    to,
                    preferred_actor_id: None,
                    preferred_until: None,
                    submission: Some(Submission {
                        commit_sha: commit.to_string(),
                        branch: branch.clone(),
                    }),
                },
                DomainEvent::LeaseReleased {
                    task_id: task.id,
                    actor_id: lease.actor_id,
                    kind: lease.kind,
                },
            ];
            if to == TaskState::Done {
                events.push(DomainEvent::AttemptEnded {
                    attempt_id: attempt.id,
                    task_id: task.id,
                    outcome: AttemptOutcome::Approved,
                    handoff_note: None,
                });
            }
            Ok(events)
        }
    }
}

/// testing --passed--> in_review (work lease released) ; testing --failed--> working (same holder)
fn complete_test(
    task: &TaskSnapshot,
    ctx: &Ctx,
    test_run_id: Id,
    passed: bool,
    violation: bool,
) -> Decision {
    match ctx.workflow.test_gate {
        TestGate::None => {
            return Err(DomainError::guard(
                "no_test_gate",
                "this project has no test gate",
            ));
        }
        TestGate::Command if ctx.caller.kind != ActorKind::Verifier => {
            return Err(DomainError::Forbidden(
                "only the verifier reports command test results".into(),
            ));
        }
        TestGate::Human if !ctx.caller.is_human() => {
            return Err(DomainError::Forbidden(
                "this project requires a human check".into(),
            ));
        }
        _ => {}
    }
    require_state(task, TaskState::Testing, "complete test")?;
    let lease = task
        .lease
        .as_ref()
        .ok_or_else(|| DomainError::guard("no_lease", "testing task without a lease"))?;
    if !passed || violation {
        return Ok(vec![
            DomainEvent::TestCompleted {
                test_run_id,
                task_id: task.id,
                passed: false,
                protected_path_violation: violation,
                resume_expires_at: Some(lease_expiry(ctx)),
            },
            state_change(task, TaskState::Working),
        ]);
    }
    let mut events = vec![
        DomainEvent::TestCompleted {
            test_run_id,
            task_id: task.id,
            passed: true,
            protected_path_violation: false,
            resume_expires_at: None,
        },
        DomainEvent::LeaseReleased {
            task_id: task.id,
            actor_id: lease.actor_id,
            kind: lease.kind,
        },
    ];
    if ctx.workflow.review_gate == ReviewGate::None {
        if let Some(att) = &task.attempt {
            events.push(DomainEvent::AttemptEnded {
                attempt_id: att.id,
                task_id: task.id,
                outcome: AttemptOutcome::Approved,
                handoff_note: None,
            });
        }
        events.push(state_change(task, TaskState::Done));
    } else {
        events.push(state_change(task, TaskState::InReview));
    }
    Ok(events)
}

/// in_review --submit_review--> done | ready (preference for the implementer) | failed
fn submit_review(task: &TaskSnapshot, cmd: &Command, ctx: &Ctx) -> Decision {
    let Command::SubmitReview {
        token_hash,
        review_id,
        commit_sha,
        verdict,
        per_criterion,
        comment,
        failure_question_id,
        failure_summary,
    } = cmd
    else {
        return Err(DomainError::invalid("command", "expected submit_review"));
    };
    let lease = check_lease(task, ctx, token_hash.as_deref(), LeaseKind::Review)?;
    require_state(task, TaskState::InReview, "submit_review")?;
    let attempt = task
        .attempt
        .as_ref()
        .ok_or_else(|| DomainError::guard("no_attempt", "no attempt to review"))?;
    let commit = commit_sha.trim();
    if attempt.commit_sha.as_deref() != Some(commit) {
        return Err(DomainError::guard(
            "commit_mismatch",
            format!(
                "review the attempt's commit {}",
                attempt.commit_sha.as_deref().unwrap_or("(none)")
            ),
        ));
    }
    let mut seen = HashSet::new();
    for v in per_criterion {
        if !seen.insert(v.ac_id.as_str()) {
            return Err(DomainError::invalid(
                "per_criterion",
                format!("duplicate verdict for {}", v.ac_id),
            ));
        }
        let Some(ac) = ctx.acceptance_criteria.iter().find(|a| a.id == v.ac_id) else {
            return Err(DomainError::invalid(
                "per_criterion",
                format!("unknown acceptance criterion {}", v.ac_id),
            ));
        };
        if ac.human_only && v.pass && !ctx.caller.is_human() {
            return Err(DomainError::Forbidden(format!(
                "{} can only be passed by a human",
                ac.id
            )));
        }
    }
    let missing: Vec<&str> = ctx
        .acceptance_criteria
        .iter()
        .filter(|a| !seen.contains(a.id.as_str()))
        .map(|a| a.id.as_str())
        .collect();
    if !missing.is_empty() {
        return Err(DomainError::guard(
            "missing_verdict",
            format!(
                "give a verdict for every acceptance criterion; missing: {}",
                missing.join(", ")
            ),
        ));
    }
    if *verdict == ReviewVerdict::Approved && !per_criterion.iter().all(|v| v.pass) {
        return Err(DomainError::guard(
            "approval_needs_all_pass",
            "approve only when every criterion passes; otherwise request changes",
        ));
    }
    let mut events = vec![
        DomainEvent::ReviewSubmitted {
            review_id: *review_id,
            task_id: task.id,
            attempt_id: attempt.id,
            reviewer_id: ctx.caller.id,
            commit_sha: commit.to_string(),
            verdict: *verdict,
            per_criterion: per_criterion.clone(),
            comment: comment.clone(),
        },
        DomainEvent::LeaseReleased {
            task_id: task.id,
            actor_id: lease.actor_id,
            kind: lease.kind,
        },
    ];
    match verdict {
        ReviewVerdict::Approved => {
            events.push(DomainEvent::AttemptEnded {
                attempt_id: attempt.id,
                task_id: task.id,
                outcome: AttemptOutcome::Approved,
                handoff_note: None,
            });
            events.push(state_change(task, TaskState::Done));
        }
        ReviewVerdict::ChangesRequested => {
            events.push(DomainEvent::AttemptEnded {
                attempt_id: attempt.id,
                task_id: task.id,
                outcome: AttemptOutcome::Rejected,
                handoff_note: comment.clone(),
            });
            if task.rejection_count + 1 >= ctx.workflow.max_rejections {
                events.push(state_change(task, TaskState::Failed));
                events.push(DomainEvent::QuestionAsked {
                    question_id: *failure_question_id,
                    task_id: task.id,
                    asked_by: ctx.system_actor_id,
                    body: failure_summary.clone(),
                    options: None,
                    blocking: false,
                });
            } else {
                events.push(DomainEvent::TaskStateChanged {
                    task_id: task.id,
                    from: task.state,
                    to: TaskState::Ready,
                    preferred_actor_id: Some(attempt.actor_id),
                    preferred_until: Some(grace_until(ctx)),
                    submission: None,
                });
            }
        }
    }
    Ok(events)
}

/// draft --spec version approved--> ready ; older-pinned non-terminal tasks get spec_outdated.
fn spec_approved(task: &TaskSnapshot, ctx: &Ctx, version: i32) -> Decision {
    if !(ctx.caller.is_human() || ctx.caller.kind == ActorKind::System) {
        return Err(DomainError::Forbidden("spec approval is human-only".into()));
    }
    if task.state.is_terminal() {
        return Ok(Vec::new());
    }
    if task.spec_version == version {
        if task.state == TaskState::Draft {
            return Ok(vec![state_change(task, TaskState::Ready)]);
        }
        return Ok(Vec::new());
    }
    if task.spec_version < version && !task.spec_outdated {
        return Ok(vec![DomainEvent::TaskSpecOutdated {
            task_id: task.id,
            approved_version: version,
        }]);
    }
    Ok(Vec::new())
}

/// repin: an explicit, recorded move to the approved spec version.
fn repin(task: &TaskSnapshot, ctx: &Ctx, token_hash: Option<&str>, to_version: i32) -> Decision {
    if task.state.is_terminal() {
        return Err(state_guard(task, "repin"));
    }
    if !task.spec_outdated {
        return Err(DomainError::guard(
            "not_outdated",
            "the task is not spec_outdated; nothing to repin",
        ));
    }
    if ctx.approved_spec_version != Some(to_version) {
        let approved = ctx
            .approved_spec_version
            .map(|v| v.to_string())
            .unwrap_or_else(|| "none".into());
        return Err(DomainError::guard(
            "repin_target",
            format!("repin only to the approved version ({approved})"),
        ));
    }
    if task.lease.is_some() {
        check_lease_any(task, ctx, token_hash)?;
    } else if !(ctx.caller.is_human() || ctx.caller.has_role(Role::Planner)) {
        return Err(DomainError::Forbidden(
            "repinning an unleased task needs a human or a planner".into(),
        ));
    }
    let mut events = vec![DomainEvent::TaskRepinned {
        task_id: task.id,
        spec_version: to_version,
    }];
    if task.state == TaskState::Draft {
        events.push(state_change(task, TaskState::Ready));
    }
    Ok(events)
}

/// any non-terminal --cancel (human)--> cancelled
fn cancel(task: &TaskSnapshot, ctx: &Ctx, reason: Option<&str>) -> Decision {
    if !ctx.caller.is_human() {
        return Err(DomainError::Forbidden("cancellation is human-only".into()));
    }
    if task.state.is_terminal() {
        return Err(state_guard(task, "cancel"));
    }
    let note = reason
        .map(str::trim)
        .filter(|r| !r.is_empty())
        .unwrap_or("Task cancelled by a human.")
        .to_string();
    let mut events = end_work(task, AttemptOutcome::Released, Some(note));
    events.push(state_change(task, TaskState::Cancelled));
    Ok(events)
}

// ---------------------------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------------------------

/// Fencing (§4): the presented token must match the current lease of `kind`, held by the caller,
/// and not be expired. Anything else is `stale_lease`, even from the same actor.
fn check_lease<'a>(
    task: &'a TaskSnapshot,
    ctx: &Ctx,
    token_hash: Option<&str>,
    kind: LeaseKind,
) -> Result<&'a Lease, DomainError> {
    let lease = check_lease_any(task, ctx, token_hash)?;
    if lease.kind != kind {
        return Err(DomainError::StaleLease(format!(
            "this command needs a {} lease",
            kind.as_str()
        )));
    }
    Ok(lease)
}

fn check_lease_any<'a>(
    task: &'a TaskSnapshot,
    ctx: &Ctx,
    token_hash: Option<&str>,
) -> Result<&'a Lease, DomainError> {
    let token =
        token_hash.ok_or_else(|| DomainError::StaleLease("lease_token is required".into()))?;
    let lease = task.lease.as_ref().ok_or_else(|| {
        DomainError::StaleLease("the task has no active lease; stop working on it".into())
    })?;
    if lease.actor_id != ctx.caller.id || lease.token_hash != token {
        return Err(DomainError::StaleLease(
            "the lease token does not match the current lease; stop working on this task".into(),
        ));
    }
    if !lease.paused && lease.expires_at <= ctx.now {
        return Err(DomainError::StaleLease(
            "the lease expired; stop working on this task".into(),
        ));
    }
    Ok(lease)
}

/// Lease check plus "the task is in the state that lease kind allows" (heartbeat / report).
fn leased_state(
    task: &TaskSnapshot,
    ctx: &Ctx,
    token_hash: Option<&str>,
    what: &str,
) -> Result<(), DomainError> {
    let lease = check_lease_any(task, ctx, token_hash)?;
    let ok = match lease.kind {
        LeaseKind::Work => task.state == TaskState::Working,
        LeaseKind::Review => task.state == TaskState::InReview,
    };
    if ok {
        Ok(())
    } else {
        Err(state_guard(task, what))
    }
}

/// End the open attempt and release the current lease.
fn end_work(
    task: &TaskSnapshot,
    outcome: AttemptOutcome,
    note: Option<String>,
) -> Vec<DomainEvent> {
    let mut events = Vec::new();
    if let Some(att) = &task.attempt {
        events.push(DomainEvent::AttemptEnded {
            attempt_id: att.id,
            task_id: task.id,
            outcome,
            handoff_note: note,
        });
    }
    if let Some(lease) = &task.lease {
        events.push(DomainEvent::LeaseReleased {
            task_id: task.id,
            actor_id: lease.actor_id,
            kind: lease.kind,
        });
    }
    events
}

fn state_change(task: &TaskSnapshot, to: TaskState) -> DomainEvent {
    DomainEvent::TaskStateChanged {
        task_id: task.id,
        from: task.state,
        to,
        preferred_actor_id: None,
        preferred_until: None,
        submission: None,
    }
}

fn lease_expiry(ctx: &Ctx) -> OffsetDateTime {
    ctx.now + Duration::seconds(ctx.workflow.lease_ttl_secs)
}

fn grace_until(ctx: &Ctx) -> OffsetDateTime {
    ctx.now + Duration::seconds(ctx.workflow.preferred_grace_secs)
}

fn require_state(task: &TaskSnapshot, state: TaskState, what: &str) -> Result<(), DomainError> {
    if task.state == state {
        Ok(())
    } else {
        Err(state_guard(task, what))
    }
}

fn state_guard(task: &TaskSnapshot, what: &str) -> DomainError {
    DomainError::guard(
        "state",
        format!(
            "{what} is not allowed while the task is {}",
            task.state.as_str()
        ),
    )
}

fn require_note(note: Option<&str>) -> Result<String, DomainError> {
    match note.map(str::trim) {
        Some(n) if !n.is_empty() => {
            if n.len() > MAX_NOTE_BYTES {
                return Err(DomainError::invalid(
                    "handoff_note",
                    "handoff_note is too long (max 16 KB)",
                ));
            }
            Ok(n.to_string())
        }
        _ => Err(DomainError::invalid(
            "handoff_note",
            "a handoff note is required: what is done, what is left, where",
        )),
    }
}

fn validate_body(field: &'static str, body: &str) -> Result<(), DomainError> {
    if body.trim().is_empty() {
        return Err(DomainError::invalid(
            field,
            format!("{field} must not be empty"),
        ));
    }
    if body.len() > MAX_REPORT_BYTES {
        return Err(DomainError::invalid(field, format!("{field} exceeds 4 KB")));
    }
    Ok(())
}

fn validate_title(title: &str) -> Result<(), DomainError> {
    let t = title.trim();
    if t.is_empty() || t.chars().count() > MAX_TITLE_CHARS {
        return Err(DomainError::invalid(
            "title",
            "title must be 1 to 500 characters",
        ));
    }
    Ok(())
}

fn forbid_kind(ctx: &Ctx, kind: ActorKind, msg: &str) -> Result<(), DomainError> {
    if ctx.caller.kind == kind {
        Err(DomainError::Forbidden(msg.into()))
    } else {
        Ok(())
    }
}
