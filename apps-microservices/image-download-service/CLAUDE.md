# image-download-service

FastAPI + RabbitMQ service that downloads, processes, and archives product images with delta sync support.

## Tech Stack

- Python 3.11, asyncio
- FastAPI + uvicorn on port **8505**
- RabbitMQ (aio-pika) consumer for download jobs
- Pillow, pyvips for image processing
- aiohttp, aiofiles
- Shared libs: `common-utils`

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/image-download-service/Dockerfile .
  ```

## Folder Structure

```
image-download-service/
  app/
    main.py                   # FastAPI app with RabbitMQ consumer lifecycle
    core/
      downloader.py           # Image download logic
      image_processor.py      # Image transformation (resize, format)
      archiver.py             # Archive creation (full/delta) + sync tracking
      ratelimiter.py          # Rate limiting for downloads
      nfs_lock.py             # NFS file locking
    messaging/
      consumer.py             # RabbitMQ consumer for download jobs (FP)
      page_image_consumer.py  # RabbitMQ consumer pour pages NON-FP (Chantier D T5)
    routers/
      pages.py                # Endpoints REST /pages/* (Chantier D T4)
  requirements.txt
  Dockerfile
```

## API Endpoints (port 8505)

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` | Health check |
| GET | `/domains` | List all domains with images |
| GET | `/domains/recent` | Domains with recent activity |
| GET | `/domains/unsynced` | Domains with unsynced products |
| GET | `/domains/{domain}/status` | Sync status for a domain |
| POST | `/archive/delta/{domain}` | Create delta archive (new products only) |
| POST | `/archive/full/{domain}` | Create full archive |
| GET | `/archives` | List all archives |
| POST | `/archives/cleanup` | Delete old archives |
| POST | `/sync/{domain}` | Mark products as synced |
| GET | `/sync/{domain}/errors` | Get download errors |
| GET | `/sync/{domain}/pending` | Get unsynced products |

## Conventions

- Images stored at `/data/images/{domain}/produit-{2|3}/{shard}/{shard}/{shard}/`.
- Delta sync: tracks synced vs unsynced products per domain.
- NFS lock for concurrent access safety.

## Dependencies on Other Services

- **RabbitMQ** (consumer for download triggers)
- **image-cdn-service** (serves the same volume read-only)

## Synchronisation d'images — manifest v2 (depuis 2026-04-24)

Le service synchronise les images stockées avec la liste `url_images` reçue dans chaque message RabbitMQ `new_data.product` selon la logique **"replace from source"** :

- **URLs déjà connues** (présentes dans `manifest.json` avec le même `url_source`, et dont les fichiers existent sur disque) → **réutilisées** sans re-téléchargement.
- **Nouvelles URLs** → **téléchargées** ; le filename est dérivé de `sha1(url)[:8]`, ce qui garantit qu'une URL donnée produit toujours le même filename (indépendamment de sa position dans la liste).
- **URLs disparues** de la nouvelle liste → les fichiers (main + thumb) correspondants sont **supprimés** du FS.

### Schéma manifest v2

```json
{"products": [{
  "id_produit": "60001", "nom": "prodA",
  "images": [{
    "url_source": "https://fournisseur.com/a.jpg",
    "main":       "produit-2/1/0/0/proda-60001-ab12cd34.jpg",
    "thumb":      "produit-3/1/0/0/proda-60001-ab12cd34.jpg",
    "filename":   "proda-60001-ab12cd34.jpg"
  }]
}], "last_updated": "2026-04-24T10:00:00"}
```

L'ordre du tableau `images` respecte l'ordre de `url_images` dans le message reçu (le front utilise cet ordre pour afficher l'image principale en premier).

### Migration depuis manifest v1

**Aucune migration préalable.** Un manifest v1 (absence de `url_source` dans les entrées image) déclenche automatiquement un **rebuild complet** au prochain message pour ce produit :
1. Suppression de tous les fichiers legacy listés dans l'ancienne entrée.
2. Téléchargement de toutes les URLs du nouveau message avec la convention v2.
3. Écriture d'un manifest v2 propre.

Les produits jamais re-ingérés après le déploiement gardent leurs fichiers v1 utilisables (aucun dommage).

### Test local

```bash
cd apps-microservices/image-download-service
source .venv/bin/activate
pytest tests/ -v
```

Scénarios couverts par `test_process_product_flow.py` : nouveau produit (J1), ajout+substitution (J2), simple réordonnancement (J2bis = 0 DL), réduction + orphelins (J3), rebuild v1 legacy, résilience aux échecs partiels, échec total préservant l'ancien manifest.

### Garanties principales

- **Cohésion URL↔fichier** : par construction (filename encode l'URL via `sha1[:8]`).
- **Idempotence** : ré-émettre deux fois le même message produit n'entraîne aucun téléchargement.
- **Ordre-indépendance** : un simple réordonnancement de `url_images` ne coûte rien en bande passante.
- **Atomicité** : écriture manifest via temp file + `os.replace`, verrou NFS-safe (`nfs_lock`).
- **Résilience** : si tous les téléchargements d'un re-message échouent, l'ancien manifest est préservé intact (pas de destruction par cascade).

---

## Pages Flow (Chantier D — NON-FP)

Flux dédié au téléchargement d'images extraites de pages NON-FP (`fiche_realisation`,
`savoir_faire`, `presentation_societe`, `page_local`, `listing_produit`). Topologie complètement
isolée du flux Fiche Produit.

### Architecture

```
Hellopro Phase 3 (PHP)
  ↓ POST /pages/enqueue (id_image_isi, domaine, url_image, page_type, ...)
image-download-service
  ↓ publish RabbitMQ
data_exchange_pages_images (TOPIC, durable)
  ↓ routing_key new_data.page_image
page_image_download_tasks_queue
  ↓ consume
PageImageConsumer (feature flag ENABLE_PAGE_IMAGE_CONSUMER)
  ↓ Downloader.process_page_image (INSERT-only)
  ├─ download HTTP image
  ├─ ImageProcessor.process_image_page (PIL/pyvips)
  ├─ atomic write manifest_pages.json (nfs_lock)
  └─ errors_pages.json on failure
```

### Composants Python

| Fichier | Rôle | Tâche |
| --- | --- | --- |
| `app/core/image_processor.py` | `process_image_page(content, domain, storage_subdir, filename)` — refactor partage `_process_image_internal` avec FP | T3 |
| `app/routers/pages.py` | POST `/enqueue` + 5 GETs (`/images`, `/status`, `/errors`, `/by-page-type`, `/by-id/{id}`) | T4 |
| `app/messaging/page_image_consumer.py` | `PageImageConsumer` — topologie RabbitMQ dédiée, MAX_RETRIES=3, RETRY_TTL_MS=30000 | T5 |
| `app/core/downloader.py` | `Downloader.process_page_image()` INSERT-only + helpers manifest_pages + errors_pages | T6 |
| `app/main.py` | Wiring conditionnel via `ENABLE_PAGE_IMAGE_CONSUMER` env var _(T7 — pas encore fusionné sur cette branche, voir `features/chantier-d-main-wiring`)_ | T7 |

### Storage layout

```
{STORAGE_BASE}/images/{domain}/
├── manifest_pages.json            (INSERT-only, atomic via nfs_lock)
├── errors_pages.json              (séparé de errors.json FP)
└── pages/
    ├── {shard1}/{shard2}/
    │   └── page-{page_type}-{id_image_isi}-{hash8}.{ext}   (main)
    └── thumbs/{shard1}/{shard2}/
        └── page-{page_type}-{id_image_isi}-{hash8}.{ext}   (thumb)
```

Sharding (2 niveaux) : `shard1 = last char of filename stem`, `shard2 = 2nd-last char of filename stem`.
À noter : la spec §9.3 mentionne 3 niveaux ; l'implémentation T3/T6 utilise 2 niveaux
(divergence documentée dans le docstring de `Downloader.process_page_image` dans `app/core/downloader.py`).

### Variables d'environnement

> **Note** : ces variables sont lues par `page_image_consumer.py` (T5) et `routers/pages.py` (T4).
> Le wiring dans `main.py` (T7) **n'est pas encore mergé sur cette branche** — voir
> `features/chantier-d-main-wiring`. Une fois mergé, le feature flag prendra effet.

```bash
ENABLE_PAGE_IMAGE_CONSUMER=false               # default OFF (feature flag)
PAGE_IMAGE_QUEUE_NAME=page_image_download_tasks_queue
PAGE_IMAGE_EXCHANGE_NAME=data_exchange_pages_images
PAGE_IMAGE_ROUTING_KEY=new_data.page_image
```

### Endpoints REST

| Method | Path | Description |
| --- | --- | --- |
| POST | `/pages/enqueue` | Publie un événement RabbitMQ → PageImageConsumer (Phase 3 Hellopro trigger, **HTTP 202 Accepted**) |
| GET | `/pages/{domain}/images` | Liste images téléchargées (contenu manifest_pages) |
| GET | `/pages/{domain}/status` | Compteurs (downloaded, error, total) |
| GET | `/pages/{domain}/errors` | Erreurs téléchargement (errors_pages.json) |
| GET | `/pages/{domain}/by-page-type` | Groupement par page_type |
| GET | `/pages/{domain}/by-id/{id_image_isi}` | Lookup direct (Phase 4 retry timeout) |

**Path traversal guard** : tous les endpoints `/pages/{domain}/*` valident `{domain}` via regex `^[A-Za-z0-9._-]+$` (voir `_validate_domain()` dans `app/routers/pages.py`).

### Sémantique INSERT-only vs FP set-based

| Aspect | FP (`process_product`) | Pages (`process_page_image`) |
| --- | --- | --- |
| Granularité événement | Produit (N URLs groupées) | 1 image |
| Sync logic | Set-based "replace from source" | INSERT-only |
| URLs disparues | Suppression fichiers main+thumb | Hors scope MVP (orphan cleanup futur) |
| Idempotence | Réutilisation par url_source dans manifest | Idem (skip si `payload.url_image` reçu == `entry.url_source` manifest + fichier main présent — mapping non trivial : payload utilise `url_image`, manifest persiste `url_source`) |
| Source autorité | `url_images` array message | Hellopro DB `image_scrapping_ia` |

### Tests

Tests Python : section à compléter par T8. Pour l'instant les tests `test_process_product_flow.py`
et `test_image_processor.py` doivent passer pré/post T3 refactor sans modification (validé).
T6 a ajouté `tests/capture_process_image_fixture.py` + `_post.py` pour diff régression FP
(ops-side, dans container Docker).

### Références

- Spec : `docs/superpowers/specs/2026-05-05-images-classification-revisee-design.md` §9 (architecture extension), §9.3 (storage layout), §9.5 (manifest schema), §9.10 (POST endpoint), §9.11 (consumer), §9.12 (downloader methods), §9.13 (main wiring).
- Plan : `docs/superpowers/plans/2026-05-05-images-classification-revisee.md` tâches T3–T9.
