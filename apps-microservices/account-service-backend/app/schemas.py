from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class AuthorizeRequest(BaseModel):
    username: str
    password: str
    client_id: str
    redirect_uri: str
    state: str
    code_challenge: str
    code_challenge_method: Literal["S256"]


class AuthorizeRedirectResponse(BaseModel):
    redirect: str


class AuthorizeConsentResponse(BaseModel):
    next: Literal["/consent"]
    consent_token: str


class TokenRequestAuthCode(BaseModel):
    grant_type: Literal["authorization_code"]
    code: str
    redirect_uri: str
    client_id: str
    client_secret: str
    code_verifier: str = Field(min_length=43, max_length=128)


class TokenRequestRefresh(BaseModel):
    grant_type: Literal["refresh_token"]
    refresh_token: str
    client_id: str
    client_secret: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int


class RevokeRequest(BaseModel):
    refresh_token: str
    client_id: str
    client_secret: str


class IntrospectRequest(BaseModel):
    token: str
    client_id: str
    client_secret: str


class IntrospectResponse(BaseModel):
    active: bool
    sub: str | None = None
    aud: str | None = None
    exp: int | None = None
    iat: int | None = None


class UserInfoResponse(BaseModel):
    sub: str
    email: str | None = None
    display_name: str | None = None


class CreateClientRequest(BaseModel):
    client_id: str
    name: str
    redirect_uris: list[HttpUrl]
    post_logout_redirect_uris: list[HttpUrl] = []
    skip_consent: bool = True


class CreateClientResponse(BaseModel):
    client_id: str
    client_secret: str
    name: str


class ClientSummary(BaseModel):
    client_id: str
    name: str
    redirect_uris: list[str]
    skip_consent: bool
    is_active: bool
    created_at: datetime


class ErrorResponse(BaseModel):
    error: str
    error_description: str | None = None
