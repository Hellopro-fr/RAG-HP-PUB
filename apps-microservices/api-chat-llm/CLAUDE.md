# api-chat-llm

Multi-provider LLM chat completion API supporting ChatGPT, DeepSeek, Gemini, and OpenRouter. Offers both REST and WebSocket streaming interfaces.

## Tech Stack

- **Language:** Python 3.10
- **Framework:** FastAPI + Uvicorn
- **LLM providers:** OpenAI, DeepSeek, Google GenAI, OpenRouter
- **gRPC:** Protobuf stubs for internal service communication
- **Shared libs:** `common_utils`, `grpc-stubs`

## Build / Run

- **Port:** 8540
- **Run:** `uvicorn main:app --host 0.0.0.0 --port 8540`
- **Tests:** `pytest tests/`
- **Docker build:** installs protobuf compiler, generates gRPC stubs at build time

## Folder Structure

```
api-chat-llm/
  main.py                   # FastAPI app
  app/
    core/
      chat.py               # LLMProvider, provider-specific completion functions
      credentials.py        # Settings (API keys, model names)
      ConnexionManager.py   # WebSocket connection manager
    router/
      chat.py               # REST + WS endpoints
    schemas/
      chat.py               # chatResponse, BatchChatRequest
    utils/
  tests/
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/llm/chat` | Chat completion (default provider) |
| `POST` | `/llm/chat/chatgpt` | ChatGPT completion |
| `POST` | `/llm/chat/deepseek` | DeepSeek completion |
| `POST` | `/llm/chat/gemini` | Gemini completion |
| `POST` | `/llm/chat/deepseek/batch` | Batch DeepSeek completions |
| `WS` | `/ws/chat` | Streaming chat via WebSocket |
| `GET` | `/` | Health check |

## Conventions

- `LLMProvider` class (Strategy pattern) selects provider from config.
- WebSocket streams token-by-token, sends `{"type": "end"}` on completion.
- Temperature is configurable per request.

## Dependencies on Other Services

- **OpenAI API**, **DeepSeek API**, **Google GenAI API**, **OpenRouter API**
- Internal gRPC services via `common_utils.grpc_clients`
