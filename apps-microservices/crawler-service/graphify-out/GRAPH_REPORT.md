# Graph Report - apps-microservices/crawler-service  (2026-04-24)

## Corpus Check
- Corpus is ~46,841 words - fits in a single context window. You may not need a graph.

## Summary
- 491 nodes · 1056 edges · 17 communities detected
- Extraction: 59% EXTRACTED · 41% INFERRED · 0% AMBIGUOUS · INFERRED: 437 edges (avg confidence: 0.58)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Node.js Crawler Core|Node.js Crawler Core]]
- [[_COMMUNITY_CrawlerManager Python|CrawlerManager Python]]
- [[_COMMUNITY_API Router and Schemas|API Router and Schemas]]
- [[_COMMUNITY_Crawler Concept Docs|Crawler Concept Docs]]
- [[_COMMUNITY_CrawlerManager Tests|CrawlerManager Tests]]
- [[_COMMUNITY_Migration and Enums|Migration and Enums]]
- [[_COMMUNITY_StatsManager TS|StatsManager TS]]
- [[_COMMUNITY_Leader Election Tests|Leader Election Tests]]
- [[_COMMUNITY_DedupManager TS|DedupManager TS]]
- [[_COMMUNITY_Archive and Disk Rationale|Archive and Disk Rationale]]
- [[_COMMUNITY_main.py and Reconcile Jobs|main.py and Reconcile Jobs]]
- [[_COMMUNITY_Archive Mock E2E|Archive Mock E2E]]
- [[_COMMUNITY_Robots.txt Guard|Robots.txt Guard]]
- [[_COMMUNITY_Auth Module|Auth Module]]
- [[_COMMUNITY_Settings Config|Settings Config]]
- [[_COMMUNITY_pytest fixtures|pytest fixtures]]
- [[_COMMUNITY_Robots Bypass Rationale|Robots Bypass Rationale]]

## God Nodes (most connected - your core abstractions)
1. `CrawlerManager` - 93 edges
2. `IncludeInArchive` - 48 edges
3. `ReindexResponse` - 48 edges
4. `CrawlStatus` - 47 edges
5. `log()` - 34 edges
6. `PruneResponse` - 18 edges
7. `CapacityResponse` - 17 edges
8. `CrawlResponse` - 17 edges
9. `StopResponse` - 17 edges
10. `ArchiveResponse` - 17 edges

## Surprising Connections (you probably didn't know these)
- `Unit tests for crawler_manager.py state-transition guards.` --uses--> `CrawlerManager`  [INFERRED]
  D:\DevHellopro\Workspaces\RAG-HP-PUB\apps-microservices\crawler-service\tests\test_crawler_manager.py → D:\DevHellopro\Workspaces\RAG-HP-PUB\apps-microservices\crawler-service\app\core\crawler_manager.py
- `Fix 1: decrement counter when stale detection marks job failed.` --uses--> `CrawlerManager`  [INFERRED]
  D:\DevHellopro\Workspaces\RAG-HP-PUB\apps-microservices\crawler-service\tests\test_crawler_manager.py → D:\DevHellopro\Workspaces\RAG-HP-PUB\apps-microservices\crawler-service\app\core\crawler_manager.py
- `Fix 2: SIGKILL the subprocess when stale detection marks job failed.` --uses--> `CrawlerManager`  [INFERRED]
  D:\DevHellopro\Workspaces\RAG-HP-PUB\apps-microservices\crawler-service\tests\test_crawler_manager.py → D:\DevHellopro\Workspaces\RAG-HP-PUB\apps-microservices\crawler-service\app\core\crawler_manager.py
- `Subprocess with returncode=None should be killed.` --uses--> `CrawlerManager`  [INFERRED]
  D:\DevHellopro\Workspaces\RAG-HP-PUB\apps-microservices\crawler-service\tests\test_crawler_manager.py → D:\DevHellopro\Workspaces\RAG-HP-PUB\apps-microservices\crawler-service\app\core\crawler_manager.py
- `Subprocess with returncode != None should NOT be killed (PID recycle risk).` --uses--> `CrawlerManager`  [INFERRED]
  D:\DevHellopro\Workspaces\RAG-HP-PUB\apps-microservices\crawler-service\tests\test_crawler_manager.py → D:\DevHellopro\Workspaces\RAG-HP-PUB\apps-microservices\crawler-service\app\core\crawler_manager.py

## Hyperedges (group relationships)
- **Duplicate-Delivery Prevention Trio** — claudemd_reconciliation_leader_election, claudemd_webhook_idempotency, claudemd_request_id_uuid [INFERRED 0.85]
- **Archive Pipeline Safety Net** — claudemd_staging_isolation, claudemd_disk_space_preflight, claudemd_upload_daemon [INFERRED 0.80]
- **Stealth Crawling Browser Stack** — claudemd_camoufox_default, claudemd_playwright, claudemd_robots_blanket_bypass [INFERRED 0.72]

## Communities

### Community 0 - "Node.js Crawler Core"
Cohesion: 0.03
Nodes (48): DetectionLangueClient, applyCliFlagGuard(), classifyFragment(), commitBypassDiez(), commitSkipDiez(), getDiezDecisionMode(), readPersistedDecision(), recordClassification() (+40 more)

### Community 1 - "CrawlerManager Python"
Cohesion: 0.05
Nodes (36): _count_files_in_dir(), CrawlerManager, _map_error_to_message(), start_new_crawl(), str, Archiving writes to a hidden .staging/ subdirectory then atomic-renames     to, archive_crawl must write tmp archives to a .staging subdirectory., archive_crawl must have a finally block that cleans up partial staging files. (+28 more)

### Community 2 - "API Router and Schemas"
Cohesion: 0.1
Nodes (73): BaseModel, archive_crawl_to_gcs(), ArchiveResponse, CapacityResponse, clear_pending_callbacks(), CrawlRequest, CrawlResponse, CrawlStatus (+65 more)

### Community 3 - "Crawler Concept Docs"
Cohesion: 0.05
Nodes (51): api-detection-langue-fr (Dependency Service), Camoufox (Stealth Firefox), Camoufox Default Browser, Camoufox Headless Mode Required, Rationale: Browser-Engine-Level Stealth Undetectable by JS, Capacity Counter Invariants, Rationale: Authoritative Capacity Gating Must Stay in Sync, common-utils (Python shared lib) (+43 more)

### Community 4 - "CrawlerManager Tests"
Cohesion: 0.06
Nodes (14): Unit tests for crawler_manager.py state-transition guards., Fix 3: _relaunch_oom_crawl aborts if status is no longer restarting_oom., Fix 4: _monitor_process skips OOM branch if status is already terminal., Fix 5: force_finish_crawl does not double-decrement., Fix 1: decrement counter when stale detection marks job failed., Fix 2: SIGKILL the subprocess when stale detection marks job failed., Subprocess with returncode=None should be killed., Subprocess with returncode != None should NOT be killed (PID recycle risk). (+6 more)

### Community 5 - "Migration and Enums"
Cohesion: 0.15
Nodes (30): CrawlMode, Mode of operation for the crawler., Enum, ArchiveContentType, cleanup_stale_chunks(), count_files_in_directory(), detect_file_format(), extract_and_fix_nesting() (+22 more)

### Community 6 - "StatsManager TS"
Cohesion: 0.14
Nodes (3): rightTrimSlash(), StatsManager, UpdateChecker

### Community 7 - "Leader Election Tests"
Cohesion: 0.12
Nodes (9): Tests for Issue #1 (leader election) and Issue #2 (fresh heartbeat,     ownersh, start_crawl's initial job_data must include last_heartbeat=now().         Asser, The stale-detection local override must NOT gate on is_local_job.         It mu, reconcile_jobs must attempt to acquire a SET NX leader lock at the top., reconcile_jobs must return early when it does not acquire the lock., reconcile_jobs must release the lock only if it still owns it,         guarded, reconcile_jobs (public wrapper) must delegate actual work to _reconcile_locked., The renamed _reconcile_locked method must contain the original scanning logic. (+1 more)

### Community 8 - "DedupManager TS"
Cohesion: 0.19
Nodes (1): DedupManager

### Community 9 - "Archive and Disk Rationale"
Cohesion: 0.18
Nodes (12): Archiving - GCS Fallback, Pre-flight Disk Space Check, Download Daemon, Fail-Open Policy for Disk Check, Rationale: Broken Measurement Must Never Block Archiving, GCS (Google Cloud Storage), restore_lock:{id} (Redis Lock), Spec: 2026-04-18 Archive Disk Space Preflight Design (+4 more)

### Community 10 - "main.py and Reconcile Jobs"
Cohesion: 0.24
Nodes (9): reconcile_jobs(), Global exception handler for Pydantic validation errors.     This intercepts an, Periodically checks the actual number of 'running' jobs in Redis and corrects, Periodically cleans up old archive files to manage disk usage.     Runs every h, reconcile_running_jobs_count(), scheduled_archive_cleanup(), shutdown_event(), startup_event() (+1 more)

### Community 11 - "Archive Mock E2E"
Cohesion: 0.33
Nodes (2): Verifies that the bash script:         1. Finds the file.         2. Calls 'gclo, TestArchiveMockE2E

### Community 12 - "Robots.txt Guard"
Cohesion: 0.6
Nodes (3): isBlanketBlock(), createMockRobotsFile(), testBlanketBlockDetection()

### Community 13 - "Auth Module"
Cohesion: 0.67
Nodes (2): Verifies the API key if API_KEY is configured in settings.     If API_KEY is not, verify_api_key()

### Community 14 - "Settings Config"
Cohesion: 0.67
Nodes (2): BaseSettings, Settings

### Community 15 - "pytest fixtures"
Cohesion: 1.0
Nodes (1): Pytest configuration and fixtures.

### Community 16 - "Robots Bypass Rationale"
Cohesion: 1.0
Nodes (2): robots.txt Blanket Block Bypass, robotsTxtGuard.ts (isBlanketBlock)

## Knowledge Gaps
- **51 isolated node(s):** `Pytest configuration and fixtures.`, `Periodically checks the actual number of 'running' jobs in Redis and corrects`, `Periodically cleans up old archive files to manage disk usage.     Runs every h`, `Global exception handler for Pydantic validation errors.     This intercepts an`, `Verifies the API key if API_KEY is configured in settings.     If API_KEY is not` (+46 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `DedupManager TS`** (14 nodes): `DedupManager.ts`, `DedupManager`, `.cleanup()`, `.connect()`, `.constructor()`, `.disconnect()`, `.ensureTtl()`, `.filterNewBlockedBatch()`, `.getAllUrls()`, `.getCount()`, `.isKnown()`, `.isKnownBatch()`, `.loadFromIterator()`, `.loadFromList()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Archive Mock E2E`** (6 nodes): `Verifies that the bash script:         1. Finds the file.         2. Calls 'gclo`, `TestArchiveMockE2E`, `.setUp()`, `.tearDown()`, `.test_daemon_logic()`, `test_archive_mock_e2e.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Auth Module`** (3 nodes): `auth.py`, `Verifies the API key if API_KEY is configured in settings.     If API_KEY is not`, `verify_api_key()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Settings Config`** (3 nodes): `config.py`, `BaseSettings`, `Settings`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `pytest fixtures`** (2 nodes): `conftest.py`, `Pytest configuration and fixtures.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Robots Bypass Rationale`** (2 nodes): `robots.txt Blanket Block Bypass`, `robotsTxtGuard.ts (isBlanketBlock)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `CrawlerManager` connect `CrawlerManager Python` to `API Router and Schemas`, `CrawlerManager Tests`, `Leader Election Tests`?**
  _High betweenness centrality (0.179) - this node is a cross-community bridge._
- **Why does `IncludeInArchive` connect `API Router and Schemas` to `CrawlerManager Python`, `Migration and Enums`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Why does `log()` connect `Node.js Crawler Core` to `DedupManager TS`, `Robots.txt Guard`, `StatsManager TS`?**
  _High betweenness centrality (0.033) - this node is a cross-community bridge._
- **Are the 57 inferred relationships involving `CrawlerManager` (e.g. with `CrawlStatus` and `IncludeInArchive`) actually correct?**
  _`CrawlerManager` has 57 INFERRED edges - model-reasoned connections that need verification._
- **Are the 44 inferred relationships involving `IncludeInArchive` (e.g. with `CrawlerManager` and `Safely counts files in a directory, excluding Crawlee metadata.`) actually correct?**
  _`IncludeInArchive` has 44 INFERRED edges - model-reasoned connections that need verification._
- **Are the 45 inferred relationships involving `ReindexResponse` (e.g. with `CrawlerManager` and `Safely counts files in a directory, excluding Crawlee metadata.`) actually correct?**
  _`ReindexResponse` has 45 INFERRED edges - model-reasoned connections that need verification._
- **Are the 45 inferred relationships involving `CrawlStatus` (e.g. with `CrawlerManager` and `Safely counts files in a directory, excluding Crawlee metadata.`) actually correct?**
  _`CrawlStatus` has 45 INFERRED edges - model-reasoned connections that need verification._