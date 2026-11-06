//! Random command sequences, issued by random actors with random tokens and clock jumps, never
//! drive the aggregate into an illegal state (§4). Rejected commands leave it untouched.

mod common;

use std::collections::HashMap;

use atb_core::{
    ActivityKind, Caller, Command, CriterionVerdict, LeaseKind, QuestionRef, ReviewGate,
    ReviewVerdict, Role, TaskState, TestGate, WorkflowConfig, apply_all, decide, invariants,
};
use common::*;
use proptest::prelude::*;
use uuid::Uuid;

#[derive(Debug, Clone)]
enum Op {
    Claim {
        who: usize,
        review: bool,
    },
    Heartbeat {
        who: usize,
        good: bool,
    },
    Report {
        who: usize,
        good: bool,
    },
    Ask {
        who: usize,
        blocking: bool,
        good: bool,
    },
    Answer {
        who: usize,
    },
    Release {
        who: usize,
        good: bool,
    },
    Expire,
    Submit {
        who: usize,
        good: bool,
    },
    TestResult {
        passed: bool,
        violation: bool,
    },
    Review {
        who: usize,
        approve: bool,
        right_commit: bool,
    },
    ApproveSpec {
        bump: bool,
    },
    Repin {
        who: usize,
    },
    Cancel {
        who: usize,
    },
    Advance {
        secs: i64,
    },
}

fn op() -> impl Strategy<Value = Op> {
    let who = 0usize..5;
    prop_oneof![
        (who.clone(), any::<bool>()).prop_map(|(who, review)| Op::Claim { who, review }),
        (who.clone(), any::<bool>()).prop_map(|(who, good)| Op::Heartbeat { who, good }),
        (who.clone(), any::<bool>()).prop_map(|(who, good)| Op::Report { who, good }),
        (who.clone(), any::<bool>(), any::<bool>()).prop_map(|(who, blocking, good)| Op::Ask {
            who,
            blocking,
            good
        }),
        who.clone().prop_map(|who| Op::Answer { who }),
        (who.clone(), any::<bool>()).prop_map(|(who, good)| Op::Release { who, good }),
        Just(Op::Expire),
        (who.clone(), any::<bool>()).prop_map(|(who, good)| Op::Submit { who, good }),
        (any::<bool>(), any::<bool>())
            .prop_map(|(passed, violation)| Op::TestResult { passed, violation }),
        (who.clone(), any::<bool>(), any::<bool>()).prop_map(|(who, approve, right_commit)| {
            Op::Review {
                who,
                approve,
                right_commit,
            }
        }),
        any::<bool>().prop_map(|bump| Op::ApproveSpec { bump }),
        who.clone().prop_map(|who| Op::Repin { who }),
        who.prop_map(|who| Op::Cancel { who }),
        (1i64..900).prop_map(|secs| Op::Advance { secs }),
    ]
}

fn workflow() -> impl Strategy<Value = WorkflowConfig> {
    (
        any::<bool>(),
        prop_oneof![
            Just(TestGate::None),
            Just(TestGate::Command),
            Just(TestGate::Human)
        ],
        prop_oneof![
            Just(ReviewGate::None),
            Just(ReviewGate::AgentOrHuman),
            Just(ReviewGate::HumanOnly)
        ],
        1i32..4,
    )
        .prop_map(
            |(spec_gate, test_gate, review_gate, max_rejections)| WorkflowConfig {
                spec_gate,
                test_gate,
                review_gate,
                require_different_model: false,
                max_rejections,
                lease_ttl_secs: 600,
                preferred_grace_secs: 120,
            },
        )
}

/// Build the command for `op`, or `None` when the op only changes the test world.
fn command(
    op: &Op,
    w: &mut World,
    actors: &[Caller],
    tokens: &mut HashMap<Uuid, String>,
    open_q: &mut Option<QuestionRef>,
    spec_version: &mut i32,
) -> Option<(Caller, Command)> {
    let tok = |who: usize, good: bool, tokens: &HashMap<Uuid, String>| {
        if good {
            tokens.get(&actors[who].id).cloned()
        } else {
            Some(token())
        }
    };
    let out = match *op {
        Op::Claim { who, review } => {
            let t = token();
            tokens.insert(actors[who].id, t.clone());
            let kind = if review {
                LeaseKind::Review
            } else {
                LeaseKind::Work
            };
            (
                actors[who].clone(),
                Command::Claim {
                    kind,
                    token_hash: t,
                    attempt_id: Uuid::now_v7(),
                },
            )
        }
        Op::Heartbeat { who, good } => (
            actors[who].clone(),
            Command::Heartbeat {
                token_hash: tok(who, good, tokens),
            },
        ),
        Op::Report { who, good } => (
            actors[who].clone(),
            Command::Report {
                token_hash: tok(who, good, tokens),
                kind: ActivityKind::Progress,
                body: "step".into(),
                trace_id: None,
            },
        ),
        Op::Ask {
            who,
            blocking,
            good,
        } => {
            let qid = Uuid::now_v7();
            let cmd = Command::Ask {
                token_hash: tok(who, good, tokens),
                question_id: qid,
                body: "?".into(),
                blocking,
                options: None,
                handoff_note: Some("note".into()),
            };
            if decide(&w.task, &cmd, &w.ctx(&actors[who])).is_ok() {
                *open_q = Some(QuestionRef {
                    id: qid,
                    asked_by: actors[who].id,
                    blocking,
                    open: true,
                });
            }
            (actors[who].clone(), cmd)
        }
        Op::Answer { who } => {
            let q = open_q.take()?;
            (
                actors[who].clone(),
                Command::Answer {
                    question: q,
                    answer: "ok".into(),
                },
            )
        }
        Op::Release { who, good } => (
            actors[who].clone(),
            Command::Release {
                token_hash: tok(who, good, tokens),
                handoff_note: "note".into(),
            },
        ),
        Op::Expire => (system(), Command::ExpireLease),
        Op::Submit { who, good } => (
            actors[who].clone(),
            Command::SubmitForTest {
                token_hash: tok(who, good, tokens),
                commit_sha: "abc".into(),
                branch: None,
                test_run_id: Uuid::now_v7(),
            },
        ),
        Op::TestResult { passed, violation } => {
            let who = if w.wf.test_gate == TestGate::Human {
                3
            } else {
                4
            };
            (
                actors[who].clone(),
                Command::CompleteTest {
                    test_run_id: Uuid::now_v7(),
                    passed,
                    protected_path_violation: violation,
                },
            )
        }
        Op::Review {
            who,
            approve,
            right_commit,
        } => {
            let per = w
                .acs
                .iter()
                .map(|a| CriterionVerdict {
                    ac_id: a.id.clone(),
                    pass: approve,
                    note: None,
                })
                .collect();
            let verdict = if approve {
                ReviewVerdict::Approved
            } else {
                ReviewVerdict::ChangesRequested
            };
            (
                actors[who].clone(),
                Command::SubmitReview {
                    token_hash: tokens.get(&actors[who].id).cloned(),
                    review_id: Uuid::now_v7(),
                    commit_sha: if right_commit { "abc" } else { "zzz" }.into(),
                    verdict,
                    per_criterion: per,
                    comment: None,
                    failure_question_id: Uuid::now_v7(),
                    failure_summary: "failed".into(),
                },
            )
        }
        Op::ApproveSpec { bump } => {
            if bump {
                *spec_version += 1;
            }
            w.approved = Some(*spec_version);
            (
                system(),
                Command::SpecApproved {
                    version: *spec_version,
                },
            )
        }
        Op::Repin { who } => (
            actors[who].clone(),
            Command::Repin {
                token_hash: tokens.get(&actors[who].id).cloned(),
                to_version: *spec_version,
            },
        ),
        Op::Cancel { who } => (actors[who].clone(), Command::Cancel { reason: None }),
        Op::Advance { secs } => {
            w.advance(secs);
            return None;
        }
    };
    Some(out)
}

proptest! {
    #![proptest_config(ProptestConfig { cases: 512, ..ProptestConfig::default() })]

    #[test]
    fn random_command_sequences_never_reach_an_illegal_state(
        wf in workflow(),
        approved_at_start in any::<bool>(),
        ops in proptest::collection::vec(op(), 1..60),
    ) {
        let mut w = World::with_approved(wf, approved_at_start.then_some(1));
        // 0, 1 implementers (1 also reviews), 2 reviewer, 3 human, 4 verifier.
        let actors = vec![
            agent(&[Role::Implementer], "m-a"),
            agent(&[Role::Implementer, Role::Reviewer], "m-b"),
            reviewer("m-c"),
            human(),
            verifier(),
        ];
        let mut tokens = HashMap::new();
        let mut open_q = None;
        let mut spec_version = 1;

        for op in &ops {
            let Some((caller, cmd)) =
                command(op, &mut w, &actors, &mut tokens, &mut open_q, &mut spec_version)
            else {
                continue;
            };
            let before = w.task.clone();
            match decide(&w.task, &cmd, &w.ctx(&caller)) {
                Ok(events) => {
                    let after = apply_all(w.task.clone(), &events);
                    let check = invariants::check(&after);
                    prop_assert!(check.is_ok(), "{:?} after {} from {:?}", check, cmd.name(), before.state);
                    if before.state.is_terminal() {
                        prop_assert_eq!(after.state, before.state, "terminal states never change");
                    }
                    if after.state == TaskState::Done && before.state != TaskState::Done {
                        let via_review = matches!(cmd, Command::SubmitReview { .. });
                        let via_test = matches!(cmd, Command::CompleteTest { .. });
                        let review_ok = w.wf.review_gate == ReviewGate::None || via_review;
                        let test_ok = w.wf.test_gate == TestGate::None || via_review || via_test;
                        prop_assert!(review_ok && test_ok, "done via {} skips a gate", cmd.name());
                    }
                    w.task = after;
                }
                Err(_) => prop_assert_eq!(&w.task, &before),
            }
        }
    }
}
