# Graph Report - unified (post-pull --update v2)  (2026-04-29)

## Corpus Check
- 250 files · ~0 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2015 nodes · 3648 edges · 72 communities detected
- Extraction: 70% EXTRACTED · 30% INFERRED · 0% AMBIGUOUS · INFERRED: 1091 edges (avg confidence: 0.64)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Milvus CRUD Layer|Milvus CRUD Layer]]
- [[_COMMUNITY_Node.js Crawler Core|Node.js Crawler Core]]
- [[_COMMUNITY_CrawlerManager Python + DLQ|CrawlerManager Python + DLQ]]
- [[_COMMUNITY_Rust Service Clients|Rust Service Clients]]
- [[_COMMUNITY_Milvus Concurrency Guard|Milvus Concurrency Guard]]
- [[_COMMUNITY_Redis Cache Rationale|Redis Cache Rationale]]
- [[_COMMUNITY_Pydantic Request Schemas|Pydantic Request Schemas]]
- [[_COMMUNITY_GCS Archive Classifier|GCS Archive Classifier]]
- [[_COMMUNITY_LLM Provider Clients|LLM Provider Clients]]
- [[_COMMUNITY_LLM gRPC Client|LLM gRPC Client]]
- [[_COMMUNITY_GCS Audit CLI|GCS Audit CLI]]
- [[_COMMUNITY_Document Text Extractor|Document Text Extractor]]
- [[_COMMUNITY_Enums and Collection Types|Enums and Collection Types]]
- [[_COMMUNITY_Update-Mode Queue Builder|Update-Mode Queue Builder]]
- [[_COMMUNITY_Rust Service Request Models|Rust Service Request Models]]
- [[_COMMUNITY_Trafilatura HTML Cleaning|Trafilatura HTML Cleaning]]
- [[_COMMUNITY_GCS Quarantine Restore|GCS Quarantine Restore]]
- [[_COMMUNITY_Regional Path Exclusion Rationale|Regional Path Exclusion Rationale]]
- [[_COMMUNITY_Qdrant CRUD Layer|Qdrant CRUD Layer]]
- [[_COMMUNITY_Graph Milvus gRPC Client|Graph Milvus gRPC Client]]
- [[_COMMUNITY_Embedding gRPC Client|Embedding gRPC Client]]
- [[_COMMUNITY_DeepSeek OCR Extractor|DeepSeek OCR Extractor]]
- [[_COMMUNITY_Header Footer Extractor|Header Footer Extractor]]
- [[_COMMUNITY_Graph Database gRPC Client|Graph Database gRPC Client]]
- [[_COMMUNITY_Claude Config Audit|Claude Config Audit]]
- [[_COMMUNITY_Archive Disk Preflight Rationale|Archive Disk Preflight Rationale]]
- [[_COMMUNITY_Dead Services Cleanup|Dead Services Cleanup]]
- [[_COMMUNITY_GCS Archive Audit Tool Rationale|GCS Archive Audit Tool Rationale]]
- [[_COMMUNITY_CleanHTML Module|CleanHTML Module]]
- [[_COMMUNITY_Crawler Monitor Rationale|Crawler Monitor Rationale]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 86|Community 86]]

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
- `BO detection contract constants (180s/10s/2 retries/2s base)` --semantically_similar_to--> `Axios Request Timeout (180s default)`  [INFERRED] [semantically similar]
  docs/superpowers/specs/2026-04-27-detection-langue-fr-bo-caller-contract-design.md → apps-microservices/crawler-service/CLAUDE.md

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
- **Detection-Langue-FR Concurrency Defense Pattern** — crawler_detection_langue_fr_client, crawler_admission_control_p_limit, crawler_detection_503_retry_policy, crawler_detection_caller_contract_parity [EXTRACTED 0.95]
- **Archive Pipeline Safety Pattern** — crawler_archive_disk_preflight, crawler_archive_staging, crawler_archiving_gcs_fallback [EXTRACTED 0.90]
- **Reconciliation + Idempotency Defense Pattern** — crawler_leader_election, crawler_webhook_idempotency, crawler_capacity_counter [EXTRACTED 0.85]
- **BO caller contract: extension + retry-loop + exception hierarchy** — bo_call_api_hellopro_extension, bo_detect_batch_urls_retry, bo_detection_exception_hierarchy [EXTRACTED 0.95]
- **FR validation hardening: drop URL fallback + API gate + crawler gate** — crawler_drop_url_fallback, api_hreflang_gate, crawler_excluded_regional_paths_gate [EXTRACTED 0.95]
- **Go migration: chi router + ws hub + safeJoin store** — monitor_go_chi_router, monitor_go_ws_hub, monitor_go_safe_join [EXTRACTED 0.90]

## Communities

### Community 0 - "Milvus CRUD Layer"
Cohesion: 0.02
Nodes (138): BaseModel, archive_crawl_to_gcs(), ArchiveResponse, CapacityResponse, clear_pending_callbacks(), CrawlMode, CrawlRequest, CrawlResponse (+130 more)

### Community 1 - "Node.js Crawler Core"
Cohesion: 0.02
Nodes (62): main(), MilvusProduitsMigration, Script de migration de la collection produits_3 vers produits_4 Objectif: Augmen, Créer une copie de sauvegarde (optionnel mais recommandé pour petites collection, Créer la nouvelle collection produits_4 avec le schéma corrigé, Filtre les chunks qui existent déjà dans la collection cible         Vérifie: id, Migrer les données par batch          Args:             batch_size: Nombre d'ent, Vérifier que la migration s'est bien passée (+54 more)

### Community 2 - "CrawlerManager Python + DLQ"
Cohesion: 0.02
Nodes (62): DedupManager, DetectionLangueClient, applyCliFlagGuard(), classifyFragment(), commitBypassDiez(), commitSkipDiez(), getDiezDecisionMode(), readPersistedDecision() (+54 more)

### Community 3 - "Rust Service Clients"
Cohesion: 0.03
Nodes (87): check_gcloud_auth(), classify_by_name(), _confirm_or_exit(), _count_dataset_files(), detect_duplicates(), extract_crawl_id(), gcloud_delete(), gcloud_download() (+79 more)

### Community 4 - "Milvus Concurrency Guard"
Cohesion: 0.02
Nodes (127): Go vs Express benchmark — crawler-monitor-backend (2026-04), queue.Analyze CPU + JSON parsing benchmark (Go), RAM idle / under-load benchmark (distroless static), WebSocket broadcast p99 benchmark (gorilla/ws hub), cache_or_execute(), close_redis_pool(), decrement_key(), delete_if_terminal() (+119 more)

### Community 5 - "Redis Cache Rationale"
Cohesion: 0.03
Nodes (27): execute_cypher(), get_categories_count(), ServiceClients, CypherBuilderService, get_couverture_by_fournisseur(), get_couverture_by_produit(), FournisseurService, GeminiClient (+19 more)

### Community 6 - "Pydantic Request Schemas"
Cohesion: 0.04
Nodes (64): GuardConfig, Configuration for MilvusConcurrencyGuard., GuardMetrics, Prometheus metrics for MilvusConcurrencyGuard.      Uses module-level singleto, Record a successful slot acquisition., Record a slot release., Record an acquire timeout., Set the configuration gauges (typically called once at startup). (+56 more)

### Community 7 - "GCS Archive Classifier"
Cohesion: 0.03
Nodes (70): ABC, common_utils.grpc_clients (client wrappers), graph-rag-api-recherche-rust-service, grpc-stubs Python package, database.proto, embedding.proto (EmbeddingService), llm.proto (LLMService), reranking.proto (RerankingService) (+62 more)

### Community 8 - "LLM Provider Clients"
Cohesion: 0.03
Nodes (41): main(), ChatRequest, get_elasticsearch_client(), get_rabbitmq_connection(), Shared connection factories for RabbitMQ and Elasticsearch., Fail fast if required environment variables are missing., Connects to RabbitMQ with exponential backoff retries., Connects to Elasticsearch with exponential backoff retries. (+33 more)

### Community 9 - "LLM gRPC Client"
Cohesion: 0.08
Nodes (23): DocumentTextExtractor, Télécharge un fichier depuis une URL                  Args:             url: URL, Résout un chemin ou URL vers un chemin local                  Args:, Convertit une image vers un format supporté par l'OCR                  Args:, Ajoute un fichier à la liste de nettoyage                  Args:             fil, Supprime tous les fichiers marqués pour le nettoyage, Extrait le texte d'une image ou d'un PDF avec OCRExtractor.         - Si un PDF, Vérifie si un document contient des images non extractibles                  Arg (+15 more)

### Community 10 - "GCS Audit CLI"
Cohesion: 0.11
Nodes (35): ChatBaseURL, ChatProvider, CollectionName, CollectionNameGraph, Enum for the possible collection names.     The values correspond to the string, Enum for the possible collection names.     The values correspond to the string, # TODO:, Enum (+27 more)

### Community 11 - "Document Text Extractor"
Cohesion: 0.08
Nodes (23): build_queue(), classify_entry(), _has_tmp_sibling(), load_exclude_ids(), load_report(), main(), parse_args(), Build the update-mode re-ingestion queue from a gcs_archive_audit report.  Reads (+15 more)

### Community 12 - "Enums and Collection Types"
Cohesion: 0.05
Nodes (29): CaracteristiqueMatching, CategorieCountResponse, ComplexFilterRequest, Constraint, CypherQueryRequest, CypherQueryResponse, DepartementCouverture, FilterCaracteristiqueRequest (+21 more)

### Community 13 - "Update-Mode Queue Builder"
Cohesion: 0.12
Nodes (19): BaseTrafilatura, BaseTrafilaturaReponse, TrafilaturaReponseHtml, InputJSON, OutputJSON, ApiDoc, extractContent(), main() (+11 more)

### Community 14 - "Rust Service Request Models"
Cohesion: 0.11
Nodes (17): _load_include_ids(), Parse --include-ids input. Returns None when no filter, else Set[str].      Ac, _exists(), gcloud_move(), main(), Move reclassified-OK archives from crawls-quarantine/ back to crawls/.  Reads a, Run a gcloud command. Centralized for test patching., Move a GCS object via `gcloud storage mv`. Raises on failure. (+9 more)

### Community 15 - "Trafilatura HTML Cleaning"
Cohesion: 0.07
Nodes (30): alternative_urls Exclusion List, robots.txt Blanket Block, running_count Drift Bug, Cross-Service Milvus Coordination, Inflight Request Deduplication, Multi-Path robots Probe, Multilingual Regional Path Duplicates, Playwright TargetClosedError flood (+22 more)

### Community 16 - "GCS Quarantine Restore"
Cohesion: 0.1
Nodes (30): api-gateway per-service downstream timeout map (detection=180s), API hreflang/data-lang same-host validation gate, DomainFR._is_valid_language_alternative static helper (Python), call_api_hellopro additive extension (&$responseHeaders + ?$connectTimeout), BO Marketplace api-detection-langue-fr Caller Contract — Plan, BO Marketplace api-detection-langue-fr Caller Contract — Spec, detectBatchUrls() retry-loop (503 + Retry-After + exp backoff), BO detection contract constants (180s/10s/2 retries/2s base) (+22 more)

### Community 17 - "Regional Path Exclusion Rationale"
Cohesion: 0.08
Nodes (26): check_entities_exist(), check_labels_exist(), Check which entity IDs already exist in Milvus.          Args:         ids: L, Search result from Milvus., Upsert a single canonical label.          Args:         label: The canonical, Upsert multiple labels in a batch.          Args:         labels: List of dic, Search for similar labels.          Args:         embedding: Query vector emb, Check which labels already exist in Milvus.          Args:         labels: Li (+18 more)

### Community 18 - "Qdrant CRUD Layer"
Cohesion: 0.1
Nodes (16): _clean_text(), chunk_text(), detokenize(), get_embedding(), get_embeddings(), Appelle le service gRPC pour obtenir les embeddings pour une liste de textes., Obtient l'embedding pour un seul texte.     Wrapper pour la fonction de batchin, Appelle le service gRPC pour tokenizer une liste de textes. (+8 more)

### Community 19 - "Graph Milvus gRPC Client"
Cohesion: 0.11
Nodes (12): DeepseekOCRDocExtractor, Télécharge un fichier depuis une URL directement en mémoire (asynchrone), Traite des fichiers à partir d'URLs (asynchrone)         Les fichiers sont télé, Client asynchrone pour l'API OCR externe utilisant Deepseek, Initialise le client OCR                  Args:             base_url: URL de, Traite des fichiers déjà téléchargés en mémoire (asynchrone)         Évite le r, Traite un seul fichier à partir d'une URL (asynchrone)                  Args:, Convertit un fichier non-supporté en PDF en utilisant LibreOffice (asynchrone) (+4 more)

### Community 20 - "Embedding gRPC Client"
Cohesion: 0.13
Nodes (11): HeaderFooterExtractor, Analyzes a BeautifulSoup object to robustly find and extract the text content of, Original signature strategy: Tag + Sorted Class Names., ZONE A Improvement: Structural signature based on DOM path.         Example: bo, Helper to get 'tag:nth-of-type(i)' string., Detects if a text block is likely a cookie/consent banner using robust regex pat, Uses boilerpy3 to strip noisy elements, then performs a structural tree, Extracts and cleans the text from a BeautifulSoup element.         It removes s (+3 more)

### Community 21 - "DeepSeek OCR Extractor"
Cohesion: 0.13
Nodes (20): BatchResult, _dict_to_struct(), execute_batch_cypher(), execute_cypher(), get_graph_schema(), GraphSchema, NodeLabel, PropertyInfo (+12 more)

### Community 22 - "Header Footer Extractor"
Cohesion: 0.16
Nodes (13): DetectionClient, Shared HTTP client enforcing the api-detection-langue-fr call contract.  Contr, HTTP client wrapper for api-detection-langue-fr enforcing the caller contract., _isolate_env(), Tests for common_utils.detection_client.DetectionClient., Reset contract env vars to known defaults so tests are hermetic., With DETECTION_MAX_CONCURRENCY=2, at most 2 requests are in flight at once., test_concurrency_semaphore_caps_inflight() (+5 more)

### Community 23 - "Graph Database gRPC Client"
Cohesion: 0.16
Nodes (17): rabbitmq-reviewer agent (proposed), security-auditor agent (proposed), test-writer agent (proposed), /pre-push command (proposed), prix-traitement port discrepancy (8595 vs 8591), 47.5/100 maturity score rationale, Claude Code Audit Report 2026-03-25, security.md rule (proposed) (+9 more)

### Community 24 - "Claude Config Audit"
Cohesion: 0.15
Nodes (16): Audit Classifications (OK/WRONG_NAME/CORRUPTED/...), Missing 'domain' field in callback_payload, --restore-from-quarantine command, ./ Prefix Tar Member Bug, tmp.tar.gz Glob Race with Upload Daemon, Update-Mode Re-ingestion, Rationale: Diagnostic-first defense over silent producer/consumer fix, Rationale: Use gcloud CLI to avoid new PyPI dependency (+8 more)

### Community 25 - "Archive Disk Preflight Rationale"
Cohesion: 0.17
Nodes (12): api-classification-v2 (test variant), api-rest-milvus-bkp (superseded), Archive Branch Strategy, Dead Services Cleanup Plan, database-service (superseded), categories-processor-service (dormant), Dormant Services Cleanup Phase 2, fournisseurs-processor-service (dormant) (+4 more)

### Community 26 - "Dead Services Cleanup"
Cohesion: 0.17
Nodes (12): GCS Archive Audit Tool Plan, Archive Classifications (OK/CORRUPTED/WRONG_NAME/...), GCS Audit Multi-Source Domain Resolution, gcloud Storage CLI Shell Wrappers (no Python GCS lib), _normalize_member_name (handles ./ prefix), GCS Audit Prefix Fix + Quarantine Restore, _resolve_domain_name Multi-Source Helper, --restore-from-quarantine Flag (+4 more)

### Community 27 - "GCS Archive Audit Tool Rationale"
Cohesion: 0.22
Nodes (5): CleanHTML, Class base to clean data., Convert HTML content to BeautifulSoup object., Steps:         1. Convert HTML to BeautifulSoup object.         2. Keep only tag, Strip HTML tags and return cleaned text.         Remove all tags except tags rel

### Community 28 - "CleanHTML Module"
Cohesion: 0.24
Nodes (9): reconcile_jobs(), Global exception handler for Pydantic validation errors.     This intercepts an, Periodically checks the actual number of 'running' jobs in Redis and corrects, Periodically cleans up old archive files to manage disk usage.     Runs every h, reconcile_running_jobs_count(), scheduled_archive_cleanup(), shutdown_event(), startup_event() (+1 more)

### Community 29 - "Crawler Monitor Rationale"
Cohesion: 0.2
Nodes (10): Crawler Monitor Alignment Plan, Monitor/Crawler Data Contract Mismatch, Crawler Monitor Dataset Browser & Queue Insights, Fail-Fast Security Defaults (admin/JWT), supertest Backend Test Harness, 3-Category URL Browser (succès/erreurs/non-FR), Container-Level cgroup Metrics, React Rules of Hooks Violation Fix (+2 more)

### Community 30 - "Community 30"
Cohesion: 0.44
Nodes (2): ModelConfig, QdrantFournisseursCrud

### Community 31 - "Community 31"
Cohesion: 0.44
Nodes (2): ModelConfig, QdrantCategoriesCrud

### Community 32 - "Community 32"
Cohesion: 0.44
Nodes (2): ModelConfig, QdrantEchangeCrud

### Community 33 - "Community 33"
Cohesion: 0.28
Nodes (8): normalize_quantity(), normalize_range(), NormalizedQuantity, NormalizedRange, Result of quantity normalization., Result of range normalization., Normalize a single quantity (value + unit).          Args:         label: The, Normalize a numeric range (min/max + unit).          Args:         label: The

### Community 34 - "Community 34"
Cohesion: 0.28
Nodes (8): Entity, extract_entities(), lemmatize(), Token with lemmatization information., Named entity extracted from text., Call the gRPC service to lemmatize text.          Args:         text: The tex, Call the gRPC service to extract named entities from text.          Args:, Token

### Community 35 - "Community 35"
Cohesion: 0.22
Nodes (2): Tests for Lua script string definitions. Validates that the scripts are well-fo, TestLuaScripts

### Community 36 - "Community 36"
Cohesion: 0.22
Nodes (9): Crawler Capacity Counter & OOM Fixes, Ghost OOM Relaunch Prevention (Fix 4), Redis Capacity Counter Drift (5 Fixes), Fresh last_heartbeat in start_crawl, Reconciliation Leader Election + Heartbeat Guard, Redis SET NX EX reconcile_leader_lock, Webhook Idempotency Client-Side Plan, Stable request_id UUID (Persisted in job_data) (+1 more)

### Community 37 - "Community 37"
Cohesion: 0.25
Nodes (6): classic_search_vector(), get_collection_schema(), hybrid_search_vector(), Appelle le service gRPC pour effectuer une recherche hybride     combinant rech, Appelle le service gRPC pour obtenir le schéma d'une collection avec un cache d', Appelle le service gRPC pour effectuer une recherche classique par filtre.

### Community 38 - "Community 38"
Cohesion: 0.25
Nodes (8): api-detection-langue-fr Concurrency Defense, TargetClosedError Flood Fix (unroute_all + try/finally), Three-Layer Defense (admission + container + contract), Milvus Global Concurrency Guard Plan, Prevent RAM Overload on Milvus VM, Redis Lua ACQUIRE/RELEASE/CORRECT Scripts, Three-Tier Slot Pool (Search > High-write > Low-write), TTL-Based Crash-Safe Leases

### Community 39 - "Community 39"
Cohesion: 0.29
Nodes (4): PDFProcessor, A class to extract text from a PDF file's binary content., Initializes the PDFProcessor with the binary content of the file.         :param, Executes the full workflow: opens the file from memory and extracts text.

### Community 40 - "Community 40"
Cohesion: 0.29
Nodes (6): get_metrics_app(), measure_processing_time(), Starts a Prometheus metrics HTTP server in a separate thread.     This is essent, Returns a WSGI app for serving Prometheus metrics.     Useful for embedding into, A decorator that measures the execution time of a function (sync or async)     a, start_metrics_server_in_thread()

### Community 41 - "Community 41"
Cohesion: 0.29
Nodes (7): BAAI/bge-reranker-v2-m3, dangvantuan/sentence-camembert-large, export_embedding_to_onnx.py, model-optimizer (ONNX export), model-optimizer/requirements.txt, export_reranker_to_onnx.py, NVIDIA Triton Inference Server

### Community 42 - "Community 42"
Cohesion: 0.38
Nodes (4): BaseSettings, env_or(), env_or_opt(), Settings

### Community 43 - "Community 43"
Cohesion: 0.47
Nodes (2): AnonymizeText, gen_email_uuid()

### Community 44 - "Community 44"
Cohesion: 0.4
Nodes (2): RabbitMQConnection, Crée une connexion RabbitMQ avec un nombre limité de tentatives.          :param

### Community 45 - "Community 45"
Cohesion: 0.4
Nodes (5): 503 Rejection + Fail-Open Diagnostics, Archive Disk Space Pre-flight Check, Atomic os.rename from .staging/ to archives/, Archive Staging Subdirectory Plan, Eliminate Upload Daemon FileNotFoundError Race

### Community 46 - "Community 46"
Cohesion: 0.5
Nodes (5): graphify CI workflows (auto-rebuild + coverage-check), graphify Team Guide (English), graphify Guide d'équipe (Français), graphify scoped post-commit/post-merge hook, graphify services-policy.yml (graphed/not_graphed registry)

### Community 47 - "Community 47"
Cohesion: 0.67
Nodes (3): create_dlq_headers(), create_dlq_properties(), DLQProperties

### Community 48 - "Community 48"
Cohesion: 0.5
Nodes (4): content-extractor-api-service Design Spec, boilerpy3 /clean Endpoint, HeaderFooterExtractor /extract Endpoint, Thin Wrapper Over libs/common-utils

### Community 49 - "Community 49"
Cohesion: 0.67
Nodes (4): Timestamped Archive Branch Approach, Dead Services Cleanup Phase 1 (2026-04-09), Dormant Services Cleanup Phase 2 (2026-04-09), Remaining Services Cleanup Phase 3 (2026-04-10)

### Community 50 - "Community 50"
Cohesion: 0.67
Nodes (3): create_dlq_headers(), create_dlq_message(), DLQPropertiesAsync

### Community 51 - "Community 51"
Cohesion: 0.67
Nodes (2): Configure root logger with a stdout handler.      Safe to call multiple times, setup_logging()

### Community 52 - "Community 52"
Cohesion: 0.67
Nodes (1): Pytest conftest for tools/ tests.  Adds the tools/ directory to sys.path so te

### Community 53 - "Community 53"
Cohesion: 0.67
Nodes (2): export_embedding_model(), Charge le modèle d'embedding, exporte le module Transformer sous-jacent en ONNX,

### Community 54 - "Community 54"
Cohesion: 0.67
Nodes (2): export_reranker_model(), Charge le modèle de reranking, l'exporte au format ONNX,     et génère le fichie

### Community 55 - "Community 55"
Cohesion: 0.67
Nodes (3): robots_txt_bypassed Callback Flag, robots.txt Total Block Detection & Bypass, Multi-Path Probe Guard (isBlanketBlock)

### Community 56 - "Community 56"
Cohesion: 0.67
Nodes (3): match_phrase Routing for Quoted Field:Value, Rule Match Viewer + Dynamic Service List, DLQ Manager UX Improvements Plan

### Community 57 - "Community 57"
Cohesion: 0.67
Nodes (3): Google Sheets Import for MCP Gateway (2026-04-16), mcp-gateway-service + frontend, Google OAuth2 + Sheets API

### Community 58 - "Community 58"
Cohesion: 0.67
Nodes (2): Verifies the API key if API_KEY is configured in settings.     If API_KEY is not, verify_api_key()

### Community 59 - "Community 59"
Cohesion: 1.0
Nodes (1): Atomic Lua scripts for Redis-based concurrency guard. All slot operations (acqu

### Community 60 - "Community 60"
Cohesion: 1.0
Nodes (1): Shared threading lock for pymilvus connection management.  All Milvus CRUD and I

### Community 61 - "Community 61"
Cohesion: 1.0
Nodes (2): Claude Config Optimization Plan, 20-25% Token Consumption Reduction

### Community 62 - "Community 62"
Cohesion: 1.0
Nodes (2): DLQ Manager UX Improvements (2026-04-11), dlq-manager-service

### Community 63 - "Community 63"
Cohesion: 1.0
Nodes (2): Crawler Monitor Dataset & Queue Insights (2026-04-12), crawler-monitor-backend / frontend

### Community 64 - "Community 64"
Cohesion: 1.0
Nodes (2): Rationale: Reduce token consumption by 20-25% per conversation, Claude Config Optimization (2026-04-16)

### Community 67 - "Community 67"
Cohesion: 1.0
Nodes (1): Creates a dictionary of headers for a DLQ message, compatible with both pika and

### Community 68 - "Community 68"
Cohesion: 1.0
Nodes (1): Creates pika.BasicProperties for a DLQ message. For backward compatibility with

### Community 69 - "Community 69"
Cohesion: 1.0
Nodes (1): Creates a dictionary of headers for a DLQ message based on an aio_pika message.

### Community 70 - "Community 70"
Cohesion: 1.0
Nodes (1): Creates a persistent aio_pika.Message ready for the Dead Letter Queue.

### Community 71 - "Community 71"
Cohesion: 1.0
Nodes (1): Cleans up whitespace and removes control characters.

### Community 75 - "Community 75"
Cohesion: 1.0
Nodes (1): Nettoie une chaîne de texte en normalisant les espaces et en corrigeant

### Community 86 - "Community 86"
Cohesion: 1.0
Nodes (1): ignoreHTTPSErrors in Camoufox/Chromium

## Knowledge Gaps
- **426 isolated node(s):** `Enum for the possible collection names.     The values correspond to the string`, `Enum for the possible collection names.     The values correspond to the string`, `DLQProperties`, `Creates a dictionary of headers for a DLQ message, compatible with both pika and`, `Creates pika.BasicProperties for a DLQ message. For backward compatibility with` (+421 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 30`** (9 nodes): `QdrantFournisseursCrud.py`, `ModelConfig`, `QdrantFournisseursCrud`, `.delete_fournisseurs()`, `.get_fournisseurs()`, `._get_or_create_collection()`, `.__init__()`, `.insert_fournisseurs()`, `.update_fournisseurs()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (9 nodes): `QdrantCategoriesCrud.py`, `ModelConfig`, `QdrantCategoriesCrud`, `.delete_categories()`, `.get_categories()`, `._get_or_create_collection()`, `.__init__()`, `.insert_categories()`, `.update_categories()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (9 nodes): `QdrantEchangeCrud.py`, `ModelConfig`, `QdrantEchangeCrud`, `.delete_echange()`, `.get_echange()`, `._get_or_create_collection()`, `.__init__()`, `.insert_echange()`, `.update_echange()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (9 nodes): `test_lua_scripts.py`, `Tests for Lua script string definitions. Validates that the scripts are well-fo`, `TestLuaScripts`, `.test_acquire_script_contains_expected_commands()`, `.test_acquire_script_is_non_empty_string()`, `.test_correct_counters_script_contains_expected_commands()`, `.test_correct_counters_script_is_non_empty_string()`, `.test_release_script_contains_expected_commands()`, `.test_release_script_is_non_empty_string()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (6 nodes): `AnonymizeText`, `.anonymize_text()`, `.normalize_text()`, `.presidio_anonymizer()`, `gen_email_uuid()`, `AnonymizeText.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (5 nodes): `rabbitmq_connection.py`, `RabbitMQConnection`, `.create_connection()`, `.__init__()`, `Crée une connexion RabbitMQ avec un nombre limité de tentatives.          :param`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (3 nodes): `logging_config.py`, `Configure root logger with a stdout handler.      Safe to call multiple times`, `setup_logging()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (3 nodes): `conftest.py`, `Pytest conftest for tools/ tests.  Adds the tools/ directory to sys.path so te`, `conftest.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (3 nodes): `export_embedding_model()`, `Charge le modèle d'embedding, exporte le module Transformer sous-jacent en ONNX,`, `export_embedding_to_onnx.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (3 nodes): `export_reranker_model()`, `Charge le modèle de reranking, l'exporte au format ONNX,     et génère le fichie`, `export_reranker_to_onnx.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (3 nodes): `auth.py`, `Verifies the API key if API_KEY is configured in settings.     If API_KEY is not`, `verify_api_key()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (2 nodes): `lua_scripts.py`, `Atomic Lua scripts for Redis-based concurrency guard. All slot operations (acqu`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (2 nodes): `milvus_lock.py`, `Shared threading lock for pymilvus connection management.  All Milvus CRUD and I`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 61`** (2 nodes): `Claude Config Optimization Plan`, `20-25% Token Consumption Reduction`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 62`** (2 nodes): `DLQ Manager UX Improvements (2026-04-11)`, `dlq-manager-service`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 63`** (2 nodes): `Crawler Monitor Dataset & Queue Insights (2026-04-12)`, `crawler-monitor-backend / frontend`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 64`** (2 nodes): `Rationale: Reduce token consumption by 20-25% per conversation`, `Claude Config Optimization (2026-04-16)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 67`** (1 nodes): `Creates a dictionary of headers for a DLQ message, compatible with both pika and`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 68`** (1 nodes): `Creates pika.BasicProperties for a DLQ message. For backward compatibility with`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 69`** (1 nodes): `Creates a dictionary of headers for a DLQ message based on an aio_pika message.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 70`** (1 nodes): `Creates a persistent aio_pika.Message ready for the Dead Letter Queue.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 71`** (1 nodes): `Cleans up whitespace and removes control characters.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 75`** (1 nodes): `Nettoie une chaîne de texte en normalisant les espaces et en corrigeant`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 86`** (1 nodes): `ignoreHTTPSErrors in Camoufox/Chromium`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `main()` connect `Update-Mode Queue Builder` to `Redis Cache Rationale`?**
  _High betweenness centrality (0.105) - this node is a cross-community bridge._
- **Why does `common_utils.grpc_clients (client wrappers)` connect `GCS Archive Classifier` to `Qdrant CRUD Layer`, `Milvus Concurrency Guard`?**
  _High betweenness centrality (0.102) - this node is a cross-community bridge._
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