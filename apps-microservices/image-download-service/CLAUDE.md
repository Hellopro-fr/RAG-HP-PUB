# image-download-service

FastAPI + RabbitMQ service that downloads, processes, and archives product images with delta sync support.

## Tech Stack

- Python 3.11, asyncio
- FastAPI + uvicorn on port **8505**
- RabbitMQ (aio-pika) consumer for download jobs
- Pillow, pyvips for image processing
- aiohttp, aiofiles
- Shared libs: `common-utils`

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/image-download-service/Dockerfile .
  ```

## Folder Structure

```
image-download-service/
  app/
    main.py                   # FastAPI app with RabbitMQ consumer lifecycle
    core/
      downloader.py           # Image download logic
      image_processor.py      # Image transformation (resize, format)
      archiver.py             # Archive creation (full/delta) + sync tracking
      ratelimiter.py          # Rate limiting for downloads
      nfs_lock.py             # NFS file locking
    messaging/
      consumer.py             # RabbitMQ consumer for download jobs
  requirements.txt
  Dockerfile
```

## API Endpoints (port 8505)

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/domains` | List all domains with images |
| GET | `/domains/recent` | Domains with recent activity |
| GET | `/domains/unsynced` | Domains with unsynced products |
| GET | `/domains/{domain}/status` | Sync status for a domain |
| POST | `/archive/delta/{domain}` | Create delta archive (new products only) |
| POST | `/archive/full/{domain}` | Create full archive |
| GET | `/archives` | List all archives |
| POST | `/archives/cleanup` | Delete old archives |
| POST | `/sync/{domain}` | Mark products as synced |
| GET | `/sync/{domain}/errors` | Get download errors |
| GET | `/sync/{domain}/pending` | Get unsynced products |

## Conventions

- Images stored at `/data/images/{domain}/produit-{2|3}/{shard}/{shard}/{shard}/`.
- Delta sync: tracks synced vs unsynced products per domain.
- NFS lock for concurrent access safety.

## Dependencies on Other Services

- **RabbitMQ** (consumer for download triggers)
- **image-cdn-service** (serves the same volume read-only)
