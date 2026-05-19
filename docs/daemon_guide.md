# Crawler Daemon Guide

This guide explains how to run the upload and download daemons for archiving crawl data to/from Google Cloud Storage.

## Prerequisites
1.  **GCloud Auth**: You must be authenticated on the host machine.
    ```bash
    gcloud auth login
    ```
2.  **Permissions**: Your account must have read/write access to the bucket configured in `GCS_BUCKET_NAME` (`.env`).

## Setup (Important)
Since Docker creates volume mount points as `root`, you must change the ownership of the shared directories so the daemons can read/write to them.

```bash
sudo chown -R $USER:$USER apps-microservices/crawler-service/crawler_archives/
sudo chown -R $USER:$USER apps-microservices/crawler-service/crawler_download_requests/
sudo chown -R $USER:$USER apps-microservices/crawler-service/crawler_download_results/
```

---

## Shared Directories & Config Mapping

The daemons communicate with the crawler service via shared directories (Docker bind mounts):

| Host Path (relative) | Container Path | Config Setting | Purpose |
|---|---|---|---|
| `crawler-service/crawler_archives/` | `/app/archives` | `ARCHIVES_SHARED_PATH` | Upload staging: service writes `.tar.gz`, daemon uploads to GCS |
| `crawler-service/crawler_download_requests/` | `/app/gcs-requests` | `DOWNLOAD_REQUESTS_PATH` | Download requests: service writes `.request`, daemon picks up |
| `crawler-service/crawler_download_results/` | `/app/gcs-downloads` | `DOWNLOAD_RESULTS_PATH` | Download results: daemon writes `.tar.gz` + `.done`, service reads |
| `crawler-service/crawler_stash/` | `/app/stash` | `STASH_SHARED_PATH` | Stash staging: service writes `.tar.gz`, stash-upload daemon uploads to GCS |
| `crawler-service/crawler_stash_download_requests/` | `/app/gcs-stash-requests` | `STASH_DOWNLOAD_REQUESTS_PATH` | Stash download requests: service writes `.request`, stash-download daemon picks up |
| `crawler-service/crawler_stash_download_results/` | `/app/gcs-stash-downloads` | `STASH_DOWNLOAD_RESULTS_PATH` | Stash download results: daemon writes `.tar.gz` + `.done`, service writes `.unstash-confirmed`, daemon writes `.unstash-cleanup-done` |

### Volume Mounts (docker-compose.yml)

```yaml
crawler-service:
  volumes:
    - ./crawler_archives:/app/archives
    - ./crawler_download_requests:/app/gcs-requests
    - ./crawler_download_results:/app/gcs-downloads
    - ./crawler_stash:/app/stash
    - ./crawler_stash_download_requests:/app/gcs-stash-requests
    - ./crawler_stash_download_results:/app/gcs-stash-downloads
```

---

## Upload Daemon (`upload_daemon.sh`)

Automatically uploads archived crawl jobs to GCS. The crawler service places `.tar.gz` archives in the shared `crawler_archives/` directory, and this daemon uploads them to `gs://{bucket}/crawls/` then deletes the local file.

### Retry & Dead Letter

The daemon retries failed uploads up to **3 times** (configurable via `MAX_RETRIES`). After exhausting retries, the archive is moved to a `dead_letter/` subdirectory inside `crawler_archives/`:

```
crawler_archives/
├── 1234.tar.gz            # Pending upload
├── 1234.tar.gz.retries    # Retry counter (deleted on success or dead-letter)
└── dead_letter/
    └── 5678.tar.gz        # Failed after 3 attempts — requires manual investigation
```

**Investigating dead-letter archives:**
```bash
# List dead-letter files
ls -la apps-microservices/crawler-service/crawler_archives/dead_letter/

# Check GCS credentials
gcloud auth list

# Retry manually
gcloud storage cp crawler_archives/dead_letter/5678.tar.gz gs://{bucket}/crawls/5678.tar.gz

# If successful, remove from dead-letter
rm crawler_archives/dead_letter/5678.tar.gz
```

### Running

**Terminal (testing):**
```bash
chmod +x tools/upload_daemon.sh
./tools/upload_daemon.sh
```

**Background (Screen/Tmux):**
```bash
mkdir -p logs
screen -S upload_daemon
./tools/upload_daemon.sh > logs/upload_daemon.log 2>&1
# Press Ctrl+A, then D to detach
```

**Systemd Service (production):**

1.  Create file `~/.config/systemd/user/crawler-upload.service`:
    ```ini
    [Unit]
    Description=Crawler Archive Upload Daemon

    [Service]
    ExecStart=%h/workspaces/RAG-HP-PUB/tools/upload_daemon.sh
    Restart=always
    RestartSec=10
    ExecStartPre=/bin/mkdir -p %h/workspaces/RAG-HP-PUB/logs
    StandardOutput=append:%h/workspaces/RAG-HP-PUB/logs/upload_daemon.log
    StandardError=append:%h/workspaces/RAG-HP-PUB/logs/upload_daemon.log

    [Install]
    WantedBy=default.target
    ```
2.  Enable and start:
    ```bash
    systemctl --user enable --now crawler-upload
    ```

### Stash Upload Daemon Variant

The same `tools/upload_daemon.sh` script runs as a second systemd instance for the stash flow:

```ini
# ~/.config/systemd/user/crawler-upload-stash.service
[Unit]
Description=Crawler Stash Upload Daemon

[Service]
Environment="UPLOAD_WATCH_DIR=%h/workspaces/RAG-HP-PUB/apps-microservices/crawler-service/crawler_stash"
Environment="UPLOAD_GCS_PREFIX=stash"
ExecStart=%h/workspaces/RAG-HP-PUB/tools/upload_daemon.sh
Restart=always
RestartSec=10
StandardOutput=append:%h/workspaces/RAG-HP-PUB/logs/upload_daemon_stash.log
StandardError=append:%h/workspaces/RAG-HP-PUB/logs/upload_daemon_stash.log

[Install]
WantedBy=default.target
```

Enable: `systemctl --user enable --now crawler-upload-stash`.

---

## Download Daemon (`download_daemon.sh`)

Downloads archived crawl data from GCS on demand. When a user requests results for an archived crawl (via `GET /results/{crawl_id}`), the crawler service writes a `.request` file to the shared `crawler_download_requests/` directory. This daemon picks it up, downloads the archive from GCS, and places it in `crawler_download_results/` with a `.done` marker. The service then streams the file to the client and cleans up.

**Flow:**
1. Service writes `{crawl_id}.request` to `crawler_download_requests/`
2. Daemon downloads `gs://{bucket}/crawls/{crawl_id}.tar.gz`
3. Daemon places the archive in `crawler_download_results/` + writes `{crawl_id}.done`
4. Service detects `.done`, streams the file, then cleans up temp files

### Running

**Terminal (testing):**
```bash
chmod +x tools/download_daemon.sh
./tools/download_daemon.sh
```

**Background (Screen/Tmux):**
```bash
mkdir -p logs
screen -S download_daemon
./tools/download_daemon.sh > logs/download_daemon.log 2>&1
# Press Ctrl+A, then D to detach
```

**Systemd Service (production):**

1.  Create file `~/.config/systemd/user/crawler-download.service`:
    ```ini
    [Unit]
    Description=Crawler Archive Download Daemon

    [Service]
    ExecStart=%h/workspaces/RAG-HP-PUB/tools/download_daemon.sh
    Restart=always
    RestartSec=10
    ExecStartPre=/bin/mkdir -p %h/workspaces/RAG-HP-PUB/logs
    StandardOutput=append:%h/workspaces/RAG-HP-PUB/logs/download_daemon.log
    StandardError=append:%h/workspaces/RAG-HP-PUB/logs/download_daemon.log

    [Install]
    WantedBy=default.target
    ```
2.  Enable and start:
    ```bash
    systemctl --user enable --now crawler-download
    ```

### Stash Download Daemon Variant

A second instance of `tools/download_daemon.sh` runs for the stash unstash flow, using `DELETE_AFTER_DOWNLOAD=true` to trigger the 2-phase commit cleanup branch:

```ini
# ~/.config/systemd/user/crawler-download-stash.service
[Unit]
Description=Crawler Stash Download Daemon (2-phase commit)

[Service]
Environment="DOWNLOAD_REQUESTS_PATH=%h/workspaces/RAG-HP-PUB/apps-microservices/crawler-service/crawler_stash_download_requests"
Environment="DOWNLOAD_RESULTS_PATH=%h/workspaces/RAG-HP-PUB/apps-microservices/crawler-service/crawler_stash_download_results"
Environment="DOWNLOAD_GCS_PREFIX=stash"
Environment="DELETE_AFTER_DOWNLOAD=true"
ExecStart=%h/workspaces/RAG-HP-PUB/tools/download_daemon.sh
Restart=always
RestartSec=10
StandardOutput=append:%h/workspaces/RAG-HP-PUB/logs/download_daemon_stash.log
StandardError=append:%h/workspaces/RAG-HP-PUB/logs/download_daemon_stash.log

[Install]
WantedBy=default.target
```

Enable: `systemctl --user enable --now crawler-download-stash`.

**2-phase commit semantics** (triggered by `POST /stash/{crawl_id}` and `POST /unstash/{crawl_id}` on the crawler service):
- After the service extracts the downloaded tar.gz, it writes `{crawl_id}.unstash-confirmed`.
- This daemon polls `.unstash-confirmed`, runs `gcloud storage rm` on the GCS object, and on success writes `{crawl_id}.unstash-cleanup-done`.
- On `gcloud rm` failure the daemon retains the `.unstash-confirmed` marker for retry on the next iteration + logs a WARNING.
- The service polls for `.unstash-cleanup-done` within `UNSTASH_CLEANUP_GRACE_SECONDS` (default 30s). Past the grace window, the service returns `gcs_cleanup_status="deferred"` and increments the Prometheus `unstash_gcs_orphan_total` counter.

---

## Monitoring & Troubleshooting

**Monitor logs (any daemon):**
```bash
tail -f logs/upload_daemon.log
tail -f logs/download_daemon.log
# OR via journalctl
journalctl --user -u crawler-upload -f
journalctl --user -u crawler-download -f
```

**Stop:**
```bash
# Screen
screen -X -S upload_daemon quit
screen -X -S download_daemon quit

# Systemd
systemctl --user stop crawler-upload
systemctl --user stop crawler-download
```

**Timeout issues (download daemon):**
If `GET /results/{crawl_id}` returns a 504 timeout for archived crawls, check that:
1. The download daemon is running (`ps aux | grep download_daemon`)
2. GCS credentials are valid (`gcloud auth list`)
3. The archive exists in GCS (`gcloud storage ls gs://{bucket}/crawls/{crawl_id}.tar.gz`)
4. The timeout is sufficient (default: 300s, configurable via `GCS_DOWNLOAD_TIMEOUT_SECONDS`)

**Upload failures going to dead-letter:**
1. Check `dead_letter/` directory for accumulated archives
2. Review upload daemon logs for GCS error messages
3. Verify GCS bucket exists and credentials have write permission
4. Retry manually with `gcloud storage cp` then remove from `dead_letter/`

**Orphan GCS objects (stash flow):**
If `POST /unstash/{crawl_id}` returns `gcs_cleanup_status="deferred"`, the local data was restored but the GCS source object was not deleted within `UNSTASH_CLEANUP_GRACE_SECONDS`. Prometheus counter `unstash_gcs_orphan_total` is incremented. To investigate:
1. Check the stash-download daemon is alive (`systemctl --user status crawler-download-stash`)
2. Look for WARNING messages in `logs/download_daemon_stash.log` about `gcloud rm` failures
3. List orphans: `gcloud storage ls gs://{bucket}/stash/` and cross-reference with Redis `crawl_job:*` keys that no longer have `stashed_at`
4. Delete confirmed orphans manually: `gcloud storage rm gs://{bucket}/stash/{crawl_id}.tar.gz`

---

## Automatic Cleanup

The crawler service automatically cleans up stale files across all shared directories:

- **Cached result archives** (`/app/storage/archives/`): deleted after 24h (background task, every 1h)
- **GCS download artifacts** (`.tar.gz`, `.done`, `.error` in download results): cleaned during the same task
- **Stale download requests** (`.request` files): cleaned during the same task
- **Manual trigger**: `POST /prune-archives?max_age_hours=24` (or `delete_all=true`)

The `dead_letter/` directory is **never** auto-cleaned — it requires manual investigation.
