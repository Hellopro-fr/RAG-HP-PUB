# extractor-testing-service

Testing harness to compare web content extraction libraries side by side.

## Tech Stack

- **Backend:** Python 3.11, FastAPI, Uvicorn + Go CLI (go-trafilatura)
- **Frontend:** Next.js 16 (React 19, TypeScript), pnpm
- **UI:** Radix UI, Tailwind CSS 4, shadcn/ui
- **Extractors:** trafilatura, beautifulsoup4, boilerpipe3, boilerpy3, markdownify
- **Go CLI:** go-trafilatura (built from `backend/go-extractor/`)

## Commands

### Frontend (`frontend/`)
| Action | Command |
|--------|---------|
| Dev | `pnpm dev` (port 3030) |
| Build | `pnpm build --webpack` |
| Start | `pnpm start -p 3030` |
| Lint | `pnpm lint` |

### Backend (`backend/`)
| Action | Command |
|--------|---------|
| Run | `uvicorn main:app --host 0.0.0.0 --port 8034` |
| Deps | `pip install -r requirements.txt` |

## Docker

- **Backend:** Port **8034**. Multi-stage: Go 1.24 builds CLI, Python 3.11 runs FastAPI. Requires JRE for boilerpipe3.
- **Frontend:** Port **3030**. Multi-stage: pnpm build then pnpm start.

## Folder Structure

```
backend/
  main.py                # FastAPI app with CORS
  core/
    preprocessor.py      # HTML preprocessing
    extractor.py         # Run all extractors
  schemas/               # Pydantic models
  go-extractor/
    main.go              # Go-trafilatura CLI (stdin/stdout JSON)
  requirements.txt
frontend/
  app/
    page.tsx             # Main comparison UI
    api/
      test-extractors/route.ts
      test-boilerplate/route.ts
  components/
    input-section.tsx    # HTML input panel
    output-section.tsx   # Extraction results panel
    ui/                  # shadcn/ui
```

## API Endpoints

- `POST /test-extractors` -- Run all extractors on given HTML
- `POST /test-boilerplate` -- Test boilerplate removal

## Conventions

- Go CLI reads JSON from stdin, writes JSON to stdout (error field on failure)
- Backend uses `common_utils` shared library for HeaderFooterExtractor
- Frontend proxies to backend; separate Dockerfiles

## Dependencies

- **common-utils** shared library (`libs/common-utils`)
