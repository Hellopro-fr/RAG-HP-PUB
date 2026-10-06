# FLUX — Normalisation d'unités (service dynamique + learner)

Détail de chaque traitement des **2 services**, de l'entrée à la sortie : pour chaque
étape, *quelle fonction la réalise*, *ce qu'elle fait*, *comment*, et *un exemple*.

```
ingestion ─► normalize-unite-processor ──(échec)──► retry ──► MANUAL DLQ
   (gRPC)            │ ok                                          │
                     ▼                                             ▼  POST /run (manuel)
              graph-rag-normalize-unite-service-dynamique   graph-rag-normalize-unite-learner
              (SERVICE 1 : normalise)                        (SERVICE 2 : apprend, inactif)
                     ▲___________________ /admin/validate ________│
```

---

# SERVICE 1 — `graph-rag-normalize-unite-service-dynamique`

Convertit une unité « sale » en **unité canonique**. Tout le savoir (mappings, alias,
réécritures, preprocessing) vient de la **base** via le BO ; le code n'est qu'un interpréteur.

## A. Démarrage & chargement du référentiel

| Étape | Fonction (fichier) | Ce qu'elle fait / comment |
|---|---|---|
| Boot | `main()` ([app/main.py](apps-microservices/graph-rag-normalize-unite-service-dynamique/app/main.py)) | Charge le référentiel (fail-fast, 5 retries), construit le normaliseur, lance le serveur gRPC dans un **thread démon** + uvicorn (REST) en principal. |
| Fetch BO | `fetch_referentiel_from_bo()` ([infrastructure/referentiel_loader.py](apps-microservices/graph-rag-normalize-unite-service-dynamique/infrastructure/referentiel_loader.py)) | `POST {BO_V2_URL}` `{etape:normalisation, field:referentiel, action:get, data:{}}` + Bearer. Déballe `{code,response}`, garde-fou si `payload` non-objet. |
| Parsing | `Referentiel.from_payload(payload)` | Transforme les sections BD en structures : `unit_to_dimension` (dict), `label_to_dimension` (**liste ordonnée** par priorité), `canonical_units` (dict), `definitions`/`preprocessing`/`rewrites`. |
| Garde santé | `Referentiel.validate()` | Lève `ValueError` si une section cœur est vide → évite de charger un référentiel mort. |
| Construction moteur | `_NormalizerState.__init__` ([infrastructure/unit_normalization_service.py](apps-microservices/graph-rag-normalize-unite-service-dynamique/infrastructure/unit_normalization_service.py)) | Crée un `UnitRegistry` pint, rejoue les `define()` **dans l'ordre**, **compile** les regex de preprocessing une fois (`_PreprocStep`), trace les `define_errors`/`preprocessing_errors`. |

**Exemple de référentiel (extrait)** : `unit_to_dimension={"kg":"mass","tonnes":"mass",...}`,
`canonical_units={"mass":"kilogram","length":"meter",...}`, `definitions=["tonne = 1000 * kilogram = t",...]`.

## B. Pipeline de normalisation (cœur)

Entrée gRPC `NormalizeQuantity` ([grpc_server.py](apps-microservices/graph-rag-normalize-unite-service-dynamique/infrastructure/grpc_server.py)) ou REST `/normalize/quantity`
([rest_api.py](apps-microservices/graph-rag-normalize-unite-service-dynamique/infrastructure/rest_api.py)) → `NormalizationUseCase.normalize_quantity`
([normalization_use_case.py](apps-microservices/graph-rag-normalize-unite-service-dynamique/application/normalization_use_case.py), convertit `"null"/None`) → **`_NormalizerState.normalize(label, unit, value, data_type)`**.

Étapes internes de `normalize()` :

| # | Sous-étape | Comment | Exemple |
|---|---|---|---|
| 1 | Parse valeur | tolère `+/- 2`, `±`, `/-` | `"+/- 2" → 2.0` |
| 2 | Preprocessing pré-snapshot | `_apply_preprocessing(unit,"pre_snapshot")` : NFKC, strip `(...)`, `·→.` → fige `original_unit` | `"dB(A)" → "dB"` ; `"µm"(U+00B5) → "μm"(U+03BC)` |
| 3 | Preprocessing post-snapshot | `_apply_preprocessing(unit,"post_snapshot")` : `³→3`, `²→2` | `"kg/m²" → "kg/m2"` |
| 4 | Désambiguïsation | `_match_disambiguation(unit,label)` sur `_STATIC_DISAMBIGUATIONS` (code, 3 cas) | `nm`+label « épaisseur » → dimension **length** ; sinon torque |
| 5 | Réécriture exacte | lookup `self.REWRITES` (SQL) : `rewrite`→expr pint, `bypass`→canonique direct | `"m3/h"→"m**3 / hour"` ; `"%"→bypass count` |
| 6 | Dimension | override désambig. sinon `_get_dimension(original_unit,label)` : unité exacte (SQL) puis sous-chaîne du label (SQL, accent-insensible via `_strip_accents`) | `"kg/m2"→area_density` ; label « Puissance »→power |
| 7 | Bypass count | si dimension ∈ {count, count_rate} → valeur passée telle quelle | `"sélections"→count` |
| 8 | Conversion pint | `self.ureg.Quantity(value, unit).to(canonical)` ; magnitude à 6 chiffres significatifs | `2 "Tonnes" → 2000 kilogram` |

**Exemples bout-en-bout**
```
normalize("Capacité","Tonnes",2)  → {valeur:2000,  unite:"kilogram"}
normalize("Hauteur","mm",2500)    → {valeur:2.5,   unite:"meter"}
normalize("Charge","kg/m²",50)    → {valeur:50,    unite:"kilogram / meter ** 2"}
normalize("Humidité","%",60)      → {valeur:60,    unite:"count"}        # bypass
normalize("Bidon","zorglub",5)    → {}                                   # inconnu → DLQ
```
`normalize_range(label,unit,min,max)` applique `normalize` aux deux bornes (même unité canonique).

## C. Concurrence & rechargement

| Fonction | Rôle |
|---|---|
| `UnitNormalizationService.normalize/...` | Façade : lit `self._state` **sans lock** (snapshot de référence atomique). |
| `UnitNormalizationService.reload(referentiel)` | Reconstruit un `_NormalizerState` complet **hors-ligne** puis **swap** la référence sous lock → jamais d'état partiel visible. |
| `start_metrics_server_in_thread` + lifespan refresh TTL | Métriques Prometheus + rafraîchissement périodique du référentiel. |

## D. Endpoints d'admin (au service du learner)

| Endpoint (fonction) | Ce qu'il fait |
|---|---|
| `POST /admin/validate` → `UnitNormalizationService.validate_proposed(proposed, label, unit, values)` | **Gate 1 fidèle** : `Referentiel.merged_with(proposed)` (courant + lignes proposées), construit un `_NormalizerState` **jetable**, exécute le **vrai** `normalize` pour **chaque valeur** ; `ok=True` ssi toutes se normalisent. Ne persiste rien. |
| `POST /admin/reload` | Re-fetch + `reload()`. Rend une unité fraîchement activée vivante. |

**Exemple `/admin/validate`** : proposé `{unite_dimension:[{quintal→mass}], definitions:[{"quintal = 100 * kilogram"}]}`, `values:[3,9]` → `{ok:true, valeur_canonique:300, unite_canonique:"kilogram"}`.

---

# SERVICE 2 — `graph-rag-normalize-unite-learner`

Apprentissage **manuel par lot** : lit la *manual DLQ*, propose la règle manquante via LLM,
la **valide** par le service 1, l'écrit **inactive** (activation humaine ensuite).

## A. Déclenchement & préparation

| Étape | Fonction (fichier) | Ce qu'elle fait / comment | Exemple |
|---|---|---|---|
| Trigger | `POST /run {limit}` → `create_app` ([app/main.py](apps-microservices/graph-rag-normalize-unite-learner/app/main.py)) | Verrou anti-runs concurrents ; capte les pré-requis manquants → `{started:false,error}`. | `{"limit":100}` |
| Borne | `BatchRunner.run` ([app/core/batch.py](apps-microservices/graph-rag-normalize-unite-learner/app/core/batch.py)) | Clamp `1 ≤ limit ≤ MAX_LIMIT`. | `1000000 → 1000` |
| Garde santé (#8) | `BatchRunner._fetch_referentiel` | `api.get_referentiel()` → `canonical_units` ; **annule** si vide (sinon le LLM inventerait une dimension par unité). | référentiel vide → run annulé |

## B. Drain & dédup

| Étape | Fonction | Comment | Exemple |
|---|---|---|---|
| Drain | `BatchRunner._drain(queue, limit)` | Boucle `queue.get(fail=False, timeout=5)` jusqu'à `limit` ou file vide (pas de consumer permanent). | récupère 42 messages |
| Parse | `_parse_message(body)` | Extrait `unite/label/values/failed_node_entry` ; `numeric`→`[valeur]`, `numeric_range`→`[min,max]` (None filtrés) ; sans unité → ignoré + ack. | voir message ci-dessous |
| Dédup | dans `run` (`groups.setdefault`) | Regroupe par `(unite, label)` → **1 traitement LLM par unité**, même si N produits. | 42 messages → 11 unités |

**Message DLQ d'entrée (exemple)**
```json
{ "failed_node_entry": { "node": { "properties": {
   "label": "Poids", "unite": "quintal", "type_donnee": "numeric", "valeur": 3 } } } }
```

## C. Traitement d'une unité (5 en parallèle)

`_handle_group` → `_process_group` (sémaphore + classification d'erreur) → **`Learner.process_unit(unite, label, values, referentiel)`** ([app/core/learner.py](apps-microservices/graph-rag-normalize-unite-learner/app/core/learner.py)) :

| # | Sous-étape | Fonction | Ce qu'elle fait | Exemple |
|---|---|---|---|---|
| 1 | Dédup inter-run | `api.apprentissage_get` | si statut terminal (`pending_activation`/`erreur_verification`/`learned`/`rejected`) → **skip** | `nm` déjà appris → skip |
| 2 | LLM | `Learner._call_llm` | charge le prompt BDD (`load_prompt`), remplit `{label}{unite}{valeur}{dimensions_existantes}{unites_canoniques}`, appelle `DeepSeek.chat` (via `asyncio.to_thread`), **trace** l'usage succès **et** erreur (`log_llm_usage`), parse (`_extract_json`) | propose `{dimension:"mass", pint_define:"quintal = 100 * kilogram", confiance:0.9}` |
| 3 | Sections | `Learner._build_sections` | construit le payload de proposition (clés `unite_dimension`/`definitions`/...), **coercition `str()`** anti-crash | `{unite_dimension:[{quintal→mass}], definitions:[{"quintal = 100 * kilogram"}]}` |
| 4 | **GATE 1** | `dynamic_client.validate` → `POST /admin/validate` (service 1) | valide **min ET max** en un appel ; lève `DynamicValidationError(permanent=4xx)` si l'appel échoue | `3 & 9 quintal → kilogram` ✅ |
| 5a | OK | `Learner._save_inactive` (`api.referentiel_save_batch`) + `apprentissage_upsert` | écrit toutes les tables en **un appel atomique**, `actif=0, statut_revue=1` ; statut `pending_activation` | lignes inactives en base |
| 5b | NOK | `apprentissage_upsert` | statut `erreur_verification`, **rien écrit** | proposition non convertible |
| 5c | Erreur | (remontée `_process_group`) | LLM/validate/save en échec → `processing_error` (+ `type` contract/transient/processing) | timeout `/admin/validate` |

## D. Sortie : PEEK & rapport

`_route(group, outcome, report)` route **au fil de l'eau**. **Mode PEEK** : le learner ne
**consomme JAMAIS** le DLQ — `_peek` fait `nack(requeue=True)` sur **tous** les messages
(comme `/dlq/messages`). Le retrait définitif se fait **plus tard** via le **requeue manuel**
(dlq-manager) après vérification + activation des unités.

| Issue | Action message | Bucket rapport |
|---|---|---|
| `pending_activation` | `_peek` (laissé dans le DLQ) | `pending_activation[]` |
| `erreur_verification` | `_peek` | `verification_errors[]` |
| `skipped` | `_peek` | `skipped[]` |
| `processing_error` | `_peek` | `processing_errors[]` (+ `type`) |

> Mail récap (les 2 issues) : **TODO** — géré par le backend, cf. [BACKEND_PLAN.md](apps-microservices/graph-rag-normalize-unite-service-dynamique/docs/BACKEND_PLAN.md).

**Rapport de run (exemple)**
```json
{ "started": true, "report": {
  "fetched": 42, "unique_units": 11, "ignored": 0,
  "pending_activation": [{"unite":"quintal","dimension":"mass","pint_define":"quintal = 100 * kilogram","reecriture":null,"confiance":0.95}],
  "verification_errors": [{"unite":"bidule","reason":"Gate 1 NOK (valeurs=[5])"}],
  "processing_errors":   [{"unite":"truc","error":"HTTP 422 sur /admin/validate","type":"contract"}],
  "skipped": ["nm"]
} }
```

## E. Activation (geste humain, hors learner)
Une unité `pending_activation` devient vivante quand un humain passe ses lignes à `actif=1`
puis déclenche `POST /admin/reload` du service 1. À partir de là, `quintal` se normalise
dans le pipeline d'ingestion.

---

# Garde-fous transverses (pourquoi c'est fiable)

| Garde-fou | Où | Effet |
|---|---|---|
| Gate 1 **fidèle** | `validate_proposed` (service 1) | le learner ne valide jamais avec un moteur « approximatif » : c'est le **vrai** pipeline. |
| Activation **manuelle** | statut `pending_activation`, `actif=0` | aucune règle LLM n'entre en prod sans revue humaine. |
| Save **atomique** | `referentiel_save_batch` (transaction BO) | jamais de ligne orpheline/dupliquée. |
| Dédup par unité | `groups` (batch) + `apprentissage` (BD) | 1 appel LLM par unité, coût maîtrisé. |
| Référentiel **non vide** | `validate()` / `_fetch_referentiel` | pas d'apprentissage sur un référentiel cassé. |
| Erreurs classées | `error_type` (contract/transient/processing) | l'opérateur sait corriger le code ou réessayer. |

Contrats détaillés des endpoints BO : [BO_V2_CONTRAT.md](apps-microservices/graph-rag-normalize-unite-service-dynamique/docs/BO_V2_CONTRAT.md).
