from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class SearchRequest(BaseModel):
    filters: Optional[Dict[str, Any]] = None
    search_term: Optional[str] = None
    page: int = 1
    page_size: int = Field(default=50, ge=1, le=500)

class RequeueBulkRequest(BaseModel):
    message_ids: List[str] = Field(max_length=500)
    rate_limit_per_second: Optional[int] = None

class UpdateStatusBulkRequest(BaseModel):
    message_ids: List[str] = Field(max_length=500)

class EditAndRequeueRequest(BaseModel):
    new_payload: Dict[str, Any]

class RequeueByFilterRequest(BaseModel):
    filters: Optional[Dict[str, Any]] = None
    search_term: Optional[str] = None
    rate_limit_per_second: Optional[int] = None

class ArchiveByFilterRequest(BaseModel):
    filters: Optional[Dict[str, Any]] = None
    search_term: Optional[str] = None

class CheckUrlsBatchRequest(BaseModel):
    """Modèle pour la vérification batch d'URLs dans les DLQ."""
    urls: List[str] = Field(max_length=500)
    since_date: Optional[str] = Field(None, description="Date ISO 8601 minimale pour filtrer les messages DLQ (ex: 2026-04-15T00:00:00). Si absent, aucun filtre date.")

class AutoArchiveRuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    search_term: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None
    is_active: bool = True

class ExtractFieldRequest(BaseModel):
    """Extracts a specific field from original_payload of matching messages."""
    filters: Optional[Dict[str, Any]] = None
    search_term: Optional[str] = None
    field_path: str  # e.g. "data.fichier_source"

class UniqueErrorsRequest(BaseModel):
    """Returns unique (service_name, error_reason) combinations matching filters."""
    filters: Optional[Dict[str, Any]] = None
    search_term: Optional[str] = None

class ServiceNamesRequest(BaseModel):
    filters: Optional[Dict[str, Any]] = None