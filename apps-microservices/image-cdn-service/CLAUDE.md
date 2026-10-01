# image-cdn-service

Nginx-based static image CDN serving product images from a shared NFS volume.

## Tech Stack

- Nginx 1.27 (Alpine) on port **8580**
- No application code -- pure Nginx config

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/image-cdn-service/Dockerfile .
  ```
- Volume mount: `/data` (read-only, shared with image-download-service)

## Folder Structure

```
image-cdn-service/
  nginx.conf    # Full Nginx configuration
  Dockerfile    # nginx:1.27-alpine base
```

## Endpoints (port 8580)

| Path | Description |
|---|---|
| `/health` | JSON health check (`{"status":"ok"}`) |
| `/images/{domain}/produit-{2\|3}/{shard}/.../file.jpg` | Serve product images |
| `*` | 404 for everything else |

## Conventions

- Only image files served (jpg, jpeg, png, gif, webp). Other types return 403.
- Browser cache: 30 days, `immutable` directive.
- CORS: `Access-Control-Allow-Origin: *`.
- Open file cache: 10K entries, 60s inactive, min 2 uses.
- No gzip (images already compressed).
- Directory listing disabled.
- Built-in Docker HEALTHCHECK every 15s.

## Dependencies on Other Services

- **image-download-service** (provides the `/data/images/` volume with downloaded images).

## Exposition publique

- URL publique (reverse-proxy api.hellopro.eu) : `https://api.hellopro.eu/image_cdn-service/`
  - `GET /image_cdn-service/health` → `{"status":"ok",...}`
  - `GET /image_cdn-service/images/{domain}/...` → image statique
- Le **même** `location /images/` sert les deux flux (un seul volume `/data` partagé) :
  - **FP** : `/images/{domain}/produit-2|3/{shard}/.../file.jpg`
  - **NON-FP (Chantier D)** : `/images/{domain}/pages/{s1}/{s2}/page-...jpg` (et `pages/thumbs/...`)
  Aucune route dédiée : le bloc jpg/png/... sert tout fichier image sous `/data/images/`.
