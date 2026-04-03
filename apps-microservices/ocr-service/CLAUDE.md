# ocr-service

OCR service using docext (Nanonets-OCR-s) with a Gradio UI and vLLM backend.

## Tech Stack

- Python 3.11 (venv inside `vllm/vllm-openai:v0.8.2` base image)
- docext framework (Gradio app) on port **8559**
- vLLM v0.8.3 with flash-attn, xgrammar
- Model: `hosted_vllm/nanonets/Nanonets-OCR-s`
- poppler-utils for PDF handling

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/ocr-service/Dockerfile .
  ```
- GPU required (CUDA).
- Entrypoint runs docext Gradio app with internal vLLM server on port 8181.

## Folder Structure

```
ocr-service/
  api_server.py         # vLLM OpenAI-compatible server (customized)
  Dockerfile            # Multi-stage: vLLM base + docext + flash-attn
  Dockerfile.override   # Alternative Dockerfile
  requirements.txt
```

## Conventions

- docext handles OCR via its Gradio interface with concurrency limit of 15.
- Internal vLLM server runs on port 8181, Gradio UI exposed on port 8559.
- CUDA graph patch applied at build time to force `enforce_eager=False`.

## Dependencies on Other Services

- None (standalone OCR service).
