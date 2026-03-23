use serde_json::Value;
use std::sync::Arc;
use tokio::sync::OnceCell;
use tracing::{error, info, warn};

use crate::config::SETTINGS;
use crate::grpc_clients::embedding::EmbeddingClient;
use crate::grpc_clients::graph_database::GraphDatabaseClient;
use crate::grpc_clients::graph_milvus::GraphMilvusClient;
use crate::grpc_clients::graph_normalization::{GraphNormalizationClient, NormResult};
use crate::grpc_clients::llm::LlmClient;
use crate::grpc_clients::reranking::{RerankScore, RerankingClient};
use crate::grpc_clients::spacy::{SpacyClient, SpacyEntity};

/// Central service clients wrapper, mirroring Python's ServiceClients class.
pub struct ServiceClients {
    embedding: OnceCell<EmbeddingClient>,
    milvus: OnceCell<GraphMilvusClient>,
    graph_db: OnceCell<GraphDatabaseClient>,
    normalization: OnceCell<GraphNormalizationClient>,
    spacy: OnceCell<SpacyClient>,
    llm: OnceCell<LlmClient>,
    reranking: OnceCell<RerankingClient>,
}

impl ServiceClients {
    pub fn new() -> Self {
        Self {
            embedding: OnceCell::new(),
            milvus: OnceCell::new(),
            graph_db: OnceCell::new(),
            normalization: OnceCell::new(),
            spacy: OnceCell::new(),
            llm: OnceCell::new(),
            reranking: OnceCell::new(),
        }
    }

    // --- Lazy client getters ---

    async fn get_embedding(&self) -> Option<&EmbeddingClient> {
        self.embedding
            .get_or_try_init(|| async {
                EmbeddingClient::new(&SETTINGS.embedding_service_url).await
            })
            .await
            .map_err(|e| error!("Failed to connect to embedding service: {}", e))
            .ok()
    }

    async fn get_milvus(&self) -> Option<&GraphMilvusClient> {
        self.milvus
            .get_or_try_init(|| async {
                GraphMilvusClient::new(&SETTINGS.milvus_service_url).await
            })
            .await
            .map_err(|e| error!("Failed to connect to milvus service: {}", e))
            .ok()
    }

    async fn get_graph_db(&self) -> Option<&GraphDatabaseClient> {
        self.graph_db
            .get_or_try_init(|| async {
                GraphDatabaseClient::new(&SETTINGS.graph_database_service_url).await
            })
            .await
            .map_err(|e| error!("Failed to connect to graph DB service: {}", e))
            .ok()
    }

    async fn get_normalization(&self) -> Option<&GraphNormalizationClient> {
        self.normalization
            .get_or_try_init(|| async {
                GraphNormalizationClient::new(&SETTINGS.normalization_service_url).await
            })
            .await
            .map_err(|e| error!("Failed to connect to normalization service: {}", e))
            .ok()
    }

    async fn get_spacy(&self) -> Option<&SpacyClient> {
        self.spacy
            .get_or_try_init(|| async {
                SpacyClient::new(&SETTINGS.spacy_service_url).await
            })
            .await
            .map_err(|e| error!("Failed to connect to spacy service: {}", e))
            .ok()
    }

    async fn get_llm(&self) -> Option<&LlmClient> {
        self.llm
            .get_or_try_init(|| async {
                LlmClient::new(&SETTINGS.llm_service_url).await
            })
            .await
            .map_err(|e| error!("Failed to connect to LLM service: {}", e))
            .ok()
    }

    async fn get_reranking(&self) -> Option<&RerankingClient> {
        self.reranking
            .get_or_try_init(|| async {
                RerankingClient::new(&SETTINGS.reranking_service_url).await
            })
            .await
            .map_err(|e| error!("Failed to connect to reranking service: {}", e))
            .ok()
    }

    // --- Public API: mirrors Python ServiceClients methods ---

    pub async fn get_embedding_vector(&self, text: &str) -> Vec<f32> {
        if let Some(client) = self.get_embedding().await {
            client.get_embedding(text).await
        } else {
            vec![]
        }
    }

    pub async fn search_milvus_entities(
        &self,
        embedding: Vec<f32>,
        entity_type: &str,
        top_k: i32,
        threshold: f32,
    ) -> Vec<crate::grpc_clients::proto::graph_milvus::SearchResult> {
        if let Some(client) = self.get_milvus().await {
            client
                .search_similar_entities(embedding, entity_type, top_k, threshold)
                .await
        } else {
            vec![]
        }
    }

    pub async fn search_milvus_characteristics(
        &self,
        embedding: Vec<f32>,
        top_k: i32,
        threshold: f32,
    ) -> Vec<crate::grpc_clients::proto::graph_milvus::SearchResult> {
        if let Some(client) = self.get_milvus().await {
            client
                .search_similar_characteristics(embedding, top_k, threshold)
                .await
        } else {
            vec![]
        }
    }

    pub async fn execute_cypher(
        &self,
        query: &str,
        params: &Value,
    ) -> Vec<Value> {
        if let Some(client) = self.get_graph_db().await {
            let (success, results, error_msg) = client
                .execute_cypher(query, Some(params), false)
                .await;
            if !success && !error_msg.is_empty() {
                error!("Cypher execution error: {}", error_msg);
            }
            results
        } else {
            vec![]
        }
    }

    pub async fn execute_cypher_read(
        &self,
        query: &str,
        params: &Value,
    ) -> Vec<Value> {
        if let Some(client) = self.get_graph_db().await {
            let (success, results, error_msg) = client
                .execute_cypher(query, Some(params), true)
                .await;
            if !success && !error_msg.is_empty() {
                error!("Cypher read error: {}", error_msg);
            }
            results
        } else {
            vec![]
        }
    }

    pub async fn get_graph_schema(&self, include_properties: bool) -> String {
        if let Some(client) = self.get_graph_db().await {
            client.get_graph_schema(include_properties).await
        } else {
            String::new()
        }
    }

    pub async fn normalize_quantity(
        &self,
        value: &str,
        unit: Option<&str>,
        label: &str,
    ) -> Option<NormResult> {
        if let Some(client) = self.get_normalization().await {
            client.normalize_quantity(label, unit, value).await
        } else {
            None
        }
    }

    pub async fn extract_entities(&self, text: &str) -> Vec<SpacyEntity> {
        if let Some(client) = self.get_spacy().await {
            client.extract_entities(text).await
        } else {
            vec![]
        }
    }

    pub async fn llm_chat(&self, message: &str) -> Result<Value, String> {
        if let Some(client) = self.get_llm().await {
            client.chat(message).await
        } else {
            Err("LLM service not available".into())
        }
    }

    pub async fn rerank_documents(
        &self,
        query: &str,
        documents: &[String],
    ) -> Vec<RerankScore> {
        if let Some(client) = self.get_reranking().await {
            client.rerank_documents_with_scores(query, documents).await
        } else {
            vec![]
        }
    }
}

/// Global singleton for service clients
pub static CLIENTS: once_cell::sync::Lazy<Arc<ServiceClients>> =
    once_cell::sync::Lazy::new(|| Arc::new(ServiceClients::new()));
