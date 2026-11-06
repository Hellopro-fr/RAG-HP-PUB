//! AC-1.8 WHEN projections are rebuilt from the event log THE SYSTEM SHALL produce the same rows as
//! the live tables (volatile timing fields excepted).

mod common;

use std::time::Duration;

use atb_server::service::{rebuild, sweeper};
use common::*;
use reqwest::StatusCode;
use serde_json::json;
use sqlx::PgPool;

async fn ok(app: &TestApp, who: As<'_>, path: &str, body: serde_json::Value) -> serde_json::Value {
    let (s, out) = app.post(who, path, body).await;
    assert!(s.is_success(), "{path}: {s} {out}");
    out
}

#[sqlx::test(migrations = "../../migrations")]
async fn replaying_the_log_reproduces_every_projection(pool: PgPool) {
    let app = spawn(pool.clone()).await;
    let mut wf = no_gates();
    wf["lease_ttl_secs"] = json!(2);
    let project = app.project(wf).await;
    let spec = app.approved_spec(project).await;
    let a = app.task(project, spec, "A").await;
    let b = app
        .task_with(
            project,
            json!({"title": "B", "spec_id": spec, "blocked_by": [a], "priority": 5}),
        )
        .await;
    let c = app.task(project, spec, "C").await;
    let one = app.implementer("one").await;
    let two = app.implementer("two").await;

    // one: claim A (priority order puts B first but B is blocked), report, ask (non-blocking), release.
    let (t, tok) = app.claim(project, &one).await;
    assert_eq!(t, a);
    ok(
        &app,
        As::Agent(&one),
        &format!("/api/tasks/{a}/report"),
        json!({"lease_token": tok, "kind": "progress", "body": "half done"}),
    )
    .await;
    ok(
        &app,
        As::Agent(&one),
        &format!("/api/tasks/{a}/ask"),
        json!({"lease_token": tok, "question": "fyi?", "blocking": false}),
    )
    .await;
    ok(
        &app,
        As::Agent(&one),
        &format!("/api/tasks/{a}/release"),
        json!({"lease_token": tok, "handoff_note": "parser done"}),
    )
    .await;
    // two: claim A, blocking question, human answers, two reclaims and finishes A.
    let (_, tok) = app.claim(project, &two).await;
    let asked = ok(&app, As::Agent(&two), &format!("/api/tasks/{a}/ask"), json!({"lease_token": tok, "question": "csv?", "blocking": true, "handoff_note": "waiting"})).await;
    let q = asked["question_id"].as_str().unwrap();
    ok(
        &app,
        As::Admin,
        &format!("/api/questions/{q}/answer"),
        json!({"answer": "yes"}),
    )
    .await;
    let (_, tok) = app.claim(project, &two).await;
    ok(
        &app,
        As::Agent(&two),
        &format!("/api/tasks/{a}/submit-for-test"),
        json!({"lease_token": tok, "commit_sha": "abc123", "branch": "feat/a"}),
    )
    .await;
    // B is unblocked; one claims it and lets the lease expire.
    let (t, _) = app.claim(project, &one).await;
    assert_eq!(t, b);
    tokio::time::sleep(Duration::from_millis(2300)).await;
    assert_eq!(sweeper::sweep_once(&app.st).await.unwrap(), 1);
    // A human edits B, links C to B, and a new spec version makes C outdated, then repins C.
    let ctx = app.task_state(b).await;
    let (s, out) = app
        .patch(
            As::Admin,
            &format!("/api/tasks/{b}"),
            json!({"expected_version": ctx["task"]["version"], "title": "B (renamed)"}),
        )
        .await;
    assert_eq!(s, StatusCode::OK, "{out}");
    ok(
        &app,
        As::Admin,
        &format!("/api/tasks/{c}/links"),
        json!({"to_id": b, "kind": "related"}),
    )
    .await;
    ok(&app, As::Admin, &format!("/api/specs/{spec}/versions"), json!({"body_md": "v2", "acceptance_criteria": [{"id": "AC-1", "text": "it works better", "verify": {"kind": "human"}}]})).await;
    ok(
        &app,
        As::Admin,
        &format!("/api/specs/{spec}/versions/2/approve"),
        json!({}),
    )
    .await;
    // Every non-terminal task pinned to v1 is now outdated (B and C; A is done).
    assert_eq!(app.task_state(c).await["task"]["spec_outdated"], true);
    assert_eq!(app.task_state(b).await["task"]["spec_outdated"], true);
    assert_eq!(app.task_state(a).await["task"]["spec_outdated"], false);
    ok(&app, As::Admin, &format!("/api/tasks/{c}/repin"), json!({})).await;
    ok(&app, As::Admin, &format!("/api/tasks/{b}/repin"), json!({})).await;
    ok(
        &app,
        As::Admin,
        &format!("/api/tasks/{c}/cancel"),
        json!({"reason": "duplicate"}),
    )
    .await;
    // B is held at check time, so the leases table is compared too.
    let (t, tok) = app.claim(project, &one).await;
    assert_eq!(t, b);
    ok(
        &app,
        As::Agent(&one),
        &format!("/api/tasks/{b}/heartbeat"),
        json!({"lease_token": tok}),
    )
    .await;

    let report = rebuild::check_project(&pool, project).await.unwrap();
    assert!(report.ok, "{report:#?}");
    assert!(
        report.events > 30,
        "a real workload: {} events",
        report.events
    );
    let rows = |t: &str| {
        report
            .tables
            .iter()
            .find(|d| d.table == t)
            .unwrap()
            .live_rows
    };
    assert_eq!(rows("tasks"), 3);
    assert_eq!(rows("leases"), 1);
    assert!(rows("attempts") >= 5);
    assert_eq!(rows("questions"), 2);
    assert_eq!(rows("spec_versions"), 2);
    assert_eq!(rows("task_links"), 2);

    // Negative control: a projection row that the log does not explain is detected.
    sqlx::query("UPDATE tasks SET title = 'tampered' WHERE id = $1")
        .bind(c)
        .execute(&pool)
        .await
        .unwrap();
    let report = rebuild::check_project(&pool, project).await.unwrap();
    assert!(!report.ok);
    let tasks = report.tables.iter().find(|d| d.table == "tasks").unwrap();
    assert_eq!((tasks.only_live, tasks.only_rebuilt), (1, 1));
}
