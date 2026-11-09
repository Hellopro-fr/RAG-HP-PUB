//! Access levels and permissions (validated maquette, "Accès" page).
//!
//! Priority, highest first:
//! 1. Admin level: everything is allowed, settings are ignored.
//! 2. Admin-only permissions (`access.manage`): refused to everyone else.
//! 3. The individual setting, when set, wins even if it is more restrictive than the teams.
//! 4. The teams' settings, combined by [`combine_teams`].
//! 5. Refused by default.
//!
//! Pure: the server loads the settings and the user's teams, this module decides.

use serde::{Deserialize, Serialize};

/// A human's level. `Admin` is the existing `admin` role; everyone else is `Classic`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Level {
    Admin,
    Classic,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub enum Permission {
    /// Create projects.
    #[serde(rename = "projects.create")]
    ProjectsCreate,
    /// Answer the agents' questions.
    #[serde(rename = "questions.answer")]
    QuestionsAnswer,
    /// Connect one's own agents (create agent actors and their tokens).
    #[serde(rename = "agents.manage")]
    AgentsManage,
    /// See the Agents page.
    #[serde(rename = "agents.view")]
    AgentsView,
    /// See the Users page.
    #[serde(rename = "users.view")]
    UsersView,
    /// Manage levels and access. Admins only, cannot be granted.
    #[serde(rename = "access.manage")]
    AccessManage,
}

impl Permission {
    pub const ALL: [Permission; 6] = [
        Permission::ProjectsCreate,
        Permission::QuestionsAnswer,
        Permission::AgentsManage,
        Permission::AgentsView,
        Permission::UsersView,
        Permission::AccessManage,
    ];

    pub fn as_str(self) -> &'static str {
        match self {
            Permission::ProjectsCreate => "projects.create",
            Permission::QuestionsAnswer => "questions.answer",
            Permission::AgentsManage => "agents.manage",
            Permission::AgentsView => "agents.view",
            Permission::UsersView => "users.view",
            Permission::AccessManage => "access.manage",
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        Self::ALL.into_iter().find(|p| p.as_str() == s)
    }

    /// Cannot be granted by a setting: only the Admin level has it.
    pub fn admin_only(self) -> bool {
        matches!(self, Permission::AccessManage)
    }
}

/// A stored setting for one subject (user or team) and one permission. Absent = not set
/// ("Hériter des équipes" for a user, "Non défini" for a team).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Effect {
    Allow,
    Deny,
}

impl Effect {
    pub fn as_str(self) -> &'static str {
        match self {
            Effect::Allow => "allow",
            Effect::Deny => "deny",
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "allow" => Some(Effect::Allow),
            "deny" => Some(Effect::Deny),
            _ => None,
        }
    }
}

/// One of the user's teams and its setting for the permission being resolved.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TeamSetting {
    pub team_id: String,
    pub team_name: String,
    pub effect: Option<Effect>,
}

/// What the user's teams say, all teams combined.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum TeamOutcome {
    /// Allowed; the names of the teams that make it so.
    Allowed { by: Vec<String> },
    /// Refused; the names of the teams that make it so.
    Denied { by: Vec<String> },
    /// No team has a setting for this permission.
    Unset,
}

/// Why a permission is allowed or refused (shown next to the effective access).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Source {
    AdminLevel,
    AdminOnly,
    /// The individual setting decided; `teams` is what the teams alone would have given.
    Individual {
        teams: TeamOutcome,
    },
    Teams {
        teams: TeamOutcome,
    },
    Default,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Decision {
    pub allowed: bool,
    pub source: Source,
}

/// Combine the settings of all the user's teams for one permission.
///
/// Validated rule (maquette v13): allowed as soon as one team allows; otherwise refused if a
/// team refuses; otherwise unset (the caller then refuses by default). Team names are listed
/// in input order so the UI can say "via Équipe catalogue, Data".
pub fn combine_teams(teams: &[TeamSetting]) -> TeamOutcome {
    let names = |effect: Effect| -> Vec<String> {
        teams
            .iter()
            .filter(|t| t.effect == Some(effect))
            .map(|t| t.team_name.clone())
            .collect()
    };
    let allowed = names(Effect::Allow);
    if !allowed.is_empty() {
        return TeamOutcome::Allowed { by: allowed };
    }
    let denied = names(Effect::Deny);
    if !denied.is_empty() {
        return TeamOutcome::Denied { by: denied };
    }
    TeamOutcome::Unset
}

/// Effective access of a human for one permission.
pub fn resolve(
    level: Level,
    permission: Permission,
    individual: Option<Effect>,
    teams: &[TeamSetting],
) -> Decision {
    if level == Level::Admin {
        return Decision {
            allowed: true,
            source: Source::AdminLevel,
        };
    }
    if permission.admin_only() {
        return Decision {
            allowed: false,
            source: Source::AdminOnly,
        };
    }
    let combined = combine_teams(teams);
    if let Some(effect) = individual {
        return Decision {
            allowed: effect == Effect::Allow,
            source: Source::Individual { teams: combined },
        };
    }
    match combined {
        TeamOutcome::Unset => Decision {
            allowed: false,
            source: Source::Default,
        },
        teams @ TeamOutcome::Allowed { .. } => Decision {
            allowed: true,
            source: Source::Teams { teams },
        },
        teams @ TeamOutcome::Denied { .. } => Decision {
            allowed: false,
            source: Source::Teams { teams },
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn team(name: &str, effect: Option<Effect>) -> TeamSetting {
        TeamSetting {
            team_id: name.to_lowercase(),
            team_name: name.to_string(),
            effect,
        }
    }

    #[test]
    fn permission_names_round_trip() {
        for p in Permission::ALL {
            assert_eq!(Permission::parse(p.as_str()), Some(p));
            assert_eq!(
                serde_json::to_value(p).unwrap(),
                serde_json::json!(p.as_str())
            );
        }
        assert_eq!(Permission::parse("nope"), None);
        assert_eq!(Effect::parse("allow"), Some(Effect::Allow));
        assert_eq!(Effect::parse(""), None);
    }

    #[test]
    fn combine_teams_one_allow_is_enough() {
        let t = [
            team("Catalogue", Some(Effect::Deny)),
            team("Data", Some(Effect::Allow)),
            team("Prix", None),
        ];
        assert_eq!(
            combine_teams(&t),
            TeamOutcome::Allowed {
                by: vec!["Data".into()]
            }
        );
    }

    #[test]
    fn combine_teams_deny_without_allow_and_unset() {
        let t = [team("Catalogue", Some(Effect::Deny)), team("Prix", None)];
        assert_eq!(
            combine_teams(&t),
            TeamOutcome::Denied {
                by: vec!["Catalogue".into()]
            }
        );
        assert_eq!(combine_teams(&[team("Prix", None)]), TeamOutcome::Unset);
        assert_eq!(combine_teams(&[]), TeamOutcome::Unset);
    }

    #[test]
    fn combine_teams_lists_every_deciding_team_in_order() {
        let t = [
            team("Catalogue", Some(Effect::Allow)),
            team("Data", Some(Effect::Allow)),
        ];
        assert_eq!(
            combine_teams(&t),
            TeamOutcome::Allowed {
                by: vec!["Catalogue".into(), "Data".into()]
            }
        );
    }

    #[test]
    fn admin_level_ignores_every_setting() {
        let d = resolve(
            Level::Admin,
            Permission::AccessManage,
            Some(Effect::Deny),
            &[team("Data", Some(Effect::Deny))],
        );
        assert_eq!(
            d,
            Decision {
                allowed: true,
                source: Source::AdminLevel
            }
        );
    }

    #[test]
    fn admin_only_cannot_be_granted() {
        let d = resolve(
            Level::Classic,
            Permission::AccessManage,
            Some(Effect::Allow),
            &[team("Data", Some(Effect::Allow))],
        );
        assert!(!d.allowed);
        assert_eq!(d.source, Source::AdminOnly);
    }

    #[test]
    fn individual_wins_even_when_more_restrictive() {
        // Maquette: Tiana A. refused individually, her team allows.
        let d = resolve(
            Level::Classic,
            Permission::AgentsManage,
            Some(Effect::Deny),
            &[team("Catalogue", Some(Effect::Allow))],
        );
        assert!(!d.allowed);
        assert_eq!(
            d.source,
            Source::Individual {
                teams: TeamOutcome::Allowed {
                    by: vec!["Catalogue".into()]
                }
            }
        );
        let d = resolve(
            Level::Classic,
            Permission::UsersView,
            Some(Effect::Allow),
            &[team("Data", Some(Effect::Deny))],
        );
        assert!(d.allowed);
    }

    #[test]
    fn teams_then_refused_by_default() {
        let allowed = resolve(
            Level::Classic,
            Permission::ProjectsCreate,
            None,
            &[team("Catalogue", Some(Effect::Allow))],
        );
        assert!(allowed.allowed);
        let default = resolve(Level::Classic, Permission::ProjectsCreate, None, &[]);
        assert_eq!(
            default,
            Decision {
                allowed: false,
                source: Source::Default
            }
        );
    }
}
