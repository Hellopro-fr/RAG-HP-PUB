"""Integration tests for the admission middleware."""
import asyncio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app(max_prod=2, max_debug=1, enabled=True):
    """Build a minimal FastAPI app with the admission middleware attached."""
    from app.middleware.admission import AdmissionMiddleware
    from app.core.admission import AdmissionController

    app = FastAPI()
    prod_ctrl = AdmissionController(max_slots=max_prod)
    debug_ctrl = AdmissionController(max_slots=max_debug)
    app.add_middleware(
        AdmissionMiddleware,
        prod_controller=prod_ctrl,
        debug_controller=debug_ctrl,
        retry_after_seconds=10,
        enabled=enabled,
    )

    @app.get("/api/v1/detect")
    async def _detect():
        await asyncio.sleep(0.05)
        return {"ok": True}

    @app.get("/api/v1/detect-batch")
    async def _batch():
        await asyncio.sleep(0.05)
        return {"ok": True}

    @app.get("/api/v1/detect-debug")
    async def _debug():
        await asyncio.sleep(0.05)
        return {"ok": True}

    @app.get("/api/v1/health")
    async def _health():
        return {"status": "healthy"}

    @app.get("/metrics")
    async def _metrics():
        return {"metrics": "here"}

    return app, prod_ctrl, debug_ctrl


class TestAdmissionMiddleware:

    def test_accepts_request_when_slots_available(self):
        app, _, _ = _make_app(max_prod=2)
        client = TestClient(app)
        r = client.get("/api/v1/detect")
        assert r.status_code == 200

    def test_rejects_with_503_when_saturated(self):
        app, prod_ctrl, _ = _make_app(max_prod=1)
        # Fill the slot manually (simulate an in-flight request)
        asyncio.get_event_loop().run_until_complete(prod_ctrl.acquire())
        client = TestClient(app)
        r = client.get("/api/v1/detect")
        assert r.status_code == 503
        assert r.headers["retry-after"] == "10"
        assert "saturated" in r.text.lower() or "unavailable" in r.text.lower()

    def test_debug_has_independent_budget(self):
        """Saturating /detect does NOT affect /detect-debug."""
        app, prod_ctrl, _ = _make_app(max_prod=1, max_debug=1)
        asyncio.get_event_loop().run_until_complete(prod_ctrl.acquire())
        client = TestClient(app)
        assert client.get("/api/v1/detect").status_code == 503
        assert client.get("/api/v1/detect-debug").status_code == 200

    def test_health_bypasses_admission(self):
        """/health (and /metrics) must always respond, even when prod is saturated."""
        app, prod_ctrl, _ = _make_app(max_prod=1)
        asyncio.get_event_loop().run_until_complete(prod_ctrl.acquire())
        client = TestClient(app)
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/metrics").status_code == 200

    def test_kill_switch_disables_admission(self):
        """With enabled=False, middleware is a no-op."""
        app, prod_ctrl, _ = _make_app(max_prod=1, enabled=False)
        asyncio.get_event_loop().run_until_complete(prod_ctrl.acquire())
        client = TestClient(app)
        # With kill switch, request goes through even though counter is at max
        assert client.get("/api/v1/detect").status_code == 200
