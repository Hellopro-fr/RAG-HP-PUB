from tortoise import fields
from tortoise.models import Model


class OAuthClient(Model):
    id = fields.UUIDField(pk=True)
    client_id = fields.CharField(max_length=64, unique=True, index=True)
    client_secret_hash = fields.CharField(max_length=255)
    name = fields.CharField(max_length=128)
    redirect_uris = fields.JSONField()
    post_logout_redirect_uris = fields.JSONField(default=list)
    skip_consent = fields.BooleanField(default=True)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "oauth_client"


class AuthorizationCode(Model):
    code_hash = fields.CharField(max_length=64, pk=True)
    client_id = fields.CharField(max_length=64, index=True)
    sub = fields.CharField(max_length=128)
    code_challenge = fields.CharField(max_length=255)
    code_challenge_method = fields.CharField(max_length=10)
    redirect_uri = fields.CharField(max_length=512)
    issued_at = fields.DatetimeField(auto_now_add=True)
    expires_at = fields.DatetimeField(index=True)
    consumed_at = fields.DatetimeField(null=True)
    user_email = fields.CharField(max_length=255, null=True)
    user_display_name = fields.CharField(max_length=255, null=True)

    class Meta:
        table = "authorization_code"


class RefreshToken(Model):
    id = fields.UUIDField(pk=True)
    token_hash = fields.CharField(max_length=64, unique=True, index=True)
    client_id = fields.CharField(max_length=64, index=True)
    sub = fields.CharField(max_length=128, index=True)
    user_email = fields.CharField(max_length=255, null=True)
    user_display_name = fields.CharField(max_length=255, null=True)
    issued_at = fields.DatetimeField(auto_now_add=True)
    expires_at = fields.DatetimeField(index=True)
    revoked_at = fields.DatetimeField(null=True)
    rotated_from_id = fields.UUIDField(null=True)
    user_agent = fields.CharField(max_length=255, null=True)
    ip = fields.CharField(max_length=45, null=True)

    class Meta:
        table = "refresh_token"


class SigningKey(Model):
    kid = fields.CharField(max_length=64, pk=True)
    private_pem_encrypted = fields.TextField()
    public_pem = fields.TextField()
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    rotated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "signing_key"


class LoginSession(Model):
    """One-shot, short-lived handoff token for the simplified login flow.

    Issued by POST /login after credential validation, consumed by
    POST /sessions/exchange. Bound to a single OAuthClient (service)
    so that interception by another service is harmless.
    """

    token_hash = fields.CharField(max_length=64, pk=True)
    client_id = fields.CharField(max_length=64, index=True)
    sub = fields.CharField(max_length=128)
    user_email = fields.CharField(max_length=255, null=True)
    user_display_name = fields.CharField(max_length=255, null=True)
    next_path = fields.CharField(max_length=512, default="/")
    issued_at = fields.DatetimeField(auto_now_add=True)
    expires_at = fields.DatetimeField(index=True)
    consumed_at = fields.DatetimeField(null=True)

    class Meta:
        table = "login_session"
