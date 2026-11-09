//! Sign in with the HelloPro account against a fake account-service (`/token`, `/introspect`).
mod common;

use atb_server::directory::{DirUser, Directory};
use axum::routing::post;
use axum::{Form, Json, Router};
use common::{As, spawn_full};
use reqwest::StatusCode;
use serde_json::{Value, json};
use sqlx::PgPool;
use std::collections::HashMap;

/// code "ana" → ana@example.com (allowed), code "carl" → carl@example.com (blocked).
async fn fake_account_service() -> String {
    let app = Router::new()
        .route(
            "/token",
            post(|Form(f): Form<HashMap<String, String>>| async move {
                assert_eq!(f["grant_type"], "authorization_code");
                assert!(f["code_verifier"].len() >= 43, "PKCE verifier sent");
                assert_eq!(f["redirect_uri"], "http://board.test/api/auth/sso/callback");
                Json(json!({"access_token": format!("tok-{}", f["code"]), "token_type": "Bearer"}))
            }),
        )
        .route(
            "/introspect",
            post(|Form(f): Form<HashMap<String, String>>| async move {
                let who = f["token"].trim_start_matches("tok-").to_string();
                Json(json!({"active": true, "sub": format!("{}@Example.com", who)}))
            }),
        );
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    format!("http://{addr}")
}

fn directory() -> Directory {
    Directory {
        users: vec![
            DirUser {
                email: "ana@example.com".into(),
                display_name: "Ana Rakoto".into(),
                is_allowed: true,
            },
            DirUser {
                email: "carl@example.com".into(),
                display_name: "Carl".into(),
                is_allowed: false,
            },
        ],
        groups: vec![],
    }
}

fn cookie_value(res: &reqwest::Response, name: &str) -> Option<String> {
    res.headers()
        .get_all("set-cookie")
        .iter()
        .filter_map(|v| v.to_str().ok())
        .filter_map(|v| v.split(';').next())
        .find(|kv| kv.starts_with(&format!("{name}=")) && kv.len() > name.len() + 1)
        .map(str::to_string)
}

/// start → callback with `code`; returns (callback status, Location, session cookie).
async fn sign_in(
    base: &str,
    code: &str,
    tamper_state: bool,
) -> (StatusCode, String, Option<String>) {
    let http = reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .unwrap();
    let res = http
        .get(format!("{base}/api/auth/sso/start?next=/questions"))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::FOUND);
    let location = res.headers()["location"].to_str().unwrap().to_string();
    assert!(location.contains("/authorize?response_type=code&client_id=atb-board"));
    assert!(location.contains("code_challenge_method=S256"));
    let state = location.split("state=").nth(1).unwrap().to_string();
    let sso = cookie_value(&res, "atb_sso").expect("sso cookie");
    let state = if tamper_state {
        format!("x{state}")
    } else {
        state
    };
    let res = http
        .get(format!(
            "{base}/api/auth/sso/callback?code={code}&state={state}"
        ))
        .header("cookie", sso)
        .send()
        .await
        .unwrap();
    let status = res.status();
    let to = res.headers()["location"].to_str().unwrap().to_string();
    (status, to, cookie_value(&res, "atb_session"))
}

#[sqlx::test(migrator = "atb_server::MIGRATOR")]
async fn sign_in_creates_then_reuses_a_classique_account(pool: PgPool) {
    let account = fake_account_service().await;
    let app = spawn_full(
        pool,
        |c| {
            c.account_internal_url = Some(account.clone());
            c.oauth_client_id = Some("atb-board".into());
            c.oauth_client_secret = Some("client-secret-for-tests".into());
            c.public_url = Some("http://board.test".into());
        },
        Some(directory()),
    )
    .await;

    let (s, m) = app.get(As::Admin, "/api/auth/methods").await;
    assert_eq!(s, StatusCode::OK);
    assert_eq!(m["sso"], true);

    let (status, to, session) = sign_in(&app.base, "ana", false).await;
    assert_eq!(status, StatusCode::FOUND);
    assert_eq!(to, "/questions");
    let session = session.expect("session cookie");
    let (s, me): (StatusCode, Value) = app.get(As::Cookie(&session), "/api/auth/me").await;
    assert_eq!(s, StatusCode::OK);
    assert_eq!(me["name"], "Ana Rakoto");
    assert_eq!(
        me["level"], "classic",
        "the bootstrap admin exists, so newcomers are Classique"
    );

    let (_, _, again) = sign_in(&app.base, "ana", false).await;
    let (_, me2) = app.get(As::Cookie(&again.unwrap()), "/api/auth/me").await;
    assert_eq!(me2["id"], me["id"], "same board account by email");
}

#[sqlx::test(migrator = "atb_server::MIGRATOR")]
async fn blocked_users_and_bad_state_are_refused(pool: PgPool) {
    let account = fake_account_service().await;
    let app = spawn_full(
        pool,
        |c| {
            c.account_internal_url = Some(account.clone());
            c.oauth_client_id = Some("atb-board".into());
            c.oauth_client_secret = Some("client-secret-for-tests".into());
            c.public_url = Some("http://board.test".into());
        },
        Some(directory()),
    )
    .await;

    let (status, to, session) = sign_in(&app.base, "carl", false).await;
    assert_eq!(status, StatusCode::FOUND);
    assert_eq!(to, "/login?error=sso_not_allowed");
    assert!(session.is_none());

    let (_, to, session) = sign_in(&app.base, "ana", true).await;
    assert_eq!(to, "/login?error=sso_state");
    assert!(session.is_none());
}
