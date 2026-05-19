# Crawler Service

This project is a high-concurrency, stateful web crawling service built with FastAPI and Node.js/Crawlee. It uses an external Redis instance for persistent job state management and Nginx as a reverse proxy for scalability.

## Dependencies

-   **External Redis:** This service requires a connection to a running Redis instance for managing the state of crawl jobs. It is used to track running processes, handle concurrency across multiple replicas, and persist job statuses across service restarts. Connection details must be provided in the project's root `.env` file (`REDIS_URL`).

## 📁 Project Structure

-   `app/`: The FastAPI application code (Python).
    -   `core/`: Core logic for managing crawler subprocesses and Redis state.
        - `crawler_manager.py`: Starts/stops Node.js processes and updates Redis.
    -   `router/`: API endpoint definitions.
    -   `schemas/`: Pydantic data models.
-   `crawler/`: The Node.js/TypeScript web crawler engine.
-   `docker-compose.yaml`: For running the service and its reverse proxy.
-   `Dockerfile`: Defines the multi-stage container image for production.
-   `nginx.conf`: Nginx configuration file that acts as a reverse proxy and load balancer for the crawler service replicas.
-   `scale_crawlers.sh`: A helper script for correctly scaling the number of crawler service instances.
-   `main.py`: Main entry point for the FastAPI application.
-   `requirements.txt`: Python dependencies.

## 🚀 Installation & Running

The services are designed to be run as a group using Docker Compose profiles. The `crawling` profile includes the `crawler-service` and the `reverse-proxy`.

1.  **Start the Services:**
    To start the entire crawling system (defaulting to 3 crawler instances), run:
    ```sh
    docker-compose --profile crawling up -d
    ```
    This will create one persistent Docker volume: `crawler_data` (for crawl artifacts). Job statuses are persisted in the external Redis instance.

2.  **Scaling the Service (Recommended Method):**
    A helper script, `scale_crawlers.sh`, is provided to handle scaling safely. It automatically calculates the `MAX_GLOBAL_CONCURRENT_CRAWLS` environment variable, which is crucial for the system's concurrency logic.

    **Prerequisites for scaling script:**
    -   `redis-cli` must be installed on your host machine.
    -   Your root `.env` file must contain `REDIS_HOST`, `REDIS_PORT`, and `REDIS_SECRET` for the script to connect to the external Redis.

    First, make the script executable:
    ```sh
    chmod +x apps-microservices/crawler-service/scale_crawlers.sh
    ```

    Then, run the script with the desired number of replicas.
    ```sh
    # Example: Scale to 5 instances
    ./apps-microservices/crawler-service/scale_crawlers.sh 5

    # Example: Scale back down to 2 instances
    ./apps-microservices/crawler-service/scale_crawlers.sh 2
    ```

3.  **Stopping the Services:**
    To stop all services associated with the crawling profile, run:
    ```sh
    docker-compose --profile crawling down
    ```

## ⚙️ API Usage

The full API documentation is available via Swagger UI at `http://localhost:8503/docs` when the service is running.

---

### Core Endpoints

#### Start a Crawl
-   `POST /crawler/start`
-   **Description:** Starts or resumes a web crawling job. A job is uniquely identified by the `id` field in the payload. If a job with the same `id` is already running, a `409 Conflict` error will be returned. Supports success and failure webhooks.
-   **Body:** `CrawlRequest` schema.

#### Stop a Crawl
-   `POST /crawler/stop/{crawl_id}`
-   **Description:** Sends a stop signal to a currently running crawl job.

#### Get All Crawl Statuses
-   `GET /crawler/status`
-   **Description:** Returns a global list of all crawl jobs and their current status known to the system (by querying Redis).

#### Get Status for a Specific Crawl
-   `GET /crawler/status/{crawl_id}`
-   **Description:** Gets the detailed status of a specific crawl job, including real-time counts of successful, failed, and "not French" URLs.

#### Download Crawl Results
-   `GET /crawler/results/{crawl_id}`
-   **Description:** Downloads a custom `.tar.gz` archive of a completed crawl job. The contents of the archive can be specified with the `include` query parameter.
-   **Query Parameters:**
    -   `include` (required, can be provided multiple times): Specifies which components to include in the archive.
    -   **Possible values:** `dataset`, `dataset_nfr`, `dataset_error`, `request_queues`, `request_urls`, `miscellaneous`.
-   **Example:** `/crawler/results/domaine_123?include=dataset&include=dataset_error`

---

### Administrative Endpoints

#### Stash a Crawl (Free Disk)
-   `POST /stash/{crawl_id}` (mounted at `/crawler/stash/{crawl_id}`)
-   **Description:** Move a terminal crawl's storage to GCS under `stash/` and delete local data. Use for crawls under investigation that occupy disk space. The crawl must be in `failed`/`stopped`/`finished` status and not already stashed/archived.
-   **Response:** 202 Accepted with `StashResponse` (`crawl_id`, `status="stashing"`, `stash_path`, `stashed_at`).

#### Unstash a Crawl
-   `POST /crawler/unstash/{crawl_id}`
-   **Description:** Restore a stashed crawl's data from GCS to local storage. Synchronous — waits for download daemon, extracts, and triggers 2-phase commit GCS cleanup. Bounded by `UNSTASH_TIMEOUT_SECONDS` (default 300s).
-   **Response:** 200 OK with `UnstashResponse` (`crawl_id`, `status="unstashed"`, `restored_to`, `elapsed_seconds`, `gcs_cleanup_status` = `"cleaned"` or `"deferred"`).

#### Check Service Capacity
-   `GET /crawler/capacity`
-   **Description:** A lightweight endpoint that returns the current number of running jobs across all replicas and the configured global maximum. Useful for schedulers to check before attempting to start a new job.

#### Re-index Storage
-   `POST /crawler/reindex-storage`
-   **Description:** An administrative tool to recover the system's state. This endpoint scans the persistent storage volume for "orphaned" crawl jobs (present on disk but missing from Redis) and re-creates their records in Redis. This is useful for disaster recovery if the Redis data is lost.