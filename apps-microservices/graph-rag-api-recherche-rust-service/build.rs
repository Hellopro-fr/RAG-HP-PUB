fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Check for Docker environment (/protos) first, fallback to local dev (../../protos)
    let proto_root = if std::path::Path::new("/protos/grpc_stubs").exists() {
        "/protos"
    } else {
        "../../protos"
    };

    tonic_build::configure()
        .build_server(false) // We only need clients
        .build_client(true)
        .compile_protos(
            &[
                format!("{}/grpc_stubs/embedding.proto", proto_root),
                format!("{}/grpc_stubs/graph_milvus.proto", proto_root),
                format!("{}/grpc_stubs/graph_database.proto", proto_root),
                format!("{}/grpc_stubs/graph_normalization.proto", proto_root),
                format!("{}/grpc_stubs/reranking.proto", proto_root),
                format!("{}/grpc_stubs/spacy.proto", proto_root),
                format!("{}/grpc_stubs/llm.proto", proto_root),
            ],
            &[format!("{}", proto_root)],
        )?;

    Ok(())
}
