//! One test per row of the §4 transition table, plus the guards that protect each row.

mod common;

use atb_core::{
    ActivityKind, AttemptOutcome, Caller, Command, CriterionVerdict, DomainError, DomainEvent,
    LeaseKind, LinkKind, QuestionRef, ReviewGate, ReviewVerdict, Role, TaskState, TestGate,
    WorkflowConfig,
};
use common::*;
use uuid::Uuid;

fn no_gates() -> WorkflowConfig {
    WorkflowConfig {
        spec_gate: false,
        test_gate: TestGate::None,
        review_gate: ReviewGate::None,
        ..gated()
    }
}

fn verdicts(pass: bool) -> Vec<CriterionVerdict> {
    ["AC-1", "AC-2"]
        .iter()
        .map(|id| CriterionVerdict {
            ac_id: (*id).into(),
            pass,
            note: None,
        })
        .collect()
}

fn review(tok: &str, commit: &str, verdict: ReviewVerdict, per: Vec<CriterionVerdict>) -> Command {
    Command::SubmitReview {
        token_hash: Some(tok.into()),
        review_id: Uuid::now_v7(),
        commit_sha: commit.into(),
        verdict,
        per_criterion: per,
        comment: Some("see notes".into()),
        failure_question_id: Uuid::now_v7(),
        failure_summary: "3 attempts rejected".into(),
    }
}

fn claim_cmd(kind: LeaseKind) -> Command {
    Command::Claim {
        kind,
        token_hash: token(),
        attempt_id: Uuid::now_v7(),
    }
}

/// Bring a gated task to in_review with `imp` as implementer and commit "abc".
fn to_in_review(w: &mut World, imp: &Caller) {
    let tok = w.claim(imp);
    w.submit(imp, &tok, "abc").unwrap();
    w.test_result(true, false).unwrap();
    assert_eq!(w.state(), TaskState::InReview);
}

fn ask_blocking(w: &mut World, who: &Caller, tok: &str) -> Uuid {
    let qid = Uuid::now_v7();
    w.run(
        who,
        Command::Ask {
            token_hash: Some(tok.into()),
            question_id: qid,
            body: "Which format?".into(),
            blocking: true,
            options: None,
            handoff_note: Some("parser done, writer left".into()),
        },
    )
    .unwrap();
    qid
}

// --- creation -----------------------------------------------------------------------------------

#[test]
fn create_starts_ready_when_pinned_version_is_approved() {
    assert_eq!(
        World::with_approved(gated(), Some(1)).state(),
        TaskState::Ready
    );
}

#[test]
fn create_starts_draft_when_pinned_version_is_not_approved() {
    assert_eq!(
        World::with_approved(gated(), None).state(),
        TaskState::Draft
    );
}

#[test]
fn create_starts_ready_when_spec_gate_is_off() {
    assert_eq!(
        World::with_approved(no_gates(), None).state(),
        TaskState::Ready
    );
}

// --- row: draft --spec version approved--> ready ---------------------------------------------

#[test]
fn row_draft_to_ready_on_spec_approval() {
    let mut w = World::with_approved(gated(), None);
    let ev = w
        .run(&system(), Command::SpecApproved { version: 1 })
        .unwrap();
    assert_eq!(types(&ev), ["task.state_changed"]);
    assert_eq!(w.state(), TaskState::Ready);
}

#[test]
fn draft_task_cannot_be_claimed() {
    let mut w = World::with_approved(gated(), None);
    let err = w
        .run(&implementer(), claim_cmd(LeaseKind::Work))
        .unwrap_err();
    assert_eq!(guard_name(&err), "state");
}

#[test]
fn newer_approved_version_marks_task_spec_outdated_and_blocks_claim_until_repin() {
    let mut w = World::new(gated());
    w.approved = Some(2);
    let ev = w
        .run(&system(), Command::SpecApproved { version: 2 })
        .unwrap();
    assert_eq!(types(&ev), ["task.spec_outdated"]);
    assert!(w.task.spec_outdated);
    let imp = implementer();
    let err = w.run(&imp, claim_cmd(LeaseKind::Work)).unwrap_err();
    assert_eq!(guard_name(&err), "spec_outdated");
    w.run(
        &human(),
        Command::Repin {
            token_hash: None,
            to_version: 2,
        },
    )
    .unwrap();
    assert!(!w.task.spec_outdated);
    assert_eq!(w.task.spec_version, 2);
    w.claim(&imp);
}

#[test]
fn agents_cannot_approve_specs() {
    let mut w = World::with_approved(gated(), None);
    let err = w
        .run(&implementer(), Command::SpecApproved { version: 1 })
        .unwrap_err();
    assert!(matches!(err, DomainError::Forbidden(_)));
}

// --- row: ready --claim--> working ------------------------------------------------------------

#[test]
fn row_ready_claim_to_working_with_attempt_and_lease() {
    let mut w = World::new(gated());
    let imp = implementer();
    let tok = w.claim(&imp);
    assert_eq!(w.state(), TaskState::Working);
    let lease = w.task.lease.as_ref().unwrap();
    assert_eq!((lease.kind, lease.actor_id), (LeaseKind::Work, imp.id));
    assert_eq!(lease.token_hash, tok);
    assert_eq!(w.task.attempt.as_ref().unwrap().n, 1);
}

#[test]
fn claim_requires_implementer_role() {
    let mut w = World::new(gated());
    let err = w
        .run(&reviewer("m"), claim_cmd(LeaseKind::Work))
        .unwrap_err();
    assert!(matches!(err, DomainError::Forbidden(_)));
}

#[test]
fn claim_refused_while_a_blocker_is_not_done() {
    let mut w = World::new(gated());
    w.blockers = vec![TaskState::Done, TaskState::Working];
    let err = w
        .run(&implementer(), claim_cmd(LeaseKind::Work))
        .unwrap_err();
    assert_eq!(guard_name(&err), "blocked");
    w.blockers = vec![TaskState::Done];
    w.claim(&implementer());
}

#[test]
fn second_claim_is_refused() {
    let mut w = World::new(gated());
    w.claim(&implementer());
    let err = w
        .run(&implementer(), claim_cmd(LeaseKind::Work))
        .unwrap_err();
    assert_eq!(guard_name(&err), "state");
}

// --- row: working heartbeat / report ------------------------------------------------------------

#[test]
fn row_working_heartbeat_and_report_keep_working() {
    let mut w = World::new(gated());
    let imp = implementer();
    let tok = w.claim(&imp);
    let ev = w
        .run(
            &imp,
            Command::Heartbeat {
                token_hash: Some(tok.clone()),
            },
        )
        .unwrap();
    assert!(ev.is_empty(), "heartbeats are not events");
    let ev = w
        .run(
            &imp,
            Command::Report {
                token_hash: Some(tok),
                kind: ActivityKind::Progress,
                body: "parsed the input".into(),
                trace_id: Some("trace-1".into()),
            },
        )
        .unwrap();
    assert_eq!(types(&ev), ["activity.reported"]);
    assert_eq!(w.state(), TaskState::Working);
}

#[test]
fn report_body_over_4kb_is_rejected() {
    let mut w = World::new(gated());
    let imp = implementer();
    let tok = w.claim(&imp);
    let err = w
        .run(
            &imp,
            Command::Report {
                token_hash: Some(tok),
                kind: ActivityKind::Thought,
                body: "x".repeat(4097),
                trace_id: None,
            },
        )
        .unwrap_err();
    assert_eq!(err.code(), "invalid_input");
}

// --- fencing (AC-1.3) ----------------------------------------------------------------------------

#[test]
fn stale_lease_for_missing_wrong_foreign_and_expired_tokens() {
    let mut w = World::new(gated());
    let imp = implementer();
    let tok = w.claim(&imp);
    let hb = |t: Option<String>| Command::Heartbeat { token_hash: t };
    assert_eq!(w.run(&imp, hb(None)).unwrap_err().code(), "stale_lease");
    assert_eq!(
        w.run(&imp, hb(Some(token()))).unwrap_err().code(),
        "stale_lease"
    );
    assert_eq!(
        w.run(&implementer(), hb(Some(tok.clone())))
            .unwrap_err()
            .code(),
        "stale_lease"
    );
    w.advance(601);
    assert_eq!(
        w.run(&imp, hb(Some(tok))).unwrap_err().code(),
        "stale_lease"
    );
}

// --- row: working --ask blocking--> input_required -----------------------------------------------

#[test]
fn row_blocking_ask_moves_to_input_required_and_releases_lease() {
    let mut w = World::new(gated());
    let imp = implementer();
    let tok = w.claim(&imp);
    let ev = w
        .run(
            &imp,
            Command::Ask {
                token_hash: Some(tok),
                question_id: Uuid::now_v7(),
                body: "Which format?".into(),
                blocking: true,
                options: None,
                handoff_note: Some("parser done, writer left".into()),
            },
        )
        .unwrap();
    assert_eq!(
        types(&ev),
        [
            "question.asked",
            "attempt.ended",
            "lease.released",
            "task.state_changed"
        ]
    );
    assert_eq!(w.state(), TaskState::InputRequired);
    assert!(w.task.lease.is_none());
}

#[test]
fn blocking_ask_needs_a_handoff_note() {
    let mut w = World::new(gated());
    let imp = implementer();
    let tok = w.claim(&imp);
    let err = w
        .run(
            &imp,
            Command::Ask {
                token_hash: Some(tok),
                question_id: Uuid::now_v7(),
                body: "?".into(),
                blocking: true,
                options: None,
                handoff_note: None,
            },
        )
        .unwrap_err();
    assert_eq!(err.code(), "invalid_input");
    assert_eq!(w.state(), TaskState::Working);
}

#[test]
fn non_blocking_ask_keeps_working() {
    let mut w = World::new(gated());
    let imp = implementer();
    let tok = w.claim(&imp);
    let ev = w
        .run(
            &imp,
            Command::Ask {
                token_hash: Some(tok),
                question_id: Uuid::now_v7(),
                body: "FYI?".into(),
                blocking: false,
                options: None,
                handoff_note: None,
            },
        )
        .unwrap();
    assert_eq!(types(&ev), ["question.asked"]);
    assert_eq!(w.state(), TaskState::Working);
}

// --- row: input_required --answered--> ready (asker preference) ------------------------------

#[test]
fn row_answer_returns_to_ready_with_preference_for_the_asker() {
    let mut w = World::new(gated());
    let imp = implementer();
    let tok = w.claim(&imp);
    let qid = ask_blocking(&mut w, &imp, &tok);
    let q = QuestionRef {
        id: qid,
        asked_by: imp.id,
        blocking: true,
        open: true,
    };
    let err = w
        .run(
            &imp,
            Command::Answer {
                question: q.clone(),
                answer: "json".into(),
            },
        )
        .unwrap_err();
    assert!(matches!(err, DomainError::Forbidden(_)));
    w.run(
        &human(),
        Command::Answer {
            question: q,
            answer: "json".into(),
        },
    )
    .unwrap();
    assert_eq!(w.state(), TaskState::Ready);
    assert_eq!(w.task.preferred_actor_id, Some(imp.id));
    let other = implementer();
    let err = w.run(&other, claim_cmd(LeaseKind::Work)).unwrap_err();
    assert_eq!(guard_name(&err), "preferred_actor");
    w.advance(121);
    w.claim(&other);
}

#[test]
fn the_asker_can_reclaim_during_the_grace_window() {
    let mut w = World::new(gated());
    let imp = implementer();
    let tok = w.claim(&imp);
    let qid = ask_blocking(&mut w, &imp, &tok);
    w.run(
        &human(),
        Command::Answer {
            question: QuestionRef {
                id: qid,
                asked_by: imp.id,
                blocking: true,
                open: true,
            },
            answer: "yes".into(),
        },
    )
    .unwrap();
    w.claim(&imp);
    assert_eq!(w.task.attempt.as_ref().unwrap().n, 2);
    assert!(w.task.preferred_actor_id.is_none());
}

#[test]
fn an_answered_question_cannot_be_answered_again() {
    let mut w = World::new(gated());
    let err = w
        .run(
            &human(),
            Command::Answer {
                question: QuestionRef {
                    id: Uuid::now_v7(),
                    asked_by: Uuid::now_v7(),
                    blocking: true,
                    open: false,
                },
                answer: "late".into(),
            },
        )
        .unwrap_err();
    assert_eq!(guard_name(&err), "question_not_open");
}

// --- row: working --release--> ready -------------------------------------------------------------

#[test]
fn row_release_returns_to_ready_with_a_handoff_note() {
    let mut w = World::new(gated());
    let imp = implementer();
    let tok = w.claim(&imp);
    let err = w
        .run(
            &imp,
            Command::Release {
                token_hash: Some(tok.clone()),
                handoff_note: "  ".into(),
            },
        )
        .unwrap_err();
    assert_eq!(err.code(), "invalid_input");
    let ev = w
        .run(
            &imp,
            Command::Release {
                token_hash: Some(tok),
                handoff_note: "done: parser; left: writer".into(),
            },
        )
        .unwrap();
    assert!(matches!(
        &ev[0],
        DomainEvent::AttemptEnded { outcome: AttemptOutcome::Released, handoff_note: Some(n), .. }
            if n.contains("writer")
    ));
    assert_eq!(w.state(), TaskState::Ready);
}

// --- row: working --lease expired--> ready (AC-1.2) -------------------------------------------

#[test]
fn row_lease_expiry_returns_to_ready_with_automatic_handoff_note() {
    let mut w = World::new(gated());
    w.claim(&implementer());
    let err = w.run(&system(), Command::ExpireLease).unwrap_err();
    assert_eq!(guard_name(&err), "lease_not_expired");
    w.advance(600);
    let ev = w.run(&system(), Command::ExpireLease).unwrap();
    assert_eq!(
        types(&ev),
        ["lease.expired", "attempt.ended", "task.state_changed"]
    );
    let DomainEvent::LeaseExpired { handoff_note, .. } = &ev[0] else {
        panic!("first event must be lease.expired");
    };
    assert!(handoff_note.contains("Automatic handoff"));
    assert_eq!(w.state(), TaskState::Ready);
}

#[test]
fn only_the_system_expires_leases() {
    let mut w = World::new(gated());
    w.claim(&implementer());
    w.advance(601);
    assert!(matches!(
        w.run(&human(), Command::ExpireLease).unwrap_err(),
        DomainError::Forbidden(_)
    ));
}

// --- row: working --submit_for_test--> testing ---------------------------------------------------

#[test]
fn row_submit_for_test_pauses_the_lease() {
    let mut w = World::new(gated());
    let imp = implementer();
    let tok = w.claim(&imp);
    let ev = w.submit(&imp, &tok, "abc").unwrap();
    assert_eq!(types(&ev), ["test.requested", "task.state_changed"]);
    assert_eq!(w.state(), TaskState::Testing);
    assert!(w.task.lease.as_ref().unwrap().paused);
    w.advance(10_000);
    assert!(
        w.run(&system(), Command::ExpireLease).is_err(),
        "a paused lease never expires"
    );
}

#[test]
fn submit_needs_a_commit_and_a_current_spec() {
    let mut w = World::new(gated());
    let imp = implementer();
    let tok = w.claim(&imp);
    assert_eq!(
        w.submit(&imp, &tok, " ").unwrap_err().code(),
        "invalid_input"
    );
    w.approved = Some(2);
    w.run(&system(), Command::SpecApproved { version: 2 })
        .unwrap();
    assert_eq!(
        guard_name(&w.submit(&imp, &tok, "abc").unwrap_err()),
        "spec_outdated"
    );
}

#[test]
fn submit_with_all_gates_off_finishes_the_task() {
    let mut w = World::new(no_gates());
    let imp = implementer();
    let tok = w.claim(&imp);
    w.submit(&imp, &tok, "abc").unwrap();
    assert_eq!(w.state(), TaskState::Done);
    assert!(w.task.lease.is_none() && w.task.attempt.is_none());
}

#[test]
fn submit_with_test_gate_off_goes_to_review() {
    let mut w = World::new(WorkflowConfig {
        test_gate: TestGate::None,
        ..gated()
    });
    let imp = implementer();
    let tok = w.claim(&imp);
    w.submit(&imp, &tok, "abc").unwrap();
    assert_eq!(w.state(), TaskState::InReview);
    assert_eq!(
        w.task.attempt.as_ref().unwrap().commit_sha.as_deref(),
        Some("abc")
    );
}

// --- rows: testing --verifier passed/failed--> -------------------------------------------------

#[test]
fn row_test_passed_moves_to_in_review_and_releases_the_work_lease() {
    let mut w = World::new(gated());
    let imp = implementer();
    let tok = w.claim(&imp);
    w.submit(&imp, &tok, "abc").unwrap();
    let ev = w.test_result(true, false).unwrap();
    assert_eq!(
        types(&ev),
        ["test.completed", "lease.released", "task.state_changed"]
    );
    assert_eq!(w.state(), TaskState::InReview);
    assert!(w.task.lease.is_none());
}

#[test]
fn row_test_failed_returns_to_working_for_the_same_holder() {
    let mut w = World::new(gated());
    let imp = implementer();
    let tok = w.claim(&imp);
    w.submit(&imp, &tok, "abc").unwrap();
    w.advance(5_000);
    w.test_result(false, false).unwrap();
    assert_eq!(w.state(), TaskState::Working);
    let lease = w.task.lease.as_ref().unwrap();
    assert_eq!(lease.actor_id, imp.id);
    assert!(!lease.paused);
    w.run(
        &imp,
        Command::Heartbeat {
            token_hash: Some(tok),
        },
    )
    .expect("fresh TTL: the same token works again");
}

#[test]
fn protected_path_violation_fails_the_run_whatever_the_exit_codes() {
    let mut w = World::new(gated());
    let imp = implementer();
    let tok = w.claim(&imp);
    w.submit(&imp, &tok, "abc").unwrap();
    w.test_result(true, true).unwrap();
    assert_eq!(w.state(), TaskState::Working);
}

#[test]
fn only_the_verifier_reports_command_results() {
    let mut w = World::new(gated());
    let imp = implementer();
    let tok = w.claim(&imp);
    w.submit(&imp, &tok, "abc").unwrap();
    let err = w
        .run(
            &imp,
            Command::CompleteTest {
                test_run_id: Uuid::now_v7(),
                passed: true,
                protected_path_violation: false,
            },
        )
        .unwrap_err();
    assert!(matches!(err, DomainError::Forbidden(_)));
}

// --- row: in_review --claim (reviewer)--> in_review ----------------------------------------------

#[test]
fn row_reviewer_claim_takes_a_review_lease() {
    let mut w = World::new(gated());
    to_in_review(&mut w, &implementer());
    w.claim_review(&reviewer("model-b")).unwrap();
    assert_eq!(w.state(), TaskState::InReview);
    assert_eq!(w.task.lease.as_ref().unwrap().kind, LeaseKind::Review);
}

#[test]
fn the_implementer_cannot_claim_its_own_review() {
    let mut w = World::new(gated());
    let imp = agent(&[Role::Implementer, Role::Reviewer], "model-a");
    to_in_review(&mut w, &imp);
    assert_eq!(
        guard_name(&w.claim_review(&imp).unwrap_err()),
        "self_review"
    );
}

#[test]
fn require_different_model_refuses_a_same_model_reviewer() {
    let mut w = World::new(WorkflowConfig {
        require_different_model: true,
        ..gated()
    });
    to_in_review(&mut w, &implementer());
    assert_eq!(
        guard_name(&w.claim_review(&reviewer("model-a")).unwrap_err()),
        "same_model"
    );
    w.claim_review(&reviewer("model-b")).unwrap();
}

#[test]
fn human_only_review_gate_refuses_agents() {
    let mut w = World::new(WorkflowConfig {
        review_gate: ReviewGate::HumanOnly,
        ..gated()
    });
    to_in_review(&mut w, &implementer());
    assert!(matches!(
        w.claim_review(&reviewer("model-b")).unwrap_err(),
        DomainError::Forbidden(_)
    ));
}

// --- row: in_review --review lease expired--> in_review (unclaimed) ------------------------------

#[test]
fn row_review_lease_expiry_leaves_the_review_unclaimed() {
    let mut w = World::new(gated());
    to_in_review(&mut w, &implementer());
    w.claim_review(&reviewer("model-b")).unwrap();
    w.advance(601);
    let ev = w.run(&system(), Command::ExpireLease).unwrap();
    assert_eq!(types(&ev), ["lease.expired"]);
    assert_eq!(w.state(), TaskState::InReview);
    assert!(w.task.lease.is_none());
    w.claim_review(&reviewer("model-c")).unwrap();
}

// --- row: in_review --submit_review approved--> done --------------------------------------------

#[test]
fn row_approved_review_finishes_the_task() {
    let mut w = World::new(gated());
    to_in_review(&mut w, &implementer());
    let rev = reviewer("model-b");
    let tok = w.claim_review(&rev).unwrap();
    w.run(
        &rev,
        review(&tok, "abc", ReviewVerdict::Approved, verdicts(true)),
    )
    .unwrap();
    assert_eq!(w.state(), TaskState::Done);
}

#[test]
fn review_of_another_commit_or_missing_ac_is_rejected() {
    let mut w = World::new(gated());
    to_in_review(&mut w, &implementer());
    let rev = reviewer("model-b");
    let tok = w.claim_review(&rev).unwrap();
    let err = w
        .run(
            &rev,
            review(&tok, "zzz", ReviewVerdict::Approved, verdicts(true)),
        )
        .unwrap_err();
    assert_eq!(guard_name(&err), "commit_mismatch");
    let mut partial = verdicts(true);
    partial.pop();
    let err = w
        .run(&rev, review(&tok, "abc", ReviewVerdict::Approved, partial))
        .unwrap_err();
    assert_eq!(guard_name(&err), "missing_verdict");
    let err = w
        .run(
            &rev,
            review(&tok, "abc", ReviewVerdict::Approved, verdicts(false)),
        )
        .unwrap_err();
    assert_eq!(guard_name(&err), "approval_needs_all_pass");
}

#[test]
fn a_human_only_criterion_can_only_be_passed_by_a_human() {
    let mut w = World::new(gated());
    w.acs[1].human_only = true;
    to_in_review(&mut w, &implementer());
    let rev = reviewer("model-b");
    let tok = w.claim_review(&rev).unwrap();
    let err = w
        .run(
            &rev,
            review(&tok, "abc", ReviewVerdict::Approved, verdicts(true)),
        )
        .unwrap_err();
    assert!(matches!(err, DomainError::Forbidden(_)));
}

// --- row: in_review --changes requested--> ready | failed ---------------------------------------

#[test]
fn row_changes_requested_returns_to_ready_with_preference_for_the_implementer() {
    let mut w = World::new(gated());
    let imp = implementer();
    to_in_review(&mut w, &imp);
    let rev = reviewer("model-b");
    let tok = w.claim_review(&rev).unwrap();
    w.run(
        &rev,
        review(
            &tok,
            "abc",
            ReviewVerdict::ChangesRequested,
            verdicts(false),
        ),
    )
    .unwrap();
    assert_eq!(w.state(), TaskState::Ready);
    assert_eq!(w.task.preferred_actor_id, Some(imp.id));
    assert_eq!(w.task.rejection_count, 1);
}

#[test]
fn reaching_max_rejections_fails_the_task_and_opens_a_human_question() {
    let mut w = World::new(WorkflowConfig {
        max_rejections: 2,
        ..gated()
    });
    let imp = implementer();
    for round in 1..=2 {
        to_in_review(&mut w, &imp);
        let rev = reviewer("model-b");
        let tok = w.claim_review(&rev).unwrap();
        let ev = w
            .run(
                &rev,
                review(
                    &tok,
                    "abc",
                    ReviewVerdict::ChangesRequested,
                    verdicts(false),
                ),
            )
            .unwrap();
        if round == 2 {
            assert_eq!(
                types(&ev),
                [
                    "review.submitted",
                    "lease.released",
                    "attempt.ended",
                    "task.state_changed",
                    "question.asked"
                ]
            );
        }
    }
    assert_eq!(w.state(), TaskState::Failed);
}

// --- row: any non-terminal --cancel (human)--> cancelled --------------------------------------

#[test]
fn row_cancel_by_a_human_from_non_terminal_states() {
    let mut w = World::new(gated());
    w.run(&human(), Command::Cancel { reason: None }).unwrap();
    assert_eq!(w.state(), TaskState::Cancelled);

    let mut w = World::new(gated());
    w.claim(&implementer());
    w.run(
        &human(),
        Command::Cancel {
            reason: Some("duplicate".into()),
        },
    )
    .unwrap();
    assert_eq!(w.state(), TaskState::Cancelled);

    let mut w = World::new(gated());
    to_in_review(&mut w, &implementer());
    w.claim_review(&reviewer("model-b")).unwrap();
    w.run(&human(), Command::Cancel { reason: None }).unwrap();
    assert_eq!(w.state(), TaskState::Cancelled);
    assert_eq!(
        guard_name(
            &w.run(&human(), Command::Cancel { reason: None })
                .unwrap_err()
        ),
        "state"
    );
}

#[test]
fn agents_cannot_cancel() {
    let mut w = World::new(gated());
    assert!(matches!(
        w.run(&implementer(), Command::Cancel { reason: None })
            .unwrap_err(),
        DomainError::Forbidden(_)
    ));
}

// --- links (AC-1.5) and UI patches -----------------------------------------------------------

#[test]
fn blocks_link_creating_a_cycle_is_rejected() {
    let mut w = World::new(gated());
    let (b, c) = (Uuid::now_v7(), Uuid::now_v7());
    // b -> c -> task already exist; task -> b would close the loop.
    w.edges = vec![(b, c), (c, w.task.id)];
    let err = w
        .run(
            &human(),
            Command::AddLink {
                to: b,
                kind: LinkKind::Blocks,
            },
        )
        .unwrap_err();
    assert_eq!(guard_name(&err), "cycle");
    // A non-blocking relation is not part of the DAG.
    w.run(
        &human(),
        Command::AddLink {
            to: b,
            kind: LinkKind::Related,
        },
    )
    .unwrap();
    let err = w
        .run(
            &human(),
            Command::AddLink {
                to: w.task.id,
                kind: LinkKind::Blocks,
            },
        )
        .unwrap_err();
    assert_eq!(guard_name(&err), "cycle");
}

#[test]
fn patch_with_stale_expected_version_is_a_version_conflict() {
    let mut w = World::new(gated());
    let err = w
        .run(
            &human(),
            Command::Update {
                expected_version: 99,
                title: Some("New".into()),
                priority: None,
            },
        )
        .unwrap_err();
    assert!(matches!(
        err,
        DomainError::VersionConflict { current: 1, .. }
    ));
    w.run(
        &human(),
        Command::Update {
            expected_version: 1,
            title: None,
            priority: Some(5),
        },
    )
    .unwrap();
    assert_eq!((w.task.priority, w.task.version), (5, 2));
}
