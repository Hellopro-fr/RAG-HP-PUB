import base64
import secrets

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from app.db.models import SigningKey


def _new_kid() -> str:
    return secrets.token_urlsafe(12)


def _generate_keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def encrypt_private_pem(pem: str, encryption_key: str) -> str:
    return Fernet(encryption_key.encode()).encrypt(pem.encode()).decode()


def decrypt_private_pem(token: str, encryption_key: str) -> str:
    return Fernet(encryption_key.encode()).decrypt(token.encode()).decode()


async def ensure_signing_key(*, encryption_key: str) -> SigningKey:
    existing = await SigningKey.filter(is_active=True).first()
    if existing:
        return existing
    private_pem, public_pem = _generate_keypair()
    enc = encrypt_private_pem(private_pem, encryption_key)
    return await SigningKey.create(
        kid=_new_kid(),
        private_pem_encrypted=enc,
        public_pem=public_pem,
        is_active=True,
    )


async def get_active_signing_key() -> SigningKey:
    key = await SigningKey.filter(is_active=True).first()
    if not key:
        raise RuntimeError("No active signing key. Call ensure_signing_key first.")
    return key


def _b64url_uint(n: int) -> str:
    byte_len = (n.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(n.to_bytes(byte_len, "big")).rstrip(b"=").decode()


def _public_jwk_from_pem(public_pem: str, kid: str) -> dict:
    pub: RSAPublicKey = serialization.load_pem_public_key(public_pem.encode())
    numbers = pub.public_numbers()
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": _b64url_uint(numbers.n),
        "e": _b64url_uint(numbers.e),
    }


async def jwks_response() -> dict:
    keys = await SigningKey.all().order_by("-created_at")
    return {"keys": [_public_jwk_from_pem(k.public_pem, k.kid) for k in keys]}
