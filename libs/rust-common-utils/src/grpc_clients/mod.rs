pub mod embedding;
pub mod graph_database;
pub mod graph_milvus;
pub mod graph_normalization;
pub mod llm;
pub mod reranking;
pub mod spacy;

// Generated proto modules
pub mod proto {
    pub mod embedding {
        tonic::include_proto!("embedding");
    }
    pub mod graph_milvus {
        tonic::include_proto!("graph_milvus");
    }
    pub mod graph_database {
        tonic::include_proto!("graph_database");
    }
    pub mod graph_normalization {
        tonic::include_proto!("graph_normalization");
    }
    pub mod reranking {
        tonic::include_proto!("reranking");
    }
    pub mod graph_spacy {
        tonic::include_proto!("graph_spacy");
    }
    pub mod llm {
        tonic::include_proto!("llm");
    }
}
