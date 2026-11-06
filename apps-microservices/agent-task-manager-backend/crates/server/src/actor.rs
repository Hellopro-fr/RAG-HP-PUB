//! The authenticated caller, resolved once per request by the auth middleware and shared by the
//! REST, SSE and MCP presentation layers and the service layer.

use atb_core::{ActorKind, Caller, Role};
use uuid::Uuid;

/// Fixed id of the system actor (seeded by migration 0001).
pub const SYSTEM_ACTOR_ID: Uuid = Uuid::from_u128(0x0000_0000_0000_7000_8000_0000_0000_0001);

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Actor {
    pub id: Uuid,
    pub kind: ActorKind,
    pub name: String,
    pub roles: Vec<Role>,
    pub model: Option<String>,
}

impl Actor {
    pub fn system() -> Self {
        Self {
            id: SYSTEM_ACTOR_ID,
            kind: ActorKind::System,
            name: "system".into(),
            roles: vec![],
            model: None,
        }
    }

    pub fn caller(&self) -> Caller {
        Caller {
            id: self.id,
            kind: self.kind,
            roles: self.roles.clone(),
            model: self.model.clone(),
        }
    }

    pub fn is_human(&self) -> bool {
        self.kind == ActorKind::Human
    }

    pub fn is_admin(&self) -> bool {
        self.roles.contains(&Role::Admin)
    }

    pub fn has_role(&self, role: Role) -> bool {
        self.caller().has_role(role)
    }

    pub fn from_row(
        id: Uuid,
        kind: &str,
        name: String,
        roles: &[String],
        model: Option<String>,
    ) -> Self {
        Self {
            id,
            kind: ActorKind::parse(kind).unwrap_or(ActorKind::Agent),
            name,
            roles: roles.iter().filter_map(|r| Role::parse(r)).collect(),
            model,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn system_actor_id_matches_the_seeded_row() {
        assert_eq!(
            SYSTEM_ACTOR_ID.to_string(),
            "00000000-0000-7000-8000-000000000001"
        );
    }
}
