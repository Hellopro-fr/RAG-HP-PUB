mod config;
mod domain;
mod grpc_clients;
mod infrastructure;
mod routers;
mod services;

use actix_web::{web, App, HttpServer, middleware};
use tracing::info;
use utoipa::OpenApi;
use utoipa_swagger_ui::SwaggerUi;

use crate::config::SETTINGS;
use crate::domain::models::*;

/// OpenAPI documentation
#[derive(OpenApi)]
#[openapi(
    paths(
        routers::query::query_handler,
        routers::recommendation::filter_handler,
        routers::recommendation::filter_by_caracteristique_handler,
        routers::recommendation::matching_handler,
        routers::product::get_product_caracteristiques,
        routers::product::delete_product,
        routers::admin::execute_cypher,
        routers::admin::get_categories_count,
        routers::fournisseur::get_couverture_by_fournisseur,
        routers::fournisseur::get_couverture_by_produit,
        routers::nodes::update_node,
        routers::nodes::get_schema,
        routers::nodes::get_node,
    ),
    components(schemas(
        QueryRequest,
        QueryResponse,
        CypherQueryRequest,
        CypherQueryResponse,
        ComplexFilterRequest,
        MatchingPayloadIdProduit,
        MatchingResponse,
        Produit,
        CaracteristiqueMatching,
        ScoredProduct,
        ResultProduct,
        NodeUpdateRequest,
        NodeResponse,
        FournisseurGeoResponse,
        ScoringOptions,
        MatchingOptions,
        MatchingOptionsScore,
        RerankingOptions,
        Constraint,
        MatchingCaracteristique,
        MetadonneUtilisateurs,
        ProductCaracteristiquesResponse,
        SchemaResponse,
    )),
    tags(
        (name = "Query", description = "RAG intelligent search"),
        (name = "Recommendation", description = "Product filtering and matching"),
        (name = "Product", description = "Product characteristics"),
        (name = "Admin", description = "Admin operations"),
        (name = "Fournisseur", description = "Supplier coverage"),
        (name = "Nodes", description = "Graph node CRUD"),
    ),
    info(
        title = "Graph RAG API Recherche (Rust)",
        version = "1.0.0",
        description = "Rust port of the Graph RAG API Recherche service — intelligent search and product matching using RAG, Cypher scoring, and LLM reranking."
    )
)]
struct ApiDoc;

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    // Load .env
    dotenvy::dotenv().ok();

    // Initialize tracing
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    let port = SETTINGS.api_port;
    info!("Starting Graph RAG API Recherche Rust Service on port {}", port);

    // Generate OpenAPI spec
    let openapi = ApiDoc::openapi();

    HttpServer::new(move || {
        App::new()
            .wrap(tracing_actix_web::TracingLogger::default())
            // Swagger UI
            .service(
                SwaggerUi::new("/docs/{_:.*}")
                    .url("/openapi.json", openapi.clone()),
            )
            // Query Router
            .service(routers::query::query_handler)
            // Recommendation Router
            .service(routers::recommendation::filter_handler)
            .service(routers::recommendation::filter_by_caracteristique_handler)
            .service(routers::recommendation::matching_handler)
            // Product Router
            .service(routers::product::get_product_caracteristiques)
            .service(routers::product::delete_product)
            // Admin Router
            .service(routers::admin::execute_cypher)
            .service(routers::admin::get_categories_count)
            // Fournisseur Router
            .service(routers::fournisseur::get_couverture_by_fournisseur)
            .service(routers::fournisseur::get_couverture_by_produit)
            // Nodes Router
            .service(routers::nodes::update_node)
            .service(routers::nodes::get_schema)
            .service(routers::nodes::get_node)
    })
    .bind(format!("0.0.0.0:{}", port))?
    .run()
    .await
}
