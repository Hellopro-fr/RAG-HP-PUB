//! What projects a caller may see, resolved ONCE per request by the auth middleware (next to the
//! [`Actor`]), so project checks are plain SQL reads (no account-service call inside a command).
//!
//! - Admins, the system, and agents without an owner (created from the CLI or before owners
//!   existed): unrestricted.
//! - A Classique human: their login (= email) and their account-service teams.
//! - An agent with an owner: its owner's login and teams, capped at editor (agents never manage
//!   members). An Admin's agents are unrestricted.
//! - Disabled humans, and agents of a disabled owner, are refused at authentication.

use atb_core::project_access::ProjectRole;
use sqlx::PgConnection;
use uuid::Uuid;

use crate::actor::Actor;
use crate::error::{AppError, AppResult};
use crate::state::AppState;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Scope {
    Unrestricted,
    Restricted {
        /// Lower-cased login of the person (the agent's owner for an agent).
        subject: String,
        /// account-service group ids.
        teams: Vec<String>,
        /// Maximum role (agents: editor).
        cap: Option<ProjectRole>,
    },
}

struct AccessRow {
    kind: String,
    login: Option<String>,
    roles: Vec<String>,
    owner_id: Option<Uuid>,
    disabled: bool,
}

async fn row(conn: &mut PgConnection, id: Uuid) -> AppResult<Option<AccessRow>> {
    let r = sqlx::query!(
        r#"SELECT kind, login, roles, owner_id, disabled_at IS NOT NULL AS "disabled!"
           FROM actors WHERE id = $1"#,
        id
    )
    .fetch_optional(&mut *conn)
    .await?;
    Ok(r.map(|r| AccessRow {
        kind: r.kind,
        login: r.login,
        roles: r.roles,
        owner_id: r.owner_id,
        disabled: r.disabled,
    }))
}

fn is_admin(roles: &[String]) -> bool {
    roles.iter().any(|r| r == "admin")
}

/// The person a restriction is keyed on: their login, or their id when they have none.
pub fn subject_of(id: Uuid, login: Option<&str>) -> String {
    login
        .map(|l| l.trim().to_lowercase())
        .filter(|l| !l.is_empty())
        .unwrap_or_else(|| id.to_string())
}

async fn teams_of(st: &AppState, login: Option<&str>) -> Vec<String> {
    let Some(login) = login else { return vec![] };
    match st.directory.get().await {
        Ok(d) => d.teams_of(login).iter().map(|g| g.id.clone()).collect(),
        Err(e) => {
            // Fail closed on team-granted access only; individual grants still work.
            tracing::warn!(error = %e.message(), "directory unavailable: resolving scope without teams");
            vec![]
        }
    }
}

pub async fn resolve(st: &AppState, conn: &mut PgConnection, actor: &Actor) -> AppResult<Scope> {
    let Some(me) = row(conn, actor.id).await? else {
        return Ok(Scope::Unrestricted); // the system actor is seeded; anything else was resolved
    };
    if me.disabled {
        return Err(AppError::Forbidden(
            "your access to the board is disabled; ask an admin".into(),
        ));
    }
    match me.kind.as_str() {
        "system" => Ok(Scope::Unrestricted),
        "human" => {
            if is_admin(&me.roles) {
                return Ok(Scope::Unrestricted);
            }
            Ok(Scope::Restricted {
                subject: subject_of(actor.id, me.login.as_deref()),
                teams: teams_of(st, me.login.as_deref()).await,
                cap: None,
            })
        }
        _ => {
            let Some(owner_id) = me.owner_id else {
                return Ok(Scope::Unrestricted);
            };
            let owner = row(conn, owner_id)
                .await?
                .ok_or_else(|| AppError::Forbidden("agent owner not found".into()))?;
            if owner.disabled {
                return Err(AppError::Forbidden(
                    "the owner of this agent has been disabled".into(),
                ));
            }
            if is_admin(&owner.roles) {
                return Ok(Scope::Unrestricted);
            }
            Ok(Scope::Restricted {
                subject: subject_of(owner_id, owner.login.as_deref()),
                teams: teams_of(st, owner.login.as_deref()).await,
                cap: Some(ProjectRole::Editor),
            })
        }
    }
}
