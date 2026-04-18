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
- GCS daemons use file-based signaling (.request/.done/.error markers).
- `gcs_archive_audit.py` uses `gcloud storage` CLI (no Python GCS library). Run `gcloud auth login` or activate a service account key before invoking.

## What This Provides to Other Services

- Automated dead-letter queue archival and replay infrastructure.
- GCS upload/download sidecar daemons for the crawler service.
