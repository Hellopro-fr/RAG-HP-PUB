//! Sign in with the HelloPro account (account-service, OAuth2 authorization code + PKCE).
//!
//! `GET /api/auth/sso/start?next=/projects` → 302 to account-service `/authorize`, with the
//! state, the PKCE verifier and `next` in a short-lived httpOnly cookie.
//! `GET /api/auth/sso/callback?code&state` → code exchange (`/token`), verified identity
//! (`/introspect`, `sub` = email), directory check (`is_allowed`), board account found or
//! created by email (`login`), session cookie, 302 to `next`.
//!
//! Failures redirect to `/login?error=<code>` (the browser is mid-redirect, not calling JSON).

use std::time::Duration;

use axum::extract::{Query, State};
use axum::http::{HeaderMap, HeaderValue, StatusCode, header};
use axum::response::{IntoResponse, Response};
use base64::Engine;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use serde::Deserialize;
use sha2::{Digest, Sha256};
use uuid::Uuid;

use super::rest::session_set_cookie;
use crate::actor::Actor;
use crate::error::AppError;
use crate::repository::access as access_repo;
use crate::repository::store::{self, NewActor};
use crate::repository::{random_token, sha256_hex};
use crate::service::now;
use crate::state::AppState;

pub const SSO_COOKIE: &str = "atb_sso";
const SSO_COOKIE_PATH: &str = "/api/auth/sso";

fn redirect(to: &str) -> Response {
    let mut res = StatusCode::FOUND.into_response();
    if let Ok(v) = HeaderValue::from_str(to) {
        res.headers_mut().insert(header::LOCATION, v);
    }
    res
}

/// Only same-site relative paths: a leading `/`, no `//host`, no backslash, and no control or
/// whitespace byte (browsers strip tab/CR/LF from URLs, so `/\t/evil` would become `//evil`).
fn safe_next(next: Option<&str>) -> String {
    match next {
        Some(n)
            if n.starts_with('/')
                && !n.starts_with("//")
                && n.bytes().all(|b| b > 0x20 && b != 0x7f && b != b'\\') =>
        {
            n.into()
        }
        _ => "/projects".into(),
    }
}

fn pkce_challenge(verifier: &str) -> String {
    URL_SAFE_NO_PAD.encode(Sha256::digest(verifier.as_bytes()))
}

fn redirect_uri(st: &AppState) -> String {
    format!(
        "{}/api/auth/sso/callback",
        st.cfg
            .public_url
            .as_deref()
            .unwrap_or_default()
            .trim_end_matches('/')
    )
}

fn sso_cookie(st: &AppState, value: &str, max_age: i64) -> HeaderValue {
    let secure = if st.cfg.cookie_secure { "; Secure" } else { "" };
    HeaderValue::from_str(&format!(
        "{SSO_COOKIE}={value}; HttpOnly; SameSite=Lax; Path={SSO_COOKIE_PATH}; Max-Age={max_age}{secure}"
    ))
    .unwrap_or_else(|_| HeaderValue::from_static(""))
}

fn read_cookie(headers: &HeaderMap, name: &str) -> Option<String> {
    headers
        .get_all(header::COOKIE)
        .iter()
        .filter_map(|v| v.to_str().ok())
        .flat_map(|v| v.split(';'))
        .filter_map(|kv| kv.trim().split_once('='))
        .find(|(k, _)| *k == name)
        .map(|(_, v)| v.to_string())
}

fn same(a: &str, b: &str) -> bool {
    a.len() == b.len()
        && a.bytes()
            .zip(b.bytes())
            .fold(0u8, |acc, (x, y)| acc | (x ^ y))
            == 0
}

fn urlencode(s: &str) -> String {
    s.bytes()
        .map(|b| match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'.' | b'_' | b'~' => {
                (b as char).to_string()
            }
            _ => format!("%{b:02X}"),
        })
        .collect()
}

#[derive(Debug, Deserialize)]
pub struct StartQuery {
    pub next: Option<String>,
}

pub async fn start(State(st): State<AppState>, Query(q): Query<StartQuery>) -> Response {
    if !st.cfg.sso_enabled() {
        return redirect("/login?error=sso_disabled");
    }
    let state = random_token();
    let verifier = random_token();
    let next = safe_next(q.next.as_deref());
    let cookie = format!(
        "{state}.{verifier}.{}",
        URL_SAFE_NO_PAD.encode(next.as_bytes())
    );
    let public = st
        .cfg
        .account_public_url
        .as_deref()
        .or(st.cfg.account_internal_url.as_deref())
        .unwrap_or_default()
        .trim_end_matches('/')
        .to_string();
    let url = format!(
        "{public}/authorize?response_type=code&client_id={}&redirect_uri={}&code_challenge={}&code_challenge_method=S256&state={state}",
        urlencode(st.cfg.oauth_client_id.as_deref().unwrap_or_default()),
        urlencode(&redirect_uri(&st)),
        pkce_challenge(&verifier),
    );
    let mut res = redirect(&url);
    res.headers_mut()
        .insert(header::SET_COOKIE, sso_cookie(&st, &cookie, 600));
    res
}

#[derive(Debug, Deserialize)]
pub struct CallbackQuery {
    pub code: Option<String>,
    pub state: Option<String>,
    pub error: Option<String>,
}

#[derive(Debug, Deserialize)]
struct TokenResponse {
    access_token: String,
}

#[derive(Debug, Deserialize)]
struct Introspection {
    active: bool,
    #[serde(default)]
    sub: String,
}

/// Why a sign-in failed; the code is shown on /login.
#[derive(Debug)]
enum SsoError {
    Denied,
    BadState,
    Exchange,
    NotAllowed,
    /// Board access disabled by an admin (the HelloPro account is fine).
    Disabled,
    Internal,
}

impl SsoError {
    fn code(&self) -> &'static str {
        match self {
            SsoError::Denied => "sso_denied",
            SsoError::BadState => "sso_state",
            SsoError::Exchange => "sso_exchange",
            SsoError::NotAllowed => "sso_not_allowed",
            SsoError::Disabled => "sso_board_disabled",
            SsoError::Internal => "sso_internal",
        }
    }
}

impl From<AppError> for SsoError {
    fn from(e: AppError) -> Self {
        tracing::warn!(error = %e.message(), "sso sign-in failed");
        SsoError::Internal
    }
}

impl From<sqlx::Error> for SsoError {
    fn from(e: sqlx::Error) -> Self {
        SsoError::from(AppError::from(e))
    }
}

pub async fn callback(
    State(st): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<CallbackQuery>,
) -> Response {
    let clear = sso_cookie(&st, "", 0);
    let mut res = match finish(&st, &headers, q).await {
        Ok((token, expires_at, next)) => match session_set_cookie(&st, &token, expires_at) {
            Ok(v) => {
                let mut res = redirect(&next);
                res.headers_mut().append(header::SET_COOKIE, v);
                res
            }
            Err(_) => redirect("/login?error=sso_internal"),
        },
        Err(e) => {
            tracing::info!(reason = e.code(), "sso sign-in refused");
            redirect(&format!("/login?error={}", e.code()))
        }
    };
    res.headers_mut().append(header::SET_COOKIE, clear);
    res
}

async fn finish(
    st: &AppState,
    headers: &HeaderMap,
    q: CallbackQuery,
) -> Result<(String, time::OffsetDateTime, String), SsoError> {
    if q.error.is_some() {
        return Err(SsoError::Denied);
    }
    let cookie = read_cookie(headers, SSO_COOKIE).ok_or(SsoError::BadState)?;
    let mut parts = cookie.splitn(3, '.');
    let (Some(state), Some(verifier), Some(next_b64)) = (parts.next(), parts.next(), parts.next())
    else {
        return Err(SsoError::BadState);
    };
    if !same(state, q.state.as_deref().unwrap_or_default()) {
        return Err(SsoError::BadState);
    }
    let next = URL_SAFE_NO_PAD
        .decode(next_b64)
        .ok()
        .and_then(|b| String::from_utf8(b).ok());
    let next = safe_next(next.as_deref());
    let code = q.code.as_deref().ok_or(SsoError::Exchange)?;

    let email = exchange(st, code, verifier).await?;
    let display_name = if st.directory.is_enabled() {
        let dir = st.directory.refresh().await?;
        let user = dir.user(&email).ok_or(SsoError::NotAllowed)?;
        if !user.is_allowed {
            return Err(SsoError::NotAllowed);
        }
        Some(user.display_name.clone()).filter(|n| !n.trim().is_empty())
    } else {
        None
    };

    let mut tx = st.pool.begin().await?;
    sqlx::query("LOCK TABLE actors IN SHARE ROW EXCLUSIVE MODE")
        .execute(&mut *tx)
        .await?;
    let actor = match access_repo::human_by_login(&mut tx, &email).await? {
        Some(a) => a,
        None => create_human(&mut tx, &email, display_name.as_deref()).await?,
    };
    let disabled = sqlx::query_scalar!(
        r#"SELECT disabled_at IS NOT NULL AS "d!" FROM actors WHERE id = $1"#,
        actor.id
    )
    .fetch_one(&mut *tx)
    .await?;
    if disabled {
        return Err(SsoError::Disabled);
    }
    let token = random_token();
    let expires_at = now() + time::Duration::hours(st.cfg.session_ttl_hours);
    store::insert_session(&mut tx, &sha256_hex(&token), actor.id, expires_at).await?;
    tx.commit().await?;
    tracing::info!(actor = %actor.id, "signed in with the HelloPro account");
    Ok((token, expires_at, next))
}

/// First board account for this email. The very first human becomes Admin (fresh install
/// without a bootstrap admin); everyone else starts Classique.
async fn create_human(
    conn: &mut sqlx::PgConnection,
    email: &str,
    display_name: Option<&str>,
) -> Result<Actor, SsoError> {
    let first = store::count_humans(conn).await? == 0;
    let roles: Vec<String> = if first {
        vec!["admin".into(), "planner".into(), "reviewer".into()]
    } else {
        vec![]
    };
    let id = Uuid::now_v7();
    let name: String = display_name.unwrap_or(email).chars().take(200).collect();
    store::insert_actor(
        conn,
        NewActor {
            id,
            kind: "human",
            name: &name,
            model: None,
            roles: roles.clone(),
            token_hash: None,
            password_hash: None,
            login: Some(email),
            gateway_subject: None,
        },
    )
    .await?;
    Ok(Actor::from_row(id, "human", name, &roles, None))
}

/// Code → access token → verified email.
async fn exchange(st: &AppState, code: &str, verifier: &str) -> Result<String, SsoError> {
    let base = st
        .cfg
        .account_internal_url
        .as_deref()
        .ok_or(SsoError::Internal)?
        .trim_end_matches('/');
    let client_id = st
        .cfg
        .oauth_client_id
        .as_deref()
        .ok_or(SsoError::Internal)?;
    let secret = st
        .cfg
        .oauth_client_secret
        .as_deref()
        .ok_or(SsoError::Internal)?;
    let http = reqwest::Client::builder()
        .timeout(Duration::from_secs(10))
        .build()
        .map_err(|_| SsoError::Internal)?;
    let redirect = redirect_uri(st);
    let token: TokenResponse = http
        .post(format!("{base}/token"))
        .basic_auth(client_id, Some(secret))
        .form(&[
            ("grant_type", "authorization_code"),
            ("code", code),
            ("redirect_uri", redirect.as_str()),
            ("code_verifier", verifier),
        ])
        .send()
        .await
        .and_then(|r| r.error_for_status())
        .map_err(|e| {
            tracing::warn!(error = %e, "sso token exchange failed");
            SsoError::Exchange
        })?
        .json()
        .await
        .map_err(|_| SsoError::Exchange)?;
    let info: Introspection = http
        .post(format!("{base}/introspect"))
        .basic_auth(client_id, Some(secret))
        .form(&[("token", token.access_token.as_str())])
        .send()
        .await
        .and_then(|r| r.error_for_status())
        .map_err(|e| {
            tracing::warn!(error = %e, "sso introspection failed");
            SsoError::Exchange
        })?
        .json()
        .await
        .map_err(|_| SsoError::Exchange)?;
    let email = info.sub.trim().to_lowercase();
    if !info.active || !email.contains('@') {
        return Err(SsoError::Exchange);
    }
    Ok(email)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn next_must_be_a_local_path() {
        assert_eq!(safe_next(Some("/projects/1?x=2")), "/projects/1?x=2");
        assert_eq!(safe_next(Some("//evil.example")), "/projects");
        assert_eq!(safe_next(Some("https://evil.example")), "/projects");
        assert_eq!(safe_next(Some("/\\evil.example")), "/projects");
        assert_eq!(safe_next(Some("/\t/evil.example")), "/projects");
        assert_eq!(safe_next(Some("/\n/evil.example")), "/projects");
        assert_eq!(safe_next(Some("/ /evil.example")), "/projects");
        assert_eq!(safe_next(Some("/a\u{7f}")), "/projects");
        assert_eq!(safe_next(None), "/projects");
    }

    #[test]
    fn pkce_s256_matches_rfc7636_appendix_b() {
        assert_eq!(
            pkce_challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"),
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        );
    }

    #[test]
    fn urlencode_escapes_reserved_characters() {
        assert_eq!(
            urlencode("https://a.b/c?d=e"),
            "https%3A%2F%2Fa.b%2Fc%3Fd%3De"
        );
    }
}
