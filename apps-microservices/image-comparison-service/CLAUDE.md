# image-comparison-service

FastAPI microservice for batch image similarity detection using perceptual hashing and structural comparison.

## Tech Stack

- Python 3.11
- FastAPI + uvicorn on port **8504**
- OpenCV (headless), imagehash, scikit-image, Pillow
- Redis for job state management
- httpx for image fetching

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/image-comparison-service/Dockerfile .
  ```

## Folder Structure

```
image-comparison-service/
  main.py                        # FastAPI app, includes comparator router
  app/
    router/comparator.py         # API endpoints (start, status, results, jobs, capacity)
    core/
      job_manager.py             # Job lifecycle, Redis state, sync/async execution
      image_processor.py         # Image comparison algorithms
      config.py                  # Configuration
    schemas/comparator.py        # Pydantic models (CompareRequest, JobStatus, etc.)
  scale_comparators.sh           # Script for horizontal scaling
  requirements.txt
  Dockerfile
```

## API Endpoints (port 8504)

| Method | Path | Description |
|---|---|---|
| GET | `/` | Health check |
| POST | `/start` | Start comparison job (sync or async) |
| GET | `/status/{job_id}` | Check job status |
| GET | `/results/{job_id}` | Get comparison results |
| GET | `/jobs` | List all jobs |
| GET | `/capacity` | Check global/local capacity |

## Conventions

- Sync mode: returns 503 when local capacity full (triggers Nginx failover to another replica).
- Async mode: always queues the job, returns job ID.
- Redis stores job state for cross-instance visibility.
- Designed for horizontal scaling behind Nginx load balancer.

## Dependencies on Other Services

- **Redis** (job state storage)
