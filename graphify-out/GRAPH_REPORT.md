# Graph Report - unified (backbone + crawler + graph-rag-rust-service)  (2026-04-24)

## Corpus Check
- 235 files · ~252,866 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1919 nodes · 3494 edges · 72 communities detected
- Extraction: 70% EXTRACTED · 30% INFERRED · 0% AMBIGUOUS · INFERRED: 1062 edges (avg confidence: 0.64)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Enums and Collection Types|Enums and Collection Types]]
- [[_COMMUNITY_CrawlerManager Python + DLQ|CrawlerManager Python + DLQ]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_CleanHTML Module|CleanHTML Module]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Trafilatura HTML Cleaning|Trafilatura HTML Cleaning]]
- [[_COMMUNITY_Pydantic Request Schemas|Pydantic Request Schemas]]
- [[_COMMUNITY_Milvus Concurrency Guard|Milvus Concurrency Guard]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Milvus CRUD Layer|Milvus CRUD Layer]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Qdrant CRUD Layer|Qdrant CRUD Layer]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Embedding gRPC Client|Embedding gRPC Client]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Header Footer Extractor|Header Footer Extractor]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Graph Database gRPC Client|Graph Database gRPC Client]]
- [[_COMMUNITY_Graph Milvus gRPC Client|Graph Milvus gRPC Client]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_LLM gRPC Client|LLM gRPC Client]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_LLM Provider Clients|LLM Provider Clients]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_DeepSeek OCR Extractor|DeepSeek OCR Extractor]]
- [[_COMMUNITY_Document Text Extractor|Document Text Extractor]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Redis Cache Rationale|Redis Cache Rationale]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Update-Mode Queue Builder|Update-Mode Queue Builder]]
- [[_COMMUNITY_GCS Audit CLI|GCS Audit CLI]]
- [[_COMMUNITY_GCS Archive Classifier|GCS Archive Classifier]]
- [[_COMMUNITY_GCS Quarantine Restore|GCS Quarantine Restore]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Claude Config Audit|Claude Config Audit]]
- [[_COMMUNITY_Dead Services Cleanup|Dead Services Cleanup]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Crawler Monitor Rationale|Crawler Monitor Rationale]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_GCS Archive Audit Tool Rationale|GCS Archive Audit Tool Rationale]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Regional Path Exclusion Rationale|Regional Path Exclusion Rationale]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Archive Disk Preflight Rationale|Archive Disk Preflight Rationale]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Node.js Crawler Core|Node.js Crawler Core]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]
- [[_COMMUNITY_Rust Service Request Models|Rust Service Request Models]]
- [[_COMMUNITY_Rust Service Clients|Rust Service Clients]]

## God Nodes (most connected - your core abstractions)
1. `CrawlerManager` - 93 edges
2. `Configuration` - 67 edges
3. `IncludeInArchive` - 48 edges
4. `ReindexResponse` - 48 edges
5. `GuardMetrics` - 47 edges
6. `CrawlStatus` - 47 edges
7. `GuardConfig` - 45 edges
8. `graph-rag-api-recherche-rust-service` - 45 edges
9. `Utils` - 44 edges
10. `log()` - 34 edges

## Surprising Connections (you probably didn't know these)
- `GeminiClient` --semantically_similar_to--> `gemini_client Gemini Infrastructure`  [INFERRED] [semantically similar]
  D:\DevHellopro\Workspaces\RAG-HP-PUB\libs\common-utils\src\common_utils\llm\providers.py → apps-microservices/graph-rag-api-recherche-rust-service/CLAUDE.md
- `MilvusProduitInserer` --conceptually_related_to--> `milvus-service gRPC (50056)`  [INFERRED]
  D:\DevHellopro\Workspaces\RAG-HP-PUB\libs\common-utils\src\common_utils\database\MilvusProduitInserer.py → apps-microservices/graph-rag-api-recherche-rust-service/CLAUDE.md
- `Configuration` --conceptually_related_to--> `Lazy<Settings> env var singleton`  [INFERRED]
  D:\DevHellopro\Workspaces\RAG-HP-PUB\libs\common-utils\src\common_utils\database\config\settings.py → apps-microservices/graph-rag-api-recherche-rust-service/CLAUDE.md
- `DLQProperties / DLQPropertiesAsync` --semantically_similar_to--> `dlq_archiver.py`  [INFERRED] [semantically similar]
  libs/common-utils/CLAUDE.md → tools/CLAUDE.md
- `OpenAIClient` --conceptually_related_to--> `LLM Providers (Gemini / OpenAI / Anthropic)`  [INFERRED]
  D:\DevHellopro\Workspaces\RAG-HP-PUB\libs\common-utils\src\common_utils\llm\providers.py → apps-microservices/graph-rag-api-recherche-rust-service/CLAUDE.md

## Hyperedges (group relationships)
- **Shared proto compilation across Python + Rust + service protos** — protos_pkg, grpc_stubs_lib, rust_grpc_clients [EXTRACTED 0.95]
- **GCS crawler archive pipeline (daemon + crawler + audit)** — tools_upload_daemon, tools_download_daemon, tools_gcs_archive_audit, daemon_crawler_service [EXTRACTED 0.90]
- **Claude Code config lifecycle (audit -> staging -> team guides)** — audit_report, audit_staging_readme, team_guide_en, config_migration_prompt [INFERRED 0.85]
- **Services Cleanup (3 Phases)** — dead_services_cleanup_plan, dormant_services_cleanup_plan, remaining_services_cleanup_plan [INFERRED 0.90]
- **GCS Audit Tool Iterative Evolution** — gcs_archive_audit_plan, gcs_audit_prefix_fix_plan, gcs_audit_domain_resolution_plan, gcs_quarantine_remediation_plan [INFERRED 0.90]
- **Crawler Service Reliability Fixes** — crawler_capacity_counter_plan, reconciliation_leader_plan, webhook_idempotency_plan, archive_staging_plan, archive_disk_preflight_plan [INFERRED 0.85]
- **Three-Phase Services Cleanup** — spec_dead_services_cleanup, spec_dormant_services_cleanup, spec_remaining_services_cleanup [EXTRACTED 0.95]
- **GCS Audit Tool Evolution Chain** — spec_gcs_archive_audit, spec_gcs_audit_prefix_fix, spec_gcs_audit_domain_resolution, spec_gcs_quarantine_remediation [EXTRACTED 0.90]
- **Crawler Archive Pipeline Fixes** — spec_archive_staging_subdir, spec_archive_disk_space_preflight, spec_gcs_archive_audit [EXTRACTED 0.85]
- **OOM Capacity Counter Invariants (transition safety)** — crawler_capacity_counter, crawler_oom_relaunch, crawler_exit_codes [EXTRACTED 0.90]
- **Stealth Browser Stack (Camoufox + Playwright + Crawlee)** — crawler_camoufox, crawler_playwright, crawler_crawlee [EXTRACTED 0.85]
- **Multi-Replica Safety Net (Leader + Webhook ID + Redis)** — crawler_leader_election, crawler_webhook_idempotency, cache_service_redisclient [INFERRED 0.80]
- **Rust Service gRPC Dependency Mesh (7 upstreams)** — graph_rag_api_recherche_rust_service, rust_service_dep_embedding_grpc, rust_service_dep_milvus_grpc, rust_service_dep_database_connector_grpc, rust_service_dep_normalize_unite_grpc, rust_service_dep_spacy_grpc, rust_service_dep_llm_grpc, rust_service_dep_reranking_grpc [EXTRACTED 1.00]
- **RAG + Cypher + Reranking Three-Stage Pipeline** — rust_service_rag_service, rust_service_cypher_builder, rust_service_dep_reranking_grpc, rust_service_dep_embedding_grpc, rust_service_dep_neo4j_bolt [INFERRED 0.85]
- **Clean Architecture 3-Layer Stack** — rust_service_routers, rust_service_services_layer, rust_service_infrastructure, rust_service_clean_architecture [EXTRACTED 1.00]
- **Multi-Provider LLM Client Cluster** — rust_service_llm_providers, rust_service_gemini_client, rust_service_llm_service, providers_geminiclient, providers_openaiclient, providers_anthropicclient [INFERRED 0.70]

## Communities

### Community 12 - "Enums and Collection Types"
Cohesion: 0.1
Nodes (37): CollectionName, Enum, CollectionNameGraph, Enum for the possible collection names.     The values correspond to the string, Enum for the possible collection names.     The values correspond to the string, # TODO:, ChatBaseURL, ChatProvider (+29 more)

### Community 2 - "CrawlerManager Python + DLQ"
Cohesion: 0.03
Nodes (61): str, DLQPropertiesAsync, create_dlq_headers(), create_dlq_message(), _count_files_in_dir(), CrawlerManager, _map_error_to_message(), TestStaleHandlerCounter (+53 more)

### Community 45 - "Community 45"
Cohesion: 0.67
Nodes (3): DLQProperties, create_dlq_headers(), create_dlq_properties()

### Community 64 - "Community 64"
Cohesion: 1.0
Nodes (1): Creates a dictionary of headers for a DLQ message, compatible with both pika and

### Community 65 - "Community 65"
Cohesion: 1.0
Nodes (1): Creates pika.BasicProperties for a DLQ message. For backward compatibility with

### Community 66 - "Community 66"
Cohesion: 1.0
Nodes (1): Creates a dictionary of headers for a DLQ message based on an aio_pika message.

### Community 67 - "Community 67"
Cohesion: 1.0
Nodes (1): Creates a persistent aio_pika.Message ready for the Dead Letter Queue.

### Community 42 - "Community 42"
Cohesion: 0.47
Nodes (2): gen_email_uuid(), AnonymizeText

### Community 28 - "CleanHTML Module"
Cohesion: 0.22
Nodes (5): CleanHTML, Class base to clean data., Convert HTML content to BeautifulSoup object., Steps:         1. Convert HTML to BeautifulSoup object.         2. Keep only tag, Strip HTML tags and return cleaned text.         Remove all tags except tags rel

### Community 68 - "Community 68"
Cohesion: 1.0
Nodes (1): Cleans up whitespace and removes control characters.

### Community 15 - "Trafilatura HTML Cleaning"
Cohesion: 0.12
Nodes (19): TrafilaturaHp, _normalize_sentence(), _normalize_whitespace(), Normalizes a sentence for accurate comparison., Cleans up whitespace and removes control characters., Pre-processes the HTML content:         1. Removes script/style/noscript tags., Post-processes the extracted content:         1. Extracts article content (produ, Extrait le texte avec BeautifulSoup en ciblant les balises pertinentes. (+11 more)

### Community 6 - "Pydantic Request Schemas"
Cohesion: 0.07
Nodes (87): BaseModel, InsertDevisRequest, InsertEchangeRequest, InsertProduitRequest, InsertWebsiteRequest, reconcile_running_jobs_count(), scheduled_archive_cleanup(), validation_exception_handler() (+79 more)

### Community 4 - "Milvus Concurrency Guard"
Cohesion: 0.04
Nodes (64): GuardConfig, Configuration for MilvusConcurrencyGuard., GuardMetrics, Prometheus metrics for MilvusConcurrencyGuard.      Uses module-level singleto, Record a successful slot acquisition., Record a slot release., Record an acquire timeout., Set the configuration gauges (typically called once at startup). (+56 more)

### Community 56 - "Community 56"
Cohesion: 1.0
Nodes (1): Atomic Lua scripts for Redis-based concurrency guard. All slot operations (acqu

### Community 0 - "Milvus CRUD Layer"
Cohesion: 0.02
Nodes (58): MilvusProduitsMigration, main(), Script de migration de la collection produits_3 vers produits_4 Objectif: Augmen, Classe pour gérer la migration de produits_3 vers produits_4, Vérifier que la collection source existe, Créer une copie de sauvegarde (optionnel mais recommandé pour petites collection, Créer la nouvelle collection produits_4 avec le schéma corrigé, Filtre les chunks qui existent déjà dans la collection cible         Vérifie: id (+50 more)

### Community 57 - "Community 57"
Cohesion: 1.0
Nodes (1): Shared threading lock for pymilvus connection management.  All Milvus CRUD and I

### Community 18 - "Qdrant CRUD Layer"
Cohesion: 0.14
Nodes (6): ModelConfig, QdrantCategoriesCrud, ModelConfig, QdrantDevisCrud, ModelConfig, QdrantFournisseursCrud

### Community 30 - "Community 30"
Cohesion: 0.44
Nodes (2): ModelConfig, QdrantProduitsCrud

### Community 31 - "Community 31"
Cohesion: 0.44
Nodes (2): ModelConfig, QdrantWebsiteCrud

### Community 20 - "Embedding gRPC Client"
Cohesion: 0.1
Nodes (16): Config, Embedding, _clean_text(), Ajoute une ligne avec le temps d’exécution dans temps_embedding.log, Délègue le chunking au microservice d'embedding., get_embeddings(), get_embedding(), tokenize() (+8 more)

### Community 72 - "Community 72"
Cohesion: 1.0
Nodes (1): Nettoie une chaîne de texte en normalisant les espaces et en corrigeant

### Community 22 - "Header Footer Extractor"
Cohesion: 0.13
Nodes (11): HeaderFooterExtractor, A class to extract header and footer text from HTML content.     It uses Beauti, Extracts and cleans the text from a BeautifulSoup element.         It removes s, Analyzes a BeautifulSoup object to robustly find and extract the text content of, Analyzes a BeautifulSoup object to robustly find and extract the text content of, Original signature strategy: Tag + Sorted Class Names., ZONE A Improvement: Structural signature based on DOM path.         Example: bo, Helper to get 'tag:nth-of-type(i)' string. (+3 more)

### Community 38 - "Community 38"
Cohesion: 0.29
Nodes (4): PDFProcessor, A class to extract text from a PDF file's binary content., Initializes the PDFProcessor with the binary content of the file.         :param, Executes the full workflow: opens the file from memory and extracts text.

### Community 36 - "Community 36"
Cohesion: 0.25
Nodes (6): get_collection_schema(), classic_search_vector(), hybrid_search_vector(), Appelle le service gRPC pour obtenir le schéma d'une collection avec un cache d', Appelle le service gRPC pour effectuer une recherche classique par filtre., Appelle le service gRPC pour effectuer une recherche hybride     combinant rech

### Community 23 - "Graph Database gRPC Client"
Cohesion: 0.13
Nodes (20): PropertyInfo, NodeLabel, RelationshipType, GraphSchema, BatchResult, _dict_to_struct(), execute_cypher(), execute_batch_cypher() (+12 more)

### Community 19 - "Graph Milvus gRPC Client"
Cohesion: 0.08
Nodes (26): SearchResult, upsert_entity(), upsert_entity_batch(), search_similar_entities(), check_entities_exist(), upsert_label(), upsert_label_batch(), search_similar_labels() (+18 more)

### Community 32 - "Community 32"
Cohesion: 0.28
Nodes (8): NormalizedQuantity, NormalizedRange, normalize_quantity(), normalize_range(), Result of quantity normalization., Result of range normalization., Normalize a single quantity (value + unit).          Args:         label: The, Normalize a numeric range (min/max + unit).          Args:         label: The

### Community 9 - "LLM gRPC Client"
Cohesion: 0.03
Nodes (41): get_llm_chat_response(), get_llm_chat_batch_response(), Appelle le service gRPC LLM pour obtenir une réponse complète (non-streamée), Appelle le service gRPC LLM pour obtenir des réponses complètes pour un lot de m, rerank_documents(), rerank_documents_with_scores(), Appelle le service gRPC de reranking pour réorganiser une liste de documents., Appelle le service gRPC de reranking pour réorganiser une liste de documents et (+33 more)

### Community 33 - "Community 33"
Cohesion: 0.28
Nodes (8): Token, Entity, lemmatize(), extract_entities(), Token with lemmatization information., Named entity extracted from text., Call the gRPC service to lemmatize text.          Args:         text: The tex, Call the gRPC service to extract named entities from text.          Args:

### Community 8 - "LLM Provider Clients"
Cohesion: 0.03
Nodes (70): BaseLLMClient, ABC, OpenAIClient, DeepSeekClient, GeminiClient, AnthropicClient, LLMFactory, create_client() (+62 more)

### Community 48 - "Community 48"
Cohesion: 0.67
Nodes (2): setup_logging(), Configure root logger with a stdout handler.      Safe to call multiple times

### Community 39 - "Community 39"
Cohesion: 0.29
Nodes (6): start_metrics_server_in_thread(), get_metrics_app(), measure_processing_time(), Starts a Prometheus metrics HTTP server in a separate thread.     This is essent, Returns a WSGI app for serving Prometheus metrics.     Useful for embedding into, A decorator that measures the execution time of a function (sync or async)     a

### Community 21 - "DeepSeek OCR Extractor"
Cohesion: 0.11
Nodes (12): DeepseekOCRDocExtractor, Client asynchrone pour l'API OCR externe utilisant Deepseek, Initialise le client OCR                  Args:             base_url: URL de, Vérifie si le fichier est un format supporté (PDF ou image)                  A, Vérifie si le fichier est un PDF                  Args:             filename:, Compte le nombre de pages d'un PDF                  Args:             content, Valide que le nombre de pages du PDF ne dépasse pas la limite autorisée, Télécharge un fichier depuis une URL directement en mémoire (asynchrone) (+4 more)

### Community 11 - "Document Text Extractor"
Cohesion: 0.08
Nodes (23): DocumentTextExtractor, Classe pour extraire le texte de différents types de documents, Initialise l'extracteur                  Args:             download_dir: Réperto, Vérifie si une chaîne est une URL                  Args:             path_or_url, Extrait le nom de fichier depuis une URL                  Args:             url:, Télécharge un fichier depuis une URL                  Args:             url: URL, Résout un chemin ou URL vers un chemin local                  Args:, Convertit une image vers un format supporté par l'OCR                  Args: (+15 more)

### Community 43 - "Community 43"
Cohesion: 0.4
Nodes (2): RabbitMQConnection, Crée une connexion RabbitMQ avec un nombre limité de tentatives.          :param

### Community 5 - "Redis Cache Rationale"
Cohesion: 0.02
Nodes (99): Initializes the Redis connection pool.     Connects to Redis using the URL from, Closes the Redis connection pool., Sets a dictionary for a key, serializing it to JSON., Atomically sets a key only if it does not already exist (SET NX).     Returns T, Gets a dictionary for a key, deserializing it from JSON., Sets a raw value for a key., Gets the raw string value of a key., Deletes a key from Redis. (+91 more)

### Community 34 - "Community 34"
Cohesion: 0.22
Nodes (2): TestLuaScripts, Tests for Lua script string definitions. Validates that the scripts are well-fo

### Community 13 - "Update-Mode Queue Builder"
Cohesion: 0.08
Nodes (23): load_report(), load_exclude_ids(), _has_tmp_sibling(), classify_entry(), build_queue(), upload_to_gcs(), parse_args(), main() (+15 more)

### Community 10 - "GCS Audit CLI"
Cohesion: 0.05
Nodes (41): _run_gcloud(), check_gcloud_auth(), gcloud_ls(), gcloud_download(), gcloud_delete(), gcloud_move(), extract_crawl_id(), classify_by_name() (+33 more)

### Community 7 - "GCS Archive Classifier"
Cohesion: 0.06
Nodes (46): inspect_archive(), _normalize_member_name(), _read_json_member(), _count_dataset_files(), _resolve_domain_name(), Open a .tar.gz and classify it.      Returns (category, details). `details` al, Strip leading './' or '.' from tar member names.      shutil.make_archive pass, Read and parse a JSON file from the tar. Handles tars produced by     shutil.ma (+38 more)

### Community 16 - "GCS Quarantine Restore"
Cohesion: 0.11
Nodes (17): _load_include_ids(), Parse --include-ids input. Returns None when no filter, else Set[str].      Ac, _run_gcloud(), gcloud_move(), _exists(), restore(), main(), Move reclassified-OK archives from crawls-quarantine/ back to crawls/.  Reads a (+9 more)

### Community 49 - "Community 49"
Cohesion: 0.67
Nodes (1): Pytest conftest for tools/ tests.  Adds the tools/ directory to sys.path so te

### Community 50 - "Community 50"
Cohesion: 0.67
Nodes (2): export_embedding_model(), Charge le modèle d'embedding, exporte le module Transformer sous-jacent en ONNX,

### Community 51 - "Community 51"
Cohesion: 0.67
Nodes (2): export_reranker_model(), Charge le modèle de reranking, l'exporte au format ONNX,     et génère le fichie

### Community 40 - "Community 40"
Cohesion: 0.29
Nodes (7): model-optimizer (ONNX export), export_embedding_to_onnx.py, export_reranker_to_onnx.py, dangvantuan/sentence-camembert-large, BAAI/bge-reranker-v2-m3, NVIDIA Triton Inference Server, model-optimizer/requirements.txt

### Community 24 - "Claude Config Audit"
Cohesion: 0.16
Nodes (17): Claude Code Audit Report 2026-03-25, security.md rule (proposed), test-writer agent (proposed), security-auditor agent (proposed), rabbitmq-reviewer agent (proposed), /pre-push command (proposed), 47.5/100 maturity score rationale, prix-traitement port discrepancy (8595 vs 8591) (+9 more)

### Community 26 - "Dead Services Cleanup"
Cohesion: 0.17
Nodes (12): Dead Services Cleanup Plan, Archive Branch Strategy, api-rest-milvus-bkp (superseded), database-service (superseded), api-classification-v2 (test variant), Dormant Services Cleanup Phase 2, categories-processor-service (dormant), fournisseurs-processor-service (dormant) (+4 more)

### Community 37 - "Community 37"
Cohesion: 0.25
Nodes (8): Milvus Global Concurrency Guard Plan, Redis Lua ACQUIRE/RELEASE/CORRECT Scripts, Three-Tier Slot Pool (Search > High-write > Low-write), TTL-Based Crash-Safe Leases, Prevent RAM Overload on Milvus VM, api-detection-langue-fr Concurrency Defense, Three-Layer Defense (admission + container + contract), TargetClosedError Flood Fix (unroute_all + try/finally)

### Community 52 - "Community 52"
Cohesion: 0.67
Nodes (3): robots.txt Total Block Detection & Bypass, Multi-Path Probe Guard (isBlanketBlock), robots_txt_bypassed Callback Flag

### Community 29 - "Crawler Monitor Rationale"
Cohesion: 0.2
Nodes (10): Crawler Monitor Alignment Plan, Monitor/Crawler Data Contract Mismatch, Fail-Fast Security Defaults (admin/JWT), Monitor Bugfixes & Reviewer Improvement Plan, React Rules of Hooks Violation Fix, Container-Level cgroup Metrics, Three New Reviewer Review Dimensions, Crawler Monitor Dataset Browser & Queue Insights (+2 more)

### Community 53 - "Community 53"
Cohesion: 0.67
Nodes (3): DLQ Manager UX Improvements Plan, match_phrase Routing for Quoted Field:Value, Rule Match Viewer + Dynamic Service List

### Community 58 - "Community 58"
Cohesion: 1.0
Nodes (2): Claude Config Optimization Plan, 20-25% Token Consumption Reduction

### Community 35 - "Community 35"
Cohesion: 0.22
Nodes (9): Crawler Capacity Counter & OOM Fixes, Redis Capacity Counter Drift (5 Fixes), Ghost OOM Relaunch Prevention (Fix 4), Reconciliation Leader Election + Heartbeat Guard, Redis SET NX EX reconcile_leader_lock, Fresh last_heartbeat in start_crawl, Webhook Idempotency Client-Side Plan, Stable request_id UUID (Persisted in job_data) (+1 more)

### Community 83 - "Community 83"
Cohesion: 1.0
Nodes (1): ignoreHTTPSErrors in Camoufox/Chromium

### Community 44 - "Community 44"
Cohesion: 0.4
Nodes (5): Archive Disk Space Pre-flight Check, 503 Rejection + Fail-Open Diagnostics, Archive Staging Subdirectory Plan, Atomic os.rename from .staging/ to archives/, Eliminate Upload Daemon FileNotFoundError Race

### Community 27 - "GCS Archive Audit Tool Rationale"
Cohesion: 0.17
Nodes (12): GCS Archive Audit Tool Plan, Archive Classifications (OK/CORRUPTED/WRONG_NAME/...), gcloud Storage CLI Shell Wrappers (no Python GCS lib), GCS Audit Multi-Source Domain Resolution, _resolve_domain_name Multi-Source Helper, GCS Audit Prefix Fix + Quarantine Restore, _normalize_member_name (handles ./ prefix), --restore-from-quarantine Flag (+4 more)

### Community 46 - "Community 46"
Cohesion: 0.5
Nodes (4): content-extractor-api-service Design Spec, boilerpy3 /clean Endpoint, HeaderFooterExtractor /extract Endpoint, Thin Wrapper Over libs/common-utils

### Community 17 - "Regional Path Exclusion Rationale"
Cohesion: 0.07
Nodes (30): Regional Path Exclusion Design (2026-04-06), Multilingual Regional Path Duplicates, alternative_urls Exclusion List, Rationale: Apply exclusion at discovery and update-mode seeding, crawler-service, api-detection-langue-fr, robots.txt Total Block Detection & Bypass (2026-04-08), robots.txt Blanket Block (+22 more)

### Community 47 - "Community 47"
Cohesion: 0.67
Nodes (4): Dead Services Cleanup Phase 1 (2026-04-09), Timestamped Archive Branch Approach, Dormant Services Cleanup Phase 2 (2026-04-09), Remaining Services Cleanup Phase 3 (2026-04-10)

### Community 59 - "Community 59"
Cohesion: 1.0
Nodes (2): DLQ Manager UX Improvements (2026-04-11), dlq-manager-service

### Community 60 - "Community 60"
Cohesion: 1.0
Nodes (2): Crawler Monitor Dataset & Queue Insights (2026-04-12), crawler-monitor-backend / frontend

### Community 61 - "Community 61"
Cohesion: 1.0
Nodes (2): Claude Config Optimization (2026-04-16), Rationale: Reduce token consumption by 20-25% per conversation

### Community 54 - "Community 54"
Cohesion: 0.67
Nodes (3): Google Sheets Import for MCP Gateway (2026-04-16), mcp-gateway-service + frontend, Google OAuth2 + Sheets API

### Community 25 - "Archive Disk Preflight Rationale"
Cohesion: 0.15
Nodes (16): Archive Pre-flight Disk Space Check (2026-04-18), Rationale: Diagnostic-first defense over silent producer/consumer fix, Archive Staging Subdirectory (2026-04-18), tmp.tar.gz Glob Race with Upload Daemon, GCS Archive Audit Tool (2026-04-18), tools/gcs_archive_audit.py, Audit Classifications (OK/WRONG_NAME/CORRUPTED/...), Rationale: Use gcloud CLI to avoid new PyPI dependency (+8 more)

### Community 55 - "Community 55"
Cohesion: 0.67
Nodes (2): verify_api_key(), Verifies the API key if API_KEY is configured in settings.     If API_KEY is not

### Community 41 - "Community 41"
Cohesion: 0.38
Nodes (4): Settings, BaseSettings, env_or(), env_or_opt()

### Community 1 - "Node.js Crawler Core"
Cohesion: 0.02
Nodes (57): classifyFragment(), recordClassification(), writeDecisionFile(), commitSkipDiez(), commitBypassDiez(), readPersistedDecision(), applyCliFlagGuard(), getDiezDecisionMode() (+49 more)

### Community 85 - "Community 85"
Cohesion: 1.0
Nodes (1): StatsManager

### Community 86 - "Community 86"
Cohesion: 1.0
Nodes (1): DedupManager

### Community 87 - "Community 87"
Cohesion: 1.0
Nodes (1): JsonlWriter

### Community 14 - "Rust Service Request Models"
Cohesion: 0.05
Nodes (29): QueryRequest, QueryResponse, CypherQueryRequest, CypherQueryResponse, CategorieCountResponse, ScoringOptions, MatchingOptionsScore, MatchingOptions (+21 more)

### Community 3 - "Rust Service Clients"
Cohesion: 0.03
Nodes (27): ServiceClients, GeminiClient, etat_societe_map(), HelloProApiClient, LlmService, execute_cypher(), get_categories_count(), get_couverture_by_fournisseur() (+19 more)

## Knowledge Gaps
- **400 isolated node(s):** `Enum for the possible collection names.     The values correspond to the string`, `Enum for the possible collection names.     The values correspond to the string`, `DLQProperties`, `Creates a dictionary of headers for a DLQ message, compatible with both pika and`, `Creates pika.BasicProperties for a DLQ message. For backward compatibility with` (+395 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 64`** (1 nodes): `Creates a dictionary of headers for a DLQ message, compatible with both pika and`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 65`** (1 nodes): `Creates pika.BasicProperties for a DLQ message. For backward compatibility with`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 66`** (1 nodes): `Creates a dictionary of headers for a DLQ message based on an aio_pika message.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 67`** (1 nodes): `Creates a persistent aio_pika.Message ready for the Dead Letter Queue.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (6 nodes): `AnonymizeText.py`, `gen_email_uuid()`, `AnonymizeText`, `.anonymize_text()`, `.presidio_anonymizer()`, `.normalize_text()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 68`** (1 nodes): `Cleans up whitespace and removes control characters.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (2 nodes): `lua_scripts.py`, `Atomic Lua scripts for Redis-based concurrency guard. All slot operations (acqu`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (2 nodes): `milvus_lock.py`, `Shared threading lock for pymilvus connection management.  All Milvus CRUD and I`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 30`** (9 nodes): `QdrantProduitCrud.py`, `ModelConfig`, `QdrantProduitsCrud`, `.__init__()`, `._get_or_create_collection()`, `.insert_produits()`, `.update_produits()`, `.delete_produits()`, `.get_produit()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (9 nodes): `QdrantWebsiteCrud.py`, `ModelConfig`, `QdrantWebsiteCrud`, `.__init__()`, `._get_or_create_collection()`, `.insert_website()`, `.update_website()`, `.delete_website()`, `.get_website()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 72`** (1 nodes): `Nettoie une chaîne de texte en normalisant les espaces et en corrigeant`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (3 nodes): `logging_config.py`, `setup_logging()`, `Configure root logger with a stdout handler.      Safe to call multiple times`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (5 nodes): `rabbitmq_connection.py`, `RabbitMQConnection`, `.__init__()`, `.create_connection()`, `Crée une connexion RabbitMQ avec un nombre limité de tentatives.          :param`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (9 nodes): `test_lua_scripts.py`, `TestLuaScripts`, `.test_acquire_script_is_non_empty_string()`, `.test_acquire_script_contains_expected_commands()`, `.test_release_script_is_non_empty_string()`, `.test_release_script_contains_expected_commands()`, `.test_correct_counters_script_is_non_empty_string()`, `.test_correct_counters_script_contains_expected_commands()`, `Tests for Lua script string definitions. Validates that the scripts are well-fo`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (3 nodes): `conftest.py`, `Pytest conftest for tools/ tests.  Adds the tools/ directory to sys.path so te`, `conftest.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (3 nodes): `export_embedding_to_onnx.py`, `export_embedding_model()`, `Charge le modèle d'embedding, exporte le module Transformer sous-jacent en ONNX,`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (3 nodes): `export_reranker_to_onnx.py`, `export_reranker_model()`, `Charge le modèle de reranking, l'exporte au format ONNX,     et génère le fichie`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (2 nodes): `Claude Config Optimization Plan`, `20-25% Token Consumption Reduction`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 83`** (1 nodes): `ignoreHTTPSErrors in Camoufox/Chromium`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (2 nodes): `DLQ Manager UX Improvements (2026-04-11)`, `dlq-manager-service`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (2 nodes): `Crawler Monitor Dataset & Queue Insights (2026-04-12)`, `crawler-monitor-backend / frontend`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 61`** (2 nodes): `Claude Config Optimization (2026-04-16)`, `Rationale: Reduce token consumption by 20-25% per conversation`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (3 nodes): `auth.py`, `verify_api_key()`, `Verifies the API key if API_KEY is configured in settings.     If API_KEY is not`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 85`** (1 nodes): `StatsManager`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 86`** (1 nodes): `DedupManager`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 87`** (1 nodes): `JsonlWriter`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `main()` connect `Trafilatura HTML Cleaning` to `Rust Service Clients`?**
  _High betweenness centrality (0.106) - this node is a cross-community bridge._
- **Why does `common_utils.grpc_clients (client wrappers)` connect `LLM Provider Clients` to `Embedding gRPC Client`, `Redis Cache Rationale`?**
  _High betweenness centrality (0.066) - this node is a cross-community bridge._
- **Are the 57 inferred relationships involving `CrawlerManager` (e.g. with `CrawlStatus` and `IncludeInArchive`) actually correct?**
  _`CrawlerManager` has 57 INFERRED edges - model-reasoned connections that need verification._
- **Are the 70 inferred relationships involving `str` (e.g. with `create_dlq_headers()` and `._preprocess_html()`) actually correct?**
  _`str` has 70 INFERRED edges - model-reasoned connections that need verification._
- **Are the 66 inferred relationships involving `Configuration` (e.g. with `MilvusProduitsMigration` and `Script de migration de la collection produits_3 vers produits_4 Objectif: Augmen`) actually correct?**
  _`Configuration` has 66 INFERRED edges - model-reasoned connections that need verification._
- **Are the 44 inferred relationships involving `IncludeInArchive` (e.g. with `CrawlerManager` and `Safely counts files in a directory, excluding Crawlee metadata.`) actually correct?**
  _`IncludeInArchive` has 44 INFERRED edges - model-reasoned connections that need verification._
- **Are the 45 inferred relationships involving `ReindexResponse` (e.g. with `CrawlerManager` and `.reindex_storage()`) actually correct?**
  _`ReindexResponse` has 45 INFERRED edges - model-reasoned connections that need verification._