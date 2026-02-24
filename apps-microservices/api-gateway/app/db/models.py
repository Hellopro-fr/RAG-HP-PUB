"""
Tortoise-ORM models for the API Gateway security layer.

Tables:
    info_refresh_token — one refresh token per microservice
    info_access_token  — access tokens linked to a refresh token
    api_call_history   — audit log of all proxied calls
"""

from tortoise import fields
from tortoise.models import Model


class InfoRefreshToken(Model):
    """
    Stores ONE active refresh token per microservice.

    When a service starts, a refresh token is auto-created if none exists.
    The `nom_service` + `est_actif` pair is used to look up the current token.
    """

    id = fields.IntField(pk=True)
    nom_service = fields.CharField(max_length=128, index=True)
    token = fields.CharField(max_length=768, index=True)
    date_creation = fields.DatetimeField(auto_now_add=True)
    ip_creation = fields.CharField(max_length=64, default="system")
    est_actif = fields.BooleanField(default=True, index=True)

    # Reverse relation to access tokens
    access_tokens: fields.ReverseRelation["InfoAccessToken"]

    class Meta:
        table = "info_refresh_token"

    def __str__(self) -> str:
        return f"InfoRefreshToken(service={self.nom_service}, active={self.est_actif})"


class InfoAccessToken(Model):
    """
    Access tokens linked to a parent refresh token via FK.

    Only the 10 most recently created, non-expired access tokens are kept active
    per refresh token.
    """

    id = fields.IntField(pk=True)
    id_refresh_token = fields.ForeignKeyField(
        "models.InfoRefreshToken",
        related_name="access_tokens",
        on_delete=fields.CASCADE,
        index=True,
    )
    token = fields.CharField(max_length=768, index=True)
    date_creation = fields.DatetimeField(auto_now_add=True)
    date_expiration = fields.DatetimeField()
    est_actif = fields.BooleanField(default=True, index=True)

    class Meta:
        table = "info_access_token"

    def __str__(self) -> str:
        return (
            f"InfoAccessToken(id={self.id}, "
            f"refresh_id={self.id_refresh_token_id}, "
            f"active={self.est_actif})"
        )


class ApiCallHistory(Model):
    """
    Audit log: one row per proxied API call passing through the gateway.
    """

    id = fields.IntField(pk=True)
    service_name = fields.CharField(max_length=128, index=True)
    method = fields.CharField(max_length=10)
    path = fields.TextField()
    status_code = fields.IntField()
    client_ip = fields.CharField(max_length=64)
    # JSON-serialised dict of all incoming request headers
    request_headers = fields.TextField(null=True)
    called_at = fields.DatetimeField(auto_now_add=True, index=True)
    # wall-clock duration of the upstream call in milliseconds
    duration_ms = fields.IntField(null=True)

    class Meta:
        table = "api_call_history"

    def __str__(self) -> str:
        return (
            f"ApiCallHistory("
            f"service={self.service_name}, "
            f"method={self.method}, "
            f"path={self.path}, "
            f"status={self.status_code})"
        )
