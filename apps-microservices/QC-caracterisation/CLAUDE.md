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
leur file** pendant ces fenêtres, puis reprennent.

Le module vit dans **`libs/common-utils/src/common_utils/autres/fenetre_tarifaire.py`**
depuis le 20-08-2026 : il était local à ce service (`app/core/`), et trois autres en ont
désormais besoin (QC-fabricant-reference, template-llm-service,
nettoyage-bruit-ocr-service). Il est sous `autres/` — namespace package sans
`__init__.py` et sans dépendance hors stdlib — parce qu'il est importé **à l'import du
consumer** : sous `rabbitmq/` ou `concurrency/`, l'`__init__` tirerait
`prometheus_client`/`redis`, que nettoyage-bruit-ocr-service n'installe pas, et le
conteneur mourrait au démarrage en boucle. Même leçon que `autres/graceful.py`
(commit `f74c83fc`).

La boucle est isolée dans **`Consumer.consommer_avec_garde(queue, sur_message)`** — pas
par goût de l'abstraction, mais parce que le test d'intégration en gardait une *copie* et
pouvait donc rester vert alors que le code livré avait changé. Il appelle maintenant cette
méthode.

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

Vérifié sur **aio_pika 9.6.2**, la version réellement déployée sur la VM (relevée le
18-08-2026 ; `requirements.txt` ne dit que `>=9.0.0`). Le `QueueIterator._on_close` de
cette version est identique à celui de 10.0.1 : `basic_cancel` puis
`nack(requeue=True, multiple=False)` sur tout le buffer de prefetch. L'horloge de la VM
a été relevée juste à la seconde le même jour.

Le message déjà sorti de l'itérateur au moment de la bascule est remis en file par un
`nack(requeue=True)` explicite (pas de dead-letter, pas de `x-death`, donc le compteur de
retry n'est pas touché). Ceux encore dans le buffer de prefetch le sont par la sortie du
`async with`, qui fait `basic_cancel` puis `nack(requeue=True)`.

Effet réel, remesuré le 20-08-2026 — **le chiffre annoncé ici auparavant (131,76 USD/mois)
était faux** : il reposait sur un total de 30 jours dominé par une **campagne ponctuelle**.
Découpage par semaine du process 30 :

| Semaine | Appels | Coût | dont heures pleines |
|---|---|---|---|
| **3 → 9 août** | **44 671** | **372,15 $** | 68,55 $ |
| 10 → 16 août | 534 | 5,80 $ | **0** |
| 17 → 19 août | 106 | 1,94 $ | **0** |

**95,5 % du volume tient dans une seule semaine**, et depuis le 10 août ce service ne fait
plus **aucun** appel en heures pleines. Sur 30 jours : 391,13 $ dont 69,74 $ au tarif
double, soit **34,87 USD/mois** récupérables — mais **0 en régime de croisière**.

La garde n'est donc pas une économie récurrente sur ce service : c'est une **assurance**,
qui aurait rendu 34 $ sur la seule semaine du 3-9 août et qui se rentabilisera à la
prochaine campagne de caractérisation. Contrepartie assumée : ces caractérisations sont
décalées de 3 à 4 h.

### Surcharger la grille horaire

La variable d'environnement **`DEEPSEEK_FENETRES_PLEINES`** remplace la grille, au format
`"1-4,6-10"` (heure de début incluse, heure de fin exclue, en UTC). Absente, la grille
DeepSeek s'applique. Une valeur illisible est **ignorée avec un avertissement** — jamais
une exception, sinon le conteneur mourrait à l'import et `restart: unless-stopped` le
relancerait en boucle. Toute surcharge active est signalée en `WARNING` au démarrage.

Deux usages : ajuster sans rebuild si DeepSeek change ses horaires, et forcer une fenêtre
courte pour **tester la garde contre un vrai broker** sans attendre 1 h du matin.

    DEEPSEEK_FENETRES_PLEINES=0-24   # tout est heure pleine : la garde suspend en permanence

### Tests

Les deux affirmations qui figuraient ici — « la boucle n'est pas couverte par les tests »
et « `aio_pika` n'est pas installable dans l'environnement de test local » — **étaient
fausses** ; corrigées le 20-08-2026.

| Quoi | Où | Comment le lancer |
|---|---|---|
| Bornes de la fenêtre, surcharge, innocuité de l'import (13 tests) | `libs/common-utils/tests/test_fenetre_tarifaire.py` | `PYTHONPATH=libs/common-utils/src pytest libs/common-utils/tests/test_fenetre_tarifaire.py -q` |
| Câblage : le consumer utilise-t-il la **vraie** garde ou un `MagicMock` ? (3 tests) | `tests/test_garde_fenetre_cablage.py` | `PYTHONPATH=. pytest tests/ -q` |
| Boucle réelle contre un **vrai** broker : rien perdu, rien en DLQ, aucun doublon | `tests/test_integration_garde_broker.py` | `RABBITMQ_URL_TEST=amqp://guest:guest@localhost:5672/ PYTHONPATH=. pytest tests/ -k integration -s` |

`aio-pika==9.6.2` s'installe sans difficulté dans un venv local, et un RabbitMQ jetable
(WSL, image Docker) suffit pour l'intégration. Validé le 20-08-2026 contre RabbitMQ 3.12.1 :
30 messages publiés, 14 traités, **16 en attente pendant la fenêtre**, 30/30 au retour,
0 en DLQ, 0 doublon.

Deux garde-fous à ne pas retirer :

- **anti-faux-vert** : le test d'intégration **échoue** si aucun message n'attendait
  pendant la fenêtre. Vécu deux fois — le 18-08 parce que le traitement était instantané,
  le 20-08 parce que le passage à un traitement concurrent vidait la file avant la
  bascule. Les deux fois, le test aurait affiché vert sans avoir rien suspendu ;
- **anti-faux-objet** : `tests/test_garde_fenetre_cablage.py` échoue si `common_utils` est
  stubbé. Un `MagicMock` est vrai en contexte booléen, donc une garde stubbée se croirait
  en heure pleine à toute heure et tous les tests de la boucle passeraient sur du vide.

## Dependencies on Other Services

- **Upstream**: QC-equivalence (step 6) publishes to `qc.step7.start`
- **HelloPro API**: REST calls via `HelloProAPIClient`
- **RabbitMQ**: required infrastructure
- **common-utils**: DLQPropertiesAsync, shared utilities

## Conventions

- Category-level deduplication via in-memory lock (per-replica only)
- Tracking files generated per run for observability
