# QC-fabricant-reference

Étape PSI 16 — extrait la **marque** et la **référence** de chaque produit depuis son
titre (et sa description si disponible) via le prompt 133 sur DeepSeek. Étape terminale :
aucune publication aval. Le statut fabricant/revendeur est calculé ensuite en SQL, côté BO.

## Tech Stack

- Python 3.10, asyncio
- RabbitMQ (aio_pika) — consumer async, retry + DLQ
- LLM : DeepSeek via client OpenAI-compatible (modèle configurable, `deepseek-v4-flash` par défaut)
- httpx (API HelloPro), Pydantic Settings, tenacity
- Pas de gRPC, pas de protobuf, pas de Gemini — image volontairement minimale

## Build / Run

```bash
# Build (contexte = racine du repo, pour libs/common-utils)
docker build -f apps-microservices/QC-fabricant-reference/Dockerfile .

# Tests unitaires (aucune I/O réelle, exécutables en local)
cd apps-microservices/QC-fabricant-reference && PYTHONPATH=. pytest tests/ -q
```

Entrypoint : `python main.py` (consumer RabbitMQ, pas de serveur HTTP).

## Folder Structure

```
QC-fabricant-reference/
  main.py                        # entrypoint asyncio
  app/
    core/
      fabricant_reference.py     # FabricantReferenceGenerator (logique métier)
      api_client.py              # HelloProAPIClient + DeepSeek
      utils.py                   # extraction JSON tolérante, tracking, stopper
      credentials.py             # pydantic-settings
    messaging/consumer.py        # qc.fabricant_reference.start
    schemas/fabricant_reference.py
  tests/                         # 51 tests, sans I/O
```

## Messaging

| Direction | Exchange | Routing Key | Queue |
|-----------|----------|-------------|-------|
| Consomme | `qc_pipeline_exchange` | `qc.fabricant_reference.start` | `qc_fabricant_reference_queue` |
| Publie | — | — | étape terminale |

Retry : `qc_retry_exchange` / `qc_fabricant_reference_queue_retry` (TTL 30 s, max 3).
DLQ : `qc_dead_letter_exchange` / `qc_fabricant_reference_queue_dlq`.

Déclenchement : `POST /ingestion-qc/publier` avec `service: "fabricant_reference"`.

## API HelloPro (etape `fabricant_reference` → `fabricant_reference.php`)

| field / action | Rôle |
|---|---|
| `produits` / `get` | Produits restants (`only_missing: true`) : `id_produit`, `titre`, `description`, `categorie` |
| `extraction` / `save` | Enregistre un batch de 10 extractions dans `produit_fabricant_reference` |
| `process` / `get` \| `reset` | Statut du run (`process_statut_ia`, étape 16) |
| `mail` / `success` \| `error` | Compte rendu de run |

Le prompt est lu via `prompt` / `info` / `get` (`id_prompt = 133`, table `action_prompt_chatgpt`).
Les coûts sont journalisés via `llm_tracking` (`type_ia = 2`, `id_process = 31`).

## Invariants — à ne pas casser

1. **Le prompt ne reçoit jamais de donnée fournisseur** (nom, site, email, domaine).
   Le statut fabricant/revendeur n'est démontrable que si les deux sources sont
   indépendantes ; sinon le modèle recopie le nom du fournisseur en marque et fabrique
   lui-même la concordance. `_assert_no_supplier_data()` lève, et un test le vérifie
   sur le prompt réellement envoyé.
2. **Le coût d'erreur est asymétrique** : une marque absente se récupère en aval
   (marque inférée depuis le catalogue du fournisseur) ; une marque fausse s'affiche
   publiquement. Tous les garde-fous de `_validate_extraction()` tranchent vers
   l'abstention.
3. **L'alignement du batch se fait sur `id_produit`, jamais sur l'ordre.** Un id manquant
   devient une abstention alertée, un id halluciné est ignoré.
4. **Une marque ou référence absente du texte source est rejetée** — « verbatim » implique
   présent dans le titre ou la description.
5. **Les sauvegardes d'un run sont sérialisées** (`_save_lock`), pas les appels LLM.
   Côté BO, `extraction/save` alimente aussi le référentiel des marques de la catégorie :
   deux batchs simultanés portant deux graphies d'une même marque (`Wacker-Neuson` /
   `Wacker Neuson`) ne la trouveraient ni l'un ni l'autre et créeraient deux lignes,
   scindant `nb_occurrences_fmr`. Un run = une catégorie, donc ce verrou suffit.

## Conventions

- 10 produits par appel LLM (le prompt ~2 900 tokens est amorti), 4 appels parallèles.
- Un batch en échec n'interrompt pas le run : les produits restent sans ligne et sont
  repris au run suivant via `only_missing`. Abandon seulement après
  `MAX_ECHECS_BATCH` (5) échecs **consécutifs**.
- Reprise : une ligne dans `produit_fabricant_reference` = produit déjà traité.
- Déduplication par catégorie locale au réplica (set in-memory) → `replicas: 1`.
- Arrêt manuel via `fichiers/stopper.json`, tracking par run dans `tracking/`.

## Dependencies on Other Services

- **API HelloPro** : produits, sauvegarde, prompt, mails, suivi LLM.
- **RabbitMQ** : infrastructure requise.
- **common-utils** : `DLQPropertiesAsync` uniquement.
- **Aval (hors service)** : rapprochement SQL fabricant/revendeur côté BO sur
  `produit_fabricant_reference` + `fabricant_marque_referentiel`.
