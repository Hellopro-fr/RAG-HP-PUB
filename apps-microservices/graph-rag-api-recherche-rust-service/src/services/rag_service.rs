use serde_json::{json, Value};
use tracing::{error, info, warn};

use crate::config::SETTINGS;
use crate::domain::models::{QueryResponse, RagState};
use crate::infrastructure::clients::CLIENTS;
use crate::infrastructure::llm_service::LlmService;
use crate::services::cypher_builder::CypherBuilderService;
use crate::services::rag_components;

/// Agentic RAG Service: custom async state machine replacing LangGraph.
/// Implements the same 4-strategy routing from Python's rag_service.py.
pub struct AgenticRAGService;

impl AgenticRAGService {
    /// Main entry point: process a query through the RAG pipeline.
    pub async fn process_query(
        query: &str,
        strategy: Option<&str>,
        use_reranking: bool,
        top_k: Option<i32>,
        threshold: Option<f64>,
    ) -> QueryResponse {
        let top_k = top_k.unwrap_or(SETTINGS.top_k_retrieval);
        let threshold = threshold.unwrap_or(SETTINGS.similarity_threshold);

        let mut state = RagState::new(query);

        // Step 1: Extract entities
        info!("RAG: Extracting entities from query");
        state.entities = Self::extract_entities_step(&state).await;

        // Step 2: Decide strategy
        let chosen_strategy = if let Some(s) = strategy {
            s.to_string()
        } else {
            Self::decide_strategy_step(&state).await
        };
        state.strategy = chosen_strategy.clone();
        info!("RAG: Using strategy: {}", state.strategy);

        // Step 3: Execute strategy
        match state.strategy.as_str() {
            "vectorstore_only" => {
                Self::vector_retrieval_step(&mut state, top_k, threshold as f32).await;
                state.merged_results = state.vector_results.clone();
            }
            "graph_only" => {
                Self::graph_retrieval_step(&mut state, top_k).await;
                state.merged_results = state.graph_results.clone();
            }
            "sequential_refinement" => {
                Self::graph_retrieval_step(&mut state, top_k).await;
                Self::vector_retrieval_step(&mut state, top_k, threshold as f32).await;
                state.merged_results = Self::merge_results(&state);
            }
            "parallel_fusion" | _ => {
                let (vector_res, graph_res) = tokio::join!(
                    Self::vector_retrieval_async(query, top_k, threshold as f32),
                    Self::graph_retrieval_async(query, &state.entities, top_k)
                );
                state.vector_results = vector_res;
                state.graph_results = graph_res;
                state.merged_results = Self::merge_results(&state);
            }
        }

        // Step 4: Optional reranking
        if use_reranking && !state.merged_results.is_empty() {
            info!("RAG: Reranking {} results", state.merged_results.len());
            state.reranked_results = Self::rerank_step(query, &state.merged_results).await;
        } else {
            state.reranked_results = state.merged_results.clone();
        }

        // Step 5: Generate answer
        info!("RAG: Generating answer");
        state.answer = Self::generate_answer_step(&state).await;

        QueryResponse {
            answer: state.answer,
            sources: state.reranked_results,
            strategy_used: Some(state.strategy),
            processing_time: None,
        }
    }

    // --- Pipeline steps ---

    async fn extract_entities_step(state: &RagState) -> Vec<String> {
        let entities = CypherBuilderService::extract_entities(&state.query).await;
        entities
            .into_iter()
            .filter_map(|e| e.get("value").and_then(|v| v.as_str()).map(String::from))
            .collect()
    }

    async fn decide_strategy_step(state: &RagState) -> String {
        let prompt = rag_components::ROUTING_DECISION_PROMPT
            .replace("{query}", &state.query)
            .replace("{entities}", &format!("{:?}", state.entities));

        match LlmService::generate_answer(&prompt).await {
            Ok(response) => {
                let strategy = response.trim().to_lowercase();
                match strategy.as_str() {
                    "vectorstore_only" | "graph_only"
                    | "sequential_refinement" | "parallel_fusion" => strategy,
                    _ => "parallel_fusion".to_string(),
                }
            }
            Err(_) => "parallel_fusion".to_string(),
        }
    }

    async fn vector_retrieval_step(state: &mut RagState, top_k: i32, threshold: f32) {
        let embedding = CLIENTS.get_embedding_vector(&state.query).await;
        if embedding.is_empty() {
            return;
        }

        let results = CLIENTS
            .search_milvus_characteristics(embedding, top_k, threshold)
            .await;

        state.vector_results = results
            .into_iter()
            .map(|r| {
                json!({
                    "id": r.id,
                    "distance": r.distance,
                    "source": "vector"
                })
            })
            .collect();
    }

    async fn vector_retrieval_async(query: &str, top_k: i32, threshold: f32) -> Vec<Value> {
        let embedding = CLIENTS.get_embedding_vector(query).await;
        if embedding.is_empty() {
            return vec![];
        }

        let results = CLIENTS
            .search_milvus_characteristics(embedding, top_k, threshold)
            .await;

        results
            .into_iter()
            .map(|r| {
                json!({
                    "id": r.id,
                    "distance": r.distance,
                    "source": "vector"
                })
            })
            .collect()
    }

    async fn graph_retrieval_step(state: &mut RagState, top_k: i32) {
        let entities = CypherBuilderService::extract_entities(&state.query).await;
        let (cypher_query, params) = CypherBuilderService::build_cypher_query(&entities, top_k);

        let results = CLIENTS.execute_cypher(&cypher_query, &params).await;
        state.graph_results = results;
    }

    async fn graph_retrieval_async(query: &str, entities_str: &[String], top_k: i32) -> Vec<Value> {
        let entities: Vec<Value> = entities_str
            .iter()
            .map(|e| json!({"type": "Produit", "value": e}))
            .collect();

        let (cypher_query, params) = CypherBuilderService::build_cypher_query(&entities, top_k);
        CLIENTS.execute_cypher(&cypher_query, &params).await
    }

    fn merge_results(state: &RagState) -> Vec<Value> {
        let mut merged = state.graph_results.clone();
        for vr in &state.vector_results {
            if !merged.iter().any(|mr| mr.get("id") == vr.get("id")) {
                merged.push(vr.clone());
            }
        }
        merged
    }

    async fn rerank_step(query: &str, results: &[Value]) -> Vec<Value> {
        let documents: Vec<String> = results
            .iter()
            .map(|r| serde_json::to_string(r).unwrap_or_default())
            .collect();

        let scores = CLIENTS.rerank_documents(query, &documents).await;

        if scores.is_empty() {
            return results.to_vec();
        }

        let mut scored: Vec<(f32, Value)> = results
            .iter()
            .enumerate()
            .map(|(i, r)| {
                let score = scores.get(i).map(|s| s.score).unwrap_or(0.0);
                (score, r.clone())
            })
            .collect();

        scored.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));
        scored.into_iter().map(|(_, v)| v).collect()
    }

    async fn generate_answer_step(state: &RagState) -> String {
        let context = state
            .reranked_results
            .iter()
            .take(5)
            .map(|r| serde_json::to_string_pretty(r).unwrap_or_default())
            .collect::<Vec<_>>()
            .join("\n---\n");

        let prompt = rag_components::ANSWER_GENERATION_PROMPT
            .replace("{query}", &state.query)
            .replace("{context}", &context);

        match LlmService::generate_answer(&prompt).await {
            Ok(answer) => answer,
            Err(e) => {
                error!("Answer generation failed: {}", e);
                "Désolé, je n'ai pas pu générer une réponse.".to_string()
            }
        }
    }
}
