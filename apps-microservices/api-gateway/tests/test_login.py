"""Regression test for /login template rendering.

Locks the Starlette TemplateResponse signature contract:
    TemplateResponse(request, name, context)

The previous form `TemplateResponse(name, context_with_request_key)` is
incompatible with Starlette >= 0.45 and triggers
`TypeError: unhashable type: 'dict'` deep inside Jinja2's template cache
(see Cycle: api-gateway /docs 500 incident).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from app.routers.login import router as login_router


@pytest.fixture
def client():
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret")
    app.include_router(login_router)
    return TestClient(app)


class TestLoginPageRenders:
    def test_get_login_returns_200(self, client):
        response = client.get("/login")
        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}. "
            f"Body: {response.text[:300]}"
        )

    def test_get_login_renders_html(self, client):
        response = client.get("/login")
        body = response.content.lower()
        assert b"<html" in body or b"<form" in body, (
            "Response does not contain rendered HTML form."
        )
