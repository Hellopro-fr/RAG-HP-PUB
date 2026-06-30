# QC-equivalence

QC pipeline step 6 -- generates equivalences between product characteristics via LLM.

Also hosts an independent **BO facade** (`generate_equivalences_bo`) that produces
equivalences for the alternate BO questionnaire (ANNUAIRE_BO) onto the **same**
category characteristic set, for price-range use on another questionnaire. It runs
in the same process via a second consumer, **publishes nothing downstream**, and
saves to a dedicated table (`equivalence_question_caracteristique_bo`).

## Tech Stack

- Python 3.10, asyncio
- RabbitMQ (aio_pika) -- async consumer/publisher
- gRPC (grpcio, protobuf) via shared `grpc-stubs`
- LLM: Google Gemini (`google-genai`) + OpenAI
- Pydantic Settings, tenacity, requests

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/QC-equivalence/Dockerfile .
  ```
- Entrypoint: `python main.py` (RabbitMQ consumer, no HTTP server)
- Shared libs: `libs/common-utils`, `libs/grpc-stubs`

## Folder Structure

```
QC-equivalence/
  main.py
  Dockerfile
  requirements.txt
  app/
    core/
      equivalence_generator.py     # business logic (EquivalenceGenerator)
      api_client.py                # HelloPro API client
      credentials.py
      ConnexionManager.py
      utils.py
    messaging/
      consumer.py                  # listens on qc.step6.start
      consumer_bo.py               # listens on qc.equivalence_bo.start (BO facade, no publish)
      publisher.py                 # publishes to qc.step7.start
    schemas/
      question_caracteristique.py
  tests/
    test_equivalence_generator.py  # BO facade unit tests
    test_consumer_bo.py            # BO consumer routing/isolation tests
```

## Backend endpoints required (PHP, BO/api/v2/)

The BO facade depends on three backend actions (to be implemented):
- `question / all_bo / get` — returns `ao_questions_criteres_algo_v2($id_rubrique)` **as-is**
  (native flat list of questions, no IA normalization).
- `equivalence / reponse_bo / save` — writes to `equivalence_question_caracteristique_bo`.
- `equivalence / reponse_bo / reset` — clears BO equivalences for a category (is_reset).

Also add step `14` to `envoie_mail`'s `$all_step` map in `function.php`
(e.g. `"14" => "Équivalence questionnaire BO -> Caractéristiques"`).

## Messaging

| Direction | Exchange              | Routing Key            | Queue                     |
|-----------|-----------------------|------------------------|---------------------------|
| Consumes  | qc_pipeline_exchange  | qc.step6.start         | qc_equivalence_queue      |
| Publishes | qc_pipeline_exchange  | qc.step7.start         | --                        |
| Consumes  | qc_pipeline_exchange  | qc.equivalence_bo.start | qc_equivalence_bo_queue  |

- Retry/DLQ: same pattern as other QC services (TTL 30s, max 3 retries)
- **BO facade** (`qc.equivalence_bo.start`): independent consumer, **no publish** (terminal),
  mail step `14` (next `$all_step` entry). Message: `{id_categorie, source="BO", is_reset}`.
  Reuses prompt 101 + the category's final characteristic set; saves via
  `equivalence/reponse_bo/save`. The BO questionnaire keeps its **native flat format**
  (a list of questions q1..n, each with `id`/`question`/`choix:[{id, choix}]`) — no
  Q1/Q2..N normalization. Characteristics are excluded cumulatively along the list.

## Dependencies on Other Services

- **Upstream**: QC-enrichissement (step 5) publishes to `qc.step6.start`
- **Downstream**: QC-caracterisation (step 7) consumes from `qc.step7.start`
- **HelloPro API**, **RabbitMQ**, **common-utils**

## Conventions

- Category deduplication per-replica only; cross-replica dedup handled by backend `can_start`
- Tracking files for observability
