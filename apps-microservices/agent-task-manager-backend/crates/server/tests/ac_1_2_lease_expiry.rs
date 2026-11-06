//! AC-1.2 WHEN a lease expires without a heartbeat THE SYSTEM SHALL return the task to ready within
//! 10 s and record `lease.expired` with a handoff note.

mod common;

use std::time::{Duration, Instant};

use atb_server::service::sweeper;
use common::*;
use serde_json::json;
use sqlx::PgPool;

#[sqlx::test(migrations = "../../migrations")]
async fn expired_lease_returns_task_to_ready_with_handoff_note(pool: PgPool) {
    let app = spawn_with(pool, |cfg| cfg.sweep_interval_secs = 1).await;
    tokio::spawn(sweeper::run(app.st.clone()));
    let mut wf = no_gates();
    wf["lease_ttl_secs"] = json!(1);
    let project = app.project(wf).await;
    let spec = app.approved_spec(project).await;
    let task = app.task(project, spec, "will be abandoned").await;
    let agent = app.implementer("crashy").await;
    app.claim(project, &agent).await;
    let started = Instant::now();
    // The agent "crashes": no heartbeat.
    loop {
        let ctx = app.task_state(task).await;
        if ctx["task"]["state"] == "ready" {
            assert!(ctx["task"]["lease"].is_null(), "lease removed");
            break;
        }
        assert!(
            started.elapsed() < Duration::from_secs(10),
            "task did not return to ready within 10 s"
        );
        tokio::time::sleep(Duration::from_millis(200)).await;
    }
    let events = app.events(project).await;
    let expired: Vec<_> = events
        .iter()
        .filter(|e| e["type"] == "lease.expired")
        .collect();
    assert_eq!(expired.len(), 1);
    let note = expired[0]["payload"]["handoff_note"].as_str().unwrap();
    assert!(note.contains("Automatic handoff"), "{note}");
    let ended = events
        .iter()
        .find(|e| e["type"] == "attempt.ended")
        .expect("attempt.ended");
    assert_eq!(ended["payload"]["outcome"], "expired");
    // The handoff note is visible to the next agent.
    let ctx = app.task_state(task).await;
    assert!(
        ctx["last_handoff_note"]
            .as_str()
            .unwrap()
            .contains("Automatic handoff")
    );
}
