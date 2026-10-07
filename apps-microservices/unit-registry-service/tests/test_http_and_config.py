import urllib.error
import urllib.request

import pytest
from pydantic import ValidationError

from app.config import Settings
from infrastructure.http_server import db_ping, start_http_server


def fetch(port, path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=3) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


@pytest.mark.parametrize("healthy,code", [(True, 200), (False, 503)])
def test_health_reflects_the_check(healthy, code):
    server = start_http_server(0, lambda: healthy, host="127.0.0.1")
    try:
        assert fetch(server.server_address[1], "/health")[0] == code
    finally:
        server.shutdown()


def test_health_is_503_when_the_check_raises():
    def boom():
        raise RuntimeError("db down")

    server = start_http_server(0, boom, host="127.0.0.1")
    try:
        assert fetch(server.server_address[1], "/health")[0] == 503
    finally:
        server.shutdown()


def test_metrics_and_404():
    server = start_http_server(0, lambda: True, host="127.0.0.1")
    try:
        port = server.server_address[1]
        status, body = fetch(port, "/metrics")
        assert status == 200 and b"python_info" in body
        assert fetch(port, "/nope")[0] == 404
    finally:
        server.shutdown()


def test_db_ping(engine):
    assert db_ping(engine) is True


def settings(**overrides):
    values = dict(MYSQL_PASSWORD="p@ss", RABBITMQ_URL="amqp://guest:guest@rabbit:5672/",
                  UNITS_ADMIN_KEY="k" * 16)
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_database_url_is_built_from_parts():
    rendered = settings().database_url.render_as_string(hide_password=False)
    assert rendered == "mysql+pymysql://normalization_user:p%40ss@mysql:3306/normalization_db?charset=utf8mb4"


def test_admin_key_must_be_long_enough():
    with pytest.raises(ValidationError):
        settings(UNITS_ADMIN_KEY="short")
