# nextjs-conseils-hp

Service Next.js 15 pour les pages conseils HelloPro.

## Stack

- **Next.js 15** (App Router)
- **React 19**
- **Tailwind CSS 4** (avec `@theme`)
- **TypeScript 5**
- **Node 22 LTS**

## Quickstart

```bash
nvm use         # Node 22
npm install
cp .env.example .env.local  # remplir les valeurs
npm run dev     # http://localhost:3000/conseils
```

## Documentation

Lire `CLAUDE.md` dans ce dossier pour :
- Architecture (pattern BlockRenderer)
- Conventions de code
- Workflow collaboration à 2 devs
- Catalogue des blocs

## Scripts

| Commande | Description |
|---|---|
| `npm run dev` | Serveur de dev sur `http://localhost:3000/conseils` |
| `npm run build` | Build production |
| `npm run start` | Lance le build production |
| `npm run lint` | ESLint |
| `npm run typecheck` | Vérification types TS |
| `npm run format` | Prettier |
| `npm test` | Tests Vitest |
| `npm run test:watch` | Tests en mode watch |

## Architecture en bref

```
app/(conseils)/[slug]/page.tsx  → Server Component, fetch données
  └─ <ConseilTemplate page={...} />
       ├─ <SiteHeader />, <Hero />
       ├─ {pageType === 'prix' && <PriceSimulator />}
       ├─ blocks.map(b => <BlockRenderer block={b} />)
       └─ <AuthorBlock />, <SiteFooter />
```

Le `BlockRenderer` est un switch qui mappe les blocs BO HelloPro vers leurs composants React. Voir `CLAUDE.md §2`.

## Service Docker isolé

Ce service est conteneurisé indépendamment. Communication avec les autres services (formulaire, API PHP) via HTTP uniquement. Pas de partage de runtime → versions de techno indépendantes du reste du monorepo.
