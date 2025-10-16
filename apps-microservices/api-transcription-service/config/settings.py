# config/settings.py
import os
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    """
    Configuration settings for the application, loaded from environment variables.
    """
    # Path to the Google Cloud JSON credentials file.
    # Ensure this file is present at the specified location.
    JSON_KEY: str = "path/to/your/google-credentials.json"
    
    # A simple token for authenticating WebSocket connections.
    # In a production environment, use a more robust authentication mechanism.
    AUTH_TOKEN: str = "your-secret-token"
    OPENAI_API_KEY: str

    class Config:
        # Specifies the file to load environment variables from.
        env_file = ".env"
        env_file_encoding = 'utf-8'

# Instantiate settings
settings = Settings()

# Set the GOOGLE_APPLICATION_CREDENTIALS environment variable dynamically.
# This is required by the Google Cloud client libraries.
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(Path(settings.JSON_KEY).resolve())
