# Crawler Service

This project is a high-concurrency, stateful web crawling service built with FastAPI and Node.js/Crawlee. It uses Redis for persistent job state management.

## Dependencies

-   **Redis:** This service requires a running Redis instance for managing the state of crawl jobs. It is used to track running processes, handle concurrency across multiple replicas, and persist job statuses across service restarts.

## 📁 Project Structure

-   `app/`: The FastAPI application code (Python).
    -   `core/`: Core logic for managing crawler subprocesses and Redis state.
        - `crawler_manager.py`: Starts/stops Node.js processes and updates Redis.
        - `redis_service.py`: A reusable client for connecting to Redis.
    -   `router/`: API endpoint definitions.
    -   `schemas/`: Pydantic data models.
-   `crawler/`: The Node.js/TypeScript web crawler engine.
-   `storage/`: (Created at runtime via Docker volume) Persisted storage for crawl data, logs, and queues.
-   `Dockerfile`: Defines the container image for production.
-   `docker-compose.yaml`: For running the service and its Redis dependency locally.
-   `main.py`: Main entry point for the FastAPI application.
-   `requirements.txt`: Python dependencies.

## 🚀 Installation & Running

### Using Docker (Recommended)

The `docker-compose.yaml` file will start both the `crawler-service` and its required `redis` database.

1.  **Build the image:**
    ```sh
    docker-compose build
    ```

2.  **Run the services:**
    ```sh
    docker-compose up
    ```
    This will also create two persistent Docker volumes: `crawler_data` (for crawl artifacts) and `redis_data` (for job statuses). Your data will be safe across restarts.

3.  **Scale the service (e.g., to 3 instances):**
    ```sh
    docker-compose up --scale crawler-service=3
    ```

### Local Development

1.  **Initialize the Python environment:**
    ```sh
    ./init.sh 
    ```
    (Note: This is no longer present in the project but would be used for local venv setup).

2.  **Install Node.js dependencies:**
    ```sh
    cd crawler && npm install && cd ..
    ```

3.  **Install PHP dependencies for calling scripts:**
    The PHP scripts that call this service now require the `predis/predis` library. Make sure you have a `composer.json` and run `composer install`.

4.  **Run the FastAPI application:**
    ```sh
    ./run.sh
    ```
    (Note: This is no longer present in the project but would be used for local execution).

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

#### Check Service Capacity
-   `GET /crawler/capacity`
-   **Description:** A lightweight endpoint that returns the current number of running jobs across all replicas and the configured global maximum. Useful for schedulers to check before attempting to start a new job.

#### Re-index Storage
-   `POST /crawler/reindex-storage`
-   **Description:** An administrative tool to recover the system's state. This endpoint scans the persistent storage volume for "orphaned" crawl jobs (present on disk but missing from Redis) and re-creates their records in Redis. This is useful for disaster recovery if the Redis data volume is lost.