import os
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

class Settings:
    # Max concurrent crawls allowed per service instance.
    # Can be set via environment variable.
    MAX_CONCURRENT_CRAWLS: int = int(os.getenv("MAX_CONCURRENT_CRAWLS", "10"))

    # Base directory for storing all crawl data (logs, datasets, etc.)
    CRAWLER_STORAGE_PATH: str = os.getenv("CRAWLER_STORAGE_PATH", "/app/storage")

    # Path to the compiled Node.js crawler entry point
    CRAWLER_EXECUTABLE_PATH: str = "/app/crawler/dist/main.js"


settings = Settings()