import os
from typing import Optional
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

class Settings:
    # Max concurrent crawls allowed PER service instance.
    # Can be set via environment variable.
    MAX_CONCURRENT_CRAWLS: int = int(os.getenv("MAX_CONCURRENT_CRAWLS", "10"))

    # A sensible fallback for the global max crawls if the Redis key is missing.
    # This should ideally be set to the default number of replicas.
    DEFAULT_MAX_GLOBAL_CRAWLS: int = int(os.getenv("DEFAULT_MAX_GLOBAL_CRAWLS", "3"))

    # Interval in seconds for the background task to reconcile the running jobs counter.
    RECONCILIATION_INTERVAL_SECONDS: int = int(os.getenv("RECONCILIATION_INTERVAL_SECONDS", "300"))

    # Base directory for storing all crawl data (logs, datasets, etc.)
    CRAWLER_STORAGE_PATH: str = os.getenv("CRAWLER_STORAGE_PATH", "/app/storage")

    # Path to the compiled Node.js crawler entry point
    CRAWLER_EXECUTABLE_PATH: str = "/app/crawler/dist/main.js"


settings = Settings()