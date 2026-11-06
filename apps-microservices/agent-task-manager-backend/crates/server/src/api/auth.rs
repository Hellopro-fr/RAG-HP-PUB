//! Authentication middleware. Resolves the caller once per request and puts an [`Actor`] in the
//! request extensions (REST handlers, SSE, and MCP tools read it from there).
//!
//! Order: MCP gateway identity (`X-Agent-Gateway-Secret` + `X-Agent-Client-Id` /
//! `X-Agent-User-Email`) → `Authorization: Bearer <token>` → `atb_session` cookie.

use axum::extract::{Request, State};
use axum::http::HeaderMap;
use axum::middleware::Next;
use axum::response::Response;

use crate::actor::Actor;
use crate::error::{AppError, AppResult};
use crate::repository::{sha256_hex, store};
use crate::service::now;
use crate::state::AppState;

pub const SESSION_COOKIE: &str = "atb_session";
pub const GATEWAY_SECRET_HEADER: &str = "x-agent-gateway-secret";
pub const GATEWAY_CLIENT_HEADER: &str = "x-agent-client-id";
pub const GATEWAY_EMAIL_HEADER: &str = "x-agent-user-email";

pub async fn require_actor(
    State(st): State<AppState>,
    mut req: Request,
    next: Next,
) -> Result<Response, AppError> {
    let actor = resolve(&st, req.headers())
        .await?
        .ok_or(AppError::Unauthorized)?;
    tracing::Span::current().record("actor_id", tracing::field::display(actor.id));
    if let Ok(mut conn) = st.pool.acquire().await {
        let _ = store::touch_actor(&mut conn, actor.id, now()).await;
    }
    req.extensions_mut().insert(actor);
    Ok(next.run(req).await)
}

fn header<'a>(headers: &'a HeaderMap, name: &str) -> Option<&'a str> {
    headers
        .get(name)
        .and_then(|v| v.to_str().ok())
        .map(str::trim)
        .filter(|v| !v.is_empty())
}

/// Constant-time comparison (the gateway secret must not leak through timing).
fn same_secret(a: &str, b: &str) -> bool {
    a.len() == b.len()
        && a.bytes()
            .zip(b.bytes())
            .fold(0u8, |acc, (x, y)| acc | (x ^ y))
            == 0
}

pub fn session_cookie(headers: &HeaderMap) -> Option<String> {
    headers
        .get_all(axum::http::header::COOKIE)
        .iter()
        .filter_map(|v| v.to_str().ok())
        .flat_map(|v| v.split(';'))
        .filter_map(|kv| kv.trim().split_once('='))
        .find(|(k, _)| *k == SESSION_COOKIE)
        .map(|(_, v)| v.to_string())
}

async fn resolve(st: &AppState, headers: &HeaderMap) -> AppResult<Option<Actor>> {
    let mut conn = st.pool.acquire().await?;
    if let Some(presented) = header(headers, GATEWAY_SECRET_HEADER) {
        let Some(expected) = st.cfg.gateway_shared_secret.as_deref() else {
            return Err(AppError::Unauthorized);
        };
        if !same_secret(presented, expected) {
            return Err(AppError::Unauthorized);
        }
        let subject = if let Some(client) = header(headers, GATEWAY_CLIENT_HEADER) {
            format!("client:{client}")
        } else if let Some(email) = header(headers, GATEWAY_EMAIL_HEADER) {
            format!("email:{}", email.to_lowercase())
        } else {
            return Err(AppError::Unauthorized);
        };
        return store::actor_by_gateway_subject(&mut conn, &subject)
            .await?
            .map(Some)
            .ok_or_else(|| {
                AppError::Forbidden(format!(
                    "gateway subject {subject} is not registered; ask an admin to create the actor"
                ))
            });
    }
    if let Some(auth) = header(headers, "authorization") {
        let token = auth
            .strip_prefix("Bearer ")
            .or_else(|| auth.strip_prefix("bearer "))
            .ok_or(AppError::Unauthorized)?;
        return store::actor_by_token_hash(&mut conn, &sha256_hex(token.trim()))
            .await?
            .map(Some)
            .ok_or(AppError::Unauthorized);
    }
    if let Some(cookie) = session_cookie(headers) {
        return Ok(store::actor_by_session(&mut conn, &sha256_hex(&cookie), now()).await?);
    }
    Ok(None)
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::HeaderValue;

    #[test]
    fn secret_comparison_and_cookie_parsing() {
        assert!(same_secret("abc", "abc"));
        assert!(!same_secret("abc", "abd"));
        assert!(!same_secret("abc", "abcd"));
        let mut h = HeaderMap::new();
        h.insert(
            "cookie",
            HeaderValue::from_static("theme=dark; atb_session=tok123; x=y"),
        );
        assert_eq!(session_cookie(&h).as_deref(), Some("tok123"));
    }
}
