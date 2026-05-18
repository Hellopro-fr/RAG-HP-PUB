# CLAUDE.md — opti-moteur-front

## Contexte metier

Remplacement du moteur de recherche produit front (www.hellopro.fr) actuellement
base sur Milvus qui prend 5-7 secondes et renvoie des resultats peu pertinents
sur les requetes commerciales courtes (1-3 mots). Cible : **< 200 ms, P@5 >= 80%**.

## Decisions d'architecture

### 1. Backend Typesense (et non Milvus direct)
- Milvus est performant pour le RAG (long context, batch) mais lent et bruyant
  sur les requetes courtes.
- Typesense fait du hybrid BM25 + kNN nativement, avec latence 20-200 ms.
- OpenSearch est une alternative credible (testee dans reports/) mais plus
  d'overhead ops (JVM, Dashboards).

### 2. Embeddings CamemBERT-large identiques a Milvus prod
- Meme modele pour eviter la re-vectorisation de 2,24 M produits.
- Les embeddings sont pulles directement depuis Milvus (`produits_3`).
- Le service d'embedding `api-embedding-service` fournit la meme fonction pour
  les queries au runtime.

### 3. Pipeline de pertinence specifique HelloPro
La formule de ranking est metier-specifique :
```
final_score = 0.55 * cosine_vector
            + 0.10 * bm25_normalise
            + 0.25 * tokens_match_nom_produit
            + 0.10 * tokens_match_categorie
```
Penalite x0.3 si (vec < 0.20 AND name_match < 0.50) : elimine les faux positifs
BM25 sur des tokens fortuits (ex: "18V" qui matche des batteries pour requete
"perceuse 18V").

### 4. Detection categorie avec "prefix-match tolerant"
- Recherche de la categorie dominante via facet Typesense.
- Ne garde la categorie pour filter_by que si les tokens de la query
  apparaissent dans les premiers mots du nom (avec tolerance sg/pl).
- Exemples :
  - query="batterie lithium" vs cat="Armoire de stockage batterie lithium"
    -> REJETE (batterie en position 4, pas un prefix match)
  - query="signalisation securite" vs cat="Signalisations securite travail"
    -> ACCEPTE (signalisation ~ signalisations via startswith bilateral)

## Conventions alignees avec le repo

- Settings via `pydantic_settings.BaseSettings` et `.env` file.
- Env vars Milvus : `ZILLIZ_URI`, `ZILLIZ_PORT`, `ZILLIZ_USER`, `ZILLIZ_PASSWORD`
  (meme que `api-rest-milvus`, `database-recherche-service`, etc).
- Singleton pattern pour les connecteurs (comme `milvus_connector` dans
  graph-rag-milvus-service).
- Async I/O via `asyncio.to_thread` pour wrap le pymilvus sync.
- FastAPI avec `lifespan` async pour warm-up, router par feature, monitoring
  `/health`.

## Workflow type (POC validation)

1. Extraire la hierarchie categories cibles (ecrtel PHP).
2. `POST /admin/collections/produits_poc` -> cree la collection Typesense.
3. `POST /ingest/categories/batch` avec la liste des categories feuilles.
4. Embedder quelques queries test via `api-embedding-service`.
5. `POST /search` -> valider P@5 + latence.
6. Pousser en canary sur une fraction du traffic front.

## Ce qu'il reste a faire

Voir la roadmap du README. En priorite :
1. Tests unitaires text.py + reranker.py (logique pure, faciles a tester).
2. Async batch ingestion avec suivi de status.
3. Integration Prometheus pour suivi SLO (P@5, P@95 latence) en prod.

## Structure code

Respecter `app/{core,services,router,schemas,utils}/` :
- `core/` : connecteurs infra (Milvus, Typesense)
- `utils/` : fonctions pures stateless (tokenize, normalize)
- `services/` : logique metier (detection, rerank, ingestion)
- `schemas/` : contrats API pydantic
- `router/` : routes FastAPI thin, deleguent aux services
- `data/` : fichiers de donnees generes offline (gitignore, cf section IDF)

## IDF tokens rares (A4, 2026-05-18)

Le reranker pondere `name_match` et `cat_match` par l'IDF des tokens query
(calcule sur l'ensemble des `nom_produit` Typesense). Cela resout les requetes
combinatoires comme "melangeur conique" ou le token rare devrait peser plus
que le token commun (audit v3, score 2.6/10 sur cette query).

### Generer / regenerer le dict IDF

Le fichier `app/data/idf_nom_produit.json` est gitignore (depend du catalogue
live). A regenerer apres chaque ingestion majeure.

**Methode recommandee : execution dans le container** (toutes les deps sont
deja la, pas besoin d'installer Python + requirements.txt sur la VM). Le
bind-mount `./app/data:/app/app/data` (cf docker-compose.yaml) garantit que
le JSON ecrit dans le container apparait aussi cote hote.

```bash
cd apps-microservices/opti-moteur-front

# 1. (Une seule fois apres ajout du bind-mount) recreer le container pour
#    que le volume soit pris en compte. `restart` seul ne suffit pas.
docker compose up -d --force-recreate opti-moteur-front

# 2. Generer le dict IDF (~10-30s sur ~700k docs)
docker compose exec opti-moteur-front python scripts/compute_idf.py

# 3. Recharger pour que le reranker charge le nouveau dict IDF en RAM
docker compose restart opti-moteur-front

# 4. Verifier les logs au demarrage
docker compose logs --tail 30 opti-moteur-front | grep -i "IDF"
# Attendu : "IDF loaded from idf_nom_produit.json : NNNN tokens, median=X.XXX, n_docs=YYYYY"
```

**Methode alternative (hors container)** : si Python 3 + deps installes sur
la VM, `python3 scripts/compute_idf.py` ecrit directement dans
`apps-microservices/opti-moteur-front/app/data/` (cote hote), visible par
le container via le bind-mount.

### Comportement si le fichier IDF est absent

`idf_loader.idf_available()` retourne `False` -> le reranker bascule
automatiquement sur le ratio simple (= comportement historique, backward-compat).
Verifier le log au demarrage : `IDF file not found at ... - reranker will
fallback to flat name_match`.

## Filter_by_category : seuil de fallback adaptatif (A3, 2026-05-18)

Le retry "sans filter_by" si pool < seuil utilise desormais un seuil adaptatif
selon le nb de tokens query :
- **1 token**  (compresseur, ERP) : seuil 150 -> evite que le filter etouffe
  la P2 sur les requetes mono-token generiques (regression v3 audit).
- **2 tokens** (armoire medicale) : seuil 20 -> conserve le gain v3 (+3.4).
- **>=3 tokens** (Ritmo ELEKTRA M) : seuil 5 -> comportement strict actuel.

Logique dans `app/services/search_service.py::_filter_fallback_threshold()`.

## Limites de scope du service

Ce service Python tourne sur la VM/GKE et expose `/search/text`, `/admin/*`,
`/sync/*` pour les autres consommateurs (PHP front Ecritel, scripts cron).

**Hors scope** (ne pas documenter ici) :
- La page 1 Solr V2 server-side, rendue par PHP sur Ecritel.
- Le rendu HTML, la pagination AJAX, le filtrage HIGH/MID/LOW cote PHP.
- Les decisions UX (regimes HEALTHY/HYBRID/TRASH, bandeaux, etc.).

Pour les specs cote PHP front (notamment garde-fous P1 Solr), voir :
- `site/moteur_recherche/PLAN_P1_GUARDRAILS.md`
- `site/moteur_recherche/SESSION_2026-04-28_OPTIMISATION_RECHERCHE.md`
- `site/INTEGRATION_TYPESENSE_CANARY.md`
