from app.db.database import build_tortoise_config


def test_build_tortoise_config_url():
    cfg = build_tortoise_config("sqlite://:memory:")
    assert cfg["connections"]["default"] == "sqlite://:memory:"
    assert "app.db.models" in cfg["apps"]["models"]["models"]
