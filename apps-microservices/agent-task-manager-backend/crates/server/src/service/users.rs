//! "Utilisateurs" page: people of the board (from their first sign-in) and people invited to a
//! project who never signed in, with their level, status, teams, projects and agents.
//! Disabling blocks the board (sessions deleted, their agents refused at authentication) without
//! touching the HelloPro account; their agents' leases then expire and the tasks return to Ready.

use std::collections::HashMap;

use atb_core::project_access::{ProjectRole, Visibility, project_role};
use serde::{Deserialize, Serialize};
use time::OffsetDateTime;
use utoipa::ToSchema;
use uuid::Uuid;

use crate::actor::Actor;
use crate::error::{AppError, AppResult};
use crate::scope::subject_of;
use crate::service::now;
use crate::state::AppState;

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct UserProject {
    pub id: Uuid,
    pub name: String,
    pub role: String,
    /// An invitation not accepted yet.
    pub pending: bool,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct UserView {
    /// Absent for a person invited who never signed in.
    pub id: Option<Uuid>,
    pub name: String,
    pub login: String,
    /// `admin` or `classic`.
    pub level: String,
    /// `active`, `disabled` or `pending` (invited, never signed in).
    pub status: String,
    #[serde(with = "time::serde::rfc3339::option")]
    pub last_seen_at: Option<OffsetDateTime>,
    #[serde(with = "time::serde::rfc3339::option")]
    pub first_seen_at: Option<OffsetDateTime>,
    pub teams: Vec<String>,
    pub projects: Vec<UserProject>,
    pub agents: Vec<String>,
}

#[derive(Debug, Clone, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UserStatusInput {
    pub disabled: bool,
}

struct Member {
    project_id: Uuid,
    subject_kind: String,
    subject_id: String,
    role: String,
    accepted: bool,
}

/// The projects a person is a member of (individually, invited, or through a team).
fn projects_of(
    subject: &str,
    team_ids: &[String],
    projects: &[(Uuid, String, String)],
    members: &[Member],
) -> Vec<UserProject> {
    let mut out = Vec::new();
    for (pid, pname, vis) in projects {
        let own = members
            .iter()
            .find(|m| m.project_id == *pid && m.subject_kind == "user" && m.subject_id == subject);
        let team_roles: Vec<ProjectRole> = members
            .iter()
            .filter(|m| {
                m.project_id == *pid && m.subject_kind == "team" && team_ids.contains(&m.subject_id)
            })
            .filter_map(|m| ProjectRole::parse(&m.role))
            .collect();
        if own.is_none() && team_roles.is_empty() {
            continue;
        }
        let individual = own
            .filter(|m| m.accepted)
            .and_then(|m| ProjectRole::parse(&m.role));
        let visibility = Visibility::parse(vis).unwrap_or(Visibility::Private);
        let (role, pending) = match project_role(false, visibility, individual, &team_roles) {
            Some((r, _)) if individual.is_some() || !team_roles.is_empty() => {
                (r.as_str().to_string(), false)
            }
            // Only a pending invitation: show the role offered.
            _ => (own.map(|m| m.role.clone()).unwrap_or_default(), true),
        };
        out.push(UserProject {
            id: *pid,
            name: pname.clone(),
            role,
            pending,
        });
    }
    out.sort_by_key(|p| p.name.to_lowercase());
    out
}

pub async fn list(st: &AppState) -> AppResult<Vec<UserView>> {
    let dir = st.directory.get().await?;
    let mut conn = st.pool.acquire().await?;
    let humans = sqlx::query!(
        r#"SELECT id, name, login, roles, last_seen_at, created_at,
                  disabled_at IS NOT NULL AS "disabled!"
           FROM actors WHERE kind = 'human' ORDER BY lower(name), id"#
    )
    .fetch_all(&mut *conn)
    .await?;
    let agents = sqlx::query!(
        r#"SELECT name, owner_id AS "owner_id!" FROM actors WHERE owner_id IS NOT NULL ORDER BY name"#
    )
    .fetch_all(&mut *conn)
    .await?;
    let projects: Vec<(Uuid, String, String)> =
        sqlx::query!("SELECT id, name, visibility FROM projects ORDER BY created_at")
            .fetch_all(&mut *conn)
            .await?
            .into_iter()
            .map(|p| (p.id, p.name, p.visibility))
            .collect();
    let members: Vec<Member> = sqlx::query!(
        r#"SELECT project_id, subject_kind, subject_id, role, accepted_at IS NOT NULL AS "accepted!"
           FROM project_members"#
    )
    .fetch_all(&mut *conn)
    .await?
    .into_iter()
    .map(|m| Member {
        project_id: m.project_id,
        subject_kind: m.subject_kind,
        subject_id: m.subject_id,
        role: m.role,
        accepted: m.accepted,
    })
    .collect();

    let teams_of = |login: Option<&str>| -> (Vec<String>, Vec<String>) {
        login
            .map(|l| {
                dir.teams_of(l)
                    .iter()
                    .map(|g| (g.id.clone(), g.name.clone()))
                    .unzip()
            })
            .unwrap_or_default()
    };

    let mut by_owner: HashMap<Uuid, Vec<String>> = HashMap::new();
    for a in agents {
        by_owner.entry(a.owner_id).or_default().push(a.name);
    }

    let mut known = Vec::new();
    let mut out: Vec<UserView> = Vec::new();
    for h in &humans {
        let subject = subject_of(h.id, h.login.as_deref());
        let (team_ids, team_names) = teams_of(h.login.as_deref());
        out.push(UserView {
            id: Some(h.id),
            name: h.name.clone(),
            login: h.login.clone().unwrap_or_default(),
            level: if h.roles.iter().any(|r| r == "admin") {
                "admin".into()
            } else {
                "classic".into()
            },
            status: if h.disabled { "disabled" } else { "active" }.into(),
            last_seen_at: h.last_seen_at,
            first_seen_at: Some(h.created_at),
            teams: team_names,
            projects: projects_of(&subject, &team_ids, &projects, &members),
            agents: by_owner.remove(&h.id).unwrap_or_default(),
        });
        known.push(subject);
    }

    // People invited to a project who never signed in.
    let mut invited: Vec<String> = members
        .iter()
        .filter(|m| m.subject_kind == "user" && !known.contains(&m.subject_id))
        .map(|m| m.subject_id.clone())
        .collect();
    invited.sort();
    invited.dedup();
    for email in invited {
        let (team_ids, team_names) = teams_of(Some(&email));
        out.push(UserView {
            id: None,
            name: dir
                .user(&email)
                .map(|u| u.display_name.clone())
                .filter(|n| !n.is_empty())
                .unwrap_or_else(|| email.clone()),
            level: "classic".into(),
            status: "pending".into(),
            last_seen_at: None,
            first_seen_at: None,
            teams: team_names,
            projects: projects_of(&email, &team_ids, &projects, &members),
            agents: vec![],
            login: email,
        });
    }
    Ok(out)
}

fn require_admin_on_other(by: &Actor, id: Uuid) -> AppResult<()> {
    if !(by.is_human() && by.is_admin()) {
        return Err(AppError::Forbidden("only admins manage users".into()));
    }
    if by.id == id {
        return Err(AppError::Forbidden(
            "you cannot do this on your own account".into(),
        ));
    }
    Ok(())
}

pub async fn set_status(
    st: &AppState,
    by: &Actor,
    id: Uuid,
    input: UserStatusInput,
) -> AppResult<()> {
    require_admin_on_other(by, id)?;
    let mut tx = st.pool.begin().await?;
    let target = sqlx::query!(
        "SELECT roles FROM actors WHERE id = $1 AND kind = 'human' FOR UPDATE",
        id
    )
    .fetch_optional(&mut *tx)
    .await?
    .ok_or_else(|| AppError::not_found("user"))?;
    if input.disabled && target.roles.iter().any(|r| r == "admin") {
        return Err(AppError::BadRequest(
            "an Admin cannot be disabled: change their level to Classique first".into(),
        ));
    }
    let at = input.disabled.then(now);
    sqlx::query!(
        "UPDATE actors SET disabled_at = $2, updated_at = now() WHERE id = $1",
        id,
        at
    )
    .execute(&mut *tx)
    .await?;
    if input.disabled {
        sqlx::query!("DELETE FROM sessions WHERE actor_id = $1", id)
            .execute(&mut *tx)
            .await?;
    }
    tx.commit().await?;
    tracing::info!(by = %by.id, user = %id, disabled = input.disabled, "user status changed");
    Ok(())
}

pub async fn revoke_sessions(st: &AppState, by: &Actor, id: Uuid) -> AppResult<()> {
    require_admin_on_other(by, id)?;
    let mut conn = st.pool.acquire().await?;
    sqlx::query!("DELETE FROM sessions WHERE actor_id = $1", id)
        .execute(&mut *conn)
        .await?;
    tracing::info!(by = %by.id, user = %id, "sessions revoked");
    Ok(())
}
