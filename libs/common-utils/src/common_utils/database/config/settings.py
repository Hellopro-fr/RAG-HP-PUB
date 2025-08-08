import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


class Configuration:
    ZILLIZ_URI: Optional[str] = os.getenv("ZILLIZ_URI")
    ZILLIZ_API_KEY: Optional[str] = os.getenv("ZILLIZ_API_KEY")
    MODEL: Optional[str] = os.getenv("MODEL") or "dangvantuan/sentence-camembert-large"
    RECREATE_COLLECTIONS: bool = False

settings = Configuration()