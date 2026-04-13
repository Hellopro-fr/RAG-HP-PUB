import pytest
from pydantic import ValidationError

from app.schemas.clean import CleanRequest, CleanResponse, OutputFormat


class TestCleanRequest:
    def test_valid_request_defaults(self):
        req = CleanRequest(html="<html><body>Hello</body></html>")
        assert req.html == "<html><body>Hello</body></html>"
        assert req.format == OutputFormat.TEXT

    def test_valid_request_html_format(self):
        req = CleanRequest(html="<html><body>Hello</body></html>", format="html")
        assert req.format == OutputFormat.HTML

    def test_empty_html_rejected(self):
        with pytest.raises(ValidationError):
            CleanRequest(html="")

    def test_missing_html_rejected(self):
        with pytest.raises(ValidationError):
            CleanRequest()

    def test_invalid_format_rejected(self):
        with pytest.raises(ValidationError):
            CleanRequest(html="<html></html>", format="xml")


class TestCleanResponse:
    def test_valid_response(self):
        resp = CleanResponse(content="Hello", format=OutputFormat.TEXT, content_length=5)
        assert resp.content == "Hello"
        assert resp.content_length == 5


from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

SAMPLE_HTML = """
<html>
<head><title>Test Page</title></head>
<body>
    <nav>Navigation menu</nav>
    <article>
        <h1>Main Article Title</h1>
        <p>This is the main content of the article. It contains important information
        that should be extracted by the boilerplate removal algorithm.</p>
        <p>Second paragraph with more relevant content for extraction testing.</p>
    </article>
    <aside>Sidebar ads and promotions</aside>
    <footer>Copyright 2026</footer>
</body>
</html>
"""


class TestCleanEndpoint:
    def test_clean_text_format(self):
        response = client.post("/clean", json={"html": SAMPLE_HTML, "format": "text"})
        assert response.status_code == 200
        data = response.json()
        assert data["format"] == "text"
        assert data["content_length"] == len(data["content"])
        assert isinstance(data["content"], str)

    def test_clean_html_format(self):
        response = client.post("/clean", json={"html": SAMPLE_HTML, "format": "html"})
        assert response.status_code == 200
        data = response.json()
        assert data["format"] == "html"
        assert "<" in data["content"]  # HTML tags present

    def test_clean_default_format_is_text(self):
        response = client.post("/clean", json={"html": SAMPLE_HTML})
        assert response.status_code == 200
        assert response.json()["format"] == "text"

    def test_clean_empty_html_rejected(self):
        response = client.post("/clean", json={"html": ""})
        assert response.status_code == 422

    def test_clean_missing_html_rejected(self):
        response = client.post("/clean", json={})
        assert response.status_code == 422

    def test_clean_invalid_format_rejected(self):
        response = client.post("/clean", json={"html": "<html></html>", "format": "xml"})
        assert response.status_code == 422

    def test_clean_minimal_html_returns_200(self):
        response = client.post("/clean", json={"html": "<html><body></body></html>"})
        assert response.status_code == 200
        data = response.json()
        assert data["content_length"] >= 0
