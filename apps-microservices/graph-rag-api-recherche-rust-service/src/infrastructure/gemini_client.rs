use reqwest::Client;
use serde_json::Value;
use std::time::Duration;
use tracing::{error, warn};

use crate::config::SETTINGS;

/// Gemini REST API client with retry logic (replaces google-genai SDK).
pub struct GeminiClient {
    client: Client,
    model: String,
}

impl GeminiClient {
    pub fn new() -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(120))
            .build()
            .expect("Failed to build reqwest client");

        Self {
            client,
            model: SETTINGS.llm_model_name.clone(),
        }
    }

    /// Generate content using Gemini REST API with retry logic.
    pub async fn chat(
        &self,
        prompt: &str,
        temperature: Option<f64>,
    ) -> Result<String, String> {
        let api_key = match &SETTINGS.gemini_api_key {
            Some(key) => key.clone(),
            None => return Err("GEMINI_API_KEY not set".into()),
        };

        let url = format!(
            "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent?key={}",
            self.model, api_key
        );

        let mut generation_config = serde_json::json!({});
        if let Some(temp) = temperature {
            generation_config["temperature"] = serde_json::json!(temp);
        }

        let body = serde_json::json!({
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": generation_config
        });

        // Retry up to 3 times with exponential backoff
        let mut last_error = String::new();
        for attempt in 0..3 {
            if attempt > 0 {
                let delay = Duration::from_millis(500 * (1 << attempt));
                warn!("Gemini retry attempt {} after {:?}", attempt + 1, delay);
                tokio::time::sleep(delay).await;
            }

            match self.client.post(&url).json(&body).send().await {
                Ok(response) => {
                    if response.status().is_success() {
                        match response.json::<Value>().await {
                            Ok(json) => {
                                let text = json["candidates"][0]["content"]["parts"][0]["text"]
                                    .as_str()
                                    .unwrap_or("")
                                    .to_string();
                                return Ok(text);
                            }
                            Err(e) => {
                                last_error = format!("Failed to parse Gemini response: {}", e);
                            }
                        }
                    } else {
                        let status = response.status();
                        let body_text = response.text().await.unwrap_or_default();
                        last_error = format!("Gemini API error {}: {}", status, body_text);

                        // Don't retry on 4xx errors (except 429)
                        if status.as_u16() >= 400 && status.as_u16() < 500 && status.as_u16() != 429 {
                            break;
                        }
                    }
                }
                Err(e) => {
                    last_error = format!("Request error: {}", e);
                }
            }
        }

        error!("Gemini API failed after retries: {}", last_error);
        Err(last_error)
    }

    /// Generate reranking response and parse as JSON.
    pub async fn generate_rerank_response(
        &self,
        system_prompt: &str,
        temperature: Option<f64>,
    ) -> Option<Value> {
        match self.chat(system_prompt, temperature).await {
            Ok(text) => {
                // Strip markdown code fences if present
                let cleaned = text
                    .trim()
                    .trim_start_matches("```json")
                    .trim_start_matches("```")
                    .trim_end_matches("```")
                    .trim();

                match serde_json::from_str::<Value>(cleaned) {
                    Ok(json) => Some(json),
                    Err(e) => {
                        error!("Failed to parse Gemini rerank response as JSON: {}", e);
                        error!("Raw response: {}", &text[..text.len().min(500)]);
                        None
                    }
                }
            }
            Err(e) => {
                error!("Gemini rerank call failed: {}", e);
                None
            }
        }
    }
}

/// Global singleton
pub static GEMINI_CLIENT: once_cell::sync::Lazy<GeminiClient> =
    once_cell::sync::Lazy::new(GeminiClient::new);
