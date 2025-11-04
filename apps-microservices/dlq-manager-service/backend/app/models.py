from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class SearchRequest(BaseModel):
    filters: Optional[Dict[str, Any]] = None
    search_term: Optional[str] = None
    page: int = 1
    page_size: int = 50

class RequeueBulkRequest(BaseModel):
    message_ids: List[str]
    rate_limit_per_second: Optional[int] = None

class UpdateStatusBulkRequest(BaseModel):
    message_ids: List[str]

class EditAndRequeueRequest(BaseModel):
    new_payload: Dict[str, Any]

class RequeueByFilterRequest(BaseModel):
    filters: Optional[Dict[str, Any]] = None
    search_term: Optional[str] = None
    rate_limit_per_second: Optional[int] = None