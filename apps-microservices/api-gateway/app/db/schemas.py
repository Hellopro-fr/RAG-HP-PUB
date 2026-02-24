"""
Pydantic v2 schemas for the API Gateway token & history endpoints.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ─── Token generation ──────────────────────────────────────────────────────────


class TokenGenerateRequest(BaseModel):
    service_name: str = Field(..., description="Unique name of the microservice")


class TokenGenerateResponse(BaseModel):
    service_name: str
    refresh_token: str
    access_token: str
    access_token_expires_minutes: int
    access_token_expires_at: datetime
    created_at: datetime


# ─── Token refresh ─────────────────────────────────────────────────────────────


class TokenRefreshRequest(BaseModel):
    service_name: str = Field(..., description="Name of the service")
    refresh_token: str = Field(..., description="The opaque refresh token")


class TokenRefreshResponse(BaseModel):
    service_name: str
    access_token: str
    access_token_expires_minutes: int
    access_token_expires_at: datetime


# ─── Token revocation ─────────────────────────────────────────────────────────


class TokenRevokeRequest(BaseModel):
    service_name: str = Field(..., description="Name of the service to revoke")


class TokenRevokeResponse(BaseModel):
    service_name: str
    revoked: bool
    message: str


# ─── API Call History ──────────────────────────────────────────────────────────


class ApiCallHistoryEntry(BaseModel):
    id: int
    service_name: str
    method: str
    path: str
    status_code: int
    client_ip: str
    request_headers: Optional[str] = None  # raw JSON string
    called_at: datetime
    duration_ms: Optional[int] = None

    model_config = {"from_attributes": True}


class ApiCallHistoryList(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ApiCallHistoryEntry]


# ─── Refresh token listing ─────────────────────────────────────────────────────


class RefreshTokenEntry(BaseModel):
    id: int
    service_name: str
    token: str
    date_creation: datetime
    ip_creation: str
    est_actif: bool
    refresh: Optional[TokenRefreshRequest] = None

    model_config = {"from_attributes": True}


class RefreshTokenList(BaseModel):
    total: int
    items: List[RefreshTokenEntry]
