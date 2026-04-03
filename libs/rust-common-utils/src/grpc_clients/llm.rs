use serde_json::Value;
use tonic::transport::Channel;
use tracing::error;

use super::proto::llm::llm_service_client::LlmServiceClient;
use super::proto::llm::ChatRequest;
use super::graph_database::GraphDatabaseClient;

#[derive(Clone)]
pub struct LlmClient {
    client: LlmServiceClient<Channel>,
}

impl LlmClient {
    pub async fn new(url: &str) -> Result<Self, Box<dyn std::error::Error>> {
        let endpoint = format!("http://{}", url);
        let channel = Channel::from_shared(endpoint)?.connect().await?;
        Ok(Self {
            client: LlmServiceClient::new(channel),
        })
    }

    pub async fn chat(&self, message: &str) -> Result<Value, String> {
        let request = tonic::Request::new(ChatRequest {
            message: message.to_string(),
            temperature: None,
            max_tokens: Some(2048),
            enable_thinking: None,
            options: None,
        });

        match self.client.clone().chat(request).await {
            Ok(response) => {
                let resp = response.into_inner();
                if let Some(full_message) = resp.full_message {
                    Ok(GraphDatabaseClient::prost_struct_to_json(&full_message))
                } else {
                    Ok(Value::Null)
                }
            }
            Err(e) => {
                error!("LLM Chat Error: {}", e);
                Err(e.to_string())
            }
        }
    }
}
