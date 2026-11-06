//! AC-1.4 WHEN an agent asks a blocking question THE SYSTEM SHALL move the task to input_required
//! and release the lease; WHEN the question is answered THE SYSTEM SHALL return the task to ready
//! with a claim preference for the asker.

mod common;

use common::*;
use reqwest::StatusCode;
use serde_json::json;
use sqlx::PgPool;

#[sqlx::test(migrations = "../../migrations")]
async fn blocking_question_releases_and_answer_prefers_the_asker(pool: PgPool) {
    let app = spawn(pool).await;
    let project = app.project(no_gates()).await;
    let spec = app.approved_spec(project).await;
    let task = app.task(project, spec, "ambiguous").await;
    let asker = app.implementer("asker").await;
    let other = app.implementer("other").await;
    let (_, token) = app.claim(project, &asker).await;

    // Blocking ask without a handoff note is refused.
    let (s, body) = app
        .post(
            As::Agent(&asker),
            &format!("/api/tasks/{task}/ask"),
            json!({"lease_token": token, "question": "JSON or CSV?", "blocking": true}),
        )
        .await;
    assert_eq!(s, StatusCode::UNPROCESSABLE_ENTITY, "{body}");

    let (s, body) = app
        .post(
            As::Agent(&asker),
            &format!("/api/tasks/{task}/ask"),
            json!({"lease_token": token, "question": "JSON or CSV?", "blocking": true,
                   "options": ["json", "csv"], "handoff_note": "parser done; writer left"}),
        )
        .await;
    assert_eq!(s, StatusCode::OK, "{body}");
    assert_eq!(body["state"], "input_required");
    let question = body["question_id"].as_str().unwrap().to_string();
    let ctx = app.task_state(task).await;
    assert_eq!(ctx["task"]["state"], "input_required");
    assert!(ctx["task"]["lease"].is_null(), "lease released");
    // The old token is now stale.
    let (s, body) = app
        .post(
            As::Agent(&asker),
            &format!("/api/tasks/{task}/heartbeat"),
            json!({"lease_token": token}),
        )
        .await;
    assert_eq!(body["code"], "stale_lease", "{s} {body}");

    // The asker cannot answer itself.
    let (s, body) = app
        .post(
            As::Agent(&asker),
            &format!("/api/questions/{question}/answer"),
            json!({"answer": "json"}),
        )
        .await;
    assert_eq!(s, StatusCode::FORBIDDEN, "{body}");
    // A human answers.
    let (s, body) = app
        .post(
            As::Admin,
            &format!("/api/questions/{question}/answer"),
            json!({"answer": "json"}),
        )
        .await;
    assert_eq!(s, StatusCode::OK, "{body}");
    let ctx = app.task_state(task).await;
    assert_eq!(ctx["task"]["state"], "ready");
    assert_eq!(ctx["task"]["preferred_actor_id"], asker.id.to_string());
    assert_eq!(ctx["questions"][0]["answer"], "json");

    // Another agent cannot claim during the grace window...
    let (s, body) = app
        .post(
            As::Agent(&other),
            &format!("/api/projects/{project}/claim"),
            json!({"role": "implementer"}),
        )
        .await;
    assert_eq!(s, StatusCode::CONFLICT, "{body}");
    let (s, body) = app
        .post(
            As::Agent(&other),
            &format!("/api/tasks/{task}/claim"),
            json!({"role": "implementer"}),
        )
        .await;
    assert_eq!(body["details"]["guard"], "preferred_actor", "{s} {body}");
    // ...the asker can.
    let (claimed, _) = app.claim(project, &asker).await;
    assert_eq!(claimed, task);
}
