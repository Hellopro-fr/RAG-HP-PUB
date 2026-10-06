# graph-rag-normalize-unite-service-dynamique

Version **dynamique** (SQL-driven) du service de normalisation d'unités. Identique
fonctionnellement à `graph-rag-normalize-unite-service`, mais les mappings/alias ne
sont plus hardcodés : ils proviennent d'un référentiel en base, rechargeable à chaud.
Expose le contrat **gRPC historique** + une **API REST** (matching prix, scripts externes).

## Tech Stack

- Python 3.10
- gRPC server (grpcio + protobuf) — contrat identique au service historique
- FastAPI + uvicorn (API REST) + httpx (lecture référentiel BO v2)
- pint (conversion d'unités)
- Prometheus metrics

## Pourquoi un nouveau service (et pas une modif de l'existant)

L'historique reste intact (rollback trivial). Le dynamique charge la donnée par-unité
depuis la base via BO v2 : les 3 dictionnaires (`UNIT_TO_DIMENSION`,
`LABEL_TO_DIMENSION`, `CANONICAL_UNITS`), les `pint define()`, ET l'essentiel de
l'ancienne chaîne `if/elif` de sanitisation, éclatée en 2 tables (preprocessing
universels + réécritures/bypass). Le code ne contient que l'**interpréteur générique**.
Seule exception assumée : la **désambiguïsation contextuelle** (nm / t/min / G, 3 cas)
reste statique en code (`_STATIC_DISAMBIGUATIONS`) — croissance quasi nulle, schéma DB
injustifié. Alimente la boucle d'auto-apprentissage LLM (service `learner`).

## Build & Run

```bash
docker build -f apps-microservices/graph-rag-normalize-unite-service-dynamique/Dockerfile .
# Entrypoint : python -m app.main  (uvicorn REST + gRPC en thread démon)
```

- **gRPC** : port 50057 (contrat `GraphNormalizationService` inchangé)
- **REST** : port 8567
- **Prometheus** : port 8557

## Folder Structure

```
app/
  main.py            # entrypoint : load référentiel (fail-fast+retry) → gRPC thread + uvicorn
  config.py          # GRPC_PORT, REST_PORT, BO_V2_URL, REFERENTIEL_TTL_SECONDS, RELOAD_AUTH_TOKEN
application/
  normalization_use_case.py     # use case (normalizer INJECTÉ, pas de singleton import-time)
infrastructure/
  referentiel_loader.py         # httpx BO v2 → Referentiel (dicts+defines+preprocessing+rewrites+disambig)
  unit_normalization_service.py # _NormalizerState (interpréteur générique pint) + swap atomique
  grpc_server.py                # serveur gRPC (contrat identique)
  rest_api.py                   # FastAPI : /normalize/{quantity,range,batch,compare}, /admin/reload, /health
scripts/
  legacy_referentiel.py         # pont vers le service historique (source du seed/parité)
  seed_referentiel_unite.py     # génère sql/03_seed_referentiel.sql + fixture JSON
sql/
  01_referentiel_unite.sql      # DDL 4 tables référentiel (mappings + canoniques + defines)
  01b_sanitisation_unite.sql    # DDL 2 tables sanitisation (preprocessing, reecriture)
  02_apprentissage_unite.sql    # DDL table dédup/journal learner
  03_seed_referentiel.sql       # INSERT seed (généré, 7 tables)
tests/
  test_parity.py                # parité STRICTE ancien vs dynamique (go/no-go cutover)
  test_reload.py                # reload + swap atomique + priorité labels + define corrompu
conftest.py                     # sys.path pour les tests
```

## API REST

| Méthode | Route | Usage |
|---|---|---|
| POST | `/normalize/quantity` | `{label, unit, value, data_type}` → `{success, valeur_canonique, unite_canonique}` |
| POST | `/normalize/range` | `{label, unit, min_value, max_value}` |
| POST | `/normalize/batch` | `{items:[...]}` (matching prix multi-critères) |
| POST | `/normalize/compare` | `{label, value_a, unit_a, value_b, unit_b, operator, tolerance}` → `{match, comparable, canonical_a, canonical_b}` |
| POST | `/admin/reload` | recharge le référentiel (header `x-reload-token` si `RELOAD_AUTH_TOKEN`) |
| GET | `/health` | liveness |

## Référentiel & concurrence

- Source : `POST {BO_V2_URL}` body `{etape:"normalisation", field:"referentiel", action:"get"}`.
- Chargement **fail-fast** au démarrage (5 retries). `Referentiel.validate()` rejette un
  payload BO mal formé (sections cœur vides) — sinon panne totale silencieuse (`/health` vert
  mais zéro normalisation). Idem au `/admin/reload` : un référentiel invalide ne remplace pas l'état courant.
- Règles de **preprocessing validées + regex compilées au build** : une règle invalide est
  ignorée (tracée dans `preprocessing_errors`, remontée par `reload()`), jamais d'erreur au runtime.
- Refresh périodique (`REFERENTIEL_TTL_SECONDS`, défaut 300s) via lifespan FastAPI ; le
  learner déclenche en plus un `/admin/reload` immédiat après apprentissage.
- **Swap atomique** : `reload()` reconstruit un `_NormalizerState` complet (registre pint
  neuf + dicts) puis remplace la référence sous lock. Le chemin de lecture prend un snapshot
  de référence sans lock (sûr sous les workers gRPC).
- **Ordre critique** : `label_dimension.priorite` (match sous-chaîne : spécifique avant
  générique) et `unite_definition.ordre` (dépendances entre `define`) — préservés au chargement.

## Tests

```bash
cd apps-microservices/graph-rag-normalize-unite-service-dynamique
python -m scripts.seed_referentiel_unite      # régénère seed SQL + fixture JSON
python -m pytest tests/ -q                     # parité + reload (5 tests)
```

`test_parity.py` est le **filet go/no-go** : il alimente le moteur dynamique avec les
données du service historique et vérifie des sorties canoniques strictement identiques
sur tout le corpus (201 unités + 99 labels + cas réels).

## Dépendances

- **BO v2 PHP** : `normalisation/referentiel/get` (lecture). Endpoints à créer côté racine PHP (Lot 1).
- **common-utils** : `metrics.prometheus.start_metrics_server_in_thread`.
- **grpc-stubs** : `graph_normalization_pb2[_grpc]` (proto inchangé).

## Limite assumée

Toute la donnée par-unité est dynamique (mappings, alias pint, réécritures, bypass,
désambiguïsations). Le learner peut donc enseigner une unité inédite en ajoutant une
ligne dans la table adéquate (`unite_dimension_ia`, `unite_reecriture_ia`, etc.).
Restent en code, génériques et non spécifiques à une unité : l'**interpréteur** et le
**type** des transforms de preprocessing (`nfkc`/`regex_sub`/`str_replace`). Un besoin
de transform d'un type radicalement nouveau (très rare) reste le seul cas exigeant du code.
