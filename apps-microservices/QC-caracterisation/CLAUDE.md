# QC-caracterisation

QC pipeline step 7 (final) -- generates product characterizations via LLM for a given category.

## Tech Stack

- Python 3.10, asyncio
- RabbitMQ (aio_pika) -- async consumer/publisher
- gRPC (grpcio, protobuf) via shared `grpc-stubs`
- LLM: **DeepSeek v4-pro** via client OpenAI-compatible (`DEEPSEEK_MODEL = "deepseek-v4-pro"`,
  `caracterisation_produit.py`). `google-genai` et `openai` sont installés mais ce chemin-là
  n'est plus utilisé pour la caractérisation — mesuré sur 30 jours : 46 707 appels DeepSeek
  (`type_ia=2`, `id_process=30`), zéro appel Gemini depuis ce service.
- Pydantic Settings, tenacity (retry), requests

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/QC-caracterisation/Dockerfile .
  ```
- Entrypoint: `python main.py` (RabbitMQ consumer, no HTTP server)
- Shared libs installed at build: `libs/common-utils`, `libs/grpc-stubs`
- Protos compiled at build from `protos/`

## Folder Structure

```
QC-caracterisation/
  main.py                          # asyncio entrypoint
  Dockerfile
  requirements.txt
  app/
    core/
      caracterisation_produit.py   # business logic (CaracterisationProduitGenerator)
      api_client.py                # HelloPro API client
      credentials.py               # pydantic-settings config
      ConnexionManager.py
      utils.py
    messaging/
      consumer.py                  # listens on qc.step7.start
      publisher.py                 # publishes to qc.complete
    schemas/
      question_caracteristique.py  # RequestProcessus model
```

## Messaging

| Direction | Exchange              | Routing Key      | Queue                       |
|-----------|-----------------------|------------------|-----------------------------|
| Consumes  | qc_pipeline_exchange  | qc.step7.start   | qc_caracterisation_queue    |
| Publishes | qc_pipeline_exchange  | qc.complete      | --                          |

- Retry: `qc_retry_exchange` / `qc_caracterisation_queue_retry` (TTL 30s)
- DLQ: `qc_dead_letter_exchange` / `qc_caracterisation_queue_dlq`
- Max retries: 3, concurrency controlled via `settings.MAX_CONCURRENCY`

## Fenêtre tarifaire DeepSeek (heures creuses)

DeepSeek facture les heures pleines **au double** depuis le 16-08-2026, avec des bornes
fixées **en UTC** : `01:00-04:00` et `06:00-10:00`. Les deux consumers **se détachent de
leur file** pendant ces fenêtres (`app/core/fenetre_tarifaire.py`), puis reprennent.

Pourquoi se détacher plutôt que refuser les messages — les deux autres approches sont
des pièges mesurés sur ce service :

- un `nack` enverrait le message en **DLQ en 90 s** (`RETRY_TTL_MS` 30 s x `MAX_RETRIES` 3) ;
- le garder non-acké heurterait **`x-consumer-timeout` = 7 200 000 ms (2 h)**, alors qu'une
  fenêtre pleine dure 3 à 4 h.

Détaché, le consumer laisse les messages en `READY`. Vérifié sur le broker le 18-08-2026 :
aucune policy (`policy` et `operator_policy` à `null`, `effective_policy_definition` vide),
et les files sont `durable=true` / `auto_delete=false` — donc rien n'expire et rien ne
disparaît pendant la suspension. **Si une policy `message-ttl` ou `expires` était ajoutée
un jour sur ces files, cette garde deviendrait destructrice** : le vérifier avant.

Le message déjà sorti de l'itérateur au moment de la bascule est remis en file par un
`nack(requeue=True)` explicite (pas de dead-letter, pas de `x-death`, donc le compteur de
retry n'est pas touché). Ceux encore dans le buffer de prefetch le sont par la sortie du
`async with`, qui fait `basic_cancel` puis `nack(requeue=True)`.

Effet attendu : 8 546 des 46 707 appels mensuels sortaient en heures pleines, soit
**131,76 USD/mois**. Contrepartie assumée : ces caractérisations sont décalées de 3 à 4 h.

⚠️ La boucle elle-même n'est **pas** couverte par les tests : `aio_pika` exige un vrai
broker et n'est pas installable dans l'environnement de test local. Seules les bornes le
sont (`tests/test_fenetre_tarifaire.py`, balayage des 24 heures).

## Dependencies on Other Services

- **Upstream**: QC-equivalence (step 6) publishes to `qc.step7.start`
- **HelloPro API**: REST calls via `HelloProAPIClient`
- **RabbitMQ**: required infrastructure
- **common-utils**: DLQPropertiesAsync, shared utilities

## Conventions

- Category-level deduplication via in-memory lock (per-replica only)
- Tracking files generated per run for observability
