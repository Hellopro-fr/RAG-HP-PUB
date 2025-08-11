import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


class Configuration:
    QDRANT_URI: Optional[str] = os.environ.get("QDRANT_URI")
    QDRANT_API_KEY: Optional[str] = os.environ.get("QDRANT_API_KEY")
    MODEL: Optional[str] = os.environ.get("MODEL") or "dangvantuan/sentence-camembert-large"
    RECREATE_COLLECTIONS: bool = False

settings = Configuration()