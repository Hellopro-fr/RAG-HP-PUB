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

### Volume Mounts (docker-compose.yml)

```yaml
crawler-service:
  volumes:
    - ./crawler_archives:/app/archives
    - ./crawler_download_requests:/app/gcs-requests
    - ./crawler_download_results:/app/gcs-downloads
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

---

## Automatic Cleanup

The crawler service automatically cleans up stale files across all shared directories:

- **Cached result archives** (`/app/storage/archives/`): deleted after 24h (background task, every 1h)
- **GCS download artifacts** (`.tar.gz`, `.done`, `.error` in download results): cleaned during the same task
- **Stale download requests** (`.request` files): cleaned during the same task
- **Manual trigger**: `POST /prune-archives?max_age_hours=24` (or `delete_all=true`)

The `dead_letter/` directory is **never** auto-cleaned — it requires manual investigation.
