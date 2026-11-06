//! AC-1.6 WHEN a mutating request reuses an idempotency key THE SYSTEM SHALL return the first
//! response without applying the change twice.

mod common;

use std::sync::Arc;

use common::*;
use reqwest::StatusCode;
use serde_json::json;
use sqlx::PgPool;

#[sqlx::test(migrations = "../../migrations")]
async fn reused_keys_replay_the_first_response(pool: PgPool) {
    let app = spawn(pool).await;
    let project = app.project(no_gates()).await;
    let spec = app.approved_spec(project).await;
    let task = app.task(project, spec, "retry me").await;
    let agent = app.implementer("retrier").await;

    // claim twice with the same key: same lease token, one lease.claimed.
    let claim_path = format!("/api/projects/{project}/claim");
    let body = json!({"role": "implementer"});
    let (s1, first) = app
        .post_idem(
            As::Agent(&agent),
            &claim_path,
            body.clone(),
            Some("claim-1"),
        )
        .await;
    let (s2, second) = app
        .post_idem(As::Agent(&agent), &claim_path, body, Some("claim-1"))
        .await;
    assert_eq!(
        (s1, s2),
        (StatusCode::OK, StatusCode::OK),
        "{first} {second}"
    );
    assert_eq!(first, second, "identical first response");
    assert_eq!(count_type(&app.events(project).await, "lease.claimed"), 1);
    let token = first["lease_token"].as_str().unwrap().to_string();

    // report: sequential retry.
    let report = json!({"lease_token": token, "kind": "progress", "body": "step 1"});
    let path = format!("/api/tasks/{task}/report");
    let (_, a) = app
        .post_idem(As::Agent(&agent), &path, report.clone(), Some("r-1"))
        .await;
    let (_, b) = app
        .post_idem(As::Agent(&agent), &path, report.clone(), Some("r-1"))
        .await;
    assert_eq!(a, b);
    assert_eq!(
        count_type(&app.events(project).await, "activity.reported"),
        1
    );

    // report: 10 concurrent duplicates.
    let app = Arc::new(app);
    let agent = Arc::new(agent);
    let mut handles = Vec::new();
    for _ in 0..10 {
        let (app, agent, path, report) = (app.clone(), agent.clone(), path.clone(), report.clone());
        handles.push(tokio::spawn(async move {
            app.post_idem(As::Agent(&agent), &path, report, Some("r-2"))
                .await
        }));
    }
    let mut bodies = Vec::new();
    for h in handles {
        let (s, body) = h.await.unwrap();
        assert_eq!(s, StatusCode::OK, "{body}");
        bodies.push(body);
    }
    assert!(
        bodies.windows(2).all(|w| w[0] == w[1]),
        "all replies identical"
    );
    assert_eq!(
        count_type(&app.events(project).await, "activity.reported"),
        2
    );

    // A different key is a different request.
    let (_, c) = app
        .post_idem(As::Agent(&agent), &path, report, Some("r-3"))
        .await;
    assert_ne!(c, bodies[0]);
    assert_eq!(
        count_type(&app.events(project).await, "activity.reported"),
        3
    );
}

#[sqlx::test(migrations = "../../migrations")]
async fn keys_are_scoped_per_actor(pool: PgPool) {
    let app = spawn(pool).await;
    let project = app.project(no_gates()).await;
    let spec = app.approved_spec(project).await;
    app.task(project, spec, "one").await;
    app.task(project, spec, "two").await;
    let a = app.implementer("a").await;
    let b = app.implementer("b").await;
    let path = format!("/api/projects/{project}/claim");
    let (_, ra) = app
        .post_idem(
            As::Agent(&a),
            &path,
            json!({"role": "implementer"}),
            Some("same"),
        )
        .await;
    let (_, rb) = app
        .post_idem(
            As::Agent(&b),
            &path,
            json!({"role": "implementer"}),
            Some("same"),
        )
        .await;
    assert_ne!(ra["task_id"], rb["task_id"], "two actors, two claims");
}
