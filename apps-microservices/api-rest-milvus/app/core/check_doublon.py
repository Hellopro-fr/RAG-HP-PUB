from app.schemas.check_doublon_shemas import SearchRequest
from pymilvus import connections, Collection, utility

from app.core.credentials import settings

from common_utils.database.MilvusProduitCrud import MilvusProduitsCrud
from common_utils.database.MilvusFournisseursCrud import MilvusFournisseursCrud

import logging
import requests
import httpx


logger = logging.getLogger(__name__)