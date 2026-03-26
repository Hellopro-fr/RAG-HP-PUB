# DeepSeek-OCR

FastAPI server wrapping the DeepSeek-OCR model with vLLM for high-performance document OCR.

## Tech Stack

- Python 3 (vLLM base image `vllm/vllm-openai:v0.8.5`)
- FastAPI + uvicorn on port **8501**
- vLLM engine with custom model registration (`DeepseekOCRForCausalLM`)
- PyMuPDF (fitz), Pillow, torch, flash-attn
- Dynamic batching for concurrent OCR requests

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/DeepSeek-OCR/Dockerfile .
  ```
- GPU required (CUDA). Model path: `/app/models/deepseek-ocr` (mounted volume).
- Config: `MAX_CONCURRENCY`, `NUM_WORKERS` env vars.

## Folder Structure

```
DeepSeek-OCR/
  start_server.py              # FastAPI app with dynamic batch processor
  custom_config.py             # Model config (image size, crop mode, prompt)
  custom_deepseek_ocr.py       # Custom model class
  custom_image_process.py      # Custom image preprocessing
  custom_run_dpsk_ocr_*.py     # Custom run scripts (PDF, image, batch eval)
  DeepSeek-OCR-master/         # Original DeepSeek-OCR source
  Dockerfile
  requirements.txt
```

## API Endpoints (port 8501)

| Method | Path | Description |
|---|---|---|
| GET | `/` | Health check |
| GET | `/health` | Detailed health (model, CUDA, queue) |
| POST | `/ocr/image` | OCR a single image (multipart upload) |
| POST | `/ocr/pdf` | OCR a PDF file (converts pages to images) |
| POST | `/ocr/batch` | OCR multiple files (images + PDFs) |

## Conventions

- Default prompt: `<image>\n<|grounding|>Convert the document to markdown.`
- Gundam mode: base_size=1024, image_size=640, crop_mode=True, 2-6 crops.
- DynamicBatchProcessor collects requests within 50ms window before GPU inference.
- Memory management: explicit `gc.collect()` + `torch.cuda.empty_cache()` after inference.

## Dependencies on Other Services

- None (standalone OCR service, consumed by other services via HTTP).
