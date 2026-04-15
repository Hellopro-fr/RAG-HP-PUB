# Contexte technique complet — `/graphoptim-service/produits/matching`

> Document de référence pour l'agent d'optimisation du scoring produit.
> Service : **`graph-rag-api-recherche-optim-service`** (copie isolée du service prod)
> URL externe : `https://api.hellopro.eu/graphoptim-service/produits/matching`
> URL directe (host) : `http://localhost:8625/produits/matching`
> URL interne (Docker) : `http://graph-rag-api-recherche-optim-service:8525/produits/matching`
>
> ⚠️ **Ce service est une copie du service prod `graph-rag-api-recherche-service`.**
> Il partage les services downstream (Neo4j, Zilliz/Milvus, LLM, etc.) avec la prod.
> Toute modification faite ici ne touche PAS la prod — c'est son unique but.
> **NE PAS merger vers prod sans validation (checkpoint CP4).**

---

## 1. Vue d'ensemble

Endpoint : `POST /produits/matching` dans `graph-rag-api-recherche-optim-service`

Pipeline de matching produit en 3 étages (identique à la prod au démarrage, l'agent va l'optimiser) :
1. **Sélection de candidats** via Neo4j (traversal de graphe)
2. **Scoring hiérarchique** (caractéristiques → questions → produit global)
3. **Diversité fournisseurs** (algorithme MMR) + reranking LLM optionnel

---

## 2. Dispatch de la requête

Fichier : `app/routers/recommendation.py` (lignes 110-147)

```python
service = recommendation_service_v2 if request.v == 2 else recommendation_service
if request.rerank.use_rerank:
    result = await service.get_products_by_caracteristique_filters_rerank(request)
else:
    result = await service.get_products_by_caracteristique_filters(request)
```

Deux sélecteurs :

- `request.v` : **2** = scoring Python (V2), **4 ou défaut** = scoring Cypher (V4)
- `request.rerank.use_rerank` : active le reranking LLM via Gemini

---

## 3. Schéma de requête

`MatchingPayloadIdProduit` (models.py 357-365) :

| Champ | Type | Défaut | Rôle |
|---|---|---|---|
| `id_categorie` | int | requis | ID catégorie produit |
| `top_k` | int | 15 | Nombre de résultats |
| `liste_caracteristique` | List | requis | Contraintes utilisateur |
| `v` | int | 2 | Version pipeline (2 ou 4) |
| `metadonnee_utilisateurs` | {pays, id_pays, cp, typologie} | - | Contexte acheteur |
| `champs_sortie` | List[str] | - | Champs à retourner par produit |
| `options.score.critique` | int | 5 | Poids caractéristiques critiques |
| `options.score.secondaire` | int | 1 | Poids caractéristiques secondaires |
| `scoring` | ScoringOptions | voir §5 | Paramètres de scoring |
| `rerank` | RerankingOptions | voir §8 | Paramètres de reranking |
| `min_matching_cids` | int | 1 | (V2) caract. min à matcher |

### Structure d'une caractéristique

```python
{
  "id_caracteristique": int,
  "type_caracteristique": "textuelle" | "numerique",
  "valeurs_cibles": List | Dict,        # [IDs] ou {min, max, exact}
  "valeurs_bloquantes": List | Dict,    # même structure
  "poids_question": int,                # défaut 1
  "poids_caracteristique": "critique" | "secondaire",
  "unite": Optional[str]
}
```

---

## 4. Pipeline V4 (Cypher, défaut)

Fichier : `app/services/recommendation_service.py`

### 4.1 — Étape 1 : Sélection des candidats (CYPHER_STEP1_*)

3 variantes :

- **ANCHOR** (défaut) : traverse `Reponse -[:EQUIVAUT_A|COUVRE]- ... -[:A_POUR_CARACTERISTIQUE|EST_PROPOSE_PAR]- Produit`, filtre par catégorie
- **TARGET** : produit unique par ID
- **BY_IDS** : liste de produits pré-sélectionnés (pour re-query post-rerank)

### 4.2 — Étape 2 : Scoring hiérarchique (CYPHER_STEP2_SCORING)

**5 priorités** pour chaque contrainte :

| # | Condition | Score |
|---|---|---|
| 1 | Valeur produit ∈ `valeurs_cibles` | **1.0** |
| 2 | Valeur produit ∈ `valeurs_bloquantes` | **`v_blocked`** (-2.0) |
| 3 | Contrainte numérique (voir §6) | 0.0 → 1.0 |
| 4 | Caractéristique présente mais non-matchée | **`v_different`** (-0.3) |
| 5 | Caractéristique absente du produit | **`c_unknown_score`** (0) |

### 4.3 — Agrégation hiérarchique (4 niveaux)

```
Niveau 1 : score_contrainte × c_weight (5 ou 1)
Niveau 2 : cid_score     = Σ(score × c_weight) / Σ(c_weight)            # par caractéristique
Niveau 3 : group_score   = Σ(cid × c_weight_sum) / Σ(c_weight_sum)      # par q_weight
Niveau 4 : global_score  = Σ(group × q_weight) / Σ(q_weight)            # global produit
```

### 4.4 — Ajustements cross-score (etat_score)

```python
raw_etat = 1.0 if (id_etat == 1 or (id_etat == 2 and id_affichage == 1)) else 0.9

# Boost fournisseurs faibles avec bon score
if raw_etat != 1.0 and global_score >= 0.8:
    etat_score = 1.0

# Bonus fournisseurs bons avec score 0.80-0.95
if raw_etat == 1.0 and 0.80 <= global_score <= 0.95:
    global_score = min(global_score + 0.05, 1.0)
```

### 4.5 — Score final et filtre

```
final_score = global_score × etat_score × zone_score × typo_score
# zone_score et typo_score sont forcés à 1.0 actuellement
```

Filtre : `final_score < absolute_threshold` (0.3) → produit écarté.

### 4.6 — Étape 3 : Diversité fournisseurs (MMR)

```python
# Pour chaque produit trié par final_score DESC, puis supplier_avg DESC
if vendor_count[supplier] < max_per_supplier_extended:
    mmr_score = λ × final_score - (1 - λ) × (vendor_count / max_per_supplier)
    # λ = diversity_lambda = 0.7 par défaut
```

Puis :
- `liste_produit` = top_k produits (tri par mmr_score DESC)
- `top_produit` = 1 meilleur par fournisseur, limité à 4

---

## 5. Paramètres de scoring (ScoringOptions)

| Paramètre | Défaut | Impact |
|---|---|---|
| `v_blocked` | **-2.0** | Score si valeur bloquante matchée → produit écarté |
| `v_different` | **-0.3** | Score si caract. présente mais pas matchée |
| `z_unmatched` | **0** | Score zone non-matchée (forcé à 1.0 actuellement) |
| `e_unmatched` | **0.9** | etat_score pour fournisseurs non-clients |
| `g_unknown_score` | **0.8** | Score zone inconnue (forcé à 1.0 actuellement) |
| `c_unknown_score` | **0** | Score caractéristique absente |
| `t_unmatched` | **0.2** | Score typologie non-matchée (forcé à 1.0) |
| `absolute_threshold` | **0.3** | Score min pour inclure le produit |
| `relative_tolerance` | **0.15** | Non utilisé actuellement |
| `max_per_supplier_extended` | **3** | Max produits par fournisseur en phase MMR |
| `diversity_lambda` | **0.7** | 70% relevance / 30% diversité fournisseurs |

---

## 6. Scoring numérique (détaillé)

### 6.1 — Valeur exacte

```
score = max(
    target / product   si product >= target,
    product / target   si product <= target
)
```

### 6.2 — Min seul

```
direct    = min_target / product      (si product >= min)
inverted  = product / min_target      (si >= 0.8 ET product <= min)
score     = max(direct, inverted)
```

> **Seuil 0.8** : accepte un produit légèrement sous la cible.

### 6.3 — Max seul

```
direct    = product / max_target      (si product <= max)
inverted  = max_target / product      (si >= 0.8 ET product >= max)
score     = max(direct, inverted)
```

### 6.4 — Range (min + max), produit à valeur unique

```
score = 1.0 si min <= product <= max, sinon 0.0
```

### 6.5 — Range (min + max), produit à range

Jaccard-style overlap :

```python
if pas de chevauchement:
    score = 0.0
else:
    overlap = min(product_max, target_max) - max(product_min, target_min)
    score = overlap / (target_max - target_min)
```

---

## 7. Pipeline V2 (scoring Python)

Fichier : `app/services/recommendation_service_v2.py`

### 7.1 — Avantages

- 1 seul round-trip Neo4j (avec `IN $all_cids` au lieu d'UNWIND)
- Scoring Python en streaming (pas d'attente de tous les résultats)
- Normalisation + fetch en parallèle (`asyncio.gather`)
- Filtre `min_matching_cids` en base

### 7.2 — Fonctions clés

| Fonction | Lignes | Rôle |
|---|---|---|
| `_score_numeric_single()` | 78-123 | Scoring numérique simple |
| `_score_numeric_range()` | 126-158 | Scoring avec range |
| `score_constraint()` | 161-231 | Scoring d'une contrainte |
| `score_product()` | 278-389 | Agrégation hiérarchique |
| `compute_etat_score()` | 392-419 | Ajustements cross-score |
| `apply_diversity_mmr()` | 440-501 | Diversité fournisseurs |

> Logique identique à V4 mais en Python pur — plus facile à debug/modifier.

---

## 8. Pipeline de reranking LLM

Déclenché si `request.rerank.use_rerank == True`.
Méthode : `_enrich_and_rerank_with_llm()` (recommendation_service.py 1639-2277).

### 8.1 — Étape 1 : Scoring initial

Même flow que sans rerank, mais retourne jusqu'à `request.rerank.top_k` produits (défaut 24).

### 8.2 — Étape 2 : Enrichissement API HelloPro (parallèle)

```python
await asyncio.gather(
    hellopro_api_client.fetch_products_info(id_categorie, id_produits),
    hellopro_api_client.fetch_all_product_caracteristiques(id_produits),
    hellopro_api_client.fetch_category_caracteristiques(id_categorie),
    hellopro_api_client.fetch_prompt(id_prompt or "112"),
)
```

| Endpoint | Usage |
|---|---|
| `POST api.hellopro.fr/api/hp/view/index.php` | Infos produit (nom, description, vendeur) |
| `POST api.hellopro.fr/api/v2/index.php` (etape=caracterisation) | Caract. détaillées du produit |
| `POST api.hellopro.fr/api/v2/index.php` (etape=caracteristique) | Définitions de caract. de la catégorie |
| `POST api.hellopro.fr/api/v2/index.php` (etape=prompt) | Prompt de reranking (112 ou 118) |

> Cache in-memory : 2h TTL.

### 8.3 — Étape 3 : Formatage pour LLM

3 composants injectés dans le prompt :

**BESOIN_ACHETEUR** : `request.rerank.parcours` (texte libre décrivant le besoin).

**CARACTERISTIQUES_CRITIQUES** (uniquement `critique`) :

```
Hauteur de levée (poids: 2) : min: 3m, max: 5m
Capacité de charge (poids: 1) : 2000 kg
```

**LISTE_PRODUITS** : encodée en **TOON** (~40% moins de tokens que JSON)

```python
{
  "id_produit": "...",
  "titre": "...",
  "description": "...",
  "fournisseur": {"nom": "...", "type": "..."},
  "caracteristiques": [...]
}
```

### 8.4 — Étape 4 : Appel Gemini

Fichier : `app/infrastructure/gemini_client.py`

| Paramètre | Valeur |
|---|---|
| Modèle | `gemini-3.1-flash-lite-preview` |
| Température | Récupérée depuis l'API prompt |
| Response format | JSON (`response_mime_type="application/json"`) |
| Max tokens | 4096 |
| Thinking level | `request.rerank.thinking_level` (défaut `minimal`) |
| Retry | Tenacity, 10× exponential backoff |

**Sortie attendue** :

```json
{
  "top_produits":     [{"id_produit": "...", "score": 0.95, "raison": "..."}],
  "autres_produits":  [...],
  "produits_ecartes": [...]
}
```

### 8.5 — Étape 5 : Réordonnancement

- `top_produit` = `llm_top_produits` (limité à 4)
- `liste_produit` = `llm_autres_produits` + produits non mentionnés
- `ecarts` = `llm_produits_ecartes`

### 8.6 — Étape 6 : Re-query (optionnel)

Ré-exécute `CYPHER_STEP1_BY_IDS` pour les produits sélectionnés par le LLM → enrichit les scores Neo4j tout en conservant l'ordre LLM.

---

## 9. Format de réponse

```python
class MatchingResponse:
    top_produit: List[Produit]              # 1 meilleur par fournisseur, ≤4
    liste_produit: List[Produit]            # Autres produits
    ecarts: Optional[List[Produit]]         # LLM-rejetés (rerank only)
    temps_de_traitement: float              # secondes

class Produit:
    rang: int
    id_produit: str
    score: float                            # final_score
    caracteristique: List[CaracteristiqueMatching]
    coeff_geo: float                        # forcé à 1.0
    coeff_type_frns: float                  # forcé à 1.0
    coeff_etat_score: float                 # 0.9 ou 1.0
    coeff_caracteristique: float            # global_score
    info_produit: Optional[Dict]            # si champs_sortie
    llm_response: Optional[Dict]            # si rerank

class CaracteristiqueMatching:
    statut_matching: int                    # 1=match, 2=écart, 3=bloquant, 4=non spécifié
    id_caracteristique: int
    type_caracteristique: int
    valeur / valeur_min / valeur_max: Optional[str]
    unite: Optional[str]
    id_valeur: List[int]
    poids: int                              # c_weight
    bareme: float                           # score de cette caract.
    poids_question: int                     # q_weight
```

---

## 10. Fichiers modifiables pour l'optim

Tous dans `apps-microservices/graph-rag-api-recherche-optim-service/` (scope isolé, auto-approuvé dans `.claude/settings.json`) :

| Fichier | Ce que l'agent peut toucher |
|---|---|
| `app/services/recommendation_service.py` | Scoring V4 : Cypher Steps, pénalités, agrégation, etat_score, MMR |
| `app/services/recommendation_service_v2.py` | Scoring V2 : fonctions Python `_score_numeric_*`, `score_product`, MMR |
| `app/services/cypher_builder.py` | Construction Cypher, seuils sémantiques |
| `app/services/rag_components.py` | Prompts LLM (si utilisés) |
| `app/services/product_service.py`, `fournisseur_service.py`, `node_service.py`, `rag_service.py` | Services auxiliaires (libres aussi) |
| `app/config.py` | `SIMILARITY_THRESHOLD` (0.75), `TOP_K_RETRIEVAL` (10), modèle LLM |

### Fichiers interdits (bloqués par `.claude/settings.json`)

| Fichier | Raison |
|---|---|
| `app/main.py` | Bootstrap FastAPI — casser ça = service down |
| `app/routers/**` | Contrat HTTP — casser ça = l'agent-optim ne peut plus appeler l'endpoint |
| `app/infrastructure/**` | Clients gRPC/LLM — transport, pas de logique scoring |
| `app/domain/**` | Schémas Pydantic — casser ça = payloads rejetés (HTTP 422) |
| `Dockerfile`, `requirements.txt` | Build container |

### Portée globale (tout le reste du monorepo bloqué)

- Tous les autres services (`graph-rag-api-recherche-service` prod, api-gateway, llm-service, etc.)
- `libs/`, `protos/`, `docker-compose*.yml`, `.env*`
- `.claude/` (config Claude elle-même)

---

## 11. Leviers d'optimisation prioritaires

1. **Seuil 0.8 du scoring numérique inversé** — contrôle la tolérance aux écarts
2. **`v_different` (-0.3)** — pénalité écart vs 0 (neutre)
3. **`absolute_threshold` (0.3)** — trade-off recall vs précision
4. **Boost +0.05 etat_score** — range `[0.80, 0.95]` arbitraire
5. **`diversity_lambda` (0.7)** — score vs diversité
6. **`max_per_supplier_extended` (3)** — concentration fournisseur
7. **Prompt 112/118** — logique de reranking LLM
8. **Modèle Gemini** — `gemini-3.1-flash-lite-preview`

---

## 12. Timing typique

| Phase | Durée |
|---|---|
| Normalisation | 50-150 ms |
| Cypher V4 | 200-800 ms |
| Scoring Python V2 | 100-300 ms |
| Diversité MMR | 10-50 ms |
| **Sans rerank** | **0.3-1 s** |
| Fetch API HelloPro | ~1 s |
| Appel Gemini | 1-3 s |
| **Avec rerank** | **2-6 s** |

---

## 13. Résumé exécutif

Le service **`graph-rag-api-recherche-optim-service`** est une copie isolée du service prod pour l'optimisation du scoring. Il expose `POST /produits/matching` sur :
- `https://api.hellopro.eu/graphoptim-service/produits/matching` (via gateway)
- `http://localhost:8625/produits/matching` (accès direct host)

Le pipeline combine :

- **Traversal de graphe Neo4j** (sélection par ancrage)
- **Scoring hiérarchique 4 niveaux** (contrainte → caract. → question → produit)
- **Algorithme MMR** (équilibre score/diversité fournisseurs)
- **Reranking LLM optionnel** (Gemini avec prompt dynamique)

Deux pipelines disponibles :
- **V4 (défaut)** : scoring en Cypher (complexe, DB-bound)
- **V2 (paramètre `v=2`)** : scoring en Python (streaming, CPU-bound)

**Mission de l'agent d'optimisation** : améliorer le scoring en modifiant **uniquement** les fichiers de `app/services/` et `app/config.py` du service optim. Leviers prioritaires : **formules de scoring numérique**, **pénalités** (`v_different`, `v_blocked`), **seuils de filtrage** (`absolute_threshold`), **équilibre MMR** (`diversity_lambda`, `max_per_supplier_extended`) et **prompts LLM** (rag_components.py). Les magic numbers hardcodés (`0.8` threshold numérique, `0.05` boost etat) restent non-configurables pour l'instant — l'espace des 11 paramètres de `ScoringOptions` doit suffire en première passe.

**Interdictions** : ne jamais modifier `main.py`, `routers/`, `infrastructure/`, `domain/`, `Dockerfile`, ni aucun fichier en dehors du service optim. Ces règles sont enforcées par `.claude/settings.json` (deny > allow).
