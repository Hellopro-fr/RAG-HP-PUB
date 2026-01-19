import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


class Configuration:
    QDRANT_HOST_URL: Optional[str] = os.environ.get("QDRANT_HOST_URL")
    QDRANT_API_KEY: Optional[str] = os.environ.get("QDRANT_API_KEY")
    QDRANT_PORT: Optional[int] = os.environ.get("QDRANT_PORT")

    ZILLIZ_URI: Optional[str] = os.environ.get("ZILLIZ_URI")
    ZILLIZ_API_KEY: Optional[str] = os.environ.get("ZILLIZ_API_KEY")
    ZILLIZ_PORT: Optional[int] = os.environ.get("ZILLIZ_PORT")
    ZILLIS_USER: Optional[str] = os.environ.get("ZILLIS_USER")
    ZILLIS_PASSWORD: Optional[str] = os.environ.get("ZILLIS_PASSWORD")
    
    M_PARAMS: Optional[int] = int(os.environ.get("M_PARAMS") or 32)
    EF_PARAMS: Optional[int] = int(os.environ.get("EF_PARAMS") or 300)
    
    MODEL: Optional[str] = os.environ.get("MODEL") or "dangvantuan/sentence-camembert-large"
    RECREATE_COLLECTIONS: bool = False

settings = Configuration()