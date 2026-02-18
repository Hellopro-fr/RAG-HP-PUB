import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Redis Configuration
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379")
    
    # Processing Limits
    MAX_CONCURRENT_JOBS: int = int(os.getenv("MAX_CONCURRENT_JOBS", "5"))
    
settings = Settings()