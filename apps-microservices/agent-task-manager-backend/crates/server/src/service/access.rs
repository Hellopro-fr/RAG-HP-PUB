//! Levels (Admin / Classique) and permissions per user and per team ("Accès" page).
//!
//! The decision itself is `atb_core::access::resolve` (pure). This module loads its inputs: the
//! user's own settings, their teams from the account-service directory, and those teams'
//! settings. Only humans are subject to permissions; agents, verifiers and the system keep the
//! role checks they had (an agent's rights are decided by the human who connected it).

use std::collections::HashMap;

use atb_core::access::{Decision, Effect, Level, Permission, Source, TeamOutcome, TeamSetting};
use serde::{Deserialize, Serialize};
use sqlx::PgConnection;
use utoipa::ToSchema;
use uuid::Uuid;

use crate::actor::Actor;
use crate::directory::{DirGroup, Directory};
use crate::error::{AppError, AppResult};
use crate::repository::access::{self as repo, HumanRow, RuleRow};
use crate::state::AppState;

pub const USER: &str = "user";
pub const TEAM: &str = "team";

pub fn level_of_roles(roles: &[String]) -> Level {
    if roles.iter().any(|r| r == "admin") {
        Level::Admin
    } else {
        Level::Classic
    }
}

fn level_str(level: Level) -> &'static str {
    match level {
        Level::Admin => "admin",
        Level::Classic => "classic",
    }
}

fn settings_of(rules: &[RuleRow], kind: &str, id: &str) -> HashMap<Permission, Effect> {
    rules
        .iter()
        .filter(|r| r.subject_kind == kind && r.subject_id == id)
        .filter_map(|r| Some((Permission::parse(&r.permission)?, Effect::parse(&r.effect)?)))
        .collect()
}

/// Everything needed to resolve one human's permissions.
struct Subject<'a> {
    level: Level,
    own: HashMap<Permission, Effect>,
    teams: Vec<(&'a DirGroup, HashMap<Permission, Effect>)>,
}

impl Subject<'_> {
    fn decide(&self, p: Permission) -> Decision {
        let teams: Vec<TeamSetting> = self
            .teams
            .iter()
            .map(|(g, s)| TeamSetting {
                team_id: g.id.clone(),
                team_name: g.name.clone(),
                effect: s.get(&p).copied(),
            })
            .collect();
        atb_core::access::resolve(self.level, p, self.own.get(&p).copied(), &teams)
    }
}

fn subject<'a>(human: &HumanRow, dir: &'a Directory, rules: &[RuleRow]) -> Subject<'a> {
    let teams = human
        .login
        .as_deref()
        .map(|login| dir.teams_of(login))
        .unwrap_or_default()
        .into_iter()
        .map(|g| (g, settings_of(rules, TEAM, &g.id)))
        .collect();
    Subject {
        level: level_of_roles(&human.roles),
        own: settings_of(rules, USER, &human.id.to_string()),
        teams,
    }
}

async fn rules_for_human(
    conn: &mut PgConnection,
    human: &HumanRow,
    dir: &Directory,
) -> AppResult<Vec<RuleRow>> {
    let mut rules = repo::rules_for(conn, USER, &[human.id.to_string()]).await?;
    if let Some(login) = human.login.as_deref() {
        let team_ids: Vec<String> = dir.teams_of(login).iter().map(|g| g.id.clone()).collect();
        if !team_ids.is_empty() {
            rules.extend(repo::rules_for(conn, TEAM, &team_ids).await?);
        }
    }
    Ok(rules)
}

async fn human_row(conn: &mut PgConnection, actor: &Actor) -> AppResult<HumanRow> {
    repo::human(conn, actor.id)
        .await?
        .ok_or_else(|| AppError::not_found("human"))
}

/// Refuse the command if a human caller lacks `p`. Call it BEFORE opening the command
/// transaction (it may call account-service).
pub async fn require(st: &AppState, actor: &Actor, p: Permission) -> AppResult<()> {
    if !actor.is_human() {
        return Ok(());
    }
    let mut conn = st.pool.acquire().await?;
    let human = human_row(&mut conn, actor).await?;
    if level_of_roles(&human.roles) == Level::Admin {
        return Ok(());
    }
    let dir = st.directory.get().await?;
    let rules = rules_for_human(&mut conn, &human, &dir).await?;
    let d = subject(&human, &dir, &rules).decide(p);
    if d.allowed {
        Ok(())
    } else {
        Err(AppError::Forbidden(format!(
            "permission {} refused ({}); ask an admin on the Accès page",
            p.as_str(),
            source_view(&d.source).label
        )))
    }
}

/// Level and allowed permissions of the caller (for `/api/auth/me`). A directory outage
/// degrades to "no teams" here so the UI still loads; commands stay strict (`require`).
pub async fn me(st: &AppState, actor: &Actor) -> AppResult<(Option<Level>, Vec<String>)> {
    if !actor.is_human() {
        return Ok((None, vec![]));
    }
    let mut conn = st.pool.acquire().await?;
    let human = human_row(&mut conn, actor).await?;
    let dir = match st.directory.get().await {
        Ok(d) => d,
        Err(e) => {
            tracing::warn!(error = %e.message(), "directory unavailable for /me, using no teams");
            Default::default()
        }
    };
    let rules = rules_for_human(&mut conn, &human, &dir).await?;
    let s = subject(&human, &dir, &rules);
    let allowed = Permission::ALL
        .into_iter()
        .filter(|p| s.decide(*p).allowed)
        .map(|p| p.as_str().to_string())
        .collect();
    Ok((Some(s.level), allowed))
}

// --- admin API ("Accès" page) ------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct PermissionInfo {
    pub key: String,
    /// Only the Admin level has it; it cannot be set.
    pub admin_only: bool,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct TeamRef {
    pub id: String,
    pub name: String,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct AccessUser {
    pub id: Uuid,
    pub name: String,
    pub login: Option<String>,
    /// `admin` or `classic`.
    pub level: String,
    pub teams: Vec<TeamRef>,
    /// Number of individual settings.
    pub settings: usize,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct AccessTeam {
    pub id: String,
    pub name: String,
    pub description: String,
    pub member_count: usize,
    /// Number of team settings.
    pub settings: usize,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct AccessOverview {
    pub permissions: Vec<PermissionInfo>,
    pub users: Vec<AccessUser>,
    pub teams: Vec<AccessTeam>,
    /// false when account-service is not configured (no teams).
    pub directory_enabled: bool,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct SourceView {
    /// `admin_level`, `admin_only`, `individual`, `teams`, `default`.
    pub kind: String,
    /// What the teams say: `allowed`, `denied` or `unset` (absent for admin_level/admin_only).
    pub teams_outcome: Option<String>,
    /// Teams that decide `teams_outcome`.
    pub teams: Vec<String>,
    /// Short English explanation (logs, errors); the UI builds its own French text.
    #[serde(skip)]
    pub label: String,
}

fn outcome_view(o: &TeamOutcome) -> (String, Vec<String>) {
    match o {
        TeamOutcome::Allowed { by } => ("allowed".into(), by.clone()),
        TeamOutcome::Denied { by } => ("denied".into(), by.clone()),
        TeamOutcome::Unset => ("unset".into(), vec![]),
    }
}

pub fn source_view(s: &Source) -> SourceView {
    let (kind, outcome) = match s {
        Source::AdminLevel => ("admin_level", None),
        Source::AdminOnly => ("admin_only", None),
        Source::Individual { teams } => ("individual", Some(outcome_view(teams))),
        Source::Teams { teams } => ("teams", Some(outcome_view(teams))),
        Source::Default => ("default", None),
    };
    let label = match (kind, &outcome) {
        ("teams", Some((o, by))) => format!("teams {o}: {}", by.join(", ")),
        ("individual", _) => "individual setting".into(),
        ("admin_only", _) => "admins only".into(),
        ("default", _) => "no setting".into(),
        _ => kind.into(),
    };
    let (teams_outcome, teams) = match outcome {
        Some((o, by)) => (Some(o), by),
        None => (None, vec![]),
    };
    SourceView {
        kind: kind.into(),
        teams_outcome,
        teams,
        label,
    }
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct EffectiveAccess {
    pub permission: String,
    /// The individual setting: `allow`, `deny`, or absent (inherit from teams).
    pub setting: Option<String>,
    pub allowed: bool,
    pub source: SourceView,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct UserAccess {
    pub user: AccessUser,
    pub permissions: Vec<EffectiveAccess>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct TeamPermission {
    pub permission: String,
    /// The team setting: `allow`, `deny`, or absent (not set).
    pub setting: Option<String>,
    /// Members with an individual setting for this permission (it overrides the team's).
    pub exceptions: usize,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct TeamMember {
    pub email: String,
    pub name: String,
    /// The board account, when the member has signed in once.
    pub user_id: Option<Uuid>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct TeamAccess {
    pub team: AccessTeam,
    pub members: Vec<TeamMember>,
    pub permissions: Vec<TeamPermission>,
}

#[derive(Debug, Clone, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SettingInput {
    /// `allow`, `deny`, or null to remove the setting.
    pub effect: Option<String>,
}

#[derive(Debug, Clone, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct LevelInput {
    /// `admin` or `classic`.
    pub level: String,
}

fn require_admin(actor: &Actor) -> AppResult<()> {
    if actor.is_human() && actor.is_admin() {
        Ok(())
    } else {
        Err(AppError::Forbidden(
            "only admins manage access (access.manage)".into(),
        ))
    }
}

fn access_user(h: &HumanRow, dir: &Directory, rules: &[RuleRow]) -> AccessUser {
    let teams = h
        .login
        .as_deref()
        .map(|l| dir.teams_of(l))
        .unwrap_or_default()
        .into_iter()
        .map(|g| TeamRef {
            id: g.id.clone(),
            name: g.name.clone(),
        })
        .collect();
    AccessUser {
        id: h.id,
        name: h.name.clone(),
        login: h.login.clone(),
        level: level_str(level_of_roles(&h.roles)).into(),
        teams,
        settings: settings_of(rules, USER, &h.id.to_string()).len(),
    }
}

fn access_team(g: &DirGroup, rules: &[RuleRow]) -> AccessTeam {
    AccessTeam {
        id: g.id.clone(),
        name: g.name.clone(),
        description: g.description.clone(),
        member_count: g.members.len(),
        settings: settings_of(rules, TEAM, &g.id).len(),
    }
}

fn permission_infos() -> Vec<PermissionInfo> {
    Permission::ALL
        .into_iter()
        .map(|p| PermissionInfo {
            key: p.as_str().into(),
            admin_only: p.admin_only(),
        })
        .collect()
}

pub async fn overview(st: &AppState, by: &Actor) -> AppResult<AccessOverview> {
    require_admin(by)?;
    let dir = st.directory.get().await?;
    let mut conn = st.pool.acquire().await?;
    let rules = repo::all_rules(&mut conn).await?;
    let humans = repo::humans(&mut conn).await?;
    Ok(AccessOverview {
        permissions: permission_infos(),
        users: humans
            .iter()
            .map(|h| access_user(h, &dir, &rules))
            .collect(),
        teams: dir.groups.iter().map(|g| access_team(g, &rules)).collect(),
        directory_enabled: st.directory.is_enabled(),
    })
}

pub async fn user_access(st: &AppState, by: &Actor, id: Uuid) -> AppResult<UserAccess> {
    require_admin(by)?;
    let dir = st.directory.get().await?;
    let mut conn = st.pool.acquire().await?;
    let human = repo::human(&mut conn, id)
        .await?
        .ok_or_else(|| AppError::not_found("user"))?;
    let rules = rules_for_human(&mut conn, &human, &dir).await?;
    let s = subject(&human, &dir, &rules);
    let permissions = Permission::ALL
        .into_iter()
        .map(|p| {
            let d = s.decide(p);
            EffectiveAccess {
                permission: p.as_str().into(),
                setting: s.own.get(&p).map(|e| e.as_str().to_string()),
                allowed: d.allowed,
                source: source_view(&d.source),
            }
        })
        .collect();
    Ok(UserAccess {
        user: access_user(&human, &dir, &rules),
        permissions,
    })
}

pub async fn team_access(st: &AppState, by: &Actor, team_id: &str) -> AppResult<TeamAccess> {
    require_admin(by)?;
    let dir = st.directory.get().await?;
    let g = dir
        .group(team_id)
        .ok_or_else(|| AppError::not_found("team"))?;
    let mut conn = st.pool.acquire().await?;
    let humans = repo::humans(&mut conn).await?;
    let members: Vec<TeamMember> = g
        .members
        .iter()
        .map(|email| {
            let h = humans.iter().find(|h| {
                h.login
                    .as_deref()
                    .is_some_and(|l| l.eq_ignore_ascii_case(email))
            });
            let display = dir
                .user(email)
                .map(|u| u.display_name.clone())
                .filter(|n| !n.is_empty());
            TeamMember {
                email: email.clone(),
                name: h
                    .map(|h| h.name.clone())
                    .or(display)
                    .unwrap_or_else(|| email.clone()),
                user_id: h.map(|h| h.id),
            }
        })
        .collect();
    let member_ids: Vec<String> = members
        .iter()
        .filter_map(|m| m.user_id.map(|u| u.to_string()))
        .collect();
    let mut rules = repo::rules_for(&mut conn, TEAM, std::slice::from_ref(&g.id)).await?;
    rules.extend(repo::rules_for(&mut conn, USER, &member_ids).await?);
    let team_settings = settings_of(&rules, TEAM, &g.id);
    let permissions = Permission::ALL
        .into_iter()
        .filter(|p| !p.admin_only())
        .map(|p| TeamPermission {
            permission: p.as_str().into(),
            setting: team_settings.get(&p).map(|e| e.as_str().to_string()),
            exceptions: rules
                .iter()
                .filter(|r| r.subject_kind == USER && r.permission == p.as_str())
                .count(),
        })
        .collect();
    Ok(TeamAccess {
        team: access_team(g, &rules),
        members,
        permissions,
    })
}

/// Set or clear one setting. `kind` is `user` or `team`.
pub async fn set_setting(
    st: &AppState,
    by: &Actor,
    kind: &str,
    id: &str,
    permission: &str,
    input: SettingInput,
) -> AppResult<()> {
    require_admin(by)?;
    let p = Permission::parse(permission)
        .ok_or_else(|| AppError::BadRequest(format!("unknown permission {permission:?}")))?;
    if p.admin_only() {
        return Err(AppError::BadRequest(format!(
            "{permission} belongs to the Admin level and cannot be set"
        )));
    }
    let effect = match input.effect.as_deref() {
        None => None,
        Some(e) => Some(Effect::parse(e).ok_or_else(|| {
            AppError::BadRequest(format!("effect must be allow, deny or null, got {e:?}"))
        })?),
    };
    let mut conn = st.pool.acquire().await?;
    let subject_id = match kind {
        USER => {
            let uid = Uuid::parse_str(id).map_err(|_| AppError::not_found("user"))?;
            repo::human(&mut conn, uid)
                .await?
                .ok_or_else(|| AppError::not_found("user"))?
                .id
                .to_string()
        }
        TEAM => {
            let dir = st.directory.get().await?;
            dir.group(id)
                .ok_or_else(|| AppError::not_found("team"))?
                .id
                .clone()
        }
        _ => return Err(AppError::not_found("subject kind")),
    };
    match effect {
        Some(e) => {
            repo::set_rule(&mut conn, kind, &subject_id, p.as_str(), e.as_str(), by.id).await?
        }
        None => repo::delete_rule(&mut conn, kind, &subject_id, p.as_str()).await?,
    }
    tracing::info!(by = %by.id, kind, subject = %subject_id, permission = p.as_str(),
        effect = ?effect.map(Effect::as_str), "access setting changed");
    Ok(())
}

/// Change a human's level. An admin cannot change their own level, and the last admin cannot
/// be demoted.
pub async fn set_level(st: &AppState, by: &Actor, id: Uuid, input: LevelInput) -> AppResult<()> {
    require_admin(by)?;
    let to_admin = match input.level.as_str() {
        "admin" => true,
        "classic" => false,
        other => {
            return Err(AppError::BadRequest(format!(
                "level must be admin or classic, got {other:?}"
            )));
        }
    };
    if id == by.id {
        return Err(AppError::Forbidden(
            "you cannot change your own level".into(),
        ));
    }
    let mut tx = st.pool.begin().await?;
    let admins = repo::lock_admin_humans(&mut tx).await?;
    let human = repo::human(&mut tx, id)
        .await?
        .ok_or_else(|| AppError::not_found("user"))?;
    let is_admin = level_of_roles(&human.roles) == Level::Admin;
    if is_admin == to_admin {
        return Ok(());
    }
    if is_admin && admins <= 1 {
        return Err(AppError::BadRequest(
            "the last admin cannot be demoted".into(),
        ));
    }
    let mut roles: Vec<String> = human.roles.into_iter().filter(|r| r != "admin").collect();
    if to_admin {
        roles.insert(0, "admin".into());
    }
    repo::set_roles(&mut tx, id, &roles).await?;
    tx.commit().await?;
    tracing::info!(by = %by.id, user = %id, level = input.level, "level changed");
    Ok(())
}
