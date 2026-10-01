# nettoyage-bruit-ocr-service

RabbitMQ consumer that cleans OCR-extracted text using LLM to remove legal/marketing noise.

## Tech Stack

- Python 3.11, asyncio
- RabbitMQ (aio-pika) with retry/DLQ
- gRPC client (to llm-service) with thinking mode enabled
- httpx
- Shared libs: `grpc-stubs`, `common-utils`

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/nettoyage-bruit-ocr-service/Dockerfile .
  ```

## Folder Structure

```
nettoyage-bruit-ocr-service/
  app/
    main.py                  # Entrypoint, connects to RabbitMQ
    core/processor.py        # LLM-based text cleaning logic
    messaging/
      consumer.py            # Single-message consumer with keep-alive
      publisher.py           # Publishes cleaned text + metrics
  tests/
    test_processor.py        # JSON escape sanitization tests
  requirements.txt
  Dockerfile
```

## RabbitMQ Topology

- **Queue**: `nettoyage_bruit_ocr_queue` (routing key: `data.ready_for_ocr_cleaning`)
- **Retry**: 30s TTL, max 3 retries
- **DLQ**: `nettoyage_bruit_ocr_queue_dlq`
- Prefetch: 1 (sequential processing)

## Conventions

- Removes 5 categories: legal mentions, contractual clauses, disclaimers, regulatory notes, marketing slogans.
- Non-French content returns empty string (filtered out).
- Uses `enable_thinking=True` for LLM calls (max 64K output tokens).
- ACK-after strategy: messages acknowledged AFTER successful processing or DLQ routing (at-least-once delivery).
- Channel keep-alive task runs every 30s to prevent timeout on long LLM calls.
- DLQ sends the correct individual message body (not hardcoded `batch_bodies[0]`).
- Reconnection loop restored in `main.py` (was commented out).
- Docker: non-root user, `--no-cache-dir`, `.dockerignore`.
- Structured logging via `common_utils.logging.setup_logging()` (no `print()`).

## Recent Reliability Fixes

- **Content truncation**: `MAX_CONTENT_CHARS=60000` in `make_chat_request()` prevents LLM context window overflow (131K tokens) from OCR artifacts with massive repeated blocks.
- **JSON escape sanitization**: LLM responses may contain invalid JSON escapes (`\e`, `\s`, `\a`). A regex sanitization step (`re.sub`) fixes lone backslashes before `json.loads()`. If parsing still fails (mixed valid/invalid escapes), fallback passes original text through unchanged rather than losing the document to DLQ.

## Fenetre tarifaire DeepSeek (heures creuses)

DeepSeek facture les heures pleines **au double** (`01:00-04:00` et `06:00-10:00` UTC).
Comme template-llm-service, ce service s'**abonne** a sa file : la garde annule
l'abonnement pendant les fenetres cheres et le retablit apres
(`Consumer._boucle_fenetre_tarifaire`).

Ici `prefetch_count=1`, donc le tampon vaut **au plus 1 message** : la fuite est d'un
seul message par bascule.

Les erreurs de canal et de connexion ne sont pas attrapees -- `main.py` les traite en
reconstruisant connexion + consumer. Detail du raisonnement et preuve contre un vrai
broker : `apps-microservices/template-llm-service/CLAUDE.md` et
`.../tests/test_integration_garde_callback.py` (meme forme de boucle).

Effet mesure le 20-08-2026 (`id_process = 33`) : 3,31 $ sur 30 jours, dont **2,03 $ au
tarif double** -> ~1,02 $/mois. Contrepartie : les nettoyages sont decales de 3 a 4 h.

`DEEPSEEK_FENETRES_PLEINES` (format `"1-4,6-10"`, UTC) surcharge la grille ; ce service a
un `env_file: .env`, donc rien a ajouter au bloc compose.

## Dependencies on Other Services

- **llm-service** (gRPC, via `common_utils.grpc_clients.llm_client`)
- **RabbitMQ**
