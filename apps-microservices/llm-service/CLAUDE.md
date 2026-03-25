# llm-service

LLM gateway exposing chat completion via gRPC, supporting DeepSeek, vLLM, and Gemini backends.

## Tech Stack

- Python 3.10, asyncio, uvloop
- gRPC (grpcio, protobuf) on port **50051**
- OpenAI-compatible client (httpx, openai)
- Shared libs: `grpc-stubs`, `common-utils`

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/llm-service/Dockerfile .
  ```
- No local test/lint config detected.

## Folder Structure

```
llm-service/
  app/main.py                  # Entrypoint, wires ChatApplicationService -> gRPC server
  application/chat_service.py  # Business logic: stream, completion, batch
  infrastructure/
    grpc_server.py             # gRPC servicer (ChatStream, Chat, ChatBatch)
    deepseek_client.py         # DeepSeek API client
    vllm_client.py             # vLLM client
    gemini_client.py           # Gemini client
  requirements.txt
  Dockerfile
```

## gRPC Methods (port 50051)

| Method | Type | Description |
|---|---|---|
| `ChatStream` | Bidirectional stream | Multi-turn streaming chat |
| `Chat` | Unary | Single prompt -> full response (dict/Struct) |
| `ChatBatch` | Unary | Parallel completion for a list of messages |

## Conventions

- LLM backend selected via `LLM_PROVIDER` env var (`deepseek` or `vllm`).
- Clean Architecture: `app/` (entry), `application/` (use cases), `infrastructure/` (adapters).
- Proto stubs generated at Docker build time from `protos/grpc_stubs/*.proto`.

## Dependencies on Other Services

- None (this is a leaf service consumed by others via gRPC).
