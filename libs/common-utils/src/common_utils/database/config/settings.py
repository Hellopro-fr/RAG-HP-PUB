import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


class Configuration:
    ZILLIZ_URI: Optional[str] = os.environ.get("ZILLIZ_URI")
    ZILLIZ_API_KEY: Optional[str] = os.environ.get("ZILLIZ_API_KEY")
    MODEL: Optional[str] = os.environ.get("MODEL") or "dangvantuan/sentence-camembert-large"
    RECREATE_COLLECTIONS: bool = False

settings = Configuration()