//! Project visibility, members and invitations ("Membres et accès"), and the role check every
//! project-scoped request goes through (REST guard layer, MCP tools, lists).
//!
//! The rule is `atb_core::project_access::project_role` (pure); this module loads its inputs from
//! `project_members` and the caller's [`Scope`] (resolved once by the auth middleware).

use std::collections::{HashMap, HashSet};

use atb_core::project_access::{ProjectRole, RoleSource, Visibility, project_role};
use serde::{Deserialize, Serialize};
use sqlx::PgConnection;
use utoipa::ToSchema;
use uuid::Uuid;

use crate::actor::Actor;
use crate::error::{AppError, AppResult};
use crate::scope::Scope;
use crate::service::now;
use crate::state::AppState;

pub const USER: &str = "user";
pub const TEAM: &str = "team";

/// Something a request points at; resolved to its project.
#[derive(Debug, Clone, Copy)]
pub enum Target {
    Project(Uuid),
    Task(Uuid),
    Spec(Uuid),
    Question(Uuid),
}

pub async fn project_of(conn: &mut PgConnection, target: Target) -> AppResult<Uuid> {
    let id = match target {
        Target::Project(id) => Some(id),
        Target::Task(id) => {
            sqlx::query_scalar!("SELECT project_id FROM tasks WHERE id = $1", id)
                .fetch_optional(&mut *conn)
                .await?
        }
        Target::Spec(id) => {
            sqlx::query_scalar!("SELECT project_id FROM specs WHERE id = $1", id)
                .fetch_optional(&mut *conn)
                .await?
        }
        Target::Question(id) => sqlx::query_scalar!(
            "SELECT t.project_id FROM questions q JOIN tasks t ON t.id = q.task_id WHERE q.id = $1",
            id
        )
        .fetch_optional(&mut *conn)
        .await?,
    };
    id.ok_or_else(|| AppError::not_found("project"))
}

struct MemberRow {
    project_id: Uuid,
    subject_kind: String,
    role: String,
}

/// Accepted grants that concern this scope (its person or one of its teams).
async fn grants_for(
    conn: &mut PgConnection,
    subject: &str,
    teams: &[String],
    project: Option<Uuid>,
) -> AppResult<Vec<MemberRow>> {
    let rows = sqlx::query!(
        r#"SELECT project_id, subject_kind, role
           FROM project_members
           WHERE ($3::uuid IS NULL OR project_id = $3)
             AND accepted_at IS NOT NULL
             AND ((subject_kind = 'user' AND subject_id = $1)
               OR (subject_kind = 'team' AND subject_id = ANY($2)))"#,
        subject,
        teams,
        project
    )
    .fetch_all(&mut *conn)
    .await?;
    Ok(rows
        .into_iter()
        .map(|r| MemberRow {
            project_id: r.project_id,
            subject_kind: r.subject_kind,
            role: r.role,
        })
        .collect())
}

fn decide(
    visibility: Visibility,
    grants: &[&MemberRow],
    cap: Option<ProjectRole>,
) -> Option<(ProjectRole, RoleSource)> {
    let individual = grants
        .iter()
        .find(|g| g.subject_kind == USER)
        .and_then(|g| ProjectRole::parse(&g.role));
    let teams: Vec<ProjectRole> = grants
        .iter()
        .filter(|g| g.subject_kind == TEAM)
        .filter_map(|g| ProjectRole::parse(&g.role))
        .collect();
    project_role(false, visibility, individual, &teams).map(|(r, s)| match cap {
        Some(c) if r > c => (c, s),
        _ => (r, s),
    })
}

fn visibility_of(s: &str) -> Visibility {
    Visibility::parse(s).unwrap_or(Visibility::Private)
}

fn source_str(s: RoleSource) -> &'static str {
    match s {
        RoleSource::Admin => "admin",
        RoleSource::Individual => "individual",
        RoleSource::Team => "team",
        RoleSource::Public => "public",
    }
}

/// The caller's role on a project, or `None` when the project is invisible to them (or absent).
pub async fn role_in(
    conn: &mut PgConnection,
    scope: &Scope,
    project: Uuid,
) -> AppResult<Option<(ProjectRole, RoleSource)>> {
    let Some(vis) = sqlx::query_scalar!("SELECT visibility FROM projects WHERE id = $1", project)
        .fetch_optional(&mut *conn)
        .await?
    else {
        return Ok(None);
    };
    match scope {
        Scope::Unrestricted => Ok(Some((ProjectRole::Owner, RoleSource::Admin))),
        Scope::Restricted {
            subject,
            teams,
            cap,
        } => {
            let grants = grants_for(conn, subject, teams, Some(project)).await?;
            let refs: Vec<&MemberRow> = grants.iter().collect();
            Ok(decide(visibility_of(&vis), &refs, *cap))
        }
    }
}

/// Require at least `min` on the target's project. An invisible project answers 404 (its
/// existence is not revealed); a visible one with a lower role answers 403.
pub async fn require(
    conn: &mut PgConnection,
    scope: &Scope,
    target: Target,
    min: ProjectRole,
) -> AppResult<ProjectRole> {
    let project = project_of(conn, target).await?;
    let Some((role, _)) = role_in(conn, scope, project).await? else {
        return Err(AppError::not_found("project"));
    };
    if role < min {
        return Err(AppError::Forbidden(format!(
            "your role on this project is {}; {} is required",
            role.as_str(),
            min.as_str()
        )));
    }
    Ok(role)
}

/// Same as [`require`] with a pooled connection (REST/MCP, before the command transaction).
pub async fn require_pooled(
    st: &AppState,
    scope: &Scope,
    target: Target,
    min: ProjectRole,
) -> AppResult<ProjectRole> {
    let mut conn = st.pool.acquire().await?;
    require(&mut conn, scope, target, min).await
}

/// Visible projects and the caller's role on each; `None` = every project (unrestricted).
pub async fn visible_projects(
    conn: &mut PgConnection,
    scope: &Scope,
) -> AppResult<Option<HashMap<Uuid, ProjectRole>>> {
    let Scope::Restricted {
        subject,
        teams,
        cap,
    } = scope
    else {
        return Ok(None);
    };
    let projects = sqlx::query!("SELECT id, visibility FROM projects")
        .fetch_all(&mut *conn)
        .await?;
    let grants = grants_for(conn, subject, teams, None).await?;
    let mut out = HashMap::new();
    for p in projects {
        let mine: Vec<&MemberRow> = grants.iter().filter(|g| g.project_id == p.id).collect();
        if let Some((role, _)) = decide(visibility_of(&p.visibility), &mine, *cap) {
            out.insert(p.id, role);
        }
    }
    Ok(Some(out))
}

// --- members, visibility, invitations -----------------------------------------------------------

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct TeamGrant {
    pub id: String,
    pub name: String,
    pub member_count: usize,
    /// `editor` or `viewer`.
    pub role: String,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct TeamRoleRef {
    pub name: String,
    pub role: String,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct PersonAccess {
    /// Lower-cased login / email.
    pub subject: String,
    pub name: String,
    /// The board account, absent until the first sign-in.
    pub user_id: Option<Uuid>,
    /// Individual role, when set (pending or accepted).
    pub individual_role: Option<String>,
    /// The individual grant is an invitation not accepted yet.
    pub invitation_pending: bool,
    /// Teams giving a role on this project.
    pub via_teams: Vec<TeamRoleRef>,
    /// Effective role (`owner`, `editor`, `viewer`), absent = no access yet.
    pub effective_role: Option<String>,
    /// `admin`, `individual`, `team`, `public`.
    pub source: Option<String>,
    /// Names of the person's agents.
    pub agents: Vec<String>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct ProjectMembers {
    pub project_id: Uuid,
    pub visibility: String,
    /// The caller's role on the project.
    pub my_role: String,
    /// Owners (and admins) manage visibility and members.
    pub can_manage: bool,
    pub teams: Vec<TeamGrant>,
    pub people: Vec<PersonAccess>,
    /// Teams that can still be given a role (owners only; empty otherwise).
    pub available_teams: Vec<TeamGrant>,
}

#[derive(Debug, Clone, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct VisibilityInput {
    /// `public` or `private`.
    pub visibility: String,
}

#[derive(Debug, Clone, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct MemberInput {
    /// `user` (an email / login: the person is invited) or `team` (an account-service group id).
    pub kind: String,
    pub id: String,
    /// `owner` (people only), `editor` or `viewer`.
    pub role: String,
}

#[derive(Debug, Clone, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct RoleInput {
    pub role: String,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct InvitationView {
    pub project_id: Uuid,
    pub project_name: String,
    pub role: String,
    pub invited_by: Option<String>,
}

fn parse_role(s: &str) -> AppResult<ProjectRole> {
    ProjectRole::parse(s).ok_or_else(|| {
        AppError::BadRequest(format!("role must be owner, editor or viewer, got {s:?}"))
    })
}

async fn require_owner(
    conn: &mut PgConnection,
    scope: &Scope,
    actor: &Actor,
    project: Uuid,
) -> AppResult<()> {
    if !actor.is_human() {
        return Err(AppError::Forbidden(
            "only people manage project members".into(),
        ));
    }
    require(conn, scope, Target::Project(project), ProjectRole::Owner).await?;
    Ok(())
}

pub async fn members(
    st: &AppState,
    scope: &Scope,
    actor: &Actor,
    project: Uuid,
) -> AppResult<ProjectMembers> {
    let dir = st.directory.get().await?;
    let mut conn = st.pool.acquire().await?;
    let my_role = require(
        &mut conn,
        scope,
        Target::Project(project),
        ProjectRole::Viewer,
    )
    .await?;
    let vis = sqlx::query_scalar!("SELECT visibility FROM projects WHERE id = $1", project)
        .fetch_one(&mut *conn)
        .await?;
    let rows = sqlx::query!(
        r#"SELECT subject_kind, subject_id, role, accepted_at IS NOT NULL AS "accepted!"
           FROM project_members WHERE project_id = $1 ORDER BY subject_kind, subject_id"#,
        project
    )
    .fetch_all(&mut *conn)
    .await?;
    let humans = sqlx::query!("SELECT id, name, login, roles FROM actors WHERE kind = 'human'")
        .fetch_all(&mut *conn)
        .await?;
    let agents = sqlx::query!(
        r#"SELECT name, owner_id AS "owner_id!" FROM actors WHERE owner_id IS NOT NULL ORDER BY name"#
    )
    .fetch_all(&mut *conn)
    .await?;

    let team_rows: Vec<_> = rows.iter().filter(|r| r.subject_kind == TEAM).collect();
    let teams: Vec<TeamGrant> = team_rows
        .iter()
        .map(|r| {
            let g = dir.group(&r.subject_id);
            TeamGrant {
                id: r.subject_id.clone(),
                name: g
                    .map(|g| g.name.clone())
                    .unwrap_or_else(|| r.subject_id.clone()),
                member_count: g.map(|g| g.members.len()).unwrap_or(0),
                role: r.role.clone(),
            }
        })
        .collect();

    // Everyone concerned: individual grants plus the members of every granted team.
    let mut subjects: Vec<String> = rows
        .iter()
        .filter(|r| r.subject_kind == USER)
        .map(|r| r.subject_id.clone())
        .collect();
    for r in &team_rows {
        if let Some(g) = dir.group(&r.subject_id) {
            subjects.extend(g.members.iter().map(|m| m.to_lowercase()));
        }
    }
    let mut seen = HashSet::new();
    subjects.retain(|s| seen.insert(s.clone()));

    let visibility = visibility_of(&vis);
    let mut people: Vec<PersonAccess> = subjects
        .into_iter()
        .map(|subject| {
            let human = humans.iter().find(|h| {
                h.login
                    .as_deref()
                    .is_some_and(|l| l.eq_ignore_ascii_case(&subject))
            });
            let own = rows
                .iter()
                .find(|r| r.subject_kind == USER && r.subject_id == subject);
            let via: Vec<TeamRoleRef> = team_rows
                .iter()
                .filter_map(|r| {
                    let g = dir.group(&r.subject_id)?;
                    g.members
                        .iter()
                        .any(|m| m.eq_ignore_ascii_case(&subject))
                        .then(|| TeamRoleRef {
                            name: g.name.clone(),
                            role: r.role.clone(),
                        })
                })
                .collect();
            let is_admin = human.is_some_and(|h| h.roles.iter().any(|r| r == "admin"));
            let individual = own
                .filter(|r| r.accepted)
                .and_then(|r| ProjectRole::parse(&r.role));
            let team_roles: Vec<ProjectRole> = via
                .iter()
                .filter_map(|t| ProjectRole::parse(&t.role))
                .collect();
            let eff = project_role(is_admin, visibility, individual, &team_roles);
            let name = human
                .map(|h| h.name.clone())
                .or_else(|| {
                    dir.user(&subject)
                        .map(|u| u.display_name.clone())
                        .filter(|n| !n.is_empty())
                })
                .unwrap_or_else(|| subject.clone());
            PersonAccess {
                name,
                user_id: human.map(|h| h.id),
                individual_role: own.map(|r| r.role.clone()),
                invitation_pending: own.is_some_and(|r| !r.accepted),
                via_teams: via,
                effective_role: eff.map(|(r, _)| r.as_str().to_string()),
                source: eff.map(|(_, s)| source_str(s).to_string()),
                agents: human
                    .map(|h| {
                        agents
                            .iter()
                            .filter(|a| a.owner_id == h.id)
                            .map(|a| a.name.clone())
                            .collect()
                    })
                    .unwrap_or_default(),
                subject,
            }
        })
        .collect();
    let rank = |p: &PersonAccess| match p.effective_role.as_deref() {
        Some("owner") => 0,
        Some("editor") => 1,
        Some("viewer") => 2,
        _ => 3,
    };
    people.sort_by(|a, b| {
        rank(a)
            .cmp(&rank(b))
            .then(a.name.to_lowercase().cmp(&b.name.to_lowercase()))
    });
    let can_manage = actor.is_human() && my_role == ProjectRole::Owner;
    let available_teams = if can_manage {
        dir.groups
            .iter()
            .filter(|g| !teams.iter().any(|t| t.id == g.id))
            .map(|g| TeamGrant {
                id: g.id.clone(),
                name: g.name.clone(),
                member_count: g.members.len(),
                role: String::new(),
            })
            .collect()
    } else {
        vec![]
    };
    Ok(ProjectMembers {
        project_id: project,
        visibility: vis,
        my_role: my_role.as_str().into(),
        can_manage,
        teams,
        people,
        available_teams,
    })
}

pub async fn set_visibility(
    st: &AppState,
    scope: &Scope,
    actor: &Actor,
    project: Uuid,
    input: VisibilityInput,
) -> AppResult<()> {
    let v = Visibility::parse(&input.visibility)
        .ok_or_else(|| AppError::BadRequest("visibility must be public or private".into()))?;
    let mut conn = st.pool.acquire().await?;
    require_owner(&mut conn, scope, actor, project).await?;
    sqlx::query!(
        "UPDATE projects SET visibility = $2, updated_at = now() WHERE id = $1",
        project,
        v.as_str()
    )
    .execute(&mut *conn)
    .await?;
    Ok(())
}

/// Accepted individual owners other than `except` (a lower-cased subject).
async fn other_owners(conn: &mut PgConnection, project: Uuid, except: &str) -> AppResult<i64> {
    Ok(sqlx::query_scalar!(
        r#"SELECT count(*) AS "n!" FROM project_members
           WHERE project_id = $1 AND subject_kind = 'user' AND role = 'owner'
             AND accepted_at IS NOT NULL AND subject_id <> $2"#,
        project,
        except
    )
    .fetch_one(&mut *conn)
    .await?)
}

fn normalize_subject(kind: &str, id: &str) -> AppResult<String> {
    let id = id.trim();
    if id.is_empty() || id.chars().count() > 255 {
        return Err(AppError::BadRequest("id must be 1..255 characters".into()));
    }
    match kind {
        USER => Ok(id.to_lowercase()),
        TEAM => Ok(id.to_string()),
        _ => Err(AppError::BadRequest("kind must be user or team".into())),
    }
}

/// Serializes member changes of one project (the "last owner" check reads then writes).
async fn lock_project(conn: &mut PgConnection, project: Uuid) -> AppResult<()> {
    sqlx::query_scalar!(
        "SELECT id FROM projects WHERE id = $1 FOR NO KEY UPDATE",
        project
    )
    .fetch_optional(&mut *conn)
    .await?
    .ok_or_else(|| AppError::not_found("project"))?;
    Ok(())
}

/// Invite a person (pending until they accept) or give a team a role (immediate).
pub async fn add_member(
    st: &AppState,
    scope: &Scope,
    actor: &Actor,
    project: Uuid,
    input: MemberInput,
) -> AppResult<()> {
    let role = parse_role(&input.role)?;
    let subject = normalize_subject(&input.kind, &input.id)?;
    if input.kind == TEAM {
        if !role.allowed_for_team() {
            return Err(AppError::BadRequest(
                "a team can be editor or viewer; owner is given to a person".into(),
            ));
        }
        let dir = st.directory.get().await?;
        if dir.group(&subject).is_none() {
            return Err(AppError::not_found("team"));
        }
    }
    let mut tx = st.pool.begin().await?;
    require_owner(&mut tx, scope, actor, project).await?;
    let accepted = (input.kind == TEAM).then(now);
    sqlx::query!(
        r#"INSERT INTO project_members
               (project_id, subject_kind, subject_id, role, invited_by, accepted_at)
           VALUES ($1, $2, $3, $4, $5, $6)
           ON CONFLICT (project_id, subject_kind, subject_id) DO UPDATE SET role = EXCLUDED.role"#,
        project,
        input.kind,
        subject,
        role.as_str(),
        actor.id,
        accepted
    )
    .execute(&mut *tx)
    .await?;
    tx.commit().await?;
    Ok(())
}

pub async fn set_member_role(
    st: &AppState,
    scope: &Scope,
    actor: &Actor,
    project: Uuid,
    kind: &str,
    id: &str,
    input: RoleInput,
) -> AppResult<()> {
    let role = parse_role(&input.role)?;
    let subject = normalize_subject(kind, id)?;
    if kind == TEAM && !role.allowed_for_team() {
        return Err(AppError::BadRequest(
            "a team can be editor or viewer; owner is given to a person".into(),
        ));
    }
    let mut tx = st.pool.begin().await?;
    require_owner(&mut tx, scope, actor, project).await?;
    lock_project(&mut tx, project).await?;
    if kind == USER
        && role != ProjectRole::Owner
        && other_owners(&mut tx, project, &subject).await? == 0
    {
        return Err(AppError::BadRequest(
            "a project keeps at least one owner".into(),
        ));
    }
    let n = sqlx::query!(
        "UPDATE project_members SET role = $4 WHERE project_id = $1 AND subject_kind = $2 AND subject_id = $3",
        project,
        kind,
        subject,
        role.as_str()
    )
    .execute(&mut *tx)
    .await?
    .rows_affected();
    if n == 0 {
        return Err(AppError::not_found("member"));
    }
    tx.commit().await?;
    Ok(())
}

pub async fn remove_member(
    st: &AppState,
    scope: &Scope,
    actor: &Actor,
    project: Uuid,
    kind: &str,
    id: &str,
) -> AppResult<()> {
    let subject = normalize_subject(kind, id)?;
    let mut tx = st.pool.begin().await?;
    require_owner(&mut tx, scope, actor, project).await?;
    lock_project(&mut tx, project).await?;
    if kind == USER {
        let is_owner = sqlx::query_scalar!(
            r#"SELECT role = 'owner' AS "o!" FROM project_members
               WHERE project_id = $1 AND subject_kind = 'user' AND subject_id = $2
                 AND accepted_at IS NOT NULL"#,
            project,
            subject
        )
        .fetch_optional(&mut *tx)
        .await?
        .unwrap_or(false);
        if is_owner && other_owners(&mut tx, project, &subject).await? == 0 {
            return Err(AppError::BadRequest(
                "a project keeps at least one owner".into(),
            ));
        }
    }
    sqlx::query!(
        "DELETE FROM project_members WHERE project_id = $1 AND subject_kind = $2 AND subject_id = $3",
        project,
        kind,
        subject
    )
    .execute(&mut *tx)
    .await?;
    tx.commit().await?;
    Ok(())
}

/// The creator of a project becomes its (accepted) owner.
pub async fn add_creator(conn: &mut PgConnection, project: Uuid, actor: &Actor) -> AppResult<()> {
    let login = login_of(conn, actor).await?;
    let subject = crate::scope::subject_of(actor.id, login.as_deref());
    sqlx::query!(
        r#"INSERT INTO project_members
               (project_id, subject_kind, subject_id, role, invited_by, accepted_at)
           VALUES ($1, 'user', $2, 'owner', $3, $4)"#,
        project,
        subject,
        actor.id,
        now()
    )
    .execute(&mut *conn)
    .await?;
    Ok(())
}

async fn login_of(conn: &mut PgConnection, actor: &Actor) -> AppResult<Option<String>> {
    Ok(
        sqlx::query_scalar!("SELECT login FROM actors WHERE id = $1", actor.id)
            .fetch_optional(&mut *conn)
            .await?
            .flatten(),
    )
}

async fn my_subject(conn: &mut PgConnection, actor: &Actor) -> AppResult<String> {
    let login = login_of(conn, actor).await?;
    Ok(crate::scope::subject_of(actor.id, login.as_deref()))
}

pub async fn my_invitations(st: &AppState, actor: &Actor) -> AppResult<Vec<InvitationView>> {
    if !actor.is_human() {
        return Ok(vec![]);
    }
    let mut conn = st.pool.acquire().await?;
    let subject = my_subject(&mut conn, actor).await?;
    let rows = sqlx::query!(
        r#"SELECT p.id, p.name, m.role, a.name AS "invited_by?"
           FROM project_members m
           JOIN projects p ON p.id = m.project_id
           LEFT JOIN actors a ON a.id = m.invited_by
           WHERE m.subject_kind = 'user' AND m.subject_id = $1 AND m.accepted_at IS NULL
           ORDER BY m.created_at"#,
        subject
    )
    .fetch_all(&mut *conn)
    .await?;
    Ok(rows
        .into_iter()
        .map(|r| InvitationView {
            project_id: r.id,
            project_name: r.name,
            role: r.role,
            invited_by: r.invited_by,
        })
        .collect())
}

/// Accept (`true`) or decline (`false`) one's own invitation.
pub async fn answer_invitation(
    st: &AppState,
    actor: &Actor,
    project: Uuid,
    accept: bool,
) -> AppResult<()> {
    if !actor.is_human() {
        return Err(AppError::Forbidden("only people answer invitations".into()));
    }
    let mut conn = st.pool.acquire().await?;
    let subject = my_subject(&mut conn, actor).await?;
    let n = if accept {
        sqlx::query!(
            r#"UPDATE project_members SET accepted_at = $3
               WHERE project_id = $1 AND subject_kind = 'user' AND subject_id = $2
                 AND accepted_at IS NULL"#,
            project,
            subject,
            now()
        )
        .execute(&mut *conn)
        .await?
        .rows_affected()
    } else {
        sqlx::query!(
            r#"DELETE FROM project_members
               WHERE project_id = $1 AND subject_kind = 'user' AND subject_id = $2
                 AND accepted_at IS NULL"#,
            project,
            subject
        )
        .execute(&mut *conn)
        .await?
        .rows_affected()
    };
    if n == 0 {
        return Err(AppError::not_found("invitation"));
    }
    Ok(())
}
