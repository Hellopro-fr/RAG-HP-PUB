# Graph Report - unified --update v5  (2026-05-12)

## Corpus Check
- 320 files · ~0 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3123 nodes · 6420 edges · 97 communities detected
- Extraction: 62% EXTRACTED · 38% INFERRED · 0% AMBIGUOUS · INFERRED: 2412 edges (avg confidence: 0.61)
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
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 91|Community 91]]
- [[_COMMUNITY_Community 99|Community 99]]
- [[_COMMUNITY_Community 100|Community 100]]
- [[_COMMUNITY_Community 101|Community 101]]
- [[_COMMUNITY_Community 102|Community 102]]
- [[_COMMUNITY_Community 103|Community 103]]
- [[_COMMUNITY_Community 104|Community 104]]
- [[_COMMUNITY_Community 105|Community 105]]
- [[_COMMUNITY_Community 109|Community 109]]
- [[_COMMUNITY_Community 110|Community 110]]
- [[_COMMUNITY_Community 114|Community 114]]
- [[_COMMUNITY_Community 116|Community 116]]
- [[_COMMUNITY_Community 117|Community 117]]
- [[_COMMUNITY_Community 118|Community 118]]
- [[_COMMUNITY_Community 119|Community 119]]
- [[_COMMUNITY_Community 120|Community 120]]
- [[_COMMUNITY_Community 121|Community 121]]
- [[_COMMUNITY_Community 122|Community 122]]
- [[_COMMUNITY_Community 123|Community 123]]
- [[_COMMUNITY_Community 124|Community 124]]
- [[_COMMUNITY_Community 125|Community 125]]
- [[_COMMUNITY_Community 126|Community 126]]

## God Nodes (most connected - your core abstractions)
1. `CrawlerManager` - 163 edges
2. `DomainFR` - 131 edges
3. `DetectionMode` - 114 edges
4. `LanguageDetector` - 111 edges
5. `Configuration` - 67 edges
6. `ScrapeResult` - 57 edges
7. `CrawlerManager` - 50 edges
8. `IncludeInArchive` - 48 edges
9. `ReindexResponse` - 48 edges
10. `GuardMetrics` - 47 edges

## Surprising Connections (you probably didn't know these)
- `GeminiClient` --semantically_similar_to--> `gemini_client Gemini Infrastructure`  [INFERRED] [semantically similar]
  D:/DevHellopro/Workspaces/RAG-HP-PUB/libs/common-utils/src/common_utils/llm/providers.py → apps-microservices/graph-rag-api-recherche-rust-service/CLAUDE.md
- `MilvusProduitInserer` --conceptually_related_to--> `milvus-service gRPC (50056)`  [INFERRED]
  D:/DevHellopro/Workspaces/RAG-HP-PUB/libs/common-utils/src/common_utils/database/MilvusProduitInserer.py → apps-microservices/graph-rag-api-recherche-rust-service/CLAUDE.md
- `Configuration` --conceptually_related_to--> `Lazy<Settings> env var singleton`  [INFERRED]
  D:/DevHellopro/Workspaces/RAG-HP-PUB/libs/common-utils/src/common_utils/database/config/settings.py → apps-microservices/graph-rag-api-recherche-rust-service/CLAUDE.md
- `DLQProperties / DLQPropertiesAsync` --semantically_similar_to--> `dlq_archiver.py`  [INFERRED] [semantically similar]
  libs/common-utils/CLAUDE.md → tools/CLAUDE.md
- `OpenAIClient` --conceptually_related_to--> `LLM Providers (Gemini / OpenAI / Anthropic)`  [INFERRED]
  D:/DevHellopro/Workspaces/RAG-HP-PUB/libs/common-utils/src/common_utils/llm/providers.py → apps-microservices/graph-rag-api-recherche-rust-service/CLAUDE.md

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
- **SSO platform: server + first client + integration guide** — account_service_sso, mcp_gateway_sso_client, account_service_client_integration [EXTRACTED 1.00]
- **Crawler observability + resilience cluster (marker-check + webhook idempotency + timing)** — crawler_stale_detector_marker_check, crawler_webhook_idempotency, crawler_timing_instrumentation [EXTRACTED 1.00]
- **FR detection page-validity gating triad** — fr_invalid_page_rejection, fr_page_validator, fr_homepage_fallback_orchestrator [EXTRACTED 1.00]

## Communities

### Community 0 - "Milvus CRUD Layer"
Cohesion: 0.01
Nodes (292): archive_crawl_to_gcs(), ArchiveResponse, CapacityResponse, clear_pending_callbacks(), CrawlRequest, CrawlResponse, CrawlStatus, download_crawl_results() (+284 more)

### Community 1 - "Node.js Crawler Core"
Cohesion: 0.01
Nodes (220): AlternativeUrl schema (url, method, reliability, validated, region_priority?), api-gateway per-service downstream timeout map (detection=180s), API hreflang/data-lang same-host validation gate, DomainFR._is_valid_language_alternative static helper (Python), Go vs Express benchmark — crawler-monitor-backend (2026-04), queue.Analyze CPU + JSON parsing benchmark (Go), RAM idle / under-load benchmark (distroless static), WebSocket broadcast p99 benchmark (gorilla/ws hub) (+212 more)

### Community 2 - "CrawlerManager Python + DLQ"
Cohesion: 0.02
Nodes (65): DLQArchiver, main(), Archives a batch of messages and ACKs/NACKs them individually., Main resilient loop to consume messages., Establishes and re-establishes connections to RabbitMQ and Elasticsearch., Declares queues and sets up consumers., Callback to buffer incoming messages., Recursively finds 'embedding' keys, extracts them into a dictionary with their J (+57 more)

### Community 3 - "Rust Service Clients"
Cohesion: 0.02
Nodes (77): DedupManager, DetectionLangueClient, applyCliFlagGuard(), classifyFragment(), commitBypassDiez(), commitSkipDiez(), getDiezDecisionMode(), readPersistedDecision() (+69 more)

### Community 4 - "Milvus Concurrency Guard"
Cohesion: 0.02
Nodes (104): check_gcloud_auth(), classify_by_name(), _confirm_or_exit(), _count_dataset_files(), detect_duplicates(), extract_crawl_id(), gcloud_delete(), gcloud_download() (+96 more)

### Community 5 - "Redis Cache Rationale"
Cohesion: 0.03
Nodes (118): _cache_key(), check_url(), _compare_without_scheme(), DomainFR, get_domain_from_url(), _identify_decision_case(), _is_strong_french_url(), _is_valid_language_alternative() (+110 more)

### Community 6 - "Pydantic Request Schemas"
Cohesion: 0.03
Nodes (93): _detect_soft_404(), _is_redirect_to_home(), Pure page validator for api-detection-langue-fr.  Classifies a ScrapeResult agai, Lightweight visible-text length for the thin-content threshold., Classify a ScrapeResult against the requested URL.      Order of checks:       1, validate(), ValidationVerdict, _visible_text_length() (+85 more)

### Community 7 - "GCS Archive Classifier"
Cohesion: 0.02
Nodes (64): _count_files_in_dir(), CrawlerManager, _map_error_to_message(), Kill a process and all its children via the process group., Returns (archive_path, is_temporary).         is_temporary=True means the file, Triggers a GCS download via the host-side download daemon and waits for the resu, Publie une mise à jour du statut d'un job sur le canal Pub/Sub de Redis., Synchronous helper function to generate the archive.         Optimized for perf (+56 more)

### Community 8 - "LLM Provider Clients"
Cohesion: 0.08
Nodes (107): BaseModel, Thresholds for aborting an update job., UpdateThresholds, InsertDevisRequest, DomainCache, _normalize_domain(), Stocke le résultat pour input_url ET result_url (si redirection).          ttl, Version debug de check_page_if_french qui collecte les informations         de (+99 more)

### Community 9 - "LLM gRPC Client"
Cohesion: 0.04
Nodes (69): BaseSettings, Config, env_or(), env_or_opt(), GuardConfig, Configuration de l'application, Settings, GuardMetrics (+61 more)

### Community 10 - "GCS Audit CLI"
Cohesion: 0.03
Nodes (27): execute_cypher(), get_categories_count(), ServiceClients, CypherBuilderService, get_couverture_by_fournisseur(), get_couverture_by_produit(), FournisseurService, GeminiClient (+19 more)

### Community 11 - "Document Text Extractor"
Cohesion: 0.02
Nodes (86): ABC, common_utils.grpc_clients (client wrappers), _clean_text(), chunk_text(), detokenize(), get_embedding(), get_embeddings(), Appelle le service gRPC pour obtenir les embeddings pour une liste de textes. (+78 more)

### Community 12 - "Enums and Collection Types"
Cohesion: 0.05
Nodes (95): ChatBaseURL, ChatProvider, CollectionName, CollectionNameGraph, Enum for the possible collection names.     The values correspond to the string, Enum for the possible collection names.     The values correspond to the string, # TODO:, CrawlMode (+87 more)

### Community 13 - "Update-Mode Queue Builder"
Cohesion: 0.05
Nodes (42): AdmissionController, AdmissionMiddleware, FastAPI admission-control middleware.  Per-path routing to two AdmissionContro, Atomic in-flight counter with a hard max.      Not a semaphore: acquire() does, Try to acquire a slot. Returns True on success, False if saturated., Release a slot. Defensive: does not go below zero., BaseHTTPMiddleware, metrics_endpoint() (+34 more)

### Community 14 - "Rust Service Request Models"
Cohesion: 0.06
Nodes (30): BaseTrafilatura, BaseTrafilaturaReponse, TrafilaturaReponseHtml, InputJSON, OutputJSON, HeaderFooterExtractor, Analyzes a BeautifulSoup object to robustly find and extract the text content of, Original signature strategy: Tag + Sorted Class Names. (+22 more)

### Community 15 - "Trafilatura HTML Cleaning"
Cohesion: 0.05
Nodes (20): main(), ChatRequest, GraphDatabaseClient, GraphMilvusClient, GraphNormalizationClient, NormRangeResult, NormResult, get_llm_chat_batch_response() (+12 more)

### Community 16 - "GCS Quarantine Restore"
Cohesion: 0.08
Nodes (23): DocumentTextExtractor, Télécharge un fichier depuis une URL                  Args:             url: URL, Résout un chemin ou URL vers un chemin local                  Args:, Convertit une image vers un format supporté par l'OCR                  Args:, Ajoute un fichier à la liste de nettoyage                  Args:             fil, Supprime tous les fichiers marqués pour le nettoyage, Extrait le texte d'une image ou d'un PDF avec OCRExtractor.         - Si un PDF, Vérifie si un document contient des images non extractibles                  Arg (+15 more)

### Community 17 - "Regional Path Exclusion Rationale"
Cohesion: 0.07
Nodes (45): Audit logs (login, token_issue, token_reuse_attack, webhook_fired, etc.), account-service-backend, Per-client branding endpoint /authorize/branding/{client_id}.json (logo, name, brand_color), claim_mapper applies client.claim_mappings to JWT (e.g. is_admin -> role_admin), Account-service client integration guide (Go + FastAPI examples for OAuth2 PKCE downstream wiring), MySQL schema: users, oauth2_clients, oauth2_authorization_codes, oauth2_refresh_tokens, logout_events, audit_logs, account-service-frontend, AuthenticateHellopro proxy (lifted from mcp-gateway) - delegates password check to hellopro.fr (+37 more)

### Community 18 - "Qdrant CRUD Layer"
Cohesion: 0.06
Nodes (24): Helpers for the pre-flight disk space check before archiving., Instantiate CrawlerManager without running __init__ (avoids Redis setup)., Source dir with 1000 bytes total → estimate returns 1500 bytes., Missing source dir → return 0 (caller applies floor)., If os.walk raises, return 0 and do not propagate., Happy path: archives_dir has one .tar.gz → state dict populated., Files in .staging/ must NOT be counted — those are in-progress tmp files., Empty archives_dir → oldest_file_age_seconds is None, not 0. (+16 more)

### Community 19 - "Graph Milvus gRPC Client"
Cohesion: 0.12
Nodes (25): addPage(), addPoolSample(), buildSummary(), createAggregator(), median(), percentile(), phaseStats(), round1() (+17 more)

### Community 20 - "Embedding gRPC Client"
Cohesion: 0.08
Nodes (23): build_queue(), classify_entry(), _has_tmp_sibling(), load_exclude_ids(), load_report(), main(), parse_args(), Build the update-mode re-ingestion queue from a gcs_archive_audit report.  Reads (+15 more)

### Community 21 - "DeepSeek OCR Extractor"
Cohesion: 0.05
Nodes (29): CaracteristiqueMatching, CategorieCountResponse, ComplexFilterRequest, Constraint, CypherQueryRequest, CypherQueryResponse, DepartementCouverture, FilterCaracteristiqueRequest (+21 more)

### Community 22 - "Header Footer Extractor"
Cohesion: 0.07
Nodes (30): alternative_urls Exclusion List, robots.txt Blanket Block, running_count Drift Bug, Cross-Service Milvus Coordination, Inflight Request Deduplication, Multi-Path robots Probe, Multilingual Regional Path Duplicates, Playwright TargetClosedError flood (+22 more)

### Community 23 - "Graph Database gRPC Client"
Cohesion: 0.08
Nodes (26): check_entities_exist(), check_labels_exist(), Check which entity IDs already exist in Milvus.          Args:         ids: L, Search result from Milvus., Upsert a single canonical label.          Args:         label: The canonical, Upsert multiple labels in a batch.          Args:         labels: List of dic, Search for similar labels.          Args:         embedding: Query vector emb, Check which labels already exist in Milvus.          Args:         labels: Li (+18 more)

### Community 24 - "Claude Config Audit"
Cohesion: 0.14
Nodes (6): ModelConfig, QdrantCategoriesCrud, ModelConfig, QdrantEchangeCrud, ModelConfig, QdrantFournisseursCrud

### Community 25 - "Archive Disk Preflight Rationale"
Cohesion: 0.11
Nodes (12): DeepseekOCRDocExtractor, Télécharge un fichier depuis une URL directement en mémoire (asynchrone), Traite des fichiers à partir d'URLs (asynchrone)         Les fichiers sont télé, Client asynchrone pour l'API OCR externe utilisant Deepseek, Initialise le client OCR                  Args:             base_url: URL de, Traite des fichiers déjà téléchargés en mémoire (asynchrone)         Évite le r, Traite un seul fichier à partir d'une URL (asynchrone)                  Args:, Convertit un fichier non-supporté en PDF en utilisant LibreOffice (asynchrone) (+4 more)

### Community 26 - "Dead Services Cleanup"
Cohesion: 0.13
Nodes (20): BatchResult, _dict_to_struct(), execute_batch_cypher(), execute_cypher(), get_graph_schema(), GraphSchema, NodeLabel, PropertyInfo (+12 more)

### Community 27 - "GCS Archive Audit Tool Rationale"
Cohesion: 0.16
Nodes (13): DetectionClient, Shared HTTP client enforcing the api-detection-langue-fr call contract.  Contr, HTTP client wrapper for api-detection-langue-fr enforcing the caller contract., _isolate_env(), Tests for common_utils.detection_client.DetectionClient., Reset contract env vars to known defaults so tests are hermetic., With DETECTION_MAX_CONCURRENCY=2, at most 2 requests are in flight at once., test_concurrency_semaphore_caps_inflight() (+5 more)

### Community 28 - "CleanHTML Module"
Cohesion: 0.16
Nodes (17): rabbitmq-reviewer agent (proposed), security-auditor agent (proposed), test-writer agent (proposed), /pre-push command (proposed), prix-traitement port discrepancy (8595 vs 8591), 47.5/100 maturity score rationale, Claude Code Audit Report 2026-03-25, security.md rule (proposed) (+9 more)

### Community 29 - "Crawler Monitor Rationale"
Cohesion: 0.15
Nodes (16): Audit Classifications (OK/WRONG_NAME/CORRUPTED/...), Missing 'domain' field in callback_payload, --restore-from-quarantine command, ./ Prefix Tar Member Bug, tmp.tar.gz Glob Race with Upload Daemon, Update-Mode Re-ingestion, Rationale: Diagnostic-first defense over silent producer/consumer fix, Rationale: Use gcloud CLI to avoid new PyPI dependency (+8 more)

### Community 30 - "Community 30"
Cohesion: 0.2
Nodes (12): get_elasticsearch_client(), get_rabbitmq_connection(), Shared connection factories for RabbitMQ and Elasticsearch., Fail fast if required environment variables are missing., Connects to RabbitMQ with exponential backoff retries., Connects to Elasticsearch with exponential backoff retries., _validate_env(), main() (+4 more)

### Community 31 - "Community 31"
Cohesion: 0.17
Nodes (12): api-classification-v2 (test variant), api-rest-milvus-bkp (superseded), Archive Branch Strategy, Dead Services Cleanup Plan, database-service (superseded), categories-processor-service (dormant), Dormant Services Cleanup Phase 2, fournisseurs-processor-service (dormant) (+4 more)

### Community 32 - "Community 32"
Cohesion: 0.17
Nodes (12): GCS Archive Audit Tool Plan, Archive Classifications (OK/CORRUPTED/WRONG_NAME/...), GCS Audit Multi-Source Domain Resolution, gcloud Storage CLI Shell Wrappers (no Python GCS lib), _normalize_member_name (handles ./ prefix), GCS Audit Prefix Fix + Quarantine Restore, _resolve_domain_name Multi-Source Helper, --restore-from-quarantine Flag (+4 more)

### Community 33 - "Community 33"
Cohesion: 0.22
Nodes (5): CleanHTML, Class base to clean data., Convert HTML content to BeautifulSoup object., Steps:         1. Convert HTML to BeautifulSoup object.         2. Keep only tag, Strip HTML tags and return cleaned text.         Remove all tags except tags rel

### Community 34 - "Community 34"
Cohesion: 0.2
Nodes (10): Crawler Monitor Alignment Plan, Monitor/Crawler Data Contract Mismatch, Crawler Monitor Dataset Browser & Queue Insights, Fail-Fast Security Defaults (admin/JWT), supertest Backend Test Harness, 3-Category URL Browser (succès/erreurs/non-FR), Container-Level cgroup Metrics, React Rules of Hooks Violation Fix (+2 more)

### Community 35 - "Community 35"
Cohesion: 0.44
Nodes (2): ModelConfig, QdrantDevisCrud

### Community 36 - "Community 36"
Cohesion: 0.28
Nodes (8): normalize_quantity(), normalize_range(), NormalizedQuantity, NormalizedRange, Result of quantity normalization., Result of range normalization., Normalize a single quantity (value + unit).          Args:         label: The, Normalize a numeric range (min/max + unit).          Args:         label: The

### Community 37 - "Community 37"
Cohesion: 0.28
Nodes (8): Entity, extract_entities(), lemmatize(), Token with lemmatization information., Named entity extracted from text., Call the gRPC service to lemmatize text.          Args:         text: The tex, Call the gRPC service to extract named entities from text.          Args:, Token

### Community 38 - "Community 38"
Cohesion: 0.22
Nodes (2): Tests for Lua script string definitions. Validates that the scripts are well-fo, TestLuaScripts

### Community 39 - "Community 39"
Cohesion: 0.22
Nodes (9): Crawler Capacity Counter & OOM Fixes, Ghost OOM Relaunch Prevention (Fix 4), Redis Capacity Counter Drift (5 Fixes), Fresh last_heartbeat in start_crawl, Reconciliation Leader Election + Heartbeat Guard, Redis SET NX EX reconcile_leader_lock, Webhook Idempotency Client-Side Plan, Stable request_id UUID (Persisted in job_data) (+1 more)

### Community 40 - "Community 40"
Cohesion: 0.25
Nodes (6): classic_search_vector(), get_collection_schema(), hybrid_search_vector(), Appelle le service gRPC pour effectuer une recherche hybride     combinant rech, Appelle le service gRPC pour obtenir le schéma d'une collection avec un cache d', Appelle le service gRPC pour effectuer une recherche classique par filtre.

### Community 41 - "Community 41"
Cohesion: 0.25
Nodes (8): api-detection-langue-fr Concurrency Defense, TargetClosedError Flood Fix (unroute_all + try/finally), Three-Layer Defense (admission + container + contract), Milvus Global Concurrency Guard Plan, Prevent RAM Overload on Milvus VM, Redis Lua ACQUIRE/RELEASE/CORRECT Scripts, Three-Tier Slot Pool (Search > High-write > Low-write), TTL-Based Crash-Safe Leases

### Community 42 - "Community 42"
Cohesion: 0.29
Nodes (4): PDFProcessor, A class to extract text from a PDF file's binary content., Initializes the PDFProcessor with the binary content of the file.         :param, Executes the full workflow: opens the file from memory and extracts text.

### Community 43 - "Community 43"
Cohesion: 0.29
Nodes (6): get_metrics_app(), measure_processing_time(), Starts a Prometheus metrics HTTP server in a separate thread.     This is essent, Returns a WSGI app for serving Prometheus metrics.     Useful for embedding into, A decorator that measures the execution time of a function (sync or async)     a, start_metrics_server_in_thread()

### Community 44 - "Community 44"
Cohesion: 0.29
Nodes (7): BAAI/bge-reranker-v2-m3, dangvantuan/sentence-camembert-large, export_embedding_to_onnx.py, model-optimizer (ONNX export), model-optimizer/requirements.txt, export_reranker_to_onnx.py, NVIDIA Triton Inference Server

### Community 45 - "Community 45"
Cohesion: 0.38
Nodes (5): Register GET /api-info on the given FastAPI app with the catalog convention., register_api_info(), test_custom_openapi_url(), test_full_payload(), test_minimal_payload()

### Community 46 - "Community 46"
Cohesion: 0.47
Nodes (2): AnonymizeText, gen_email_uuid()

### Community 47 - "Community 47"
Cohesion: 0.4
Nodes (2): RabbitMQConnection, Crée une connexion RabbitMQ avec un nombre limité de tentatives.          :param

### Community 48 - "Community 48"
Cohesion: 0.4
Nodes (5): 503 Rejection + Fail-Open Diagnostics, Archive Disk Space Pre-flight Check, Atomic os.rename from .staging/ to archives/, Archive Staging Subdirectory Plan, Eliminate Upload Daemon FileNotFoundError Race

### Community 49 - "Community 49"
Cohesion: 0.5
Nodes (3): graphify CI workflows (auto-rebuild + coverage-check), graphify scoped post-commit/post-merge hook, graphify services-policy.yml (graphed/not_graphed registry)

### Community 50 - "Community 50"
Cohesion: 0.67
Nodes (3): create_dlq_headers(), create_dlq_properties(), DLQProperties

### Community 51 - "Community 51"
Cohesion: 0.5
Nodes (4): content-extractor-api-service Design Spec, boilerpy3 /clean Endpoint, HeaderFooterExtractor /extract Endpoint, Thin Wrapper Over libs/common-utils

### Community 52 - "Community 52"
Cohesion: 0.67
Nodes (4): Timestamped Archive Branch Approach, Dead Services Cleanup Phase 1 (2026-04-09), Dormant Services Cleanup Phase 2 (2026-04-09), Remaining Services Cleanup Phase 3 (2026-04-10)

### Community 53 - "Community 53"
Cohesion: 0.67
Nodes (2): Configure root logger with a stdout handler.      Safe to call multiple times, setup_logging()

### Community 54 - "Community 54"
Cohesion: 0.67
Nodes (1): Pytest conftest for tools/ tests.  Adds the tools/ directory to sys.path so te

### Community 55 - "Community 55"
Cohesion: 0.67
Nodes (2): export_embedding_model(), Charge le modèle d'embedding, exporte le module Transformer sous-jacent en ONNX,

### Community 56 - "Community 56"
Cohesion: 0.67
Nodes (2): export_reranker_model(), Charge le modèle de reranking, l'exporte au format ONNX,     et génère le fichie

### Community 57 - "Community 57"
Cohesion: 0.67
Nodes (3): robots_txt_bypassed Callback Flag, robots.txt Total Block Detection & Bypass, Multi-Path Probe Guard (isBlanketBlock)

### Community 58 - "Community 58"
Cohesion: 0.67
Nodes (3): match_phrase Routing for Quoted Field:Value, Rule Match Viewer + Dynamic Service List, DLQ Manager UX Improvements Plan

### Community 59 - "Community 59"
Cohesion: 0.67
Nodes (3): Google Sheets Import for MCP Gateway (2026-04-16), mcp-gateway-service + frontend, Google OAuth2 + Sheets API

### Community 60 - "Community 60"
Cohesion: 0.67
Nodes (2): Verifies the API key if API_KEY is configured in settings.     If API_KEY is not, verify_api_key()

### Community 61 - "Community 61"
Cohesion: 0.67
Nodes (3): Crawler Monitor design system: oklch tokens + Tailwind theme + primitives (Pill, StatTile, Sparkline, Timeline, CapacityRing, AreaChart, LogLine, KV, ProjCard), Refondue pages: Overview, Job Details, Domains, Capacity Planning, Health, Audit, Albums, Dark Mode, Mobile responsive, Crawler Monitor UI Redesign (oklch tokens, Linear/Vercel/Stripe aesthetic)

### Community 62 - "Community 62"
Cohesion: 1.0
Nodes (1): Atomic Lua scripts for Redis-based concurrency guard. All slot operations (acqu

### Community 63 - "Community 63"
Cohesion: 1.0
Nodes (1): Shared threading lock for pymilvus connection management.  All Milvus CRUD and I

### Community 64 - "Community 64"
Cohesion: 1.0
Nodes (2): Claude Config Optimization Plan, 20-25% Token Consumption Reduction

### Community 65 - "Community 65"
Cohesion: 1.0
Nodes (2): DLQ Manager UX Improvements (2026-04-11), dlq-manager-service

### Community 66 - "Community 66"
Cohesion: 1.0
Nodes (2): Crawler Monitor Dataset & Queue Insights (2026-04-12), crawler-monitor-backend / frontend

### Community 67 - "Community 67"
Cohesion: 1.0
Nodes (2): Rationale: Reduce token consumption by 20-25% per conversation, Claude Config Optimization (2026-04-16)

### Community 69 - "Community 69"
Cohesion: 1.0
Nodes (1): Prometheus metrics for api-detection-langue-fr.  Exposed at /metrics. Used to

### Community 72 - "Community 72"
Cohesion: 1.0
Nodes (1): Creates a dictionary of headers for a DLQ message, compatible with both pika and

### Community 73 - "Community 73"
Cohesion: 1.0
Nodes (1): Creates pika.BasicProperties for a DLQ message. For backward compatibility with

### Community 74 - "Community 74"
Cohesion: 1.0
Nodes (1): Creates a dictionary of headers for a DLQ message based on an aio_pika message.

### Community 75 - "Community 75"
Cohesion: 1.0
Nodes (1): Creates a persistent aio_pika.Message ready for the Dead Letter Queue.

### Community 76 - "Community 76"
Cohesion: 1.0
Nodes (1): Cleans up whitespace and removes control characters.

### Community 80 - "Community 80"
Cohesion: 1.0
Nodes (1): Nettoie une chaîne de texte en normalisant les espaces et en corrigeant

### Community 91 - "Community 91"
Cohesion: 1.0
Nodes (1): ignoreHTTPSErrors in Camoufox/Chromium

### Community 99 - "Community 99"
Cohesion: 1.0
Nodes (1): Maps internal error codes to human-readable French messages for DB storage.

### Community 100 - "Community 100"
Cohesion: 1.0
Nodes (1): A stale 'running' job marked failed must decrement the global counter.

### Community 101 - "Community 101"
Cohesion: 1.0
Nodes (1): If somehow we hit stale handler with terminal status, skip decrement.

### Community 102 - "Community 102"
Cohesion: 1.0
Nodes (1): When marker says finished, decrement + lock release + set_json with finished, NO

### Community 103 - "Community 103"
Cohesion: 1.0
Nodes (1): When marker says failed, same reconcile path but Redis status=failed. Webhook st

### Community 104 - "Community 104"
Cohesion: 1.0
Nodes (1): Marker None → existing stale-failure path runs (webhook sent, status=failed).

### Community 105 - "Community 105"
Cohesion: 1.0
Nodes (1): Marker invalid (helper returned None for unknown final_status) → fall through to

### Community 109 - "Community 109"
Cohesion: 1.0
Nodes (1): Current admitted in-flight count (unsynchronized read for observability).

### Community 110 - "Community 110"
Cohesion: 1.0
Nodes (1): Number of coalesced calls served from a shared future.

### Community 114 - "Community 114"
Cohesion: 1.0
Nodes (1): Normalise l'encodage du contenu HTML en UTF-8.          Reproduit le comportem

### Community 116 - "Community 116"
Cohesion: 1.0
Nodes (1): Test endpoint /health

### Community 117 - "Community 117"
Cohesion: 1.0
Nodes (1): Test endpoint /check-url avec TLD .fr

### Community 118 - "Community 118"
Cohesion: 1.0
Nodes (1): Test endpoint /check-url sans indicateur FR

### Community 119 - "Community 119"
Cohesion: 1.0
Nodes (1): Test endpoint /detect avec contenu HTML fourni

### Community 120 - "Community 120"
Cohesion: 1.0
Nodes (1): Test validation endpoint /detect-batch avec liste vide

### Community 121 - "Community 121"
Cohesion: 1.0
Nodes (1): Test endpoint racine /

### Community 122 - "Community 122"
Cohesion: 1.0
Nodes (1): Mode simple ne doit pas détecter les liens hreflang

### Community 123 - "Community 123"
Cohesion: 1.0
Nodes (1): Mode complete doit détecter les liens hreflang

### Community 124 - "Community 124"
Cohesion: 1.0
Nodes (1): Verify CAMOUFOX_ENABLED setting is respected.

### Community 125 - "Community 125"
Cohesion: 1.0
Nodes (1): On happy path, page.unroute_all is called before context.close.

### Community 126 - "Community 126"
Cohesion: 1.0
Nodes (1): A mid-fetch exception still triggers context.close and browser.close (try/finall

## Knowledge Gaps
- **715 isolated node(s):** `Enum for the possible collection names.     The values correspond to the string`, `Enum for the possible collection names.     The values correspond to the string`, `DLQProperties`, `Creates a dictionary of headers for a DLQ message, compatible with both pika and`, `Creates pika.BasicProperties for a DLQ message. For backward compatibility with` (+710 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 35`** (9 nodes): `QdrantDevisCrud.py`, `ModelConfig`, `QdrantDevisCrud`, `.delete_devis()`, `.get_devis()`, `._get_or_create_collection()`, `.__init__()`, `.insert_devis()`, `.update_devis()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (9 nodes): `test_lua_scripts.py`, `Tests for Lua script string definitions. Validates that the scripts are well-fo`, `TestLuaScripts`, `.test_acquire_script_contains_expected_commands()`, `.test_acquire_script_is_non_empty_string()`, `.test_correct_counters_script_contains_expected_commands()`, `.test_correct_counters_script_is_non_empty_string()`, `.test_release_script_contains_expected_commands()`, `.test_release_script_is_non_empty_string()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (6 nodes): `AnonymizeText`, `.anonymize_text()`, `.normalize_text()`, `.presidio_anonymizer()`, `gen_email_uuid()`, `AnonymizeText.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (5 nodes): `rabbitmq_connection.py`, `RabbitMQConnection`, `.create_connection()`, `.__init__()`, `Crée une connexion RabbitMQ avec un nombre limité de tentatives.          :param`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (3 nodes): `logging_config.py`, `Configure root logger with a stdout handler.      Safe to call multiple times`, `setup_logging()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (3 nodes): `conftest.py`, `Pytest conftest for tools/ tests.  Adds the tools/ directory to sys.path so te`, `conftest.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (3 nodes): `export_embedding_model()`, `Charge le modèle d'embedding, exporte le module Transformer sous-jacent en ONNX,`, `export_embedding_to_onnx.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (3 nodes): `export_reranker_model()`, `Charge le modèle de reranking, l'exporte au format ONNX,     et génère le fichie`, `export_reranker_to_onnx.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (3 nodes): `auth.py`, `Verifies the API key if API_KEY is configured in settings.     If API_KEY is not`, `verify_api_key()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 62`** (2 nodes): `lua_scripts.py`, `Atomic Lua scripts for Redis-based concurrency guard. All slot operations (acqu`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 63`** (2 nodes): `milvus_lock.py`, `Shared threading lock for pymilvus connection management.  All Milvus CRUD and I`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 64`** (2 nodes): `Claude Config Optimization Plan`, `20-25% Token Consumption Reduction`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 65`** (2 nodes): `DLQ Manager UX Improvements (2026-04-11)`, `dlq-manager-service`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 66`** (2 nodes): `Crawler Monitor Dataset & Queue Insights (2026-04-12)`, `crawler-monitor-backend / frontend`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 67`** (2 nodes): `Rationale: Reduce token consumption by 20-25% per conversation`, `Claude Config Optimization (2026-04-16)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 69`** (2 nodes): `metrics.py`, `Prometheus metrics for api-detection-langue-fr.  Exposed at /metrics. Used to`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 72`** (1 nodes): `Creates a dictionary of headers for a DLQ message, compatible with both pika and`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 73`** (1 nodes): `Creates pika.BasicProperties for a DLQ message. For backward compatibility with`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 74`** (1 nodes): `Creates a dictionary of headers for a DLQ message based on an aio_pika message.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 75`** (1 nodes): `Creates a persistent aio_pika.Message ready for the Dead Letter Queue.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 76`** (1 nodes): `Cleans up whitespace and removes control characters.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 80`** (1 nodes): `Nettoie une chaîne de texte en normalisant les espaces et en corrigeant`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 91`** (1 nodes): `ignoreHTTPSErrors in Camoufox/Chromium`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 99`** (1 nodes): `Maps internal error codes to human-readable French messages for DB storage.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 100`** (1 nodes): `A stale 'running' job marked failed must decrement the global counter.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 101`** (1 nodes): `If somehow we hit stale handler with terminal status, skip decrement.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 102`** (1 nodes): `When marker says finished, decrement + lock release + set_json with finished, NO`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 103`** (1 nodes): `When marker says failed, same reconcile path but Redis status=failed. Webhook st`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 104`** (1 nodes): `Marker None → existing stale-failure path runs (webhook sent, status=failed).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 105`** (1 nodes): `Marker invalid (helper returned None for unknown final_status) → fall through to`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 109`** (1 nodes): `Current admitted in-flight count (unsynchronized read for observability).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 110`** (1 nodes): `Number of coalesced calls served from a shared future.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 114`** (1 nodes): `Normalise l'encodage du contenu HTML en UTF-8.          Reproduit le comportem`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 116`** (1 nodes): `Test endpoint /health`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 117`** (1 nodes): `Test endpoint /check-url avec TLD .fr`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 118`** (1 nodes): `Test endpoint /check-url sans indicateur FR`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 119`** (1 nodes): `Test endpoint /detect avec contenu HTML fourni`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 120`** (1 nodes): `Test validation endpoint /detect-batch avec liste vide`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 121`** (1 nodes): `Test endpoint racine /`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 122`** (1 nodes): `Mode simple ne doit pas détecter les liens hreflang`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 123`** (1 nodes): `Mode complete doit détecter les liens hreflang`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 124`** (1 nodes): `Verify CAMOUFOX_ENABLED setting is respected.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 125`** (1 nodes): `On happy path, page.unroute_all is called before context.close.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 126`** (1 nodes): `A mid-fetch exception still triggers context.close and browser.close (try/finall`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `common_utils.grpc_clients (client wrappers)` connect `Document Text Extractor` to `Node.js Crawler Core`?**
  _High betweenness centrality (0.124) - this node is a cross-community bridge._
- **Why does `common-utils (Python shared lib)` connect `Node.js Crawler Core` to `Regional Path Exclusion Rationale`, `Document Text Extractor`?**
  _High betweenness centrality (0.123) - this node is a cross-community bridge._
- **Why does `DetectionMode` connect `Redis Cache Rationale` to `Milvus CRUD Layer`, `LLM Provider Clients`, `Enums and Collection Types`?**
  _High betweenness centrality (0.078) - this node is a cross-community bridge._
- **Are the 123 inferred relationships involving `CrawlerManager` (e.g. with `CrawlStatus` and `IncludeInArchive`) actually correct?**
  _`CrawlerManager` has 123 INFERRED edges - model-reasoned connections that need verification._
- **Are the 118 inferred relationships involving `DomainFR` (e.g. with `_detect_single_url()` and `detect_french_debug()`) actually correct?**
  _`DomainFR` has 118 INFERRED edges - model-reasoned connections that need verification._
- **Are the 110 inferred relationships involving `DetectionMode` (e.g. with `Normalize URL for dedup key: scheme + lowercase host + path + query.` and `Build the root URL for a given URL (preserves scheme + host + port).`) actually correct?**
  _`DetectionMode` has 110 INFERRED edges - model-reasoned connections that need verification._
- **Are the 101 inferred relationships involving `LanguageDetector` (e.g. with `DomainCache` and `DomainFR`) actually correct?**
  _`LanguageDetector` has 101 INFERRED edges - model-reasoned connections that need verification._