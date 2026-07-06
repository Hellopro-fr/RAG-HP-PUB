import base64, hashlib
import jwt
import pytest
from hellopro_auth.oauth import (
    gen_pkce, random_state, build_authorize_url, exchange_code, verify_and_extract,
)


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def test_pkce_challenge():
    p = gen_pkce()
    assert p.challenge == _b64url(hashlib.sha256(p.verifier.encode()).digest())
    assert "=" not in p.verifier


def test_authorize_url():
    url = build_authorize_url(
        public_url="http://localhost:8601", client_id="cid",
        redirect_uri="http://localhost:3551/auth/callback", challenge="chal", state="st",
    )
    assert url.startswith("http://localhost:8601/authorize?")
    assert "code_challenge_method=S256" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A3551%2Fauth%2Fcallback" in url


def test_exchange_code(monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 200
        def json(self):
            return {"access_token": "tok"}

    def fake_post(url, data=None, auth=None, headers=None, timeout=None):
        captured.update(url=url, data=data, auth=auth)
        return FakeResp()

    monkeypatch.setattr("hellopro_auth.oauth.httpx.post", fake_post)
    out = exchange_code(
        base_url="http://acct:8600", client_id="cid", client_secret="sec",
        code="c", redirect_uri="r", verifier="v",
    )
    assert out["access_token"] == "tok"
    assert captured["url"] == "http://acct:8600/token"
    assert captured["auth"] == ("cid", "sec")
    assert captured["data"]["grant_type"] == "authorization_code"


def test_exchange_code_non_200(monkeypatch):
    class FakeResp:
        status_code = 401
    monkeypatch.setattr("hellopro_auth.oauth.httpx.post", lambda *a, **k: FakeResp())
    with pytest.raises(RuntimeError, match="401"):
        exchange_code(base_url="b", client_id="c", client_secret="s", code="x", redirect_uri="r", verifier="v")


def test_verify_and_extract():
    tok = jwt.encode({"sub": "alice@hp.fr"}, "secret", algorithm="HS256")
    assert verify_and_extract(tok, "secret").email == "alice@hp.fr"
    with pytest.raises(Exception):
        verify_and_extract(jwt.encode({"sub": "a@hp.fr"}, "wrong", algorithm="HS256"), "secret")
