//! A person's role on a project (validated maquette, "Membres et accès").
//!
//! Priority, highest first:
//! 1. Admin level: full access to every project (owner rights).
//! 2. The individual role, when set and accepted, even if lower than a team's.
//! 3. Otherwise the highest role given by the person's teams.
//! 4. Otherwise a public project is readable by everyone (viewer); a private one is invisible.
//!
//! Teams get editor or viewer only; owner is given to a person.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProjectRole {
    /// Read the board, tasks, specs and questions.
    Viewer,
    /// Viewer + every work command (tasks, specs, answers, claims by their agents).
    Editor,
    /// Editor + visibility and members.
    Owner,
}

impl ProjectRole {
    pub fn as_str(self) -> &'static str {
        match self {
            ProjectRole::Viewer => "viewer",
            ProjectRole::Editor => "editor",
            ProjectRole::Owner => "owner",
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "viewer" => Some(ProjectRole::Viewer),
            "editor" => Some(ProjectRole::Editor),
            "owner" => Some(ProjectRole::Owner),
            _ => None,
        }
    }

    /// Roles a team can be given.
    pub fn allowed_for_team(self) -> bool {
        self != ProjectRole::Owner
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Visibility {
    /// Every signed-in person can read it (viewer).
    Public,
    /// Members and invited teams only.
    Private,
}

impl Visibility {
    pub fn as_str(self) -> &'static str {
        match self {
            Visibility::Public => "public",
            Visibility::Private => "private",
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "public" => Some(Visibility::Public),
            "private" => Some(Visibility::Private),
            _ => None,
        }
    }
}

/// Where the effective role comes from (shown on the members page).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RoleSource {
    Admin,
    Individual,
    Team,
    Public,
}

/// Effective role of a person on a project, or `None` (no access: the project is invisible).
/// `individual` is an ACCEPTED individual grant (a pending invitation gives nothing).
pub fn project_role(
    is_admin: bool,
    visibility: Visibility,
    individual: Option<ProjectRole>,
    team_roles: &[ProjectRole],
) -> Option<(ProjectRole, RoleSource)> {
    if is_admin {
        return Some((ProjectRole::Owner, RoleSource::Admin));
    }
    if let Some(role) = individual {
        return Some((role, RoleSource::Individual));
    }
    if let Some(best) = team_roles.iter().copied().max() {
        return Some((best, RoleSource::Team));
    }
    match visibility {
        Visibility::Public => Some((ProjectRole::Viewer, RoleSource::Public)),
        Visibility::Private => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ProjectRole::*;

    #[test]
    fn admin_owns_everything() {
        assert_eq!(
            project_role(true, Visibility::Private, Some(Viewer), &[]),
            Some((Owner, RoleSource::Admin))
        );
    }

    #[test]
    fn individual_wins_even_when_lower_than_a_team() {
        // Maquette: Tiana A., individual viewer, her team gives editor → viewer.
        assert_eq!(
            project_role(false, Visibility::Private, Some(Viewer), &[Editor]),
            Some((Viewer, RoleSource::Individual))
        );
    }

    #[test]
    fn highest_team_role_otherwise() {
        assert_eq!(
            project_role(false, Visibility::Private, None, &[Viewer, Editor]),
            Some((Editor, RoleSource::Team))
        );
    }

    #[test]
    fn public_is_readable_private_is_invisible() {
        assert_eq!(
            project_role(false, Visibility::Public, None, &[]),
            Some((Viewer, RoleSource::Public))
        );
        assert_eq!(project_role(false, Visibility::Private, None, &[]), None);
        // A member of a public project keeps their (higher) role.
        assert_eq!(
            project_role(false, Visibility::Public, None, &[Editor]),
            Some((Editor, RoleSource::Team))
        );
    }

    #[test]
    fn names_round_trip_and_ordering() {
        for r in [Viewer, Editor, Owner] {
            assert_eq!(ProjectRole::parse(r.as_str()), Some(r));
        }
        assert!(Viewer < Editor && Editor < Owner);
        assert!(!Owner.allowed_for_team() && Editor.allowed_for_team());
        assert_eq!(Visibility::parse("public"), Some(Visibility::Public));
        assert_eq!(Visibility::parse("x"), None);
    }
}
