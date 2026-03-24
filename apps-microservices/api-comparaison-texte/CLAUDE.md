# api-comparaison-texte

Text comparison API using difflib to determine if content has changed enough to require an update. Supports HTML cleaning and batch processing.

## Tech Stack

- **Language:** Python 3.10
- **Framework:** FastAPI + Uvicorn
- **Text comparison:** difflib (stdlib)
- **HTML parsing:** BeautifulSoup4 + lxml
- **No shared libs** (standalone service)

## Build / Run

- **Port:** 8998
- **Run:** `uvicorn main:app --host 0.0.0.0 --port 8998 --proxy-headers`
- **Tests:** `pytest tests/`

## Folder Structure

```
api-comparaison-texte/
  main.py                         # FastAPI app
  app/
    api/
      routes.py                   # /compare, /compare-batch, /health
    core/
      config.py                   # Settings (APP_NAME, BATCH_MAX_ITEMS, etc.)
      text_comparator.py          # compare_texts (difflib SequenceMatcher)
    models/
      schemas.py                  # ComparisonRequest/Response, Decision enum
    services/
      html_cleaner.py             # extract_text_from_html
  tests/
    test_api.py
    test_text_comparator.py
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/compare` | Compare two texts, return similarity ratio + UPDATE/SKIP |
| `POST` | `/api/v1/compare-batch` | Batch comparison (capped by BATCH_MAX_ITEMS) |
| `GET` | `/api/v1/health` | Health check |
| `GET` | `/` | Service info |

## Conventions

- Decision is `UPDATE` when `similarity_ratio < threshold`, `SKIP` otherwise.
- HTML content is auto-cleaned before comparison when `content_type` is `HTML`.

## Dependencies on Other Services

None (standalone).
