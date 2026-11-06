//! AC-1.7 (server half) WHEN a state change commits THE SYSTEM SHALL show it on every open stream
//! within 1 s; WHEN a client reconnects with `Last-Event-ID` THE SYSTEM SHALL replay missed events
//! in order with no duplicates. (The browser half is e2e/board-live.spec.ts in the frontend.)

mod common;

use std::time::{Duration, Instant};

use common::*;
use futures::StreamExt;
use reqwest::StatusCode;
use serde_json::{Value, json};
use sqlx::PgPool;
use tokio::sync::mpsc;
use uuid::Uuid;

#[derive(Debug, Clone)]
struct SseEvent {
    id: i64,
    event: String,
    data: Value,
}

/// Open the project stream and push parsed events into a channel until dropped.
async fn open(
    app: &TestApp,
    project: Uuid,
    last_event_id: Option<i64>,
) -> (mpsc::Receiver<SseEvent>, tokio::task::JoinHandle<()>) {
    let mut req = app
        .http
        .get(format!("{}/api/projects/{project}/stream", app.base))
        .header("cookie", &app.admin_cookie)
        .header("accept", "text/event-stream");
    if let Some(id) = last_event_id {
        req = req.header("last-event-id", id.to_string());
    }
    let res = req.send().await.unwrap();
    assert_eq!(res.status(), StatusCode::OK);
    assert_eq!(res.headers()["content-type"], "text/event-stream");
    let (tx, rx) = mpsc::channel(1024);
    let handle = tokio::spawn(async move {
        let mut body = res.bytes_stream();
        let mut buf = String::new();
        while let Some(Ok(chunk)) = body.next().await {
            buf.push_str(&String::from_utf8_lossy(&chunk));
            while let Some(end) = buf.find("\n\n") {
                let block: String = buf.drain(..end + 2).collect();
                let (mut id, mut event, mut data) = (None, String::new(), String::new());
                for line in block.lines() {
                    if let Some(v) = line.strip_prefix("id:") {
                        id = v.trim().parse().ok();
                    } else if let Some(v) = line.strip_prefix("event:") {
                        event = v.trim().to_string();
                    } else if let Some(v) = line.strip_prefix("data:") {
                        data.push_str(v.trim());
                    }
                }
                if let Some(id) = id {
                    let data = serde_json::from_str(&data).unwrap_or(Value::Null);
                    if tx.send(SseEvent { id, event, data }).await.is_err() {
                        return;
                    }
                }
            }
        }
    });
    (rx, handle)
}

async fn next(rx: &mut mpsc::Receiver<SseEvent>, within: Duration) -> SseEvent {
    tokio::time::timeout(within, rx.recv())
        .await
        .expect("no SSE event in time")
        .expect("stream closed")
}

#[sqlx::test(migrations = "../../migrations")]
async fn live_within_one_second_and_gapless_replay(pool: PgPool) {
    let app = spawn(pool).await;
    let project = app.project(no_gates()).await;
    let spec = app.approved_spec(project).await;
    let task = app.task(project, spec, "watched").await;
    let agent = app.implementer("streamer").await;

    // Board snapshot, then stream from its seq: exactly the later changes arrive.
    let (_, board) = app
        .get(As::Admin, &format!("/api/projects/{project}/board"))
        .await;
    let snapshot_seq = board["seq"].as_i64().unwrap();
    let (mut rx, reader) = open(&app, project, Some(snapshot_seq)).await;
    // Second open board: every board sees the change.
    let (mut rx2, reader2) = open(&app, project, Some(snapshot_seq)).await;

    let t0 = Instant::now();
    let (claimed, token) = app.claim(project, &agent).await;
    assert_eq!(claimed, task);
    let first = next(&mut rx, Duration::from_secs(1)).await;
    let latency = t0.elapsed();
    assert!(
        latency < Duration::from_secs(1),
        "state change took {latency:?}"
    );
    assert_eq!(
        first.id,
        snapshot_seq + 1,
        "first event right after the snapshot"
    );
    assert_eq!(first.event, "task.state_changed");
    assert_eq!(first.data["payload"]["to"], "working");
    let second = next(&mut rx, Duration::from_secs(1)).await;
    assert_eq!(
        (second.id, second.event.as_str()),
        (snapshot_seq + 2, "lease.claimed")
    );
    let other_board = next(&mut rx2, Duration::from_secs(1)).await;
    assert_eq!(other_board.id, first.id);
    let mut last_seen = second.id;

    // Disconnect, then miss three events.
    reader.abort();
    drop(rx);
    let report = format!("/api/tasks/{task}/report");
    for i in 0..3 {
        let (s, body) = app
            .post(
                As::Agent(&agent),
                &report,
                json!({"lease_token": token, "kind": "progress", "body": format!("step {i}")}),
            )
            .await;
        assert_eq!(s, StatusCode::OK, "{body}");
    }

    // Reconnect with Last-Event-ID: the three missed events, in order, then live ones.
    let (mut rx, _reader) = open(&app, project, Some(last_seen)).await;
    for i in 0..3 {
        let ev = next(&mut rx, Duration::from_secs(2)).await;
        assert_eq!(ev.id, last_seen + 1, "gapless and in order");
        assert_eq!(ev.event, "activity.reported");
        assert_eq!(ev.data["payload"]["body"], format!("step {i}"));
        last_seen = ev.id;
    }
    let (s, _) = app
        .post(
            As::Agent(&agent),
            &report,
            json!({"lease_token": token, "kind": "action", "body": "live"}),
        )
        .await;
    assert_eq!(s, StatusCode::OK);
    let live = next(&mut rx, Duration::from_secs(1)).await;
    assert_eq!(
        live.id,
        last_seen + 1,
        "no duplicate, no gap between replay and live"
    );
    assert_eq!(live.data["payload"]["body"], "live");
    // Nothing else is pending: no duplicate delivery.
    assert!(
        tokio::time::timeout(Duration::from_millis(500), rx.recv())
            .await
            .is_err(),
        "unexpected extra event"
    );
    reader2.abort();
}

#[sqlx::test(migrations = "../../migrations")]
async fn concurrent_writers_produce_one_gapless_ordered_stream(pool: PgPool) {
    let app = spawn(pool).await;
    let project = app.project(no_gates()).await;
    let spec = app.approved_spec(project).await;
    let (_, board) = app
        .get(As::Admin, &format!("/api/projects/{project}/board"))
        .await;
    let start = board["seq"].as_i64().unwrap();
    let (mut rx, _reader) = open(&app, project, Some(start)).await;
    let app = std::sync::Arc::new(app);
    let mut handles = Vec::new();
    for i in 0..20 {
        let app = app.clone();
        handles.push(tokio::spawn(async move {
            app.task(project, spec, &format!("parallel {i}")).await;
        }));
    }
    for h in handles {
        h.await.unwrap();
    }
    for expected in (start + 1..).take(20) {
        let ev = next(&mut rx, Duration::from_secs(3)).await;
        assert_eq!(
            ev.id, expected,
            "per-project seq order equals delivery order"
        );
        assert_eq!(ev.event, "task.created");
    }
}
