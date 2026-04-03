# stat-pj-service

Offline batch tool for auditing document quality in Milvus -- counts short-content documents per year.

## Tech Stack

- Python 3 (script-based, no Docker)
- pymilvus (Milvus client)
- PyMuPDF (fitz), httpx, jsonlines
- Bash orchestration script

## Build / Run

- **Local script** (no Dockerfile):
  ```bash
  python verif_nb_caractere_pj.py <year>
  # Or run all years:
  bash stat_pj.sh
  ```
- Requires: Milvus access, OCR service URL (`URL_OCR` env var)

## Folder Structure

```
stat-pj-service/
  verif_nb_caractere_pj.py    # Main script: reads JSONL, queries Milvus, OCR fallback
  stat_pj.sh                  # Bash loop runner (2018-2025)
  stat_colab/                 # Input JSONL files (page_counts_YYYY_less_than_*.jsonl)
  requirements.txt
```

## Conventions

- Reads JSONL files from `stat_colab/` directory per year.
- For each document: checks Milvus first, falls back to OCR (DeepSeek-OCR) if not found.
- Counts documents with fewer than 200 characters of content.
- Outputs results to `resultats_<year>.jsonl`.
- Uses async semaphore (20 concurrent tasks) to avoid file descriptor exhaustion.

## Dependencies on Other Services

- **Milvus** (direct connection, `document` collection)
- **DeepSeek-OCR** (HTTP, `URL_OCR` env var, for OCR fallback)
