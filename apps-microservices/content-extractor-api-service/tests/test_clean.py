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
