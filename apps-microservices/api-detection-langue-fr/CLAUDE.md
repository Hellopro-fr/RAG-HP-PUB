# api-detection-langue-fr

Detects whether a website is in French or has a French version. Uses URL analysis, HTML lang tags, hreflang links, and NLP content detection.

## Tech Stack

- **Language:** Python 3.10
- **Framework:** FastAPI + Uvicorn
- **Scraping:** Playwright (Chromium), httpx
- **NLP:** langdetect, langid, fastText
- **HTML parsing:** BeautifulSoup4 + lxml
- **No shared libs** (standalone service)

## Build / Run

- **Port:** 8999
- **Run:** `uvicorn main:app --host 0.0.0.0 --port 8999 --proxy-headers --timeout-keep-alive 300`
- **Tests:** `pytest tests/`
- **Docker build:** installs Playwright + Chromium browser at build time

## Folder Structure

```
api-detection-langue-fr/
  main.py                        # FastAPI app
  app/
    api/
      routes.py                  # /detect, /detect-batch, /check-url, /detect-debug
    core/
      config.py                  # Settings
      domain_fr.py               # DomainFR detector (URL + HTML + NLP pipeline)
    models/
      schemas.py                 # DetectionRequest/Response, BatchItem, etc.
    services/
      language_detector.py       # Challenge page detection
      scraper.py                 # HTML fetching
      redirect_tracker.py        # fetch_html with redirect tracking
  tests/
    test_api.py
    test_domain_fr.py
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/detect` | Detect French for a single URL (simple/complete mode) |
| `POST` | `/api/v1/detect-batch` | Batch detection (max 100 URLs, parallel + retry) |
| `GET` | `/api/v1/check-url` | URL-only check (no HTML fetch) |
| `POST` | `/api/v1/detect-debug` | Debug mode with full pipeline trace |
| `GET` | `/api/v1/health` | Health check |

## Conventions

- Two modes: `simple` (URL + lang attr only) and `complete` (+ hreflang, NLP).
- Batch has 2-pass: parallel processing then sequential retry for failures.
- Stagger delay (0.5s per item) in batch to reduce proxy pressure.
- Detects Cloudflare/WAF challenge pages and reports them as errors.

## Dependencies on Other Services

None (standalone). Optionally uses a proxy (`proxy_url` parameter).
