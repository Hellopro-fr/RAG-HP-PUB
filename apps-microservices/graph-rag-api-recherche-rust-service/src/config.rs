use once_cell::sync::Lazy;
use std::env;

/// Application configuration, loaded from environment variables.
#[derive(Debug, Clone)]
pub struct Settings {
    // API Config
    pub api_port: u16,
    pub app_env: String,
    pub log_level: String,

    // Neo4j Direct Connection
    pub neo4j_uri: String,
    pub neo4j_user: String,
    pub neo4j_password: String,
    pub neo4j_database: String,

    // gRPC Services
    pub embedding_service_url: String,
    pub milvus_service_url: String,
    pub graph_database_service_url: String,
    pub normalization_service_url: String,
    pub spacy_service_url: String,
    pub llm_service_url: String,
    pub reranking_service_url: String,

    // LLM Config
    pub llm_provider: String,
    pub openai_api_key: Option<String>,
    pub gemini_api_key: Option<String>,
    pub anthropic_api_key: Option<String>,
    pub llm_model_name: String,

    // RAG Config
    pub similarity_threshold: f64,
    pub top_k_retrieval: i32,

    // HelloPro API
    pub hellopro_api_bearer_token: String,

    // Prometheus Metrics
    pub prometheus_port: u16,
}

fn env_or(key: &str, default: &str) -> String {
    env::var(key).unwrap_or_else(|_| default.to_string())
}

fn env_or_opt(key: &str) -> Option<String> {
    env::var(key).ok().filter(|s| !s.is_empty())
}

impl Settings {
    pub fn from_env() -> Self {
        Self {
            api_port: env_or("API_PORT", "8527").parse().unwrap_or(8527),
            app_env: env_or("APP_ENV", "development"),
            log_level: env_or("LOG_LEVEL", "INFO"),

            neo4j_uri: env_or("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user: env_or("NEO4J_USER", "neo4j"),
            neo4j_password: env_or("NEO4J_PASSWORD", "password"),
            neo4j_database: env_or("NEO4J_DATABASE", "neo4j"),

            embedding_service_url: env_or("EMBEDDING_SERVICE_URL", "localhost:50052"),
            milvus_service_url: env_or("MILVUS_SERVICE_URL", "localhost:50056"),
            graph_database_service_url: env_or("GRAPH_DATABASE_SERVICE_URL", "localhost:50055"),
            normalization_service_url: env_or("NORMALIZATION_SERVICE_URL", "localhost:50057"),
            spacy_service_url: env_or("SPACY_SERVICE_URL", "localhost:50058"),
            llm_service_url: env_or("LLM_SERVICE_URL", "localhost:50051"),
            reranking_service_url: env_or("RERANKING_SERVICE_URL", "localhost:50053"),

            llm_provider: env_or("LLM_PROVIDER", "gemini"),
            openai_api_key: env_or_opt("OPENAI_API_KEY"),
            gemini_api_key: env_or_opt("GEMINI_API_KEY"),
            anthropic_api_key: env_or_opt("ANTHROPIC_API_KEY"),
            llm_model_name: env_or("LLM_MODEL_NAME", "gemini-1.5-pro"),

            similarity_threshold: env_or("SIMILARITY_THRESHOLD", "0.75")
                .parse()
                .unwrap_or(0.75),
            top_k_retrieval: env_or("TOP_K_RETRIEVAL", "10")
                .parse()
                .unwrap_or(10),

            hellopro_api_bearer_token: env_or("HELLOPRO_API_BEARER_TOKEN", ""),

            prometheus_port: env_or("PROMETHEUS_PORT", "8566")
                .parse()
                .unwrap_or(8566),
        }
    }
}

pub static SETTINGS: Lazy<Settings> = Lazy::new(|| Settings::from_env());
