# prix-caracterisation

Caractérisation des prix Milvus (collection `prix`) via le jeu de caractéristiques de la catégorie. Peuple la table `caracterisation_prix_produit_ia` (_cppi) à partir des 4 sources (produit / message / devis / siteweb).

## Tech Stack

- Python 3.10, asyncio
- RabbitMQ (aio_pika) — async consumer/publisher
- LLM: DeepSeek (via `openai` SDK) avec retry tenacity sur 429/503 (max_retries=5)
- Milvus : **accès direct via pymilvus** (pattern api-rest-milvus/app/core/api_rest_milvus.py)
- httpx (appels BO v2 uniquement)
- Pydantic Settings

## Build / Run

- **Docker-only build** (context = repo root) :
  ```
  docker build -f apps-microservices/prix-caracterisation/Dockerfile .
  ```
- Entrypoint : `python main.py` (consumer RabbitMQ, pas de HTTP server)
- Shared lib : `libs/common-utils`

## Folder Structure

```
prix-caracterisation/
  main.py                          # asyncio entrypoint
  Dockerfile
  requirements.txt
  app/
    core/
      caracterisation_prix.py      # CaracterisationPrixGenerator (logique métier)
      api_client.py                # HelloProAPIClient + DeepSeek (retry 429/503)
      milvus_client.py             # MilvusPrixClient — accès direct pymilvus, pagination Milvus
      credentials.py               # pydantic-settings (PROMPT IDs, MILVUS_PAGE_SIZE)
      utils.py                     # extract_json_from_text, tracking files, get_prompt
    messaging/
      consumer.py                  # listens on prix.caracterisation.start
      publisher.py                 # publishes to prix.caracterisation.complete
    schemas/
      caracterisation_prix.py      # RequestProcessus, CaracterisationPrixResult
```

## Messaging

| Direction | Exchange                  | Routing Key                     | Queue                        |
|-----------|---------------------------|---------------------------------|------------------------------|
| Consumes  | `prix_pipeline_exchange`  | `prix.caracterisation.start`    | `prix_caracterisation_queue` |
| Publishes | `prix_pipeline_exchange`  | `prix.caracterisation.complete` | —                            |

- Retry : `prix_retry_exchange` / `prix_caracterisation_queue_retry` (TTL 30s)
- DLQ : `prix_dead_letter_exchange` / `prix_caracterisation_queue_dlq`
- Max retries : 3, concurrency contrôlée via `settings.MAX_CONCURRENCY`

**Routing indépendant du pipeline QC 1-7** (pas d'utilisation de `qc_pipeline_exchange`).

## Message Payload

```json
{
  "id_categorie": "2007702",
  "is_reset":     false,
  "source":       "devis"   // optionnel : filtre sur une source (devis/message/produit/siteweb)
}
```

## Flux par catégorie

1. **Milvus** : accès direct pymilvus (`collection.query(expr, output_fields, limit, offset)`) — récupère tous les points `prix` par `(id_categorie, source?)` avec pagination (offset+limit ≤ 16384 par contrainte Milvus). Connexion partagée au niveau module via `common_utils.database.config.Configuration` (ZILLIZ_URI / ZILLIZ_PORT / ZILLIZ_USER / ZILLIZ_PASSWORD).
2. **Déjà traités** : `POST v2/prix/caracterisation/get` — récupère la liste des `id_prix_milvus` déjà présents dans `_cppi`.
3. **Filtre** : garde uniquement les points Milvus non traités.
4. **Caractérisation** (par item, parallélisé) :
   - `source = produit` → copie depuis `caracterisation_produit_ia` (mode `copy_from_cpi`). Payload minimal : `{id_prix_milvus, source, id_cible=id_produit}` — l'API BO réhydrate les caracs.
   - `autre source` → LLM DeepSeek 2 passes (extraction + repasse) comme `QC-caracterisation`.
5. **Save** :
   - `POST v2/prix/caracterisation/save_produit` → batch pour source produit
   - `POST v2/prix/caracterisation/save` → batch pour autres sources
6. **Mail fin** : `POST v2/prix/mail/success`.

## Endpoints API BO v2 requis (à créer côté PHP)

| Endpoint | Usage |
|----------|-------|
| `prix/caracterisation/get` | Liste des `id_prix_milvus` déjà caractérisés (filtre catégorie + source) |
| `prix/caracterisation/reset` | Purge _cppi pour une catégorie (+ source optionnelle) |
| `prix/caracterisation/save` | Insert batch _cppi depuis payload LLM (caracs expand en lignes) |
| `prix/caracterisation/save_produit` | Insert batch _cppi en réhydratant depuis `caracterisation_produit_ia` |

## Conventions

- Dédoublonnage catégorie in-memory par réplica (`_processing_categories`)
- Tracking file par run : `tracking/<yyyy>/<mm>/<timestamp>-tracking-prix-caracterisation-<id_categorie>.txt`
- Logs bufferisés par item (contextvar) pour éviter l'entrelacement en parallèle
- Prompts chargés depuis BDD `action_prompt_chatgpt` (IDs `PROMPT_CARACTERISATION_ID` / `PROMPT_REPASSE_ID`)
- Tracking LLM via `log_llm_usage` (type_ia=2, id_process=38, origine=`prix-caracterisation[-repasse]`)
- Étape projet `_psi` : `ETAPE=11` (hors pipeline QC 1-7)
- `MilvusPrixClient.search_prix()` est **synchrone** (pymilvus) — enveloppé par `asyncio.to_thread` côté consommateur pour ne pas bloquer l'event loop

## Prérequis métier

- Jeu de caractéristiques final disponible pour la catégorie (étape QC 5 terminée).
- Table `caracterisation_prix_produit_ia` (_cppi) créée en BDD.
- Prompts `PROMPT_CARACTERISATION_ID` et `PROMPT_REPASSE_ID` présents dans `action_prompt_chatgpt`.

## Dependencies on Other Services

- **Milvus (Zilliz Cloud)** : connexion directe pymilvus via env `ZILLIZ_URI / ZILLIZ_PORT / ZILLIZ_USER / ZILLIZ_PASSWORD` (pas de passage par api-rest-milvus)
- **HelloPro API BO v2** : `prix/caracterisation/{get,save,save_produit,reset}`, `caracteristique/final/get`, `category/info/get`, `prompt/info/get`, `prix/mail/{success,error}`, `llm_tracking`
- **RabbitMQ** : infrastructure messaging
- **common-utils** : `DLQPropertiesAsync`, `database.config.Configuration` (lit ZILLIZ_*)
