//! Accounts: human login (argon2id + httpOnly session cookie) and agent/verifier bearer tokens
//! (32 random bytes, stored as SHA-256). Secrets are shown once and never stored in clear.

use argon2::Argon2;
use argon2::password_hash::{PasswordHash, PasswordHasher, PasswordVerifier, SaltString};
use serde::{Deserialize, Serialize};
use sqlx::{PgConnection, PgPool};
use time::{Duration, OffsetDateTime};
use utoipa::ToSchema;
use uuid::Uuid;

use super::now;
use crate::actor::Actor;
use crate::error::{AppError, AppResult};
use crate::repository::store::{self, NewActor};
use crate::repository::{random_token, sha256_hex};

const MIN_PASSWORD_LEN: usize = 10;

pub fn hash_password(password: &str) -> AppResult<String> {
    use rand::RngCore;
    let mut salt_bytes = [0u8; 16];
    rand::rng().fill_bytes(&mut salt_bytes);
    let salt = SaltString::encode_b64(&salt_bytes)
        .map_err(|e| AppError::Internal(anyhow::anyhow!("salt: {e}")))?;
    Argon2::default()
        .hash_password(password.as_bytes(), &salt)
        .map(|h| h.to_string())
        .map_err(|e| AppError::Internal(anyhow::anyhow!("argon2: {e}")))
}

pub fn verify_password(password: &str, hash: &str) -> bool {
    PasswordHash::new(hash)
        .map(|parsed| {
            Argon2::default()
                .verify_password(password.as_bytes(), &parsed)
                .is_ok()
        })
        .unwrap_or(false)
}

/// Returns the actor, the raw session token (cookie value) and its expiry.
pub async fn login(
    conn: &mut PgConnection,
    login: &str,
    password: &str,
    ttl_hours: i64,
) -> AppResult<(Actor, String, OffsetDateTime)> {
    let Some((actor, hash)) = store::human_credentials(conn, login.trim()).await? else {
        // Same work and same answer for unknown logins.
        let _ = verify_password(
            password,
            "$argon2id$v=19$m=19456,t=2,p=1$AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        );
        return Err(AppError::Unauthorized);
    };
    if !verify_password(password, &hash) {
        return Err(AppError::Unauthorized);
    }
    let token = random_token();
    let expires_at = now() + Duration::hours(ttl_hours);
    store::insert_session(conn, &sha256_hex(&token), actor.id, expires_at).await?;
    Ok((actor, token, expires_at))
}

pub async fn logout(conn: &mut PgConnection, session_token: &str) -> AppResult<()> {
    store::delete_session(conn, &sha256_hex(session_token)).await?;
    Ok(())
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum NewActorKind {
    Agent,
    Human,
    Verifier,
}

#[derive(Debug, Clone, Deserialize, ToSchema)]
pub struct NewActorInput {
    pub kind: NewActorKind,
    pub name: String,
    /// LLM model (agents). Used by `require_different_model`.
    pub model: Option<String>,
    /// admin, planner, implementer, reviewer
    #[serde(default)]
    pub roles: Vec<String>,
    /// Humans only.
    pub login: Option<String>,
    /// Humans only, at least 10 characters.
    pub password: Option<String>,
    /// Identity forwarded by the MCP gateway: `client:<oauth client id>` or `email:<address>`.
    pub gateway_subject: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct CreatedActor {
    pub id: Uuid,
    pub kind: NewActorKind,
    pub name: String,
    pub roles: Vec<String>,
    pub model: Option<String>,
    /// Bearer token for agents and verifiers. Shown ONCE; only its SHA-256 is stored.
    pub token: Option<String>,
}

pub async fn create_actor(
    conn: &mut PgConnection,
    by: &Actor,
    input: NewActorInput,
) -> AppResult<CreatedActor> {
    if !by.is_admin() {
        return Err(AppError::Forbidden("only admins create actors".into()));
    }
    insert_actor(conn, input).await
}

async fn insert_actor(conn: &mut PgConnection, input: NewActorInput) -> AppResult<CreatedActor> {
    let name = input.name.trim();
    if name.is_empty() || name.chars().count() > 200 {
        return Err(AppError::BadRequest(
            "name must be 1..200 characters".into(),
        ));
    }
    for r in &input.roles {
        if atb_core::Role::parse(r).is_none() {
            return Err(AppError::BadRequest(format!(
                "unknown role {r:?} (admin, planner, implementer, reviewer)"
            )));
        }
    }
    let id = Uuid::now_v7();
    let (kind, token, password_hash, login) = match input.kind {
        NewActorKind::Human => {
            let login = input
                .login
                .as_deref()
                .map(str::trim)
                .filter(|l| !l.is_empty())
                .ok_or_else(|| AppError::BadRequest("humans need a login".into()))?;
            let password = input.password.as_deref().unwrap_or("");
            if password.chars().count() < MIN_PASSWORD_LEN {
                return Err(AppError::BadRequest(format!(
                    "password must have at least {MIN_PASSWORD_LEN} characters"
                )));
            }
            (
                "human",
                None,
                Some(hash_password(password)?),
                Some(login.to_string()),
            )
        }
        NewActorKind::Agent => ("agent", Some(random_token()), None, None),
        NewActorKind::Verifier => ("verifier", Some(random_token()), None, None),
    };
    let model = input
        .model
        .as_deref()
        .map(str::trim)
        .filter(|m| !m.is_empty());
    store::insert_actor(
        conn,
        NewActor {
            id,
            kind,
            name,
            model,
            roles: input.roles.clone(),
            token_hash: token.as_deref().map(sha256_hex),
            password_hash,
            login: login.as_deref(),
            gateway_subject: input.gateway_subject.as_deref().map(str::trim),
        },
    )
    .await
    .map_err(|e| match e {
        sqlx::Error::Database(db) if db.is_unique_violation() => {
            AppError::BadRequest("login or gateway_subject already in use".into())
        }
        other => other.into(),
    })?;
    Ok(CreatedActor {
        id,
        kind: input.kind,
        name: name.to_string(),
        roles: input.roles,
        model: model.map(str::to_string),
        token,
    })
}

/// Create the first human admin when no human exists yet. Returns true if created.
pub async fn bootstrap_admin(pool: &PgPool, login: &str, password: &str) -> AppResult<bool> {
    let mut tx = pool.begin().await?;
    sqlx::query("LOCK TABLE actors IN SHARE ROW EXCLUSIVE MODE")
        .execute(&mut *tx)
        .await?;
    if store::count_humans(&mut tx).await? > 0 {
        return Ok(false);
    }
    insert_actor(
        &mut tx,
        NewActorInput {
            kind: NewActorKind::Human,
            name: login.to_string(),
            model: None,
            roles: vec!["admin".into(), "planner".into(), "reviewer".into()],
            login: Some(login.to_string()),
            password: Some(password.to_string()),
            gateway_subject: None,
        },
    )
    .await?;
    tx.commit().await?;
    Ok(true)
}

/// CLI / tests: create an actor without an admin caller.
pub async fn create_actor_unchecked(
    pool: &PgPool,
    input: NewActorInput,
) -> AppResult<CreatedActor> {
    let mut conn = pool.acquire().await?;
    insert_actor(&mut conn, input).await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn argon2id_round_trip() {
        let h = hash_password("correct horse battery").unwrap();
        assert!(h.starts_with("$argon2id$"));
        assert!(verify_password("correct horse battery", &h));
        assert!(!verify_password("wrong", &h));
        assert!(!verify_password("x", "not-a-hash"));
    }
}
