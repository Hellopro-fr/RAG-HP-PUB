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

**Note 2026-05-21** : section "Recap final optimisations + etat audits" plus bas
liste les chantiers techniques en cours. Cette section ci-dessous est l'historique
des objectifs initiaux du POC (largement atteints au 21/05).

1. ~~Tests unitaires text.py + reranker.py~~ **DONE** (45 tests, voir tests/).
2. Async batch ingestion avec suivi de status. (Non-prioritaire post-audit BDD)
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

## Synonymes dans le reranker (A6, 2026-05-20)

Le reranker considere desormais les synonymes Typesense pour le matching
name/cat. Resout le cas multilingue ("crane" anglais -> "Grue" francais) et
toutes les variantes (medical/medicale, electrique/electric, etc.).

### Probleme avant
Typesense applique deja les synonymes au niveau de la recherche (le multi_search
retourne les Grues XCMG quand la query est "crane"). Mais le reranker Python
recalculait `name_match` en mode texte strict :
  query="crane", doc="Grue XCMG QY50KA"
  tokens_query = {"crane"}, doc_tokens = {"grue","xcmg",...}
  intersection vide -> name_match = 0 -> reranker remontait d'autres produits.

### Fix
`app/services/synonyms_loader.py` charge le mapping Typesense au runtime
(GET /collections/<col>/synonyms) et expose `get_synonyms_map() -> {token: Set}`.
Le reranker (`_idf_weighted_match`) considere un token query "couvert" si
lui-meme OU un de ses synonymes apparait dans le doc.

### Comportement si Typesense KO
`get_synonyms_map()` retourne {} -> matching strict (= comportement A4 sans A6).
Aucune regression possible.

### Pour ajouter de nouveaux synonymes en prod
1. Editer `site/fichiers_communs_bo_front/hellopro_fr/typesense_synonyms_manual.json`
2. Push direct via curl PUT sur Typesense (ou via le script sync_synonyms_daily.php)
3. Restart opti-moteur-front -> reload du cache

Exemple :
```bash
TS_KEY=$(grep '^TYPESENSE_API_KEY=' .env | cut -d= -f2-)
curl -X PUT "http://10.0.130.66:8108/collections/produits_prod/synonyms/manual-grue" \
  -H "X-TYPESENSE-API-KEY: $TS_KEY" \
  -H "Content-Type: application/json" \
  -d '{"synonyms":["grue","grues","grutier","crane","cranes","e-crane"]}'

docker compose restart opti-moteur-front
```

## A7 R3 -- Coverage strict des tokens query (2026-05-21)

Si la majorite des tokens query ne sont pas couverts par le doc (ni en
direct ni via synonyme), penalite progressive sur le score final :
- coverage < 50% : score * 0.5  (penalty `low_coverage_50`)
- coverage < 70% : score * 0.75 (penalty `low_coverage_70`)

Resout les faux amis semantiques type `barre laser a led` -> scanner code-barre
(la query a 3 tokens, le scanner n'en matche que 2/3 -> penalite). Le produit
qui matche les 3 tokens passe devant.

Logique dans `_is_covered()` et `rerank_candidates()` (reranker.py).

## A8 R2 -- Marque comme contrainte forte (2026-05-21)

Quand une query contient une marque connue + un autre token (type produit),
le doc doit egalement couvrir le type. Sinon penalite forte (score * 0.3,
penalty `missing_type_with_brand`).

Resout `urinoir delabie` -> Distributeur Delabie en pos 1 (le distributeur
matche "delabie" mais pas "urinoir" -> penalite).

### Source des marques

`app/services/brands_loader.py` charge la liste des marques mono-token via
facets Typesense (`marque` + `fournisseur`). Lazy + cache singleton, fallback
safe si Typesense KO (R2 inactif sans regression).

### Comportement

- Query "delabie" seule (juste une marque) -> R2 inactif (pas de type token)
- Query "urinoir delabie" -> brand={delabie}, type={urinoir} -> R2 actif
- Query "armoire medicale" (pas de marque) -> R2 inactif

Pour les marques multi-mots (ex: "Saint Gobain"), elles sont skipees pour
l'instant (detection multi-token plus complexe). A enrichir plus tard si
necessaire business.

## Recap final optimisations + etat audits (2026-05-21)

### Optimisations livrees cette serie (mai 2026)

| Code | Optimisation                                    | Fichier(s)                    | Statut prod |
|------|-------------------------------------------------|-------------------------------|-------------|
| A3   | Seuil fallback adaptatif filter_by_category     | `search_service.py`           | ✅ Actif    |
| A4   | Ponderation IDF des tokens (dict 665k tokens)   | `idf_loader.py`, `reranker.py`| ✅ Actif    |
| A6   | Synonymes Typesense dans le reranker            | `synonyms_loader.py`, reranker| ✅ Actif    |
| A7 R3| Coverage strict tokens query (faux amis)        | `reranker.py`                 | ✅ Actif    |
| A8 R2| Marque comme contrainte forte (type vs brand)   | `brands_loader.py`, reranker  | ✅ Actif    |

Ces 5 optimisations cumulees ont fait progresser la note BDD moyenne :
- Baseline (19/05) : **6.01/10**
- Session 2 (post A3+A4)              : 6.23 (+0.22)
- Session 3 (post A6 synonymes)       : 6.54 (+0.31)
- Session 4 (post R2+R3+message TRASH): 6.62 (+0.08)
- Session 5 attendue (post strict_p2) : ~7.2-7.5 (+0.6 cumule)

### Cas resolu durant la serie

| Plainte commerciale                          | Status    | Resolu par   |
|----------------------------------------------|-----------|--------------|
| "armoire medicale" -> batteries en pos 1     | ✅ Resolu | A4 IDF       |
| "soudure ritmo" -> Romus avant Apreau        | ✅ Resolu | A4 IDF       |
| "ritmo" -> produits sans ritmo en pos 1      | ✅ Resolu | A4 IDF       |
| "e-crane" -> 0 produit (mode categories pur) | ✅ Resolu | A6 + guards P1 PHP |
| "urinoir delabie" -> distributeur en pos 1   | ✅ Resolu | A8 R2        |
| "barre laser a led" -> scanner code-barre    | ✅ Partiel| A7 R3        |
| "lockers bagagerie" -> page 1 vide           | ✅ Resolu | A6 (synonyme casier) + guards P1 |

### Cas critiques residuels (pas resolus, hors scope reranker)

| Mot-cle                       | Cause                              | Plan         |
|-------------------------------|------------------------------------|--------------|
| `mantsinen`     -> 0 resultat | Pas de produit Mantsinen en BDD    | Job de cohérence log BDD vs SERP |
| `gadus s2 v220 2` -> pollution| 29 produits Gadus en BDD mais TOUS chez fournisseurs en pause (etat_societe=2) | À voir avec commercial |
| `barre laser a led` (residuel)| Token "led" ignore par BM25 dominant | R3 marche partiellement, top 1 = lampe LED Wiha mais scanners encore en pos 4-10 |

## Modifs PHP front Ecritel (reference hors repo)

Le code PHP du front HelloPro vit sur **Ecritel** (FTP upload), pas dans ce repo
public. Les fichiers suivants ont ete modifies dans cette serie pour
collaborer avec opti-moteur-front :

### `site/hellopro_fr/moteur_recherche.php`

- **Garde-fous P1 (regimes HEALTHY/HYBRID/TRASH)** : fonction `hp_decide_p1_regime()`
  classe la P1 Solr V2 selon les ratios HIGH/MID/LOW.
  - HEALTHY (high>=50% ET low<20%) : 40 Solr direct, no AJAX
  - HYBRID  (entre les deux)        : N Solr (HIGH+MID) + (40-N) Typesense AJAX
  - TRASH   (high=0 ET mid<3 OU low>=90%) : 0 Solr + 40 Typesense AJAX
- **Marqueur HTML debug** : `<!-- HP_QUALITY_P1: regime=... -->`
- **Injection JS** : `window.HP_SEARCH_STATE.regime` + `p1_stats` pour debug
- **Bump JS version** : `?v=20260520a` pour invalider cache navigateur

### `site/moteur_recherche/search_ajax.php`

- **A9 strict_p2 (2026-05-21)** : `$_strict_p2 = (count($exclude_ids_map) >= 40)`
  -> passe `exclude_low=true` au helper quand la P1 a transmis 40 ids.
- Vire les LOW de la P2 quand P1 est saine (evite le bruit semantique).
- Reponse JSON augmentee : champs `strict_p2` et `exclude_ids_count` pour debug.

### `site/design_system/js/moteur_recherche_ajax.js`

- **Message "Aucun produit"** : nouvelle fonction `showNoResultsMessage(reason)`
  affichee quand TRASH + AJAX retourne 0 produit. Cache le carousel de
  categories (souvent hors-sujet en TRASH) + masque la pagination.

### `site/fichiers_communs_bo_front/hellopro_fr/typesense_synonyms_manual.json`

- **Cluster manual-grue elargi** : ajout de `crane, cranes, e-crane` aux
  synonymes existants (resout les marques anglaises type "e-crane" Mantsinen).
- **Cluster manual-casier nouveau** : `["casier","casiers","vestiaire","vestiaires","locker","lockers","consigne","consignes","bagagerie"]`
  (resout "lockers bagagerie" en P1 TRASH).

### Workflow d'upload Ecritel

Les modifs PHP ne passent pas par Git -- elles sont **uploadees via FTP** sur
le serveur Ecritel. Les fichiers gardent leur path canonique pour faciliter
les rollbacks. Backup du 15 mai disponible en filet de secours.

## Architecture finale (pour reference)

```
URL : ?ajax=1&core_v2=1

Page 1 (server-side PHP)
└── Solr V2 (text_fr + ASCIIFolding + FrenchLightStem)
    └── recherche_produit_solr (qf nom_produit^50,categorie^25,sku^40)
        + boost cumul ^8000 (cert AND tous_tokens_dans_nom)
    └── hp_classify_and_alternate_docs (HIGH/MID/LOW + cert + round-robin 5/soc)
    └── hp_decide_p1_regime : HEALTHY / HYBRID / TRASH

Pages 2-4 (AJAX background)
└── search_ajax.php (avec strict_p2 quand P1 saine)
    └── recup_info_prod_typesense (offset=(page-1)*150)
        └── POST https://api.hellopro.eu/optimoteur-service/search/text
            └── opti-moteur-front (VM GCP):
                ├── category_detector (facet + prefix-match)
                ├── search_service (multi_search 4 pages * 250 candidats)
                │   └── A3 : seuil fallback adaptatif (150/20/5)
                └── reranker (A4+A6+A7+A8)
                    ├── A4 : ponderation IDF (665k tokens)
                    ├── A6 : synonymes (1993 clusters, 21k tokens)
                    ├── A7 R3 : penalite coverage strict
                    └── A8 R2 : marque comme contrainte (3803 marques)
    └── hp_classify_and_alternate_docs (avec exclude_low=$_strict_p2)
```

## Roadmap restante

1. **Migration GKE** : DevOps (Tafita). Repointer `api.hellopro.eu/optimoteur-service`
   vers le service GKE au lieu de la VM legacy. PVC pour `app/data/idf_nom_produit.json`.
2. **Monitoring continu** : job hebdo qui rejoue les 20 mots-cles BDD et alerte
   sur tout delta > 1 point.
3. **Job de coherence log** : compare `moteur_solr_historique.nombre_total_resultat_msh`
   vs nombre de produits affichables -> alerte si discordance (cas `mantsinen`).
4. **Reactiver fournisseurs Gadus** ou autres marques avec produits etat=Pause -> Complet.
5. **Marques multi-mots** dans brands_loader (Saint Gobain, Case IH, etc.)
6. **Cache PHP APCu** sur les top queries (latence 1-2s -> 50ms si cache hit).
7. **Cleanup doublons multi-chunks** Typesense (Forest crane DOT 50 K TAJFUN apparait 2x).
