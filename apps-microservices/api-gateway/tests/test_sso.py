def test_sso_module_imports() -> None:
    """Smoke test: module loads without raising."""
    from app.routers import sso
    assert sso.router is not None
