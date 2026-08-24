# template-llm-service

RabbitMQ consumer that classifies web pages and OCR documents by type using an LLM.

⚠️ The model is **not** chosen here. This service calls `llm-service` over gRPC, and
`llm.proto` has no `provider` or `model` field — whatever a caller puts in its Pydantic
`ChatRequest` is silently dropped at the gRPC hop. `llm-service`'s own `LLM_PROVIDER`
decides alone. Measured on the VM on 19-08-2026: `LLM_PROVIDER=deepseek` and
`DEEPSEEK_MODEL_NAME=deepseek-chat` — and `deepseek-chat` is an **alias DeepSeek routes to
`deepseek-v4-flash`** (proven from production by the response's `model` field *and* an
identical `system_fingerprint`). So this service bills DeepSeek v4-flash, not R1 as this
line claimed until 20-08-2026.

## Tech Stack

- Python 3.11, asyncio
- RabbitMQ (aio-pika) with batch processing, retry/DLQ
- gRPC client (to llm-service)
- transformers AutoTokenizer (for token counting/truncation)
- Prometheus metrics on port **8530**
- Shared libs: `grpc-stubs`, `common-utils`

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/template-llm-service/Dockerfile .
  ```
- Tests: `pytest tests/` (test_messaging.py, test_qualifier.py)

## Folder Structure

```
template-llm-service/
  app/
    main.py                  # Entrypoint, connects to RabbitMQ
    core/processor.py        # Page classification logic, prompt templates
    messaging/
      consumer.py            # Batch consumer (BATCH_SIZE=16, TIMEOUT=2s)
      publisher.py           # Publishes classified results + metrics
  tests/
  start.sh
  requirements.txt
  Dockerfile
```

## RabbitMQ Topology

- **Queue**: `llm_templating_queue` (routing key: `data.ready_for_templating`)
- **Retry**: 30s TTL, max 3 retries
- **DLQ**: `llm_templating_queue_dlq`
- Messages grouped by collection type before batch processing.

## Conventions

- Classifies into predefined page types: `home`, `fiche_produit`, `catalogue`, `devis`, etc.
- Prompts truncated at 127,488 tokens (DeepSeek-R1 128K context - 512 safety margin).
- Batch processor collects up to 16 messages or waits 2s, then sends concurrent LLM calls.

## Fenetre tarifaire DeepSeek (heures creuses)

DeepSeek facture les heures pleines **au double** (`01:00-04:00` et `06:00-10:00` UTC).
Ce service ne pioche pas dans sa file : il s'y **abonne**. La garde annule donc
l'abonnement (`queue.cancel(tag)`) pendant les fenetres cheres et le retablit apres --
voir `Consumer._boucle_fenetre_tarifaire`.

Le tampon interne (`message_buffer`) est borne par le prefetch (`BATCH_SIZE` = 16) : au
pire 16 messages sont traites au tarif double a chaque bascule, mesure a ~1,6 % du volume
quotidien. Le vider en `nack` a ete essaye puis **abandonne** : `nack()` leve
`MessageProcessError` sur un message deja acquitte, donc l'operation court contre le
`batch_processor` qui acquitte au meme moment.

**Les erreurs de canal et de connexion ne sont pas attrapees, volontairement.** `main.py`
les traite deja (`except (AMQPConnectionError, ChannelInvalidStateError)`) en
reconstruisant connexion + consumer. Une premiere version les avalait et retentait :
apres une coupure, `queue` restait attachee au canal mort et la boucle retentait a
l'infini -- service muet, rien en DLQ, aucune alerte. C'est aussi pourquoi la boucle est
**awaitee** dans `start_consuming()` et non lancee en `create_task()`.

Prouve contre un vrai broker (RabbitMQ 3.12.1, `aio_pika` 9.6.2, le 20-08-2026) --
`tests/test_integration_garde_callback.py`, 5 phases : suspension exercee (8 messages en
attente), 0 DLQ, tampon vide en 0,36 s, **coupure reseau en pleine fenetre sans
reabonnement**, 40/40 messages au retour, 0 doublon, et l'erreur de canal qui remonte.

`DEEPSEEK_FENETRES_PLEINES` (format `"1-4,6-10"`, UTC) surcharge la grille. Ce service a
un `env_file: .env`, donc la variable y suffit -- rien a ajouter au bloc compose.

## Dependencies on Other Services

- **llm-service** (gRPC, via `common_utils.grpc_clients.llm_client`)
- **RabbitMQ**
