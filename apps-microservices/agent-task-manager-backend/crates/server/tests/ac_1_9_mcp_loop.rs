//! AC-1.9 WHEN an MCP client connects to `/mcp` THE SYSTEM SHALL support the loop
//! list_ready → claim → report → ask → answer → claim → release (scripted rmcp client).

mod common;

use common::*;
use rmcp::model::CallToolRequestParams;
use rmcp::service::RunningService;
use rmcp::transport::StreamableHttpClientTransport;
use rmcp::transport::streamable_http_client::StreamableHttpClientTransportConfig;
use rmcp::{RoleClient, ServiceExt};
use serde_json::{Value, json};
use sqlx::PgPool;

async fn connect(app: &TestApp, token: &str) -> RunningService<RoleClient, ()> {
    let mut cfg = StreamableHttpClientTransportConfig::with_uri(format!("{}/mcp", app.base));
    cfg.auth_header = Some(token.to_string());
    cfg.allow_stateless = true;
    let transport = StreamableHttpClientTransport::from_config(cfg);
    ().serve(transport).await.expect("MCP initialize")
}

/// Call a tool; returns (is_error, summary line, JSON body).
async fn call(
    client: &RunningService<RoleClient, ()>,
    name: &'static str,
    args: Value,
) -> (bool, String, Value) {
    let res = client
        .call_tool(
            CallToolRequestParams::new(name).with_arguments(args.as_object().unwrap().clone()),
        )
        .await
        .expect("tool call");
    let text = res
        .content
        .iter()
        .find_map(|c| c.as_text().map(|t| t.text.clone()))
        .unwrap_or_default();
    let (summary, json) = text.split_once('\n').unwrap_or((&text, "null"));
    (
        res.is_error.unwrap_or(false),
        summary.to_string(),
        serde_json::from_str(json).unwrap_or(Value::Null),
    )
}

#[sqlx::test(migrations = "../../migrations")]
async fn agent_loop_over_mcp(pool: PgPool) {
    let app = spawn(pool).await;
    let project = app.project(no_gates()).await;
    let spec = app.approved_spec(project).await;
    let task = app.task(project, spec, "MCP task").await;
    let worker = app.implementer("worker").await;
    let helper = app.agent("helper", &["planner"], "model-b").await;
    let w = connect(&app, &worker.token).await;
    let h = connect(&app, &helper.token).await;

    // The server advertises the agent protocol and every tool.
    let info = w.peer_info().expect("server info");
    assert!(
        info.instructions
            .as_deref()
            .unwrap_or("")
            .contains("Heartbeat at least every lease_ttl/3")
    );
    let tools: Vec<String> = w
        .list_all_tools()
        .await
        .unwrap()
        .into_iter()
        .map(|t| t.name.to_string())
        .collect();
    for expected in [
        "list_ready",
        "get_task",
        "claim",
        "heartbeat",
        "report",
        "ask",
        "answer",
        "wait_for_updates",
        "create_task",
        "propose_spec_version",
        "repin",
        "submit_for_test",
        "release",
    ] {
        assert!(
            tools.iter().any(|t| t == expected),
            "missing tool {expected}: {tools:?}"
        );
    }

    // list_ready
    let (err, summary, body) = call(&w, "list_ready", json!({"project_id": project})).await;
    assert!(!err, "{summary}");
    assert_eq!(body["tasks"][0]["task_id"], task.to_string());
    // claim (best task) → lease token + context
    let (err, summary, body) = call(&w, "claim", json!({"project_id": project})).await;
    assert!(!err, "{summary} {body}");
    let token = body["lease_token"].as_str().unwrap().to_string();
    assert_eq!(body["context"]["task"]["state"], "working");
    // report
    let (err, summary, _) = call(
        &w,
        "report",
        json!({"task_id": task, "lease_token": token, "kind": "progress", "body": "read the spec"}),
    )
    .await;
    assert!(!err, "{summary}");
    // ask (blocking)
    let (err, summary, body) = call(&w, "ask", json!({"task_id": task, "lease_token": token, "question": "Which format?", "blocking": true, "handoff_note": "parser done, writer left"})).await;
    assert!(!err, "{summary}");
    let question = body["question_id"].as_str().unwrap().to_string();
    // A stale write is reported as an actionable tool error.
    let (err, summary, body) = call(
        &w,
        "heartbeat",
        json!({"task_id": task, "lease_token": token}),
    )
    .await;
    assert!(err, "{summary}");
    assert_eq!(body["code"], "stale_lease");
    // answer (by another agent)
    let (err, summary, _) = call(
        &h,
        "answer",
        json!({"question_id": question, "answer": "JSON"}),
    )
    .await;
    assert!(!err, "{summary}");
    // wait_for_updates sees the answer to the worker's question
    let (err, summary, body) = call(
        &w,
        "wait_for_updates",
        json!({"project_id": project, "cursor": 0, "timeout_s": 5}),
    )
    .await;
    assert!(!err, "{summary}");
    let types: Vec<&str> = body["events"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(|e| e["type"].as_str())
        .collect();
    assert!(types.contains(&"question.answered"), "{types:?}");
    // claim again (the asker has the preference)
    let (err, summary, body) =
        call(&w, "claim", json!({"project_id": project, "task_id": task})).await;
    assert!(!err, "{summary}");
    let token = body["lease_token"].as_str().unwrap().to_string();
    assert_eq!(
        body["context"]["last_handoff_note"],
        "parser done, writer left"
    );
    assert_eq!(body["context"]["questions"][0]["answer"], "JSON");
    // release
    let (err, summary, body) = call(&w, "release", json!({"task_id": task, "lease_token": token, "handoff_note": "writer half done, see branch feat/x"})).await;
    assert!(!err, "{summary}");
    assert_eq!(body["state"], "ready");

    let events = app.events(project).await;
    for ty in [
        "lease.claimed",
        "activity.reported",
        "question.asked",
        "question.answered",
        "lease.released",
    ] {
        assert!(count_type(&events, ty) >= 1, "missing {ty}");
    }
    w.cancel().await.ok();
    h.cancel().await.ok();
}

#[sqlx::test(migrations = "../../migrations")]
async fn gateway_identity_headers_resolve_the_actor(pool: PgPool) {
    use atb_server::service::auth::{self, NewActorInput, NewActorKind};
    let app = spawn(pool.clone()).await;
    let created = auth::create_actor_unchecked(
        &pool,
        NewActorInput {
            kind: NewActorKind::Agent,
            name: "via-gateway".into(),
            model: None,
            roles: vec!["implementer".into()],
            login: None,
            password: None,
            gateway_subject: Some("client:abc".into()),
        },
    )
    .await
    .unwrap();
    let me = |secret: &str, client: &str| {
        app.http
            .get(format!("{}/api/auth/me", app.base))
            .header("x-agent-gateway-secret", secret.to_string())
            .header("x-agent-client-id", client.to_string())
            .send()
    };
    let ok = me("test-gateway-secret", "abc").await.unwrap();
    assert_eq!(ok.status(), 200);
    assert_eq!(
        ok.json::<Value>().await.unwrap()["id"],
        created.id.to_string()
    );
    assert_eq!(me("wrong-secret", "abc").await.unwrap().status(), 401);
    assert_eq!(
        me("test-gateway-secret", "unknown").await.unwrap().status(),
        403
    );
}
