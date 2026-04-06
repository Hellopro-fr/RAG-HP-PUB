import pytest
from pydantic import ValidationError

from app.schemas.extract import ExtractRequest, ExtractResponse, ExtractDebugResponse


class TestExtractRequest:
    def test_valid_request_defaults(self):
        req = ExtractRequest(
            main_html="<html><body>Main</body></html>",
            reference_htmls=["<html>Ref1</html>", "<html>Ref2</html>"],
        )
        assert req.debug is False

    def test_one_reference_rejected(self):
        with pytest.raises(ValidationError):
            ExtractRequest(
                main_html="<html></html>",
                reference_htmls=["<html>Ref1</html>"],
            )

    def test_empty_references_rejected(self):
        with pytest.raises(ValidationError):
            ExtractRequest(
                main_html="<html></html>",
                reference_htmls=[],
            )

    def test_empty_main_html_rejected(self):
        with pytest.raises(ValidationError):
            ExtractRequest(
                main_html="",
                reference_htmls=["<html>Ref1</html>", "<html>Ref2</html>"],
            )

    def test_debug_flag(self):
        req = ExtractRequest(
            main_html="<html></html>",
            reference_htmls=["<html>Ref1</html>", "<html>Ref2</html>"],
            debug=True,
        )
        assert req.debug is True


class TestExtractResponse:
    def test_valid_response(self):
        resp = ExtractResponse(
            header="Site Header",
            footer="Site Footer",
            header_method="structural_intersection",
            footer_method="class_intersection",
        )
        assert resp.header == "Site Header"
        assert resp.header_method == "structural_intersection"


class TestExtractDebugResponse:
    def test_valid_debug_response(self):
        resp = ExtractDebugResponse(
            header="Site Header",
            footer="Site Footer",
            header_method="structural_intersection",
            footer_method="class_intersection",
            strategies={
                "original": {"header": "H1", "footer": "F1"},
                "class_intersection": {"header": "H2", "footer": "F2"},
                "structural_intersection": {"header": "H3", "footer": "F3"},
            },
            intersections_class=[],
            intersections_structural=[],
            cleaned_htmls={"main": "<html>cleaned</html>"},
            gap_analysis=[],
        )
        assert resp.strategies["original"]["header"] == "H1"


from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

MAIN_HTML = """
<html>
<head><title>Page 1</title></head>
<body>
    <header><nav><a href="/">Home</a> <a href="/about">About</a></nav></header>
    <main><h1>Page One Content</h1><p>Unique content for page one.</p></main>
    <footer><p>Copyright 2026 Company Inc. All rights reserved.</p></footer>
</body>
</html>
"""

REF_HTML_1 = """
<html>
<head><title>Page 2</title></head>
<body>
    <header><nav><a href="/">Home</a> <a href="/about">About</a></nav></header>
    <main><h1>Page Two Content</h1><p>Different content for page two.</p></main>
    <footer><p>Copyright 2026 Company Inc. All rights reserved.</p></footer>
</body>
</html>
"""

REF_HTML_2 = """
<html>
<head><title>Page 3</title></head>
<body>
    <header><nav><a href="/">Home</a> <a href="/about">About</a></nav></header>
    <main><h1>Page Three Content</h1><p>Yet another page with different content.</p></main>
    <footer><p>Copyright 2026 Company Inc. All rights reserved.</p></footer>
</body>
</html>
"""


class TestExtractEndpoint:
    def test_extract_basic(self):
        response = client.post("/extract/header-footer", json={
            "main_html": MAIN_HTML,
            "reference_htmls": [REF_HTML_1, REF_HTML_2],
        })
        assert response.status_code == 200
        data = response.json()
        assert "header" in data
        assert "footer" in data
        assert "header_method" in data
        assert "footer_method" in data

    def test_extract_debug_mode(self):
        response = client.post("/extract/header-footer", json={
            "main_html": MAIN_HTML,
            "reference_htmls": [REF_HTML_1, REF_HTML_2],
            "debug": True,
        })
        assert response.status_code == 200
        data = response.json()
        assert "header" in data
        assert "strategies" in data
        assert "gap_analysis" in data
        assert "intersections_class" in data
        assert "intersections_structural" in data
        assert "cleaned_htmls" in data

    def test_extract_one_reference_rejected(self):
        response = client.post("/extract/header-footer", json={
            "main_html": MAIN_HTML,
            "reference_htmls": [REF_HTML_1],
        })
        assert response.status_code == 422

    def test_extract_empty_main_rejected(self):
        response = client.post("/extract/header-footer", json={
            "main_html": "",
            "reference_htmls": [REF_HTML_1, REF_HTML_2],
        })
        assert response.status_code == 422

    def test_extract_empty_references_rejected(self):
        response = client.post("/extract/header-footer", json={
            "main_html": MAIN_HTML,
            "reference_htmls": [],
        })
        assert response.status_code == 422
