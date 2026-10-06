# graph-rag-normalize-unite-learner

Apprentissage **manuel par lot** des unités inconnues. Déclenché à la demande, draine N
messages de la *manual DLQ* de normalisation, demande à un LLM la règle manquante par
unité, la **valide via le vrai moteur** (service dynamique), et écrit la règle en base
**INACTIVE** — l'activation de la nouvelle unité reste un **geste humain**.

Remplace l'ancien geste manuel (« ajouter un `FIX N` en dur + redéployer ») tout en
gardant l'humain dans la boucle pour l'activation.

## Tech Stack

- Python 3.10, asyncio
- FastAPI + uvicorn (déclenchement manuel `POST /run`)
- RabbitMQ (aio_pika) — drain ponctuel (`queue.get`), pas de consumer continu
- LLM : DeepSeek (`openai` SDK) + retry tenacity 429/503
- httpx (BO v2 + Gate 1 via service dynamique)
- Prometheus

## Déclenchement

```
POST {host}:8566/run        body {"limit": 100}   # limit optionnel (défaut 100)
GET  {host}:8566/health
```
Un seul run à la fois (verrou). **1 seul réplica** recommandé.

## Flux d'un run (BatchRunner — `app/core/batch.py`)

```
1. fetch référentiel BO (dimensions/canoniques existantes) — pour l'input LLM
2. drain ≤ limit messages du manual DLQ (graph_rag_normalization_manual_dlq)
3. dédup PAR UNITÉ (1 traitement LLM par unité unique, pas par produit)
4. traitement parallèle (MAX_PARALLEL=5) — par unité (learner.process_unit) :
     - déjà 'pending_activation'/'erreur_verification'/... -> skip (pas de re-LLM)
     - LLM DeepSeek (prompt BDD) -> proposition
     - GATE 1 FIDÈLE via service dynamique /admin/validate (min ET max pour les plages) :
         OK  -> referentiel/save INACTIF (actif=0, statut_revue=1) ; statut 'pending_activation'
         NOK -> aucune écriture ; statut 'erreur_verification' (vérification manuelle)
     - erreur (LLM / validate injoignable / save) -> erreur SERVICE
5. PEEK : AUCUN message n'est retiré du DLQ (nack requeue=True partout, comme /dlq/messages).
   Le retrait se fait plus tard via le requeue MANUEL (dlq-manager), après vérification + activation.
6. TODO mail récap (géré par le backend) — non implémenté (cf. docs/BACKEND_PLAN.md)
6. retourne un rapport : pending_activation[], verification_errors[], processing_errors[], skipped[], ignored
```

## Décisions clés (vs version always-on)

- **Pas d'auto-réparation** : plus de seuil de confiance, plus de reload auto, plus de
  requeue vers la retry queue. Tout ce qui passe Gate 1 est écrit **inactif** → activation manuelle.
- **Gate 1 fidèle (#6)** : la validation passe par `/admin/validate` du service dynamique
  (vrai pipeline : préprocessing + réécritures + désambiguïsation). Pas de pint ré-implémenté.
- **Plages (#7)** : `valeur_min` ET `valeur_max` validées ; aucune magnitude fabriquée.
- **Erreurs (#3)** : une erreur de traitement remonte comme **erreur de service** dans le
  rapport et le message est requeue — jamais de boucle nack infinie.
- **Concurrence (#5)** : 1 réplica + drain borné + dédup par unité + 5 en parallèle →
  pas de claim concurrent ni de course de cache.
- **Atomicité (#4)** : les lignes apprises étant **inactives**, une écriture partielle
  n'a aucun impact sur le moteur live (le dynamique ne charge que `actif=1`).
- **URL BO (#1)** : `settings.BO_V2_URL` (jamais hardcodée), **identique** au service dynamique.
- **Tracking LLM (#8)** : chaque appel (succès **et** erreur) est logué via `llm_tracking`.

## Endpoints BO v2 requis (racine PHP)

Voir `graph-rag-normalize-unite-service-dynamique/docs/BO_V2_CONTRAT.md` :
`prompt/info/get`, `normalisation/referentiel/{get,save}`,
`normalisation/apprentissage/{get,upsert}`, `llm_tracking`.
Statuts apprentissage : `pending_activation`, `erreur_verification` (+ `learned`/`rejected` legacy).

## Activation manuelle (hors learner)

Une unité `pending_activation` devient effective quand un humain passe `actif=1` sur ses
lignes référentiel puis déclenche `/admin/reload` du service dynamique. (Hors périmètre du learner.)

## Build / Run

```
docker build -f apps-microservices/graph-rag-normalize-unite-learner/Dockerfile .
# python -m app.main  (uvicorn :8566, Prometheus :8567)
```
docker-compose : `deploy.replicas: 1` (drain non concurrent).

## Conventions

- Logique 100 % testable hors RabbitMQ (`Learner.process_unit()` retourne un `UnitOutcome` ;
  dépendances injectables : api_client, validate_fn, deepseek_factory).
- Prompt en BDD `action_prompt_chatgpt` (jamais hardcodé). Placeholders : `{label}`, `{unite}`,
  `{valeur}`, `{dimensions_existantes}`, `{unites_canoniques}`.
- Tracking LLM via `llm_tracking` (type_ia=2 DeepSeek, id_process=38, origine=`normalize-unite-learner`).
