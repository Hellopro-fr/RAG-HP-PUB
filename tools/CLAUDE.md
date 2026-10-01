# tools

Operational scripts for DLQ management and S3/GCS file transfers.

## Tech Stack

- Python 3.10 (DLQ scripts): pika (RabbitMQ), elasticsearch
- Bash (upload/download daemons): gcloud CLI
- Docker (containerized DLQ archiver)

## Run

```bash
# DLQ Archiver (long-running consumer)
python tools/dlq_archiver.py

# DLQ Requeuer (one-shot or watch mode)
python tools/dlq_requeuer.py --filter "service_name.keyword:my-service" --dry-run
python tools/dlq_requeuer.py --watch --interval 60

# GCS daemons
bash tools/upload_daemon.sh
bash tools/download_daemon.sh

# GCS Archive Audit (one-shot, requires gcloud auth login first)
python tools/gcs_archive_audit.py --bucket <name> --output report.json
python tools/gcs_archive_audit.py --bucket <name> --name-only            # fast mode: names only
python tools/gcs_archive_audit.py --bucket <name> --quarantine quarantine/ --yes   # move bad archives
python tools/gcs_archive_audit.py --bucket <name> --delete --yes                    # delete bad archives

# Recover from a faulty prior audit (move quarantined archives back to crawls/):
python tools/gcs_archive_audit.py --bucket <name> --restore-from-quarantine crawls-quarantine/ --yes
# Then re-audit so the fixed classifier re-quarantines only the real bad ones:
python tools/gcs_archive_audit.py --bucket <name> --quarantine crawls-quarantine/ --yes --output corrected_report.json
```

## File Inventory

```
dlq_archiver.py      # Consumes RabbitMQ DLQ queues, archives messages to Elasticsearch
                     # Handles mapping conflicts with fallback serialization
dlq_requeuer.py      # Re-publishes archived DLQ messages back to original exchanges
                     # Supports filters, date ranges, dry-run, and watch mode
es_mapping.py        # Elasticsearch index mapping for the failed_messages_archive index
upload_daemon.sh     # Polls crawler_archives/ for .tar.gz, uploads to GCS, deletes local
download_daemon.sh     # Polls for .request files, downloads from GCS, writes .done marker
gcs_archive_audit.py   # Audits GCS archives for corruption/incompleteness, optional --delete/--quarantine
requirements.txt     # pika, elasticsearch
Dockerfile           # Python 3.10-slim image for DLQ archiver/requeuer
```

## Conventions

- Environment variables for all connection strings: `RABBITMQ_URL`, `ELASTICSEARCH_URL`, `GCS_BUCKET_NAME`.
- DLQ archiver uses batch inserts (size 50, timeout 5s) with individual ACK/NACK.
- Requeuer marks processed messages with `status: "Re-queued"` in Elasticsearch.
- GCS daemons use file-based signaling (.request/.done/.error markers, plus .unstash-confirmed/.unstash-cleanup-done for the 2-phase commit on the stash flow).
- Daemon env vars (defaults preserve current archive-flow behavior):
  - Upload: `UPLOAD_WATCH_DIR` (default `crawler_archives/`), `UPLOAD_GCS_PREFIX` (default `crawls`), `UPLOAD_DEAD_LETTER_SUBDIR` (default `dead_letter`).
  - Download: `DOWNLOAD_REQUESTS_PATH`, `DOWNLOAD_RESULTS_PATH`, `DOWNLOAD_GCS_PREFIX` (default `crawls`), `DELETE_AFTER_DOWNLOAD` (default `false`, set `true` for the stash unstash flow).
  - Move (stash→archive, auto-stash workflow): `ENABLE_MOVE` (default `false`, set `true` for the move-flow instance), `MOVE_REQUESTS_PATH`, `MOVE_RESULTS_PATH`, `MOVE_SOURCE_PREFIX` (default `stash`), `MOVE_TARGET_PREFIX` (default `crawls`). When `ENABLE_MOVE=true`, `download_daemon.sh` runs a third loop (`process_move_requests`) that consumes `{id}.move-request` and does `gcloud storage mv {SOURCE_PREFIX}/{id}.tar.gz → {TARGET_PREFIX}/{id}.tar.gz` (same-bucket server-side rewrite), writing `{id}.move-done` or `{id}.move-error`. Idempotent (target-present = done). Run it as a dedicated `download_daemon.sh` invocation with `ENABLE_MOVE=true` and the `MOVE_*` paths set. Marker family: `.move-request`/`.move-done`/`.move-error`. Spec: `docs/superpowers/specs/2026-06-01-auto-stash-unstash-workflow-design.md`.
- Same env var names align with the crawler-service Python `Settings` (`apps-microservices/crawler-service/app/core/config.py`), so a single `.env` entry per direction configures both layers. Defaults point at `apps-microservices/crawler-service/crawler_download_{requests,results}` matching the `docker-compose.yml` bind source for the crawler-service container.
- `gcs_archive_audit.py` uses `gcloud storage` CLI (no Python GCS library). Run `gcloud auth login` or activate a service account key before invoking.

## What This Provides to Other Services

- Automated dead-letter queue archival and replay infrastructure.
- GCS upload/download sidecar daemons for the crawler service.
