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
