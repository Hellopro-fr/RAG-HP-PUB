import hellopro_auth.flow as flow
from hellopro_auth.config import AuthConfig
from hellopro_auth.oauth import Identity


def _cfg(**over):
    base = dict(
        account_public_url="http://localhost:8601", account_base_url="http://acct:8600",
        client_id="cid", client_secret="sec", redirect_uri="http://localhost:3551/auth/callback",
        jwt_secret="jwt", admin_emails=frozenset({"alice@hp.fr"}), secure_cookie=False,
        session_ttl_seconds=3600, central_logout=False,
    )
    base.update(over)
    return AuthConfig(**base)


def test_start_login(monkeypatch):
    monkeypatch.setattr(flow, "get_auth_config", _cfg)
    out = flow.start_login()
    assert out.authorize_url.startswith("http://localhost:8601/authorize?")
    assert out.secure_cookie is False and out.verifier and out.state


def test_callback_missing(monkeypatch):
    monkeypatch.setattr(flow, "get_auth_config", _cfg)
    assert flow.complete_callback(code=None, state=None, state_cookie=None, verifier_cookie=None)["status"] == "error"


def test_callback_state_mismatch(monkeypatch):
    monkeypatch.setattr(flow, "get_auth_config", _cfg)
    r = flow.complete_callback(code="c", state="a", state_cookie="b", verifier_cookie="v")
    assert r == {"status": "error", "reason": "state_mismatch"}


def test_callback_missing_verifier(monkeypatch):
    monkeypatch.setattr(flow, "get_auth_config", _cfg)
    r = flow.complete_callback(code="c", state="a", state_cookie="a", verifier_cookie=None)
    assert r == {"status": "error", "reason": "missing_verifier"}


def test_callback_denied(monkeypatch):
    monkeypatch.setattr(flow, "get_auth_config", _cfg)
    monkeypatch.setattr(flow, "exchange_code", lambda **k: {"access_token": "t"})
    monkeypatch.setattr(flow, "verify_and_extract", lambda *a: Identity(email="mallory@hp.fr"))
    r = flow.complete_callback(code="c", state="a", state_cookie="a", verifier_cookie="v")
    assert r == {"status": "denied", "email": "mallory@hp.fr"}


def test_callback_ok(monkeypatch):
    monkeypatch.setattr(flow, "get_auth_config", _cfg)
    monkeypatch.setattr(flow, "exchange_code", lambda **k: {"access_token": "t"})
    monkeypatch.setattr(flow, "verify_and_extract", lambda *a: Identity(email="Alice@hp.fr", name="Alice"))
    monkeypatch.setattr(flow, "create_session_token", lambda *a: "session-jwt")
    r = flow.complete_callback(code="c", state="a", state_cookie="a", verifier_cookie="v")
    assert r == {"status": "ok", "session_token": "session-jwt", "ttl_seconds": 3600, "secure_cookie": False}


def test_callback_exchange_fails(monkeypatch):
    monkeypatch.setattr(flow, "get_auth_config", _cfg)
    def boom(**k):
        raise RuntimeError("x")
    monkeypatch.setattr(flow, "exchange_code", boom)
    r = flow.complete_callback(code="c", state="a", state_cookie="a", verifier_cookie="v")
    assert r == {"status": "error", "reason": "exchange_failed"}


def test_callback_token_invalid(monkeypatch):
    monkeypatch.setattr(flow, "get_auth_config", _cfg)
    monkeypatch.setattr(flow, "exchange_code", lambda **k: {"access_token": "t"})
    def boom(*a):
        raise RuntimeError("bad")
    monkeypatch.setattr(flow, "verify_and_extract", boom)
    r = flow.complete_callback(code="c", state="a", state_cookie="a", verifier_cookie="v")
    assert r == {"status": "error", "reason": "token_invalid"}
