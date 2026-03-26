# api-html-recherche

Web frontend for the search system. Serves HTML pages (Jinja2 templates) with JWT-based session auth and a search UI communicating via WebSocket.

## Tech Stack

- **Language:** Python 3.10
- **Framework:** FastAPI + Uvicorn
- **Templates:** Jinja2
- **Auth:** JWT (PyJWT), session middleware
- **Frontend:** Tailwind CSS (bundled), vanilla JS
- **Shared lib:** `common_utils`

## Build / Run

- **Port:** 8550
- **Run:** `uvicorn main:app --host 0.0.0.0 --port 8550 --proxy-headers`
- **Docker build context:** monorepo root (needs `libs/common-utils`)

## Folder Structure

```
api-html-recherche/
  main.py                   # FastAPI app, login/logout, page routing
  middlewares/
    auth.py                 # AuthMiddleware (session-based)
  templates/
    login.html              # Login form
    recherche.html          # Main search page
    ws.html                 # WebSocket test page
    404.html
  static/
    css/                    # recherche.css, style.css
    js/                     # script.js, transcription.js, tailwind.min.js
    image/                  # loading indicators
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/login` | Login page |
| `POST` | `/login` | Authenticate via external hellopro.fr API |
| `GET` | `/logout` | Clear session |
| `GET` | `/recherche` | Search UI (requires auth) |
| `GET` | `/{page}` | Generic template rendering |

## Conventions

- Session middleware must be added before AuthMiddleware (Starlette ordering).
- ProxyHeadersMiddleware enabled for reverse-proxy deployments.

## Dependencies on Other Services

- External: `hellopro.fr` auth endpoint
- Connects to `api-recherche` WebSocket for search (client-side JS)
