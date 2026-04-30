import hashlib

from app.core.security import (
    generate_random_token,
    hash_secret,
    sha256_hex,
    verify_pkce,
    verify_secret,
)


def test_sha256_hex_matches_stdlib():
    assert sha256_hex("hello") == hashlib.sha256(b"hello").hexdigest()


def test_hash_and_verify_secret_roundtrip():
    h = hash_secret("supersecret")
    assert verify_secret("supersecret", h) is True
    assert verify_secret("nope", h) is False


def test_generate_random_token_length():
    t = generate_random_token(32)
    assert len(t) >= 32


def test_verify_pkce_s256_ok():
    import base64

    verifier = "a" * 64
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert verify_pkce(verifier, challenge, "S256") is True


def test_verify_pkce_rejects_plain_method():
    assert verify_pkce("v", "v", "plain") is False


def test_verify_pkce_wrong_verifier():
    assert verify_pkce("wrong", "any-challenge", "S256") is False
