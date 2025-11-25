# Upload Daemon Guide

This guide explains how to run the `upload_daemon.sh` script to automatically upload archived crawl jobs to Google Cloud Storage.

## Prerequisites
1.  **GCloud Auth**: You must be authenticated on the host machine.
    ```bash
    gcloud auth login
    ```
2.  **Permissions**: Your account must have write access to the bucket `gs://hp-rag-crawling-data-gcp-gcs`.

## Setup (Important)
Since Docker creates volume mount points as `root`, you must change the ownership of the archives directory to your user so the script and tests can write to it.

```bash
sudo chown -R $USER:$USER apps-microservices/crawler-service/crawler_archives/
```

## Running the Daemon

### Option 1: Simple Loop (Terminal)
For testing or temporary usage, just run the script directly. It will block the terminal.
```bash
chmod +x tools/upload_daemon.sh
./tools/upload_daemon.sh
```

### Option 2: Background (Screen/Tmux)
To keep it running after you disconnect, and save logs to a file:

**Start:**
```bash
# Create logs directory if it doesn't exist
mkdir -p logs

screen -S upload_daemon
# Run script and redirect output to a log file
./tools/upload_daemon.sh > logs/daemon.log 2>&1
# Press Ctrl+A, then D to detach
```

**Monitor Logs:**
```bash
tail -f logs/daemon.log
```

**Stop:**
```bash
# Reattach to the screen session
screen -r upload_daemon
# Press Ctrl+C to stop the script
# Then type 'exit' to close the screen
```
*Alternative (Kill directly):* `screen -X -S upload_daemon quit`

### Option 3: Systemd Service (Production)
For a permanent deployment, create a systemd service.

1.  Create file `~/.config/systemd/user/crawler-upload.service`:
    ```ini
    [Unit]
    Description=Crawler Archive Upload Daemon

    [Service]
    ExecStart=%h/workspaces/RAG-HP-PUB/tools/upload_daemon.sh
    Restart=always
    RestartSec=10
    # Ensure logs directory exists or use a standard path. 
    # Systemd won't create the directory for StandardOutput automatically.
    # It is safer to use a pre-existing path or create it in ExecStartPre.
    ExecStartPre=/bin/mkdir -p %h/workspaces/RAG-HP-PUB/logs
    StandardOutput=append:%h/workspaces/RAG-HP-PUB/logs/daemon.log
    StandardError=append:%h/workspaces/RAG-HP-PUB/logs/daemon.log

    [Install]
    WantedBy=default.target
    ```
2.  Enable and start:
    ```bash
    systemctl --user enable --now crawler-upload
    ```

**Monitor Logs:**
```bash
# View live logs
tail -f logs/daemon.log
# OR via journalctl
journalctl --user -u crawler-upload -f
```

**Stop:**
```bash
systemctl --user stop crawler-upload
```
