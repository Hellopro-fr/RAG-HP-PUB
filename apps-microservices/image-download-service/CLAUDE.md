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
      consumer.py             # RabbitMQ consumer for download jobs
  requirements.txt
  Dockerfile
```

## API Endpoints (port 8505)

| Method | Path | Description |
|---|---|---|
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
