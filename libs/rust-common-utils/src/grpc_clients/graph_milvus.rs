use tonic::transport::Channel;
use tracing::error;

use super::proto::graph_milvus::graph_milvus_service_client::GraphMilvusServiceClient;
use super::proto::graph_milvus::{SearchCharacteristicsRequest, SearchEntitiesRequest, SearchResult};

#[derive(Clone)]
pub struct GraphMilvusClient {
    client: GraphMilvusServiceClient<Channel>,
}

impl GraphMilvusClient {
    pub async fn new(url: &str) -> Result<Self, Box<dyn std::error::Error>> {
        let endpoint = format!("http://{}", url);
        let channel = Channel::from_shared(endpoint)?.connect().await?;
        Ok(Self {
            client: GraphMilvusServiceClient::new(channel),
        })
    }

    pub async fn search_similar_entities(
        &self,
        embedding: Vec<f32>,
        entity_type: &str,
        top_k: i32,
        threshold: f32,
    ) -> Vec<SearchResult> {
        let request = tonic::Request::new(SearchEntitiesRequest {
            embedding,
            entity_type: entity_type.to_string(),
            top_k,
            threshold,
        });

        match self.client.clone().search_similar_entities(request).await {
            Ok(response) => response.into_inner().results,
            Err(e) => {
                error!("Milvus Search Error: {}", e);
                vec![]
            }
        }
    }

    pub async fn search_similar_characteristics(
        &self,
        embedding: Vec<f32>,
        top_k: i32,
        threshold: f32,
    ) -> Vec<SearchResult> {
        let request = tonic::Request::new(SearchCharacteristicsRequest {
            embedding,
            top_k,
            threshold,
        });

        match self.client.clone().search_similar_characteristics(request).await {
            Ok(response) => response.into_inner().results,
            Err(e) => {
                error!("Milvus Characteristic Search Error: {}", e);
                vec![]
            }
        }
    }
}
