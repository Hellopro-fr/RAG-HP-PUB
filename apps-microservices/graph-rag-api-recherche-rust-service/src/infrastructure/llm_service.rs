use serde_json::Value;
use tracing::{error, warn};

use crate::infrastructure::clients::CLIENTS;

/// LLM Service wrapper using gRPC LLM client, mirroring Python's llm_service.
pub struct LlmService;

impl LlmService {
    /// Generate an answer from a text prompt via gRPC LLM.
    pub async fn generate_answer(prompt: &str) -> Result<String, String> {
        match CLIENTS.llm_chat(prompt).await {
            Ok(value) => {
                // Extract the text from the LLM response
                if let Some(text) = value.get("text").and_then(|t| t.as_str()) {
                    Ok(text.to_string())
                } else if let Some(text) = value.as_str() {
                    Ok(text.to_string())
                } else {
                    Ok(value.to_string())
                }
            }
            Err(e) => Err(e),
        }
    }

    /// Invoke a chain with a templated prompt.
    pub async fn invoke_chain(template: &str, variables: &Value) -> Result<String, String> {
        let mut prompt = template.to_string();

        // Simple template variable substitution
        if let Some(obj) = variables.as_object() {
            for (key, value) in obj {
                let placeholder = format!("{{{}}}", key);
                let replacement = match value {
                    Value::String(s) => s.clone(),
                    _ => value.to_string(),
                };
                prompt = prompt.replace(&placeholder, &replacement);
            }
        }

        Self::generate_answer(&prompt).await
    }
}
