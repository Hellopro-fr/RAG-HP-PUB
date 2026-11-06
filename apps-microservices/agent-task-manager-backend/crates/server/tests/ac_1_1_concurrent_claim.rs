//! AC-1.1 WHEN 20 agents claim concurrently in a project with 5 ready tasks THE SYSTEM SHALL grant
//! exactly 5 leases, one per task.

mod common;

use std::collections::HashSet;

use common::*;
use reqwest::StatusCode;
use serde_json::json;
use sqlx::PgPool;

#[sqlx::test(migrations = "../../migrations")]
async fn twenty_concurrent_claimers_get_exactly_five_leases(pool: PgPool) {
    let app = spawn(pool.clone()).await;
    let project = app.project(no_gates()).await;
    let spec = app.approved_spec(project).await;
    for i in 0..5 {
        app.task(project, spec, &format!("task {i}")).await;
    }
    let mut agents = Vec::new();
    for i in 0..20 {
        agents.push(app.implementer(&format!("agent-{i}")).await);
    }
    let app = std::sync::Arc::new(app);
    let barrier = std::sync::Arc::new(tokio::sync::Barrier::new(20));
    let mut handles = Vec::new();
    for agent in agents {
        let app = app.clone();
        let barrier = barrier.clone();
        handles.push(tokio::spawn(async move {
            barrier.wait().await;
            app.post(
                As::Agent(&agent),
                &format!("/api/projects/{project}/claim"),
                json!({"role": "implementer"}),
            )
            .await
        }));
    }
    let mut granted = Vec::new();
    let mut refused = 0;
    for h in handles {
        let (status, body) = h.await.unwrap();
        match status {
            StatusCode::OK => granted.push(body["task_id"].as_str().unwrap().to_string()),
            StatusCode::CONFLICT => {
                assert_eq!(body["code"], "guard_failed", "{body}");
                assert_eq!(body["details"]["guard"], "nothing_to_claim", "{body}");
                refused += 1;
            }
            other => panic!("unexpected {other}: {body}"),
        }
    }
    let distinct: HashSet<_> = granted.iter().collect();
    assert_eq!(granted.len(), 5, "exactly five leases granted");
    assert_eq!(distinct.len(), 5, "one lease per task");
    assert_eq!(refused, 15);
    let leases: i64 = sqlx::query_scalar("SELECT count(*) FROM leases")
        .fetch_one(&pool)
        .await
        .unwrap();
    assert_eq!(leases, 5);
    let working: i64 = sqlx::query_scalar("SELECT count(*) FROM tasks WHERE state = 'working'")
        .fetch_one(&pool)
        .await
        .unwrap();
    assert_eq!(working, 5);
    assert_eq!(count_type(&app.events(project).await, "lease.claimed"), 5);
}
