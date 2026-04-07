# content-extractor-api-service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a stateless FastAPI service that exposes boilerpy3 HTML cleaning and HeaderFooterExtractor as a REST API, behind api-gateway.

**Architecture:** Thin wrapper over `libs/common-utils` (HeaderFooterExtractor) and `boilerpy3` (pip). Two endpoint groups: `/clean` for boilerpy3, `/extract/header-footer` for HeaderFooterExtractor. No DB, queue, or cache. Prometheus metrics via `common_utils.metrics.prometheus.get_metrics_app()`.

**Tech Stack:** Python 3.10, FastAPI, Uvicorn, Pydantic, boilerpy3, common-utils, prometheus-client

**Spec:** `docs/superpowers/specs/2026-04-06-content-extractor-api-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `apps-microservices/content-extractor-api-service/main.py` | FastAPI app, CORS, metrics mount, health endpoint, logging setup |
| `apps-microservices/content-extractor-api-service/app/__init__.py` | Package marker |
| `apps-microservices/content-extractor-api-service/app/core/__init__.py` | Package marker |
| `apps-microservices/content-extractor-api-service/app/core/config.py` | Pydantic BaseSettings: PORT, LOG_LEVEL, MAX_PAYLOAD_SIZE_MB |
| `apps-microservices/content-extractor-api-service/app/routers/__init__.py` | Package marker |
| `apps-microservices/content-extractor-api-service/app/routers/clean.py` | POST /clean endpoint — delegates to boilerpy3 extractors |
| `apps-microservices/content-extractor-api-service/app/routers/extract.py` | POST /extract/header-footer endpoint — delegates to HeaderFooterExtractor |
| `apps-microservices/content-extractor-api-service/app/schemas/__init__.py` | Package marker |
| `apps-microservices/content-extractor-api-service/app/schemas/clean.py` | CleanRequest, CleanResponse Pydantic models |
| `apps-microservices/content-extractor-api-service/app/schemas/extract.py` | ExtractRequest, ExtractResponse, ExtractDebugResponse Pydantic models |
| `apps-microservices/content-extractor-api-service/tests/__init__.py` | Package marker |
| `apps-microservices/content-extractor-api-service/tests/test_clean.py` | Tests for /clean endpoint |
| `apps-microservices/content-extractor-api-service/tests/test_extract.py` | Tests for /extract/header-footer endpoint |
| `apps-microservices/content-extractor-api-service/requirements.txt` | Pip dependencies |
| `apps-microservices/content-extractor-api-service/Dockerfile` | Docker build with common-utils |
| `apps-microservices/content-extractor-api-service/CLAUDE.md` | Service documentation |

---

### Task 1: Project Scaffold — Config, Requirements, Package Markers

**Files:**
- Create: `apps-microservices/content-extractor-api-service/requirements.txt`
- Create: `apps-microservices/content-extractor-api-service/app/__init__.py`
- Create: `apps-microservices/content-extractor-api-service/app/core/__init__.py`
- Create: `apps-microservices/content-extractor-api-service/app/core/config.py`
- Create: `apps-microservices/content-extractor-api-service/app/routers/__init__.py`
- Create: `apps-microservices/content-extractor-api-service/app/schemas/__init__.py`
- Create: `apps-microservices/content-extractor-api-service/tests/__init__.py`

- [ ] **Step 1: Create directory structure and package markers**

```bash
mkdir -p apps-microservices/content-extractor-api-service/app/core
mkdir -p apps-microservices/content-extractor-api-service/app/routers
mkdir -p apps-microservices/content-extractor-api-service/app/schemas
mkdir -p apps-microservices/content-extractor-api-service/tests
touch apps-microservices/content-extractor-api-service/app/__init__.py
touch apps-microservices/content-extractor-api-service/app/core/__init__.py
touch apps-microservices/content-extractor-api-service/app/routers/__init__.py
touch apps-microservices/content-extractor-api-service/app/schemas/__init__.py
touch apps-microservices/content-extractor-api-service/tests/__init__.py
```

- [ ] **Step 2: Create requirements.txt**

```
# apps-microservices/content-extractor-api-service/requirements.txt
fastapi>=0.109.0
uvicorn>=0.27.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
boilerpy3>=1.0.6
beautifulsoup4>=4.12.0
lxml>=5.1.0
prometheus-client>=0.19.0
httpx>=0.26.0
pytest>=7.0.0
```

- [ ] **Step 3: Create config.py**

```python
# apps-microservices/content-extractor-api-service/app/core/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Content Extractor API"
    APP_VERSION: str = "1.0.0"
    PORT: int = 8600
    LOG_LEVEL: str = "info"
    MAX_PAYLOAD_SIZE_MB: int = 10

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
```

- [ ] **Step 4: Commit scaffold**

```bash
cd apps-microservices/content-extractor-api-service
git add requirements.txt app/__init__.py app/core/__init__.py app/core/config.py app/routers/__init__.py app/schemas/__init__.py tests/__init__.py
git commit -m "chore(content-extractor-api): scaffold project structure and config"
```

---

### Task 2: Pydantic Schemas — Clean Endpoint

**Files:**
- Create: `apps-microservices/content-extractor-api-service/app/schemas/clean.py`
- Create: `apps-microservices/content-extractor-api-service/tests/test_clean.py` (schema validation tests only)

- [ ] **Step 1: Write failing tests for schema validation**

```python
# apps-microservices/content-extractor-api-service/tests/test_clean.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd apps-microservices/content-extractor-api-service
python -m pytest tests/test_clean.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.schemas.clean'`

- [ ] **Step 3: Write the schemas**

```python
# apps-microservices/content-extractor-api-service/app/schemas/clean.py
from enum import Enum

from pydantic import BaseModel, Field


class OutputFormat(str, Enum):
    TEXT = "text"
    HTML = "html"


class CleanRequest(BaseModel):
    html: str = Field(..., min_length=1, description="Raw HTML to clean")
    format: OutputFormat = Field(
        default=OutputFormat.TEXT,
        description="Output format: 'text' for plain text, 'html' for marked HTML",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "html": "<html><body><article>Main content</article><nav>Menu</nav></body></html>",
                    "format": "text",
                }
            ]
        }
    }


class CleanResponse(BaseModel):
    content: str = Field(..., description="Extracted content")
    format: OutputFormat = Field(..., description="Output format used")
    content_length: int = Field(..., description="Length of extracted content in characters")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd apps-microservices/content-extractor-api-service
python -m pytest tests/test_clean.py -v
```

Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/schemas/clean.py tests/test_clean.py
git commit -m "feat(content-extractor-api): add Pydantic schemas for /clean endpoint"
```

---

### Task 3: Pydantic Schemas — Extract Endpoint

**Files:**
- Create: `apps-microservices/content-extractor-api-service/app/schemas/extract.py`
- Create: `apps-microservices/content-extractor-api-service/tests/test_extract.py` (schema validation tests only)

- [ ] **Step 1: Write failing tests for schema validation**

```python
# apps-microservices/content-extractor-api-service/tests/test_extract.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd apps-microservices/content-extractor-api-service
python -m pytest tests/test_extract.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.schemas.extract'`

- [ ] **Step 3: Write the schemas**

```python
# apps-microservices/content-extractor-api-service/app/schemas/extract.py
from typing import Any

from pydantic import BaseModel, Field


class ExtractRequest(BaseModel):
    main_html: str = Field(..., min_length=1, description="Main page HTML")
    reference_htmls: list[str] = Field(
        ...,
        min_length=2,
        description="Reference page HTMLs from the same domain (minimum 2)",
    )
    debug: bool = Field(
        default=False,
        description="Include detailed strategy results, gap analysis, and cleaned HTMLs",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "main_html": "<html><body><header>Nav</header><main>Content</main><footer>Footer</footer></body></html>",
                    "reference_htmls": [
                        "<html><body><header>Nav</header><main>Other</main><footer>Footer</footer></body></html>",
                        "<html><body><header>Nav</header><main>Third</main><footer>Footer</footer></body></html>",
                    ],
                    "debug": False,
                }
            ]
        }
    }


class ExtractResponse(BaseModel):
    header: str = Field(..., description="Extracted header text")
    footer: str = Field(..., description="Extracted footer text")
    header_method: str = Field(..., description="Strategy that produced the header")
    footer_method: str = Field(..., description="Strategy that produced the footer")


class ExtractDebugResponse(ExtractResponse):
    strategies: dict[str, dict[str, str]] = Field(
        ...,
        description="Results from all 3 strategies: original, class_intersection, structural_intersection",
    )
    intersections_class: list[dict[str, Any]] = Field(
        ..., description="Matched elements via class intersection"
    )
    intersections_structural: list[dict[str, Any]] = Field(
        ..., description="Matched elements via structural intersection"
    )
    cleaned_htmls: dict[str, str] = Field(
        ..., description="boilerpy3-cleaned HTML per input page"
    )
    gap_analysis: list[dict[str, Any]] = Field(
        ..., description="DOM gap scoring details"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd apps-microservices/content-extractor-api-service
python -m pytest tests/test_extract.py -v
```

Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/schemas/extract.py tests/test_extract.py
git commit -m "feat(content-extractor-api): add Pydantic schemas for /extract endpoint"
```

---

### Task 4: Clean Router — POST /clean Endpoint

**Files:**
- Create: `apps-microservices/content-extractor-api-service/app/routers/clean.py`
- Modify: `apps-microservices/content-extractor-api-service/tests/test_clean.py` (add endpoint tests)

- [ ] **Step 1: Add endpoint tests to test_clean.py**

Append these tests to the existing `tests/test_clean.py`:

```python
# Append to apps-microservices/content-extractor-api-service/tests/test_clean.py
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
```

- [ ] **Step 2: Run tests to verify endpoint tests fail**

```bash
cd apps-microservices/content-extractor-api-service
python -m pytest tests/test_clean.py::TestCleanEndpoint -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'main'` (main.py not created yet)

- [ ] **Step 3: Create a minimal main.py to make tests importable**

```python
# apps-microservices/content-extractor-api-service/main.py
from fastapi import FastAPI

from app.routers import clean

app = FastAPI(
    title="Content Extractor API",
    description="HTML cleaning and header/footer extraction API",
    version="1.0.0",
)

app.include_router(clean.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
```

- [ ] **Step 4: Create the clean router**

```python
# apps-microservices/content-extractor-api-service/app/routers/clean.py
import logging
import time

from fastapi import APIRouter, HTTPException
from boilerpy3 import extractors as BoilerpyExtractor

from app.schemas.clean import CleanRequest, CleanResponse, OutputFormat

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/clean", response_model=CleanResponse)
async def clean_html(request: CleanRequest):
    """Remove boilerplate from HTML and return cleaned content."""
    start_time = time.monotonic()

    try:
        if request.format == OutputFormat.HTML:
            extractor = BoilerpyExtractor.KeepEverythingExtractor()
            content = extractor.get_marked_html(request.html)
        else:
            extractor = BoilerpyExtractor.DefaultExtractor()
            content = extractor.get_content(request.html)
    except Exception:
        logger.exception("Extraction failed")
        raise HTTPException(
            status_code=500,
            detail={"detail": "Extraction failed", "error_code": "INTERNAL_ERROR"},
        )

    duration = time.monotonic() - start_time
    logger.info("Cleaned HTML in %.3fs, format=%s, length=%d", duration, request.format.value, len(content))

    return CleanResponse(
        content=content,
        format=request.format,
        content_length=len(content),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd apps-microservices/content-extractor-api-service
python -m pytest tests/test_clean.py -v
```

Expected: All 13 tests PASS (6 schema + 7 endpoint)

- [ ] **Step 6: Commit**

```bash
git add main.py app/routers/clean.py tests/test_clean.py
git commit -m "feat(content-extractor-api): implement POST /clean endpoint with boilerpy3"
```

---

### Task 5: Extract Router — POST /extract/header-footer Endpoint

**Files:**
- Create: `apps-microservices/content-extractor-api-service/app/routers/extract.py`
- Modify: `apps-microservices/content-extractor-api-service/tests/test_extract.py` (add endpoint tests)
- Modify: `apps-microservices/content-extractor-api-service/main.py` (include extract router)

- [ ] **Step 1: Add endpoint tests to test_extract.py**

Append these tests to the existing `tests/test_extract.py`:

```python
# Append to apps-microservices/content-extractor-api-service/tests/test_extract.py
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
```

- [ ] **Step 2: Run tests to verify endpoint tests fail**

```bash
cd apps-microservices/content-extractor-api-service
python -m pytest tests/test_extract.py::TestExtractEndpoint -v
```

Expected: FAIL — router not registered / module not found

- [ ] **Step 3: Create the extract router**

```python
# apps-microservices/content-extractor-api-service/app/routers/extract.py
import logging
import time

from fastapi import APIRouter, HTTPException
from common_utils.extractor.HeaderFooterExtractor import HeaderFooterExtractor

from app.schemas.extract import ExtractRequest, ExtractResponse, ExtractDebugResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/extract")


@router.post("/header-footer", response_model=ExtractResponse | ExtractDebugResponse)
async def extract_header_footer(request: ExtractRequest):
    """Extract header and footer from HTML using multi-strategy comparison."""
    start_time = time.monotonic()

    try:
        extractor = HeaderFooterExtractor(request.main_html)

        if request.debug:
            result = extractor.extract_all_debug(request.reference_htmls)
            duration = time.monotonic() - start_time

            header_method = result.get("header_method_used", "none")
            footer_method = result.get("footer_method_used", "none")

            logger.info(
                "Extracted header/footer (debug) in %.3fs, header_method=%s, footer_method=%s",
                duration, header_method, footer_method,
            )

            return ExtractDebugResponse(
                header=result.get("header_selected", ""),
                footer=result.get("footer_selected", ""),
                header_method=header_method,
                footer_method=footer_method,
                strategies={
                    "original": {
                        "header": result.get("header_old", ""),
                        "footer": result.get("footer_old", ""),
                    },
                    "class_intersection": {
                        "header": result.get("header_class", ""),
                        "footer": result.get("footer_class", ""),
                    },
                    "structural_intersection": {
                        "header": result.get("header_structural", ""),
                        "footer": result.get("footer_structural", ""),
                    },
                },
                intersections_class=result.get("intersections_class", []),
                intersections_structural=result.get("intersections_structural", []),
                cleaned_htmls={
                    k: v for k, v in result.items()
                    if k.startswith("cleaned_html_")
                },
                gap_analysis=result.get("gap_analysis", []),
            )
        else:
            result = extractor.extract_with_fallback(request.reference_htmls)
            duration = time.monotonic() - start_time

            logger.info(
                "Extracted header/footer in %.3fs, header_method=%s, footer_method=%s",
                duration, result.get("header_method", "none"), result.get("footer_method", "none"),
            )

            return ExtractResponse(
                header=result.get("header", ""),
                footer=result.get("footer", ""),
                header_method=result.get("header_method", "none"),
                footer_method=result.get("footer_method", "none"),
            )
    except Exception:
        logger.exception("Header/footer extraction failed")
        raise HTTPException(
            status_code=500,
            detail={"detail": "Extraction failed", "error_code": "INTERNAL_ERROR"},
        )
```

- [ ] **Step 4: Register extract router in main.py**

Update `main.py` to include the extract router. Add this import and include:

```python
# In apps-microservices/content-extractor-api-service/main.py
# Add to imports:
from app.routers import clean, extract

# Add after clean router include:
app.include_router(extract.router)
```

Full updated `main.py`:

```python
# apps-microservices/content-extractor-api-service/main.py
from fastapi import FastAPI

from app.routers import clean, extract

app = FastAPI(
    title="Content Extractor API",
    description="HTML cleaning and header/footer extraction API",
    version="1.0.0",
)

app.include_router(clean.router)
app.include_router(extract.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd apps-microservices/content-extractor-api-service
python -m pytest tests/test_extract.py -v
```

Expected: All 12 tests PASS (7 schema + 5 endpoint)

- [ ] **Step 6: Commit**

```bash
git add app/routers/extract.py tests/test_extract.py main.py
git commit -m "feat(content-extractor-api): implement POST /extract/header-footer endpoint"
```

---

### Task 6: Main App — CORS, Metrics, Logging, Payload Limit

**Files:**
- Modify: `apps-microservices/content-extractor-api-service/main.py`

- [ ] **Step 1: Update main.py with CORS, metrics, logging, and payload limit middleware**

```python
# apps-microservices/content-extractor-api-service/main.py
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.wsgi import WSGIMiddleware
from common_utils.logging import setup_logging
from common_utils.metrics.prometheus import get_metrics_app

from app.core.config import settings
from app.routers import clean, extract

setup_logging("content-extractor-api-service")
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    description="HTML cleaning and header/footer extraction API",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Prometheus metrics
metrics_app = get_metrics_app()
app.mount("/metrics", WSGIMiddleware(metrics_app))

# CORS — internal service, not exposed publicly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Internal service only — not exposed publicly
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def check_payload_size(request: Request, call_next):
    """Reject requests exceeding MAX_PAYLOAD_SIZE_MB."""
    content_length = request.headers.get("content-length")
    max_bytes = settings.MAX_PAYLOAD_SIZE_MB * 1024 * 1024
    if content_length and int(content_length) > max_bytes:
        return JSONResponse(
            status_code=413,
            content={
                "detail": f"Payload exceeds {settings.MAX_PAYLOAD_SIZE_MB}MB limit",
                "error_code": "PAYLOAD_TOO_LARGE",
            },
        )
    return await call_next(request)


app.include_router(clean.router)
app.include_router(extract.router)


@app.get("/")
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
```

- [ ] **Step 2: Run all tests to verify nothing broke**

```bash
cd apps-microservices/content-extractor-api-service
python -m pytest tests/ -v
```

Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat(content-extractor-api): add CORS, Prometheus metrics, logging, and payload limit"
```

---

### Task 7: Prometheus Metrics — Request Counter and Extraction Method Tracking

**Files:**
- Modify: `apps-microservices/content-extractor-api-service/app/routers/clean.py`
- Modify: `apps-microservices/content-extractor-api-service/app/routers/extract.py`

- [ ] **Step 1: Add Prometheus counters to clean.py**

Add at the top of `app/routers/clean.py`, after existing imports:

```python
from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)
```

Update the endpoint to record metrics. Replace the `clean_html` function:

```python
@router.post("/clean", response_model=CleanResponse)
async def clean_html(request: CleanRequest):
    """Remove boilerplate from HTML and return cleaned content."""
    start_time = time.monotonic()

    try:
        if request.format == OutputFormat.HTML:
            extractor = BoilerpyExtractor.KeepEverythingExtractor()
            content = extractor.get_marked_html(request.html)
        else:
            extractor = BoilerpyExtractor.DefaultExtractor()
            content = extractor.get_content(request.html)
    except Exception:
        logger.exception("Extraction failed")
        REQUEST_COUNT.labels(method="POST", endpoint="/clean", status="500").inc()
        raise HTTPException(
            status_code=500,
            detail={"detail": "Extraction failed", "error_code": "INTERNAL_ERROR"},
        )

    duration = time.monotonic() - start_time
    REQUEST_COUNT.labels(method="POST", endpoint="/clean", status="200").inc()
    REQUEST_DURATION.labels(method="POST", endpoint="/clean").observe(duration)

    logger.info("Cleaned HTML in %.3fs, format=%s, length=%d", duration, request.format.value, len(content))

    return CleanResponse(
        content=content,
        format=request.format,
        content_length=len(content),
    )
```

- [ ] **Step 2: Add Prometheus counters to extract.py**

Add at the top of `app/routers/extract.py`, after existing imports:

```python
from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)
EXTRACTION_METHOD = Counter(
    "extraction_method_used_total",
    "Header/footer extraction method used",
    ["method"],
)
```

**Important:** The `REQUEST_COUNT` and `REQUEST_DURATION` metrics are shared across routers via Prometheus's global registry — declaring them with the same name/labels in both files will cause a `ValueError: Duplicated timeseries` at import time. Instead, create a shared metrics module.

Create `app/core/metrics.py`:

```python
# apps-microservices/content-extractor-api-service/app/core/metrics.py
from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)

EXTRACTION_METHOD = Counter(
    "extraction_method_used_total",
    "Header/footer extraction method used",
    ["method"],
)
```

Then update both routers to import from `app.core.metrics`:

In `app/routers/clean.py`, replace prometheus imports with:
```python
from app.core.metrics import REQUEST_COUNT, REQUEST_DURATION
```

In `app/routers/extract.py`, replace prometheus imports with:
```python
from app.core.metrics import REQUEST_COUNT, REQUEST_DURATION, EXTRACTION_METHOD
```

Add metric tracking to the extract endpoint. After `result = extractor.extract_with_fallback(...)`:
```python
EXTRACTION_METHOD.labels(method=result.get("header_method", "none")).inc()
EXTRACTION_METHOD.labels(method=result.get("footer_method", "none")).inc()
```

And after `result = extractor.extract_all_debug(...)`:
```python
EXTRACTION_METHOD.labels(method=header_method).inc()
EXTRACTION_METHOD.labels(method=footer_method).inc()
```

Add `REQUEST_COUNT` and `REQUEST_DURATION` tracking in the extract endpoint matching the pattern from clean.py (200 on success, 500 on error, endpoint="/extract/header-footer").

- [ ] **Step 3: Run all tests**

```bash
cd apps-microservices/content-extractor-api-service
python -m pytest tests/ -v
```

Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add app/core/metrics.py app/routers/clean.py app/routers/extract.py
git commit -m "feat(content-extractor-api): add Prometheus request and extraction method metrics"
```

---

### Task 8: Dockerfile

**Files:**
- Create: `apps-microservices/content-extractor-api-service/Dockerfile`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# apps-microservices/content-extractor-api-service/Dockerfile
FROM python:3.10-slim

WORKDIR /app

ENV PYTHONPATH=/app

# Install common-utils first (shared library)
COPY libs/common-utils /app/libs/common-utils
RUN pip install --no-cache-dir -e /app/libs/common-utils

# Install service dependencies
COPY apps-microservices/content-extractor-api-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service source
COPY apps-microservices/content-extractor-api-service/main.py .
COPY apps-microservices/content-extractor-api-service/app ./app

# Non-root user
RUN useradd --create-home appuser
USER appuser

EXPOSE 8600

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl --fail http://localhost:8600/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8600", "--proxy-headers"]
```

- [ ] **Step 2: Verify Dockerfile syntax**

```bash
cd apps-microservices/content-extractor-api-service
docker build --check -f Dockerfile ../.. 2>&1 || echo "Note: --check may not be supported; visual review sufficient"
```

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "chore(content-extractor-api): add Dockerfile with common-utils and non-root user"
```

---

### Task 9: CLAUDE.md — Service-Level and Root Update

**Files:**
- Create: `apps-microservices/content-extractor-api-service/CLAUDE.md`
- Modify: `CLAUDE.md` (root)

- [ ] **Step 1: Create service CLAUDE.md**

```markdown
# content-extractor-api-service

REST API exposing boilerpy3 HTML cleaning and HeaderFooterExtractor for external teams, internal services, and ad-hoc usage.

## Tech Stack

- Python 3.10 / FastAPI / Uvicorn
- boilerpy3 (HTML cleaning)
- common-utils (HeaderFooterExtractor)
- Prometheus metrics

## Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/clean` | POST | boilerpy3 HTML cleaning (text or HTML output) |
| `/extract/header-footer` | POST | Header/footer extraction with optional debug mode |
| `/health` | GET | Health check |
| `/metrics` | GET | Prometheus metrics |

## Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8600
```

## Test

```bash
python -m pytest tests/ -v
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8600` | Service port |
| `LOG_LEVEL` | `"info"` | Logging level |
| `MAX_PAYLOAD_SIZE_MB` | `10` | Max request body size |

## Dependencies

- No RabbitMQ, Redis, or database
- Sits behind `api-gateway` for auth
- Imports `HeaderFooterExtractor` from `libs/common-utils`

## What This Provides to Other Services

- On-demand HTML content extraction without going through the RabbitMQ pipeline
- Header/footer detection API for external consumers
```

- [ ] **Step 2: Update root CLAUDE.md Service Map**

In `CLAUDE.md` (root), change the API Services row from:

```
| API Services | `api-*` (16 services) | Python / FastAPI | Remote |
```

to:

```
| API Services | `api-*`, `content-extractor-api-service` (17) | Python / FastAPI | Remote |
```

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/content-extractor-api-service/CLAUDE.md CLAUDE.md
git commit -m "docs(content-extractor-api): add service CLAUDE.md and update root service map"
```

---

### Task 10: docker-compose.yml Entry

**Files:**
- Modify: `docker-compose.yml` (root)

- [ ] **Step 1: Add service entry to docker-compose.yml**

Add the following service block in the appropriate alphabetical position among the API services:

```yaml
  content-extractor-api-service:
    build:
      context: .
      dockerfile: apps-microservices/content-extractor-api-service/Dockerfile
    ports:
      - "${CONTENT_EXTRACTOR_API_PORT:-8600}:8600"
    environment:
      - PORT=8600
      - LOG_LEVEL=info
      - MAX_PAYLOAD_SIZE_MB=10
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8600/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    restart: unless-stopped
```

- [ ] **Step 2: Validate docker-compose syntax**

```bash
docker compose config --quiet 2>&1 || echo "Syntax check failed"
```

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "chore(content-extractor-api): add service to docker-compose.yml"
```

---

### Task 11: Final Verification — Full Test Suite

- [ ] **Step 1: Run the complete test suite**

```bash
cd apps-microservices/content-extractor-api-service
python -m pytest tests/ -v --tb=short
```

Expected: All tests PASS (13 clean + 12 extract = 25 total)

- [ ] **Step 2: Verify imports and app startup**

```bash
cd apps-microservices/content-extractor-api-service
python -c "from main import app; print('App created:', app.title)"
```

Expected: `App created: Content Extractor API`

- [ ] **Step 3: Verify all files exist**

```bash
ls -la apps-microservices/content-extractor-api-service/
ls -la apps-microservices/content-extractor-api-service/app/core/
ls -la apps-microservices/content-extractor-api-service/app/routers/
ls -la apps-microservices/content-extractor-api-service/app/schemas/
ls -la apps-microservices/content-extractor-api-service/tests/
```

Expected: All files from the file structure table exist.
