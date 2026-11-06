//! Integration-test harness: the real router on a random port, a real Postgres database per test
//! (`sqlx::test`), the realtime hub running, a logged-in human admin, and helpers to create agents,
//! projects, approved specs and tasks.
#![allow(dead_code)]

use std::time::Duration;

use atb_server::service::auth::{self, NewActorInput, NewActorKind};
use atb_server::{AppState, Config, api};
use reqwest::StatusCode;
use serde_json::{Value, json};
use sqlx::PgPool;
use uuid::Uuid;

pub const ADMIN_LOGIN: &str = "admin";
pub const ADMIN_PASSWORD: &str = "correct-horse-battery";

pub struct TestApp {
    pub base: String,
    pub st: AppState,
    pub http: reqwest::Client,
    pub admin_cookie: String,
}

pub struct Agent {
    pub id: Uuid,
    pub token: String,
}

#[derive(Clone, Copy)]
pub enum As<'a> {
    Admin,
    Agent(&'a Agent),
}

pub fn no_gates() -> Value {
    json!({
        "spec_gate": true, "test_gate": "none", "review_gate": "none",
        "require_different_model": false, "max_rejections": 3,
        "lease_ttl_secs": 600, "preferred_grace_secs": 120
    })
}

pub async fn spawn(pool: PgPool) -> TestApp {
    spawn_with(pool, |_| {}).await
}

pub async fn spawn_with(pool: PgPool, tweak: impl FnOnce(&mut Config)) -> TestApp {
    let mut cfg = Config::for_tests(String::new());
    tweak(&mut cfg);
    let st = AppState::new(pool.clone(), cfg);
    tokio::spawn(st.hub.clone().run(pool.clone()));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let app = api::router(st.clone());
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    auth::bootstrap_admin(&pool, ADMIN_LOGIN, ADMIN_PASSWORD)
        .await
        .expect("bootstrap admin");
    let http = reqwest::Client::builder()
        .timeout(Duration::from_secs(60))
        .build()
        .unwrap();
    let base = format!("http://{addr}");
    let res = http
        .post(format!("{base}/api/auth/login"))
        .json(&json!({"login": ADMIN_LOGIN, "password": ADMIN_PASSWORD}))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::OK, "admin login");
    let cookie = res
        .headers()
        .get("set-cookie")
        .unwrap()
        .to_str()
        .unwrap()
        .split(';')
        .next()
        .unwrap()
        .to_string();
    // Give the LISTEN connection a moment to subscribe before tests generate events.
    tokio::time::sleep(Duration::from_millis(200)).await;
    TestApp {
        base,
        st,
        http,
        admin_cookie: cookie,
    }
}

impl TestApp {
    pub async fn agent(&self, name: &str, roles: &[&str], model: &str) -> Agent {
        let created = auth::create_actor_unchecked(
            &self.st.pool,
            NewActorInput {
                kind: NewActorKind::Agent,
                name: name.into(),
                model: Some(model.into()),
                roles: roles.iter().map(|r| r.to_string()).collect(),
                login: None,
                password: None,
                gateway_subject: None,
            },
        )
        .await
        .expect("create agent");
        Agent {
            id: created.id,
            token: created.token.expect("agent token"),
        }
    }

    pub async fn implementer(&self, name: &str) -> Agent {
        self.agent(name, &["implementer"], "model-a").await
    }

    fn req(&self, who: As<'_>, method: reqwest::Method, path: &str) -> reqwest::RequestBuilder {
        let r = self.http.request(method, format!("{}{path}", self.base));
        match who {
            As::Admin => r.header("cookie", &self.admin_cookie),
            As::Agent(a) => r.bearer_auth(&a.token),
        }
    }

    pub async fn get(&self, who: As<'_>, path: &str) -> (StatusCode, Value) {
        let res = self
            .req(who, reqwest::Method::GET, path)
            .send()
            .await
            .unwrap();
        let status = res.status();
        (status, res.json().await.unwrap_or(Value::Null))
    }

    pub async fn post(&self, who: As<'_>, path: &str, body: Value) -> (StatusCode, Value) {
        self.post_idem(who, path, body, None).await
    }

    pub async fn post_idem(
        &self,
        who: As<'_>,
        path: &str,
        body: Value,
        key: Option<&str>,
    ) -> (StatusCode, Value) {
        let mut r = self.req(who, reqwest::Method::POST, path).json(&body);
        if let Some(k) = key {
            r = r.header("idempotency-key", k);
        }
        let res = r.send().await.unwrap();
        let status = res.status();
        (status, res.json().await.unwrap_or(Value::Null))
    }

    pub async fn patch(&self, who: As<'_>, path: &str, body: Value) -> (StatusCode, Value) {
        let res = self
            .req(who, reqwest::Method::PATCH, path)
            .json(&body)
            .send()
            .await
            .unwrap();
        let status = res.status();
        (status, res.json().await.unwrap_or(Value::Null))
    }

    pub async fn project(&self, workflow: Value) -> Uuid {
        let (s, body) = self
            .post(
                As::Admin,
                "/api/projects",
                json!({"name": "Test project", "workflow": workflow}),
            )
            .await;
        assert_eq!(s, StatusCode::CREATED, "{body}");
        body["id"].as_str().unwrap().parse().unwrap()
    }

    /// A spec with version 1 approved.
    pub async fn approved_spec(&self, project: Uuid) -> Uuid {
        let (s, body) = self
            .post(
                As::Admin,
                &format!("/api/projects/{project}/specs"),
                json!({
                    "title": "Spec",
                    "body_md": "Do the thing.",
                    "acceptance_criteria": [
                        {"id": "AC-1", "text": "it works", "verify": {"kind": "command", "command": "true"}}
                    ]
                }),
            )
            .await;
        assert_eq!(s, StatusCode::CREATED, "{body}");
        let spec: Uuid = body["spec_id"].as_str().unwrap().parse().unwrap();
        let (s, body) = self
            .post(
                As::Admin,
                &format!("/api/specs/{spec}/versions/1/approve"),
                json!({}),
            )
            .await;
        assert_eq!(s, StatusCode::OK, "{body}");
        spec
    }

    pub async fn task(&self, project: Uuid, spec: Uuid, title: &str) -> Uuid {
        self.task_with(project, json!({"title": title, "spec_id": spec}))
            .await
    }

    pub async fn task_with(&self, project: Uuid, body: Value) -> Uuid {
        let (s, out) = self
            .post(As::Admin, &format!("/api/projects/{project}/tasks"), body)
            .await;
        assert_eq!(s, StatusCode::CREATED, "{out}");
        out["task_id"].as_str().unwrap().parse().unwrap()
    }

    /// Claim the best task as `agent`; returns (task_id, lease_token).
    pub async fn claim(&self, project: Uuid, agent: &Agent) -> (Uuid, String) {
        let (s, body) = self
            .post(
                As::Agent(agent),
                &format!("/api/projects/{project}/claim"),
                json!({"role": "implementer"}),
            )
            .await;
        assert_eq!(s, StatusCode::OK, "{body}");
        (
            body["task_id"].as_str().unwrap().parse().unwrap(),
            body["lease_token"].as_str().unwrap().to_string(),
        )
    }

    pub async fn task_state(&self, task: Uuid) -> Value {
        let (s, body) = self.get(As::Admin, &format!("/api/tasks/{task}")).await;
        assert_eq!(s, StatusCode::OK, "{body}");
        body
    }

    pub async fn events(&self, project: Uuid) -> Vec<Value> {
        let (s, body) = self
            .get(
                As::Admin,
                &format!("/api/projects/{project}/events?after=0&limit=5000"),
            )
            .await;
        assert_eq!(s, StatusCode::OK, "{body}");
        body.as_array().unwrap().clone()
    }
}

pub fn count_type(events: &[Value], ty: &str) -> usize {
    events.iter().filter(|e| e["type"] == ty).count()
}
