//! Admin / Classique levels and per-user / per-team permissions (validated maquette, "Accès").
mod common;

use atb_server::directory::{DirGroup, DirUser, Directory};
use common::{As, spawn_full};
use reqwest::StatusCode;
use serde_json::json;
use sqlx::PgPool;

const ANA: &str = "ana@example.com";
const BOB: &str = "bob@example.com";

fn directory() -> Directory {
    Directory {
        users: vec![
            DirUser {
                email: ANA.into(),
                display_name: "Ana".into(),
                is_allowed: true,
            },
            DirUser {
                email: BOB.into(),
                display_name: "Bob".into(),
                is_allowed: true,
            },
        ],
        groups: vec![
            DirGroup {
                id: "g-cat".into(),
                name: "Catalogue".into(),
                description: String::new(),
                members: vec![ANA.into()],
            },
            DirGroup {
                id: "g-data".into(),
                name: "Data".into(),
                description: String::new(),
                members: vec![ANA.into(), BOB.into()],
            },
        ],
    }
}

fn new_project() -> serde_json::Value {
    json!({"name": "P", "workflow": common::no_gates()})
}

#[sqlx::test(migrator = "atb_server::MIGRATOR")]
async fn priority_individual_then_teams_then_refused(pool: PgPool) {
    let app = spawn_full(pool, |_| {}, Some(directory())).await;
    let (ana, ana_cookie) = app.human(ANA).await;
    let ana_as = As::Cookie(&ana_cookie);

    // Classique, no setting: refused by default.
    let (s, body) = app.post(ana_as, "/api/projects", new_project()).await;
    assert_eq!(s, StatusCode::FORBIDDEN, "{body}");
    let (_, me) = app.get(ana_as, "/api/auth/me").await;
    assert_eq!(me["level"], "classic");
    assert_eq!(me["permissions"], json!([]));

    // A team denies, another allows: one allow is enough.
    let (s, _) = app
        .put(
            As::Admin,
            "/api/access/teams/g-data/permissions/projects.create",
            json!({"effect": "deny"}),
        )
        .await;
    assert_eq!(s, StatusCode::NO_CONTENT);
    let (s, _) = app
        .put(
            As::Admin,
            "/api/access/teams/g-cat/permissions/projects.create",
            json!({"effect": "allow"}),
        )
        .await;
    assert_eq!(s, StatusCode::NO_CONTENT);
    let (s, body) = app.post(ana_as, "/api/projects", new_project()).await;
    assert_eq!(s, StatusCode::CREATED, "{body}");

    // The individual setting wins even when more restrictive.
    let path = format!("/api/access/users/{ana}/permissions/projects.create");
    let (s, _) = app.put(As::Admin, &path, json!({"effect": "deny"})).await;
    assert_eq!(s, StatusCode::NO_CONTENT);
    let (s, _) = app.post(ana_as, "/api/projects", new_project()).await;
    assert_eq!(s, StatusCode::FORBIDDEN);

    let (s, detail) = app
        .get(As::Admin, &format!("/api/access/users/{ana}"))
        .await;
    assert_eq!(s, StatusCode::OK);
    let row = detail["permissions"]
        .as_array()
        .unwrap()
        .iter()
        .find(|p| p["permission"] == "projects.create")
        .unwrap()
        .clone();
    assert_eq!(row["setting"], "deny");
    assert_eq!(row["allowed"], false);
    assert_eq!(row["source"]["kind"], "individual");
    assert_eq!(row["source"]["teams_outcome"], "allowed");
    assert_eq!(row["source"]["teams"], json!(["Catalogue"]));

    // Back to "inherit": the teams decide again.
    let (s, _) = app.put(As::Admin, &path, json!({"effect": null})).await;
    assert_eq!(s, StatusCode::NO_CONTENT);
    let (s, _) = app.post(ana_as, "/api/projects", new_project()).await;
    assert_eq!(s, StatusCode::CREATED);

    // The team view counts members with an individual exception.
    let path = format!("/api/access/users/{ana}/permissions/agents.view");
    app.put(As::Admin, &path, json!({"effect": "allow"})).await;
    let (_, team) = app.get(As::Admin, "/api/access/teams/g-data").await;
    let views = team["permissions"]
        .as_array()
        .unwrap()
        .iter()
        .find(|p| p["permission"] == "agents.view")
        .unwrap()
        .clone();
    assert_eq!(views["exceptions"], 1);
    assert_eq!(team["members"].as_array().unwrap().len(), 2);
}

#[sqlx::test(migrator = "atb_server::MIGRATOR")]
async fn only_admins_manage_access(pool: PgPool) {
    let app = spawn_full(pool, |_| {}, Some(directory())).await;
    let (ana, ana_cookie) = app.human(ANA).await;
    let ana_as = As::Cookie(&ana_cookie);

    let (s, _) = app.get(ana_as, "/api/access").await;
    assert_eq!(s, StatusCode::FORBIDDEN);
    let (s, _) = app
        .put(
            ana_as,
            &format!("/api/access/users/{ana}/permissions/users.view"),
            json!({"effect": "allow"}),
        )
        .await;
    assert_eq!(s, StatusCode::FORBIDDEN);

    // access.manage belongs to the Admin level and cannot be granted.
    let (s, _) = app
        .put(
            As::Admin,
            &format!("/api/access/users/{ana}/permissions/access.manage"),
            json!({"effect": "allow"}),
        )
        .await;
    assert_eq!(s, StatusCode::UNPROCESSABLE_ENTITY);
    let (s, _) = app
        .put(
            As::Admin,
            "/api/access/teams/unknown/permissions/users.view",
            json!({"effect": "allow"}),
        )
        .await;
    assert_eq!(s, StatusCode::NOT_FOUND);

    let (s, overview) = app.get(As::Admin, "/api/access").await;
    assert_eq!(s, StatusCode::OK);
    assert_eq!(overview["directory_enabled"], true);
    assert_eq!(overview["teams"].as_array().unwrap().len(), 2);
    let ana_row = overview["users"]
        .as_array()
        .unwrap()
        .iter()
        .find(|u| u["login"] == ANA)
        .unwrap()
        .clone();
    assert_eq!(ana_row["level"], "classic");
    assert_eq!(ana_row["teams"].as_array().unwrap().len(), 2);
}

#[sqlx::test(migrator = "atb_server::MIGRATOR")]
async fn levels_promote_demote_and_guards(pool: PgPool) {
    let app = spawn_full(pool, |_| {}, Some(directory())).await;
    let (ana, ana_cookie) = app.human(ANA).await;
    let (_, me) = app.get(As::Admin, "/api/auth/me").await;
    let admin_id = me["id"].as_str().unwrap().to_string();
    assert_eq!(me["level"], "admin");
    assert_eq!(me["permissions"].as_array().unwrap().len(), 6);

    // Own level: refused.
    let (s, _) = app
        .put(
            As::Admin,
            &format!("/api/access/users/{admin_id}/level"),
            json!({"level": "classic"}),
        )
        .await;
    assert_eq!(s, StatusCode::FORBIDDEN);

    let (s, _) = app
        .put(
            As::Admin,
            &format!("/api/access/users/{ana}/level"),
            json!({"level": "admin"}),
        )
        .await;
    assert_eq!(s, StatusCode::NO_CONTENT);
    let (_, me) = app.get(As::Cookie(&ana_cookie), "/api/auth/me").await;
    assert_eq!(me["level"], "admin");
    // Admin = full access, settings ignored.
    let (s, _) = app
        .post(As::Cookie(&ana_cookie), "/api/projects", new_project())
        .await;
    assert_eq!(s, StatusCode::CREATED);

    // Two admins: Ana may demote the bootstrap admin; then she cannot demote herself.
    let (s, _) = app
        .put(
            As::Cookie(&ana_cookie),
            &format!("/api/access/users/{admin_id}/level"),
            json!({"level": "classic"}),
        )
        .await;
    assert_eq!(s, StatusCode::NO_CONTENT);
    let (s, _) = app
        .put(
            As::Cookie(&ana_cookie),
            &format!("/api/access/users/{ana}/level"),
            json!({"level": "classic"}),
        )
        .await;
    assert_eq!(s, StatusCode::FORBIDDEN, "own level");
    let (s, _) = app
        .put(
            As::Cookie(&ana_cookie),
            &format!("/api/access/users/{admin_id}/level"),
            json!({"level": "bogus"}),
        )
        .await;
    assert_eq!(s, StatusCode::UNPROCESSABLE_ENTITY);
}

#[sqlx::test(migrator = "atb_server::MIGRATOR")]
async fn agents_manage_lets_classique_connect_agents_only(pool: PgPool) {
    let app = spawn_full(pool, |_| {}, Some(directory())).await;
    let (_, bob_cookie) = app.human(BOB).await;
    let bob_as = As::Cookie(&bob_cookie);
    let agent = json!({"kind": "agent", "name": "bob-bot", "model": "m", "roles": ["implementer"]});

    let (s, _) = app.post(bob_as, "/api/actors", agent.clone()).await;
    assert_eq!(s, StatusCode::FORBIDDEN);

    app.put(
        As::Admin,
        "/api/access/teams/g-data/permissions/agents.manage",
        json!({"effect": "allow"}),
    )
    .await;
    let (s, body) = app.post(bob_as, "/api/actors", agent).await;
    assert_eq!(s, StatusCode::CREATED, "{body}");
    assert!(body["token"].is_string());

    // Only implementer agents: no reviewer (would review their own agents' work), no planner.
    for role in ["reviewer", "planner"] {
        let (s, _) = app
            .post(
                bob_as,
                "/api/actors",
                json!({"kind": "agent", "name": "x", "roles": [role]}),
            )
            .await;
        assert_eq!(s, StatusCode::FORBIDDEN, "{role}");
    }
    // Never an admin agent, never a human.
    let (s, _) = app
        .post(
            bob_as,
            "/api/actors",
            json!({"kind": "agent", "name": "x", "roles": ["admin"]}),
        )
        .await;
    assert_eq!(s, StatusCode::FORBIDDEN);
    let (s, _) = app
        .post(
            bob_as,
            "/api/actors",
            json!({"kind": "human", "name": "x", "login": "x", "password": "0123456789ab"}),
        )
        .await;
    assert_eq!(s, StatusCode::FORBIDDEN);
}

#[sqlx::test(migrator = "atb_server::MIGRATOR")]
async fn agents_are_not_subject_to_levels(pool: PgPool) {
    let app = spawn_full(pool, |_| {}, Some(directory())).await;
    let a = app.implementer("impl").await;
    let (_, me) = app.get(As::Agent(&a), "/api/auth/me").await;
    assert_eq!(me["level"], serde_json::Value::Null);
    assert_eq!(me["permissions"], json!([]));
}

#[sqlx::test(migrator = "atb_server::MIGRATOR")]
async fn auth_methods_and_disabled_password_login(pool: PgPool) {
    let app = spawn_full(pool.clone(), |_| {}, None).await;
    let (s, m) = app.get(As::Admin, "/api/auth/methods").await;
    assert_eq!(s, StatusCode::OK);
    assert_eq!(m, json!({"sso": false, "password": true}));

    // A second router with password login off.
    let mut cfg = atb_server::Config::for_tests(String::new());
    cfg.password_login = false;
    let st = atb_server::AppState::new(pool, cfg);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move {
        axum::serve(listener, atb_server::api::router(st))
            .await
            .unwrap()
    });
    let res = app
        .http
        .post(format!("http://{addr}/api/auth/login"))
        .json(&json!({"login": common::ADMIN_LOGIN, "password": common::ADMIN_PASSWORD}))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::FORBIDDEN);

    // SSO not configured: redirected to the login page with a reason.
    let no_redirect = reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .unwrap();
    let res = no_redirect
        .get(format!("http://{addr}/api/auth/sso/start"))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::FOUND);
    assert_eq!(res.headers()["location"], "/login?error=sso_disabled");
}
