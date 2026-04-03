# dlq-manager-service

Dead Letter Queue manager for browsing, searching, and requeuing failed messages.

## Tech Stack

- **Backend:** Python 3.10, FastAPI, Uvicorn
- **Frontend:** Next.js 16 (React 19, TypeScript), pnpm
- **UI:** Radix UI, Tailwind CSS 4, shadcn/ui, Axios
- **Message Broker:** RabbitMQ (via pika)
- **Search:** Elasticsearch
- **Build:** Multi-stage Dockerfile (frontend static export + Python backend)

## Commands

### Frontend (`frontend/`)
| Action | Command |
|--------|---------|
| Dev | `pnpm dev` |
| Build | `pnpm build` |
| Lint | `pnpm lint` |

### Backend (`backend/`)
| Action | Command |
|--------|---------|
| Run | `uvicorn main:app --host 0.0.0.0 --port 8560` (container) / accessible on host port **8585** |
| Deps | `pip install -r requirements.txt` |

## Docker

- Port: **8585** (host) / **8560** (container)
- Frontend built as static export, served by FastAPI `StaticFiles`
- Backend runs Uvicorn with FastAPI

## Folder Structure

```
backend/
  main.py              # FastAPI app + background rule processor
  app/
    api.py             # API router (search, requeue, rules)
    es_client.py       # Elasticsearch client
    rabbitmq_client.py # RabbitMQ client
    models.py          # Pydantic models
  requirements.txt
frontend/
  app/                 # Next.js pages
  components/
    dlq/               # DLQ-specific components
      Dashboard.tsx
      MessageList.tsx
      MessageDetailModal.tsx
      SearchPage.tsx
      UniqueErrorsModal.tsx
      RulesPage.tsx
      CreateRuleModal.tsx
      Sidebar.tsx
    ui/                # shadcn/ui components
  lib/api.ts           # Frontend API client
```

## API Endpoints (Backend: `/api`)

- `GET /api/rules` -- List auto-archive rules
- `POST /api/rules` -- Create rule
- `PATCH /api/rules/{id}/toggle` -- Toggle rule active/inactive
- `POST /api/search` -- Search DLQ messages
- `POST /api/requeue-bulk` -- Bulk requeue messages
- `POST /api/update-status-bulk` -- Bulk update status
- `POST /api/archive-by-filter` -- Archive messages by filter
- `POST /api/messages/unique-errors` -- Get unique (service_name, error_reason) combos matching filters

## Conventions

- Background task auto-archives noise messages every 60s based on active rules
- Frontend is a static SPA export served at `/` by FastAPI

## Dependencies

- **RabbitMQ** for message requeuing
- **Elasticsearch** for message search and storage
