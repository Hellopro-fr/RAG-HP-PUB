use serde::{Deserialize, Serialize};
use tonic::transport::Channel;
use tracing::error;

use super::proto::reranking::reranking_service_client::RerankingServiceClient;
use super::proto::reranking::RerankRequest;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RerankScore {
    pub document: String,
    pub score: f32,
}

#[derive(Clone)]
pub struct RerankingClient {
    client: RerankingServiceClient<Channel>,
}

impl RerankingClient {
    pub async fn new(url: &str) -> Result<Self, Box<dyn std::error::Error>> {
        let endpoint = format!("http://{}", url);
        let channel = Channel::from_shared(endpoint)?.connect().await?;
        Ok(Self {
            client: RerankingServiceClient::new(channel),
        })
    }

    pub async fn rerank_documents_with_scores(
        &self,
        query: &str,
        documents: &[String],
    ) -> Vec<RerankScore> {
        let request = tonic::Request::new(RerankRequest {
            query: query.to_string(),
            documents: documents.to_vec(),
        });

        match self.client.clone().rerank_documents(request).await {
            Ok(response) => {
                response
                    .into_inner()
                    .scores
                    .into_iter()
                    .map(|s| RerankScore {
                        document: s.document,
                        score: s.score,
                    })
                    .collect()
            }
            Err(e) => {
                error!("Reranking Error: {}", e);
                vec![]
            }
        }
    }
}
