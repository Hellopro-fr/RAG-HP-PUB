# api-transcription-service

Real-time audio transcription service using WebSocket streaming. Supports Google Speech-to-Text and OpenAI Realtime API backends.

## Tech Stack

- **Language:** Python 3.10
- **Framework:** FastAPI + Uvicorn
- **Speech-to-Text:** Google Cloud Speech, OpenAI Realtime API
- **WebSocket:** websockets 12.0
- **No shared libs** (standalone service)

## Build / Run

- **Port:** 8515
- **Run:** `uvicorn app.main:app --host 0.0.0.0 --port 8515`
- **Note:** entrypoint is `app.main:app` (not `main:app`)

## Folder Structure

```
api-transcription-service/
  app/
    main.py                          # FastAPI app
    api/
      endpoints.py                   # WebSocket endpoints
    core/
      models.py                      # Domain models
      services.py                    # TranscriptionService, OpenAIRealtimeService
    infrastructure/
      websocket_manager.py           # WebSocketManager, OpenAIRealtimeWebSocketManager
  config/
    settings.py                      # AUTH_TOKEN, etc.
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `WS` | `/ws/google/transcription` | Google Speech-to-Text streaming |
| `WS` | `/ws/openai/transcription` | OpenAI Realtime API transcription |

## Conventions

- WebSocket auth via `token` query parameter (compared to `settings.AUTH_TOKEN`).
- Dependency injection pattern: `get_speech_client` -> `get_transcription_service` -> `get_websocket_manager`.
- Clean Architecture layers: `api/` (endpoints), `core/` (services), `infrastructure/` (WebSocket managers).

## Dependencies on Other Services

- **Google Cloud Speech-to-Text API**
- **OpenAI Realtime API**
