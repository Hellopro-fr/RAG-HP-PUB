//! AC-1.3 WHEN a write carries an expired or foreign lease token THE SYSTEM SHALL reject it with
//! `stale_lease`.

mod common;

use std::time::Duration;

use common::*;
use reqwest::StatusCode;
use serde_json::json;
use sqlx::PgPool;

fn assert_stale(status: StatusCode, body: &serde_json::Value) {
    assert_eq!(status, StatusCode::CONFLICT, "{body}");
    assert_eq!(body["code"], "stale_lease", "{body}");
}

#[sqlx::test(migrations = "../../migrations")]
async fn foreign_wrong_missing_and_expired_tokens_are_stale(pool: PgPool) {
    let app = spawn(pool).await;
    let mut wf = no_gates();
    wf["lease_ttl_secs"] = json!(2);
    let project = app.project(wf).await;
    let spec = app.approved_spec(project).await;
    let task = app.task(project, spec, "fenced").await;
    let holder = app.implementer("holder").await;
    let intruder = app.implementer("intruder").await;
    let (_, token) = app.claim(project, &holder).await;
    let hb = format!("/api/tasks/{task}/heartbeat");
    let report = format!("/api/tasks/{task}/report");

    // Positive control: the holder's token works.
    let (s, body) = app
        .post(As::Agent(&holder), &hb, json!({"lease_token": token}))
        .await;
    assert_eq!(s, StatusCode::OK, "{body}");

    // Foreign: right token, wrong actor.
    let (s, body) = app
        .post(As::Agent(&intruder), &hb, json!({"lease_token": token}))
        .await;
    assert_stale(s, &body);
    // Wrong token, same actor.
    let (s, body) = app
        .post(
            As::Agent(&holder),
            &report,
            json!({"lease_token": "0".repeat(64), "kind": "progress", "body": "x"}),
        )
        .await;
    assert_stale(s, &body);
    // Missing token.
    let (s, body) = app.post(As::Agent(&holder), &hb, json!({})).await;
    assert_stale(s, &body);

    // Expired (no sweeper running, so the lease row is still there).
    tokio::time::sleep(Duration::from_millis(2300)).await;
    let (s, body) = app
        .post(As::Agent(&holder), &hb, json!({"lease_token": token}))
        .await;
    assert_stale(s, &body);
    let (s, body) = app
        .post(
            As::Agent(&holder),
            &format!("/api/tasks/{task}/release"),
            json!({"lease_token": token, "handoff_note": "late"}),
        )
        .await;
    assert_stale(s, &body);
    // Nothing was written by the rejected calls.
    assert_eq!(
        count_type(&app.events(project).await, "activity.reported"),
        0
    );
}
