//! Public/private projects, members (people and teams), invitations, agent owners, disabled
//! users (validated maquette: "Projets", "Membres et accès", "Utilisateurs").
mod common;

use atb_server::directory::{DirGroup, DirUser, Directory};
use common::{Agent, As, TestApp, spawn_full};
use reqwest::StatusCode;
use serde_json::{Value, json};
use sqlx::PgPool;
use uuid::Uuid;

const ANA: &str = "ana@example.com";
const BOB: &str = "bob@example.com";

fn directory() -> Directory {
    let user = |email: &str, name: &str| DirUser {
        email: email.into(),
        display_name: name.into(),
        is_allowed: true,
    };
    Directory {
        users: vec![user(ANA, "Ana"), user(BOB, "Bob")],
        groups: vec![DirGroup {
            id: "g-data".into(),
            name: "Data".into(),
            description: String::new(),
            members: vec![ANA.into()],
        }],
    }
}

async fn project(app: &TestApp, visibility: &str) -> Uuid {
    let (s, body) = app
        .post(
            As::Admin,
            "/api/projects",
            json!({"name": format!("P {visibility}"), "workflow": common::no_gates(), "visibility": visibility}),
        )
        .await;
    assert_eq!(s, StatusCode::CREATED, "{body}");
    assert_eq!(body["visibility"], visibility);
    body["id"].as_str().unwrap().parse().unwrap()
}

fn spec_body() -> Value {
    json!({
        "title": "Spec", "body_md": "Do it.",
        "acceptance_criteria": [{"id": "AC-1", "text": "ok", "verify": {"kind": "command", "command": "true"}}]
    })
}

fn ids(list: &Value) -> Vec<String> {
    list.as_array()
        .unwrap()
        .iter()
        .map(|p| p["id"].as_str().unwrap().to_string())
        .collect()
}

#[sqlx::test(migrator = "atb_server::MIGRATOR")]
async fn private_projects_are_invisible_and_public_ones_read_only(pool: PgPool) {
    let app = spawn_full(pool, |_| {}, Some(directory())).await;
    let (_, bob_cookie) = app.human(BOB).await;
    let bob = As::Cookie(&bob_cookie);
    let private = project(&app, "private").await;
    let public = project(&app, "public").await;
    let spec = app.approved_spec(private).await;
    let task = app.task(private, spec, "secret task").await;

    let (_, list) = app.get(bob, "/api/projects").await;
    assert_eq!(ids(&list), vec![public.to_string()]);
    assert_eq!(list[0]["my_role"], "viewer");

    // Invisible: 404 everywhere, existence not revealed.
    for path in [
        format!("/api/projects/{private}"),
        format!("/api/projects/{private}/board"),
        format!("/api/tasks/{task}"),
        format!("/api/specs/{spec}"),
    ] {
        let (s, _) = app.get(bob, &path).await;
        assert_eq!(s, StatusCode::NOT_FOUND, "{path}");
    }

    // Public: readable, not writable.
    let (s, _) = app.get(bob, &format!("/api/projects/{public}/board")).await;
    assert_eq!(s, StatusCode::OK);
    let (s, _) = app
        .post(bob, &format!("/api/projects/{public}/specs"), spec_body())
        .await;
    assert_eq!(s, StatusCode::FORBIDDEN);

    // The admin owns everything; the creator is listed as owner.
    let (_, list) = app.get(As::Admin, "/api/projects").await;
    assert_eq!(list.as_array().unwrap().len(), 2);
    let (_, members) = app
        .get(As::Admin, &format!("/api/projects/{private}/members"))
        .await;
    assert_eq!(members["people"][0]["effective_role"], "owner");
    assert_eq!(members["can_manage"], true);
}

#[sqlx::test(migrator = "atb_server::MIGRATOR")]
async fn team_then_individual_priority_and_invitations(pool: PgPool) {
    let app = spawn_full(pool, |_| {}, Some(directory())).await;
    let (_, ana_cookie) = app.human(ANA).await;
    let ana = As::Cookie(&ana_cookie);
    let p = project(&app, "private").await;
    let specs = format!("/api/projects/{p}/specs");
    let members = format!("/api/projects/{p}/members");

    // A team gets editor: Ana (member of Data) can write at once.
    let (s, body) = app
        .post(
            As::Admin,
            &members,
            json!({"kind": "team", "id": "g-data", "role": "editor"}),
        )
        .await;
    assert_eq!(s, StatusCode::NO_CONTENT, "{body}");
    let (s, body) = app.post(ana, &specs, spec_body()).await;
    assert_eq!(s, StatusCode::CREATED, "{body}");
    // A team cannot be owner.
    let (s, _) = app
        .put(
            As::Admin,
            &format!("{members}/team/g-data"),
            json!({"role": "owner"}),
        )
        .await;
    assert_eq!(s, StatusCode::UNPROCESSABLE_ENTITY);

    // An individual invitation gives nothing until accepted…
    let (s, _) = app
        .post(
            As::Admin,
            &members,
            json!({"kind": "user", "id": "Ana@Example.com", "role": "viewer"}),
        )
        .await;
    assert_eq!(s, StatusCode::NO_CONTENT);
    let (s, _) = app.post(ana, &specs, spec_body()).await;
    assert_eq!(
        s,
        StatusCode::CREATED,
        "pending invitation: the team role still applies"
    );
    let (_, inv) = app.get(ana, "/api/invitations").await;
    assert_eq!(inv[0]["project_id"], p.to_string());
    assert_eq!(inv[0]["role"], "viewer");

    // …once accepted, the individual role wins even though it is lower than the team's.
    let (s, _) = app
        .post(ana, &format!("/api/invitations/{p}/accept"), json!({}))
        .await;
    assert_eq!(s, StatusCode::NO_CONTENT);
    let (s, _) = app.post(ana, &specs, spec_body()).await;
    assert_eq!(s, StatusCode::FORBIDDEN);
    let (_, m) = app.get(As::Admin, &members).await;
    let ana_row = m["people"]
        .as_array()
        .unwrap()
        .iter()
        .find(|x| x["subject"] == ANA)
        .unwrap()
        .clone();
    assert_eq!(ana_row["effective_role"], "viewer");
    assert_eq!(ana_row["source"], "individual");
    assert_eq!(ana_row["via_teams"][0]["role"], "editor");

    // Removing the individual access falls back to the team role.
    let (s, _) = app
        .delete(As::Admin, &format!("{members}/user/{ANA}"))
        .await;
    assert_eq!(s, StatusCode::NO_CONTENT);
    let (s, _) = app.post(ana, &specs, spec_body()).await;
    assert_eq!(s, StatusCode::CREATED);

    // Decline removes the invitation.
    app.post(
        As::Admin,
        &members,
        json!({"kind": "user", "id": ANA, "role": "editor"}),
    )
    .await;
    let (s, _) = app
        .post(ana, &format!("/api/invitations/{p}/decline"), json!({}))
        .await;
    assert_eq!(s, StatusCode::NO_CONTENT);
    let (_, inv) = app.get(ana, "/api/invitations").await;
    assert_eq!(inv, json!([]));
}

#[sqlx::test(migrator = "atb_server::MIGRATOR")]
async fn only_owners_manage_and_a_project_keeps_an_owner(pool: PgPool) {
    let app = spawn_full(pool, |_| {}, Some(directory())).await;
    let (_, ana_cookie) = app.human(ANA).await;
    let ana = As::Cookie(&ana_cookie);
    let p = project(&app, "public").await;
    let members = format!("/api/projects/{p}/members");
    let visibility = format!("/api/projects/{p}/visibility");

    let (s, _) = app
        .post(
            ana,
            &members,
            json!({"kind": "user", "id": BOB, "role": "viewer"}),
        )
        .await;
    assert_eq!(s, StatusCode::FORBIDDEN, "a viewer does not manage members");
    let (s, _) = app
        .put(ana, &visibility, json!({"visibility": "private"}))
        .await;
    assert_eq!(s, StatusCode::FORBIDDEN);

    // The bootstrap admin created it: login "admin" is the only owner.
    let (s, _) = app
        .delete(As::Admin, &format!("{members}/user/admin"))
        .await;
    assert_eq!(s, StatusCode::UNPROCESSABLE_ENTITY);
    let (s, _) = app
        .put(
            As::Admin,
            &format!("{members}/user/admin"),
            json!({"role": "editor"}),
        )
        .await;
    assert_eq!(s, StatusCode::UNPROCESSABLE_ENTITY);

    // Ana becomes owner (accepted): she can now manage, and the admin row can go.
    app.post(
        As::Admin,
        &members,
        json!({"kind": "user", "id": ANA, "role": "owner"}),
    )
    .await;
    app.post(ana, &format!("/api/invitations/{p}/accept"), json!({}))
        .await;
    let (s, _) = app
        .put(ana, &visibility, json!({"visibility": "private"}))
        .await;
    assert_eq!(s, StatusCode::NO_CONTENT);
    let (s, _) = app.delete(ana, &format!("{members}/user/admin")).await;
    assert_eq!(s, StatusCode::NO_CONTENT);
}

#[sqlx::test(migrator = "atb_server::MIGRATOR")]
async fn agents_see_what_their_owner_sees_and_disabled_users_are_locked_out(pool: PgPool) {
    let app = spawn_full(pool, |_| {}, Some(directory())).await;
    let (bob_id, bob_cookie) = app.human(BOB).await;
    let bob = As::Cookie(&bob_cookie);
    let p = project(&app, "private").await;

    // Bob connects an agent (agents.manage given individually).
    app.put(
        As::Admin,
        &format!("/api/access/users/{bob_id}/permissions/agents.manage"),
        json!({"effect": "allow"}),
    )
    .await;
    let (s, body) = app
        .post(
            bob,
            "/api/actors",
            json!({"kind": "agent", "name": "bob-bot", "model": "m", "roles": ["implementer"]}),
        )
        .await;
    assert_eq!(s, StatusCode::CREATED, "{body}");
    let agent = Agent {
        id: body["id"].as_str().unwrap().parse().unwrap(),
        token: body["token"].as_str().unwrap().to_string(),
    };
    let ready = format!("/api/projects/{p}/ready");
    let (s, _) = app.get(As::Agent(&agent), &ready).await;
    assert_eq!(
        s,
        StatusCode::NOT_FOUND,
        "Bob cannot see the project, nor can his agent"
    );

    // Bob becomes editor: so does his agent.
    app.post(
        As::Admin,
        &format!("/api/projects/{p}/members"),
        json!({"kind": "user", "id": BOB, "role": "editor"}),
    )
    .await;
    app.post(bob, &format!("/api/invitations/{p}/accept"), json!({}))
        .await;
    let (s, _) = app.get(As::Agent(&agent), &ready).await;
    assert_eq!(s, StatusCode::OK);

    // An agent created by an admin from the CLI (no owner) keeps full access.
    let cli = app.implementer("cli-bot").await;
    let (s, _) = app.get(As::Agent(&cli), &ready).await;
    assert_eq!(s, StatusCode::OK);

    // Disabled: Bob's sessions are gone and his agent is refused; re-enabled: the agent works.
    let status = format!("/api/users/{bob_id}/status");
    let (s, _) = app.put(As::Admin, &status, json!({"disabled": true})).await;
    assert_eq!(s, StatusCode::NO_CONTENT);
    let (s, _) = app.get(bob, "/api/auth/me").await;
    assert_eq!(s, StatusCode::UNAUTHORIZED);
    let (s, _) = app.get(As::Agent(&agent), &ready).await;
    assert_eq!(s, StatusCode::FORBIDDEN);
    let (s, _) = app
        .put(As::Admin, &status, json!({"disabled": false}))
        .await;
    assert_eq!(s, StatusCode::NO_CONTENT);
    let (s, _) = app.get(As::Agent(&agent), &ready).await;
    assert_eq!(s, StatusCode::OK);

    // Nobody acts on their own account.
    let (_, me) = app.get(As::Admin, "/api/auth/me").await;
    let admin_id = me["id"].as_str().unwrap();
    let (s, _) = app
        .put(
            As::Admin,
            &format!("/api/users/{admin_id}/status"),
            json!({"disabled": true}),
        )
        .await;
    assert_eq!(s, StatusCode::FORBIDDEN);
}

#[sqlx::test(migrator = "atb_server::MIGRATOR")]
async fn users_page_lists_people_invitees_projects_and_agents(pool: PgPool) {
    let app = spawn_full(pool, |_| {}, Some(directory())).await;
    let (ana_id, ana_cookie) = app.human(ANA).await;
    let p = project(&app, "private").await;
    let members = format!("/api/projects/{p}/members");
    app.post(
        As::Admin,
        &members,
        json!({"kind": "team", "id": "g-data", "role": "editor"}),
    )
    .await;
    app.post(
        As::Admin,
        &members,
        json!({"kind": "user", "id": "new.person@example.com", "role": "viewer"}),
    )
    .await;

    let (s, _) = app.get(As::Cookie(&ana_cookie), "/api/users").await;
    assert_eq!(s, StatusCode::FORBIDDEN, "users.view not granted");
    app.put(
        As::Admin,
        &format!("/api/access/users/{ana_id}/permissions/users.view"),
        json!({"effect": "allow"}),
    )
    .await;
    let (s, users) = app.get(As::Cookie(&ana_cookie), "/api/users").await;
    assert_eq!(s, StatusCode::OK);
    let users = users.as_array().unwrap();
    let ana = users.iter().find(|u| u["login"] == ANA).unwrap();
    assert_eq!(ana["status"], "active");
    assert_eq!(ana["teams"], json!(["Data"]));
    assert_eq!(ana["projects"][0]["role"], "editor");
    let invitee = users
        .iter()
        .find(|u| u["login"] == "new.person@example.com")
        .unwrap();
    assert_eq!(invitee["status"], "pending");
    assert_eq!(invitee["projects"][0]["pending"], true);
    assert_eq!(invitee["id"], Value::Null);
}
