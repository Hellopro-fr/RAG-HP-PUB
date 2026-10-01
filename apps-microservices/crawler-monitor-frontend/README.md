# crawler-monitor-frontend

Interface web de supervision du crawler : suivi temps réel des jobs, capacité
des replicas, queues de requêtes, datasets, callbacks, journal d'audit et
albums d'images produits.

SPA React 19 / Vite 7, servie en production par nginx sur le port **8099**.
Elle consomme l'API REST et le WebSocket de **crawler-monitor-backend**
(service Go, port 3001).

## Prérequis

- Node 20+
- Yarn 4 (via `corepack enable` — la version est épinglée dans `package.json`)

## Développement

```bash
yarn install
yarn dev
```

Le serveur de dev proxifie `/api` vers `http://localhost:3001` et
`/cdn-images` vers `http://localhost:8580` : il faut donc que
`crawler-monitor-backend` (et, pour les albums, `image-cdn-service`) tournent
en local.

## Scripts

| Commande | Effet |
|----------|-------|
| `yarn dev` | serveur de développement avec HMR |
| `yarn build` | build de production dans `dist/` |
| `yarn preview` | sert le build de production localement |
| `yarn lint` | ESLint sur tout le projet |
| `yarn test` | suite de tests vitest (une passe) |
| `yarn test:watch` | vitest en mode watch |

## Docker

```bash
docker build -t crawler-monitor-frontend .
docker run -p 8099:8099 crawler-monitor-frontend
```

Le build est multi-stage (Node pour compiler, nginx pour servir). En
conteneur, nginx résout les upstreams par leur nom de service Docker :
`crawler-monitor-backend:3001` et `image-cdn-service:8580`.

## Configuration

Aucune variable d'environnement au build : les URLs backend ne sont pas
compilées dans le bundle, tout passe par des chemins relatifs (`/api`,
`/cdn-images`) résolus par le proxy — Vite en développement, nginx en
production (voir `vite.config.js` et `nginx.conf`).

L'authentification se fait à l'exécution : l'utilisateur se connecte, le JWT
retourné est conservé côté navigateur et joint à chaque appel.

## Documentation

`CLAUDE.md` détaille la stack, l'arborescence, les routes et les conventions
de code.
