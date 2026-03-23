use tonic::transport::Channel;
use tracing::error;

use super::proto::embedding::embedding_service_client::EmbeddingServiceClient;
use super::proto::embedding::EmbeddingsRequest;

#[derive(Clone)]
pub struct EmbeddingClient {
    client: EmbeddingServiceClient<Channel>,
}

impl EmbeddingClient {
    pub async fn new(url: &str) -> Result<Self, Box<dyn std::error::Error>> {
        let endpoint = format!("http://{}", url);
        let channel = Channel::from_shared(endpoint)?.connect().await?;
        Ok(Self {
            client: EmbeddingServiceClient::new(channel),
        })
    }

    pub async fn get_embedding(&self, text: &str) -> Vec<f32> {
        let request = tonic::Request::new(EmbeddingsRequest {
            texts: vec![text.to_string()],
            source_service: Some("graph-rag-api-recherche-rust-service".to_string()),
        });

        match self.client.clone().get_embeddings(request).await {
            Ok(response) => {
                let resp = response.into_inner();
                if let Some(first) = resp.embeddings.first() {
                    first.vector.clone()
                } else {
                    vec![]
                }
            }
            Err(e) => {
                error!("Embedding Error: {}", e);
                vec![]
            }
        }
    }
}
