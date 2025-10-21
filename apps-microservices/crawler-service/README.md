# Crawler Service

This project is a high-concurrency web crawling service built with FastAPI and Node.js/Crawlee.

## 📁 Project Structure

-   `app/`: The FastAPI application code (Python).
    -   `core/`: Core logic for managing crawler subprocesses.
    -   `router/`: API endpoint definitions.
    -   `schemas/`: Pydantic data models.
-   `crawler/`: The Node.js/TypeScript web crawler engine.
-   `storage/`: (Created at runtime) Persisted storage for crawl data, logs, and queues.
-   `Dockerfile`: Defines the container image for production.
-   `docker-compose.yaml`: For running the service locally.
-   `main.py`: Main entry point for the FastAPI application.
-   `requirements.txt`: Python dependencies.
-   `run.sh`: Script for local development.

## 🚀 Installation & Running

### Using Docker (Recommended)

1.  **Build the image:**
    ```sh
    docker-compose build
    ```

2.  **Run the service:**
    ```sh
    docker-compose up
    ```

3.  **Scale the service (e.g., to 3 instances):**
    ```sh
    docker-compose up --scale crawler-service=3
    ```

### Local Development

1.  **Initialize the Python environment:**
    ```sh
    ./init.sh
    ```

2.  **Install Node.js dependencies for the crawler:**
    ```sh
    cd crawler && npm install && cd ..
    ```

3.  **Run the FastAPI application:**
    ```sh
    ./run.sh
    ```

## ⚙️ API Usage

The API documentation is available at `http://localhost:8503/docs` when the service is running.

-   **Start a crawl:** `POST /crawler/start`
-   **Stop a crawl:** `POST /crawler/stop/{crawl_id}`
-   **Get status:** `GET /crawler/status`
-   **Get results:** `GET /crawler/results/{crawl_id}`