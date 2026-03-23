use serde::{Deserialize, Serialize};
use tonic::transport::Channel;
use tracing::error;

use super::proto::graph_spacy::graph_spacy_service_client::GraphSpacyServiceClient;
use super::proto::graph_spacy::ExtractEntitiesRequest;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SpacyEntity {
    pub text: String,
    pub label: String,
}

#[derive(Clone)]
pub struct SpacyClient {
    client: GraphSpacyServiceClient<Channel>,
}

impl SpacyClient {
    pub async fn new(url: &str) -> Result<Self, Box<dyn std::error::Error>> {
        let endpoint = format!("http://{}", url);
        let channel = Channel::from_shared(endpoint)?.connect().await?;
        Ok(Self {
            client: GraphSpacyServiceClient::new(channel),
        })
    }

    pub async fn extract_entities(&self, text: &str) -> Vec<SpacyEntity> {
        let request = tonic::Request::new(ExtractEntitiesRequest {
            text: text.to_string(),
        });

        match self.client.clone().extract_entities(request).await {
            Ok(response) => {
                response
                    .into_inner()
                    .entities
                    .into_iter()
                    .map(|e| SpacyEntity {
                        text: e.text,
                        label: e.label,
                    })
                    .collect()
            }
            Err(e) => {
                error!("Spacy Extraction Error: {}", e);
                vec![]
            }
        }
    }
}
