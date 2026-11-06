//! Per-project workflow configuration (§5). Validated on write.

use serde::{Deserialize, Serialize};

use crate::error::DomainError;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TestGate {
    None,
    Command,
    Human,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ReviewGate {
    None,
    AgentOrHuman,
    HumanOnly,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WorkflowConfig {
    pub spec_gate: bool,
    pub test_gate: TestGate,
    pub review_gate: ReviewGate,
    pub require_different_model: bool,
    pub max_rejections: i32,
    pub lease_ttl_secs: i64,
    pub preferred_grace_secs: i64,
}

impl Default for WorkflowConfig {
    fn default() -> Self {
        Self {
            spec_gate: true,
            test_gate: TestGate::Command,
            review_gate: ReviewGate::AgentOrHuman,
            require_different_model: false,
            max_rejections: 3,
            lease_ttl_secs: 600,
            preferred_grace_secs: 120,
        }
    }
}

impl WorkflowConfig {
    pub fn validate(&self) -> Result<(), DomainError> {
        let bad = |field: &'static str, hint: &str| Err(DomainError::invalid(field, hint));
        if !(1..=100).contains(&self.max_rejections) {
            return bad(
                "workflow.max_rejections",
                "max_rejections must be between 1 and 100",
            );
        }
        if !(1..=86_400).contains(&self.lease_ttl_secs) {
            return bad(
                "workflow.lease_ttl_secs",
                "lease_ttl_secs must be between 1 and 86400",
            );
        }
        if !(0..=86_400).contains(&self.preferred_grace_secs) {
            return bad(
                "workflow.preferred_grace_secs",
                "preferred_grace_secs must be between 0 and 86400",
            );
        }
        if self.require_different_model && self.review_gate == ReviewGate::None {
            return bad(
                "workflow.require_different_model",
                "require_different_model needs a review gate",
            );
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_is_valid_and_bad_values_are_rejected() {
        assert!(WorkflowConfig::default().validate().is_ok());
        let bad = WorkflowConfig {
            max_rejections: 0,
            ..WorkflowConfig::default()
        };
        assert!(bad.validate().is_err());
        let bad = WorkflowConfig {
            require_different_model: true,
            review_gate: ReviewGate::None,
            ..WorkflowConfig::default()
        };
        assert!(bad.validate().is_err());
    }

    #[test]
    fn unknown_keys_are_rejected() {
        let json = r#"{"spec_gate":true,"test_gate":"none","review_gate":"none",
            "require_different_model":false,"max_rejections":3,"lease_ttl_secs":600,
            "preferred_grace_secs":120,"surprise":1}"#;
        assert!(serde_json::from_str::<WorkflowConfig>(json).is_err());
    }
}
