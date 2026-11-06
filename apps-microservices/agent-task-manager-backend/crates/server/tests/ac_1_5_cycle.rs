//! AC-1.5 WHEN a `blocks` link would create a cycle THE SYSTEM SHALL reject it.

mod common;

use common::*;
use reqwest::StatusCode;
use serde_json::json;
use sqlx::PgPool;

#[sqlx::test(migrations = "../../migrations")]
async fn blocks_links_stay_acyclic(pool: PgPool) {
    let app = spawn(pool).await;
    let project = app.project(no_gates()).await;
    let spec = app.approved_spec(project).await;
    let a = app.task(project, spec, "A").await;
    let b = app
        .task_with(
            project,
            json!({"title": "B", "spec_id": spec, "blocked_by": [a]}),
        )
        .await;
    let c = app.task(project, spec, "C").await;
    let link = |from, to| {
        (
            format!("/api/tasks/{from}/links"),
            json!({"to_id": to, "kind": "blocks"}),
        )
    };

    // B -> C: fine (A -> B -> C).
    let (path, body) = link(b, c);
    let (s, out) = app.post(As::Admin, &path, body).await;
    assert_eq!(s, StatusCode::OK, "{out}");
    // A -> C: a shortcut, still a DAG.
    let (path, body) = link(a, c);
    let (s, out) = app.post(As::Admin, &path, body).await;
    assert_eq!(s, StatusCode::OK, "{out}");
    // C -> A closes A -> B -> C -> A.
    let (path, body) = link(c, a);
    let (s, out) = app.post(As::Admin, &path, body).await;
    assert_eq!(s, StatusCode::CONFLICT, "{out}");
    assert_eq!(out["details"]["guard"], "cycle", "{out}");
    // Self-loop.
    let (path, body) = link(a, a);
    let (s, out) = app.post(As::Admin, &path, body).await;
    assert_eq!(out["details"]["guard"], "cycle", "{s} {out}");
    // A non-blocking relation back is allowed (not part of the DAG).
    let (s, out) = app
        .post(
            As::Admin,
            &format!("/api/tasks/{c}/links"),
            json!({"to_id": a, "kind": "related"}),
        )
        .await;
    assert_eq!(s, StatusCode::OK, "{out}");
    // The rejected link was not written; B and C show as blocked on the board.
    let (_, board) = app
        .get(As::Admin, &format!("/api/projects/{project}/board"))
        .await;
    let blocks = board["links"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|l| l["kind"] == "blocks")
        .count();
    assert_eq!(blocks, 3);
    let blocked: Vec<_> = board["tasks"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|t| t["blocked"] == true)
        .collect();
    assert_eq!(blocked.len(), 2);
}
