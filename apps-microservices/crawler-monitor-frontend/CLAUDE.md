# crawler-monitor-frontend

SPA de supervision temps réel des jobs du crawler : état des jobs, capacité des
replicas, queues de requêtes, datasets, callbacks, journal d'audit et albums
d'images produits.

## Stack

| Couche | Techno |
|--------|--------|
| Build | **Vite 7** (ESM, `"type": "module"`) |
| UI | **React 19** en JSX (pas de TypeScript) |
| Styles | **Tailwind CSS 3** + `tailwindcss-animate`, primitives Radix UI |
| Data fetching | **TanStack React Query 5** (+ WebSocket pour l'invalidation live) |
| Routing | **react-router-dom 6** |
| Icônes / charts | **lucide-react**, **recharts 3** |
| Virtualisation | **react-window 2** (listes albums / produits) |
| Tests | **vitest 3** + Testing Library + jsdom |
| Lint | **ESLint 9** (flat config) |
| Package manager | **yarn 4** (Berry, `nodeLinker: node-modules`) |

> Pas de `date-fns` ni de `react-date-range` : le formatage des dates passe par
> `Intl` / `toLocaleString('fr-FR')`.

## Commandes

| Action | Commande |
|--------|----------|
| Dev (HMR, port Vite par défaut) | `yarn dev` |
| Build de production | `yarn build` |
| Prévisualiser le build | `yarn preview` |
| Lint | `yarn lint` |
| Tests (une passe) | `yarn test` |
| Tests en watch | `yarn test:watch` |

## Arborescence

```
src/
  main.jsx          # point d'entrée (providers : QueryClient, Theme, Toast, Router)
  App.jsx           # shell applicatif : auth, WebSocket, table de routage
  index.css         # tokens de design + base Tailwind
  pages/            # une page par route (Overview, Queue, Dataset, Albums, Audit…)
  components/       # composants métier
    albums/         # albums d'images produits (table, cartes, strip Coverflow)
    layout/         # AppShell, Sidebar, Topbar, Breadcrumbs, BottomTabBar
    providers/      # ThemeProvider
    ui/             # primitives shadcn-like (button, badge, dialog, table…)
  hooks/            # queries.js (tous les hooks React Query), hooks divers
  lib/              # client API, constantes, navigation, utilitaires
  coherence/        # moteur de règles de cohérence UI/backend + pastille de santé
tests/              # tests d'intégration des pages (vitest + Testing Library)
```

Les tests unitaires proches du code vivent à côté de leur module
(`src/lib/*.test.js`, `src/coherence/**/*.test.js`) ; les tests de page sont
dans `tests/`. Il n'y a pas de `App.test.js`.

## Routes

Servies par `react-router-dom` depuis `src/App.jsx` (SPA : nginx renvoie
`index.html` sur tout chemin inconnu) :

- `/` — vue d'ensemble des jobs
- `/jobs/:id` — détail d'un job, avec ses sous-vues queue / dataset / replay
- `/albums`, `/albums/:domain` — albums d'images par domaine
- `/domains`, `/domains/:domain` — domaines crawlés
- `/callbacks` — webhooks en échec et rejeu
- `/audit` — journal d'audit
- `/capacity-planning` — planification de capacité
- `/health` — santé des règles de cohérence
- tout le reste redirige vers `/`

## Backend et proxy

Le frontend ne parle qu'à **crawler-monitor-backend** (service **Go / chi**,
port **3001**), qui expose l'API REST `/api/*` et le WebSocket temps réel sur
le même préfixe.

| Préfixe | Dev (`vite.config.js`) | Prod (`nginx.conf`) |
|---------|------------------------|---------------------|
| `/api` | `http://localhost:3001` | `http://crawler-monitor-backend:3001` |
| `/cdn-images` | `http://localhost:8580` (réécrit en `/images`) | `http://image-cdn-service:8580` (réécrit en `/images`) |

Authentification par JWT : le token est envoyé en header `Authorization:
Bearer` sur les appels REST, et en query string sur le handshake WebSocket
(`/api?token=…`) — d'où le `log_format` sans query string sur le bloc `/api`
de nginx, pour ne pas écrire le token dans les access logs.

## Docker

Build multi-stage : `node:20-alpine` (corepack + `yarn install --immutable` +
`yarn build`) puis `nginx:alpine` qui sert `dist/` sur le port **8099**.
`.dockerignore` exclut `node_modules`, `dist` et le cache yarn du contexte de
build. Les source maps sont désactivées (`sourcemap: false`) et nginx renvoie
404 sur `*.map`.

## Conventions

- JSX simple, sans TypeScript ; modules ESM.
- Libellés d'interface en **français**, pas d'i18n.
- Les appels réseau passent tous par `src/lib/api.js` et les hooks de
  `src/hooks/queries.js` — pas de `fetch` direct dans les composants.
- Les primitives de `src/components/ui/` suivent la convention shadcn/ui
  (`cn()` + `class-variance-authority`).
