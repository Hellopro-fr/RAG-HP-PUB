# nextjs-conseils-hp — Pages conseils HelloPro

> **Service Next.js 15 du monorepo RAG-HP-PUB** (conteneur Docker isolé)
> Remplacement progressif des pages conseils PHP actuelles (`conseils.hellopro.fr`) par un nouveau template moderne, hébergé sur GCP, monté en reverse proxy sur le **sous-domaine** `conseils.hellopro.fr/<slug>-<id>.html`. Les URLs existantes restent strictement identiques (préservation totale du SEO).
>
> ⚠️ **Lire intégralement ce fichier au début de CHAQUE session Claude Code** avant d'écrire du code.

---

## 0. Contexte projet

| Élément | Valeur |
|---|---|
| Service | `nextjs-conseils-hp` |
| Localisation | `apps-microservices/nextjs-conseils-hp/` (monorepo RAG-HP-PUB) |
| URL publique | `https://conseils.hellopro.fr/<slug>-<id>.html` (sous-domaine via reverse proxy nginx) |
| Pattern URL | `<slug>-<id>.html` — l'ID numérique est extrait du suffixe `-<digits>` du slug |
| basePath Next.js | **Aucun** — app montée à la racine du sous-domaine |
| Service jumeau de référence | `nextjs-formulaire-hp` (suivre ses conventions, sauf basePath qui diffère) |
| Skill associée | `hellopro-nextjs` (à consulter pour les patterns standards) |
| Backend données | API HelloPro (proxy via routes API Next.js, **pas de connexion DB directe**) |
| Source de vérité du contenu | BO HelloPro (table de blocs ordonnés) |
| Devs | Erick + partenaire (collaboration parallèle, voir §16) |

---

## 1. Stack — versions verrouillées

| Couche | Version exacte | Note |
|---|---|---|
| Node.js | **22 LTS** | Verrouillé via `.nvmrc` et `engines` |
| Package manager | **npm** | ❌ Pas de bun, pas de pnpm, pas de yarn |
| Next.js | **15.x** | App Router, `params` et `searchParams` async |
| React | **19.x** | `forwardRef` plus nécessaire (ref est une prop) |
| TypeScript | **5.x** | `strict: true` |
| Tailwind CSS | **4.x** | Config via `@theme` dans `globals.css` (pas de `tailwind.config.ts`) |
| shadcn/ui | Latest stable | Composants Radix copy-paste, pas npm |
| TanStack React Query | 5.x | Server components-friendly |
| Zustand | 5.x | Pour états cross-blocs côté client |
| React Hook Form + Zod | Latest | Pour les formulaires (devis, contact) |
| Vitest + React Testing Library | Latest | Tests unitaires |

**📌 Service isolé en conteneur Docker** — pas de partage de runtime avec les autres services du monorepo. Communication via HTTP/JSON uniquement. Les versions ci-dessus peuvent évoluer indépendamment du formulaire HP.

**Vérifier la version avant tout commit** :
```bash
node -v    # doit être >= 22, < 25
npm -v     # doit être >= 10
cat .nvmrc # doit afficher 22
```

---

## 2. Architecture — le pattern central : `BlockRenderer`

### 2.1 Principe directeur

Le BO HelloPro stocke les pages conseils comme une **liste ordonnée de blocs typés**. Le front **doit** refléter cet ordre dynamiquement. **Ne JAMAIS hardcoder la composition d'une page conseil** sauf pour les blocs spécifiques au type (`prix` / `top` / `autre`) qui n'existent pas en BO.

```typescript
// types/conseils.ts
export type ConseilPageType = 'prix' | 'top' | 'autre';

export type ConseilBlockType =
  | 'h2'              // Titre secondaire
  | 'h3'              // Titre paragraphe
  | 'texte'           // Texte (+ estimation facultatif + CTA facultatif)
  | 'pros-cons'       // Tableau avantages & inconvénients
  | 'resume'          // "L'essentiel à retenir"
  | 'image'           // Image seule
  | 'texte-image'     // Texte à gauche, image à droite
  | 'image-texte'     // Image à gauche, texte à droite
  | 'image-image'     // Deux images côte à côte
  | 'video'           // URL YouTube
  | 'cta'             // Bandeau orange "Estimez le prix de..."
  | 'produits'        // Liste de fournisseurs (IDs produits)
  | 'tableau-html'    // HTML brut (sandboxé)
  | 'tableau-prix'    // 2 colonnes "Estimation de prix" + valeur
  | 'faq';            // Bloc FAQ (accordéon)

export interface ConseilBlock {
  id: string;
  type: ConseilBlockType;
  order: number;
  data: Record<string, unknown>;  // payload typé par bloc, voir types par bloc
}

export interface ConseilPage {
  slug: string;
  pageType: ConseilPageType;
  meta: { title: string; description: string; ogImage?: string };
  hero: { title: string; subtitle?: string; image?: string; estimation?: { min: number; max: number; unit: string } };
  blocks: ConseilBlock[];
  // Blocs spécifiques au type, gérés HORS du BlockRenderer :
  priceData?: PriceData;          // Si pageType === 'prix'
  topFabricants?: TopFabricantsData; // Si pageType === 'top'
  rulesTable?: RulesTableData;       // Si pageType === 'autre'
}
```

### 2.2 Composition côté page

```typescript
// app/(conseils)/[slug]/page.tsx (Server Component)
export default async function Page({ params }: { params: { slug: string } }) {
  const page = await fetchConseilPage(params.slug); // côté serveur
  return <ConseilTemplate page={page} />;
}

// components/conseil/ConseilTemplate.tsx
export function ConseilTemplate({ page }: { page: ConseilPage }) {
  return (
    <>
      <SiteHeader />
      <Hero {...page.hero} />
      <main className="mx-auto max-w-[1400px] grid lg:grid-cols-[280px_1fr] gap-10 px-4 py-10">
        <Sidebar items={extractTOC(page.blocks)} />
        <article className="min-w-0">
          {/* Blocs spécifiques au type — insérés à position fixe */}
          {page.pageType === 'prix' && page.priceData && (
            <PriceSimulator data={page.priceData} />
          )}
          {page.pageType === 'top' && page.topFabricants && (
            <TopFabricantsCards data={page.topFabricants} />
          )}

          {/* Rendu dynamique de la liste de blocs BO */}
          {page.blocks
            .sort((a, b) => a.order - b.order)
            .map((block) => (
              <BlockRenderer key={block.id} block={block} />
            ))}

          {/* Blocs de pied (communs aux 3 types) */}
          <AuthorBlock />
          <Crossell />
        </article>
      </main>
      <SiteFooter />
    </>
  );
}
```

### 2.3 Le BlockRenderer

```typescript
// components/conseil/BlockRenderer.tsx
import { ConseilBlock } from '@/types/conseils';
import { H2Block } from './blocks/H2Block';
import { TextBlock } from './blocks/TextBlock';
// ... autres imports

export function BlockRenderer({ block }: { block: ConseilBlock }) {
  switch (block.type) {
    case 'h2':            return <H2Block data={block.data as any} />;
    case 'h3':            return <H3Block data={block.data as any} />;
    case 'texte':         return <TextBlock data={block.data as any} />;
    case 'pros-cons':     return <ProsConsBlock data={block.data as any} />;
    case 'resume':        return <ResumeBlock data={block.data as any} />;
    case 'image':         return <ImageBlock data={block.data as any} />;
    case 'texte-image':   return <TexteImageBlock data={block.data as any} />;
    case 'image-texte':   return <ImageTexteBlock data={block.data as any} />;
    case 'image-image':   return <ImageImageBlock data={block.data as any} />;
    case 'video':         return <VideoBlock data={block.data as any} />;
    case 'cta':           return <CTABlock data={block.data as any} />;
    case 'produits':      return <ProduitsBlock data={block.data as any} />;
    case 'tableau-html':  return <TableauHtmlBlock data={block.data as any} />;
    case 'tableau-prix':  return <TableauPrixBlock data={block.data as any} />;
    case 'faq':           return <FaqBlock data={block.data as any} />;
    default: {
      const exhaustive: never = block.type;
      console.warn(`[BlockRenderer] Type non géré: ${exhaustive}`);
      return null;
    }
  }
}
```

**Pourquoi `never` ?** Garantit qu'un nouveau type de bloc ajouté dans `ConseilBlockType` mais oublié dans le switch sera **flag par TypeScript à la compilation**.

---

## 3. Structure des dossiers (à respecter strictement)

```
app/
  layout.tsx                       # Root layout (providers, fonts, analytics)
  page.tsx                         # / → page d'accueil conseils (liste / redirection)
  not-found.tsx
  [slugWithId]/                    # Dynamic catch-all : <slug>-<id>.html
    page.tsx                       # Server Component (extrait ID, fetch données)
    not-found.tsx
  api/                             # Routes API Next.js (proxy backend)
    conseils/
      [slug]/route.ts              # GET page complète par slug
    produits/route.ts              # GET liste produits par IDs
    devis/route.ts                 # POST soumission devis

components/
  conseil/
    BlockRenderer.tsx              # Le switch central
    ConseilTemplate.tsx            # Layout principal
    SiteHeader.tsx                 # Header global
    SiteFooter.tsx                 # Footer global
    Hero.tsx                       # Hero générique paramétrable
    Sidebar.tsx                    # Sommaire TOC auto
    AuthorBlock.tsx
    Crossell.tsx
    blocks/                        # Composants de bloc BO
      H2Block.tsx
      H3Block.tsx
      TextBlock.tsx
      ProsConsBlock.tsx
      ResumeBlock.tsx
      ImageBlock.tsx
      TexteImageBlock.tsx
      ImageTexteBlock.tsx
      ImageImageBlock.tsx
      VideoBlock.tsx
      CTABlock.tsx
      ProduitsBlock.tsx
      TableauHtmlBlock.tsx
      TableauPrixBlock.tsx
      FaqBlock.tsx
    specific/                      # Blocs spécifiques au type de page
      prix/
        PriceSimulator.tsx
        PriceCurve.tsx
        Comparator.tsx
      top/
        TopFabricantsCards.tsx
      autre/
        RulesTable.tsx
  ui/                              # shadcn/ui (NE PAS modifier les fichiers générés)

hooks/
  useTOC.ts                        # Extraction sommaire depuis blocs
  api/
    useConseilPage.ts
    useProduits.ts
    useDevisSubmission.ts

lib/
  api/
    client.ts                      # apiClient générique (réutiliser celui du formulaire)
    endpoints.ts
    conseils.ts                    # fetchConseilPage(slug)
    produits.ts
  blocks/
    extractTOC.ts                  # Génère la liste sommaire depuis les H2/H3
    validators.ts                  # Validation Zod par type de bloc
  analytics/                       # GTM, GA4, Hotjar (réutiliser ceux du formulaire)
  utils.ts                         # cn(), helpers

types/
  conseils.ts                      # Types Block, Page, etc.
  blocks/                          # Types détaillés par bloc
    text.ts
    image.ts
    video.ts
    ...

data/
  mocks/                           # Fixtures pour dev local (Phase 6)
    page-prix.ts
    page-top.ts
    page-autre.ts

styles/
  globals.css                      # Design tokens HSL (copie du formulaire HP)

public/
  images/
  fonts/

__tests__/                         # ou *.test.tsx à côté de chaque composant
```

---

## 4. Pattern obligatoire pour ajouter un bloc BO

Quand on ajoute un nouveau type de bloc à supporter, **suivre ces étapes dans l'ordre** :

1. ✅ **Ajouter le type** dans `types/conseils.ts` → `ConseilBlockType`
2. ✅ **Créer le type de données** dans `types/blocks/<nom>.ts` (Zod schema + TS interface)
3. ✅ **Créer le composant** dans `components/conseil/blocks/<NomDuBloc>Block.tsx`
4. ✅ **Ajouter le case** dans `BlockRenderer.tsx` (avec cast typé)
5. ✅ **Créer une fixture** dans `data/mocks/blocks/<nom>.ts` pour tester en local
6. ✅ **Écrire le test** `<NomDuBloc>Block.test.tsx` (Vitest + RTL)
7. ✅ **Documenter** dans ce CLAUDE.md (section 17 "Catalogue des blocs")
8. ✅ **Vérifier la couverture exhaustive** : `npm run typecheck` ne doit pas se plaindre du `never`

**Anti-pattern** : ❌ ne JAMAIS créer un composant `<MonBloc>` hors de `components/conseil/blocks/` et l'utiliser directement dans une page. Tout passe par le BlockRenderer.

---

## 5. Pattern pour les pages

### 5.1 Page Server Component (obligatoire)

⚠️ **Next.js 15** : `params` et `searchParams` sont des **Promises**. Toujours `await`.

```typescript
// app/[slugWithId]/page.tsx
import { Metadata } from 'next';
import { fetchConseilPage } from '@/lib/api/conseils';
import { ConseilTemplate } from '@/components/conseil/ConseilTemplate';
import { notFound } from 'next/navigation';

export const revalidate = 3600; // ISR 1h, ajustable par page

type PageProps = {
  params: Promise<{ slugWithId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

/**
 * Pattern URL : <slug>-<id>.html
 * Exemple : combien-coute-un-conteneur-1243.html → slug = "combien-coute-un-conteneur", id = 1243
 */
function parseSlugWithId(input: string): { slug: string; id: number } | null {
  const match = input.match(/^(.+)-(\d+)\.html$/);
  if (!match) return null;
  return { slug: match[1], id: Number(match[2]) };
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slugWithId } = await params;
  const parsed = parseSlugWithId(slugWithId);
  if (!parsed) return {};
  const page = await fetchConseilPage(parsed.id);
  if (!page) return {};
  return {
    title: page.meta.title,
    description: page.meta.description,
    openGraph: {
      title: page.meta.title,
      description: page.meta.description,
      images: page.meta.ogImage ? [page.meta.ogImage] : [],
    },
  };
}

export default async function Page({ params }: PageProps) {
  const { slugWithId } = await params;
  const parsed = parseSlugWithId(slugWithId);
  if (!parsed) notFound();
  const page = await fetchConseilPage(parsed.id);
  if (!page) notFound();
  return <ConseilTemplate page={page} />;
}
```

**Idem pour `cookies()`, `headers()`, `draftMode()`** : tous async en Next.js 15.

### 5.2 Règle : Server > Client

- **Toujours** rendre les pages côté serveur (SEO).
- Passer en Client Component **uniquement** les sous-arbres qui ont besoin d'interactivité (PriceSimulator, formulaires, accordéons FAQ contrôlés).
- Marquer explicitement `'use client'` en haut des composants concernés.

---

## 6. Routage — sous-domaine sans basePath

⚠️ **Différence majeure avec `nextjs-formulaire-hp`** : ce service est monté sur un **sous-domaine** (`conseils.hellopro.fr`), pas sur un sous-chemin (`/conseils`). **Pas de `basePath` à configurer.**

```javascript
// next.config.js
const nextConfig = {
  // PAS de basePath ni assetPrefix — l'app vit à la racine du sous-domaine
  output: 'standalone',
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: 'cdn.hellopro.fr' },
      { protocol: 'https', hostname: 'api.hellopro.fr' },
    ],
  },
  // pas de "trailingSlash" — alignement avec formulaire HP
};
module.exports = nextConfig;
```

### 6.1 Pattern URL

Toutes les pages conseils suivent le format hérité de l'ancien site PHP :

```
https://conseils.hellopro.fr/<slug>-<id>.html
```

Exemples :
- `combien-coute-un-conteneur-1243.html` → slug=`combien-coute-un-conteneur`, id=`1243`
- `top-10-fabricants-portes-industrielles-892.html` → slug=`top-10-fabricants-portes-industrielles`, id=`892`

**L'ID numérique est la clé de fetch côté API.** Le slug est cosmétique (SEO) mais doit toujours être présent dans l'URL pour préserver le référencement existant.

Si quelqu'un arrive sur `<slug-modifié>-<id>.html` (slug ne correspondant pas au slug canonique de l'ID), on **renvoie un 301** vers le slug canonique (à implémenter en Phase 8).

### 6.2 Reverse proxy nginx

```nginx
# conseils.hellopro.fr → conteneur Next.js
server {
  server_name conseils.hellopro.fr;
  location / {
    proxy_pass http://nextjs-conseils-hp:3000;
    # pas de rewrite ni de prefix — passthrough direct
  }
}
```

### 6.3 Navigation interne

**URLs internes** : toujours utiliser `<Link>` de Next.js. Aucun préfixe à gérer (pas de basePath).

**Assets** : `<Image>` de Next.js fonctionne nativement (pas besoin de `getAssetPath()` à la différence du formulaire).

---

## 7. Design system

### 7.1 Tokens

- Couleurs : **tokens CSS HSL** dans `app/globals.css`, déclarés via `@theme {}` (syntaxe Tailwind 4).
- ❌ Jamais de couleurs hardcodées en hex/rgb dans les composants.
- Polices : Inter (par défaut), à confirmer avec le formulaire HP.
- Les **valeurs HSL** doivent rester identiques au formulaire HP (sync UX), même si la syntaxe de déclaration diffère (Tailwind 3 vs 4). Toute modification de palette → coordonner avec l'équipe formulaire.

**Exemple de déclaration Tailwind 4** :
```css
/* app/globals.css */
@import "tailwindcss";
@import "tw-animate-css";

@theme {
  --color-primary: hsl(231 100% 60%);
  --color-primary-foreground: hsl(0 0% 100%);
  --color-accent: hsl(21 80% 55%);
  /* ... */
}
```

Tailwind 4 génère automatiquement les classes `bg-primary`, `text-primary-foreground`, `bg-accent`, etc.

### 7.1bis ⚠️ `max-w-2xl` vaut 1400px dans ce projet — ne pas l'utiliser

`globals.css` définit `--container-2xl: 1400px` pour la largeur de page. En
Tailwind 4, les utilitaires `max-w-*` lisent le **même namespace `--container-*`**
que `--container-2xl`. Conséquence : `max-w-2xl` ne vaut pas 42rem (672px) comme
dans la doc Tailwind, mais **1400px**.

Symptômes déjà rencontrés : une pop-up `max-w-2xl` large de 1400px, avec un champ
e-mail en `flex-1` étiré sur toute la largeur et des éléments centrés qui semblent
flotter dans le vide.

**Règle** : pour une largeur de lecture, écrire la valeur explicitement —
`max-w-[42rem]`. Les autres échelons (`max-w-sm/md/lg/xl/3xl/7xl`) ne sont pas
redéfinis et se comportent normalement ; seul `2xl` est piégé.

### 7.1ter Échelle typographique du HUB — `components/hub/typography.ts`

**Aucune classe `text-<taille>` en dur sur un titre d'un composant
`components/hub/`.** Les tailles viennent des constantes de
`components/hub/typography.ts` : `PAGE_TITLE`, `SECTION_TITLE`, `SECTION_SUBTITLE`,
`BANNER_TITLE`, `FEATURE_TITLE`, `CARD_TITLE`, `CARD_BODY`, `PROSE`,
`DIALOG_TITLE`, `TAG`, `LINK_LABEL`, `CHECK_ITEM`, `TILE_LABEL`, `META`.

Pourquoi : les tailles avaient été portées bloc par bloc depuis le prototype
Lovable. Mesure avant correction — **3 échelles de titre de section** (`text-3xl
sm:text-4xl`, `text-2xl`, `text-xl sm:text-2xl`) et **4 de titre de carte**
(`text-lg`, `text-[17px]`, `text-base`, `text-2xl sm:text-3xl`) pour 6 niveaux de
hiérarchie réels. En scrollant, l'œil lit un changement de police à chaque bloc.
Chaque valeur prise isolément était défendable : c'est un défaut de cohérence, pas
de goût, et il ne se corrige donc qu'en un seul endroit.

Deux règles à ne pas contourner :

- **Aucune couleur dans les constantes.** Le même niveau sert sur fond clair et sur
  aplat foncé (`FinalCta`, `OverlayCard`, hero). Et concaténer deux classes de
  couleur Tailwind ne les départage pas de façon déterministe — c'est l'ordre dans
  la feuille compilée qui tranche, pas l'ordre dans l'attribut. La couleur reste au
  point d'appel.
- **Un nouveau niveau se justifie par écrit** dans le fichier, ou n'existe pas.

`__tests__/components/hub/typography.test.ts` échoue sur toute classe de taille
écrite en dur dans un `<h1>`..`<h4>` de `components/hub/`.

Deux exclusions assumées, listées dans le test :

| Fichier | Raison |
|---|---|
| `components/hub/AssistantForm.tsx` | Questionnaire du hero — laissé tel quel sur demande. Retirer la ligne du test dira ce qu'il reste à convertir. |
| `components/conseil/blocks/FaqBlock.tsx` | Partagé avec les pages conseils : le modifier changerait tout le template conseils. Rend son titre en `text-3xl font-extrabold` sans palier `sm:` — seul écart typographique restant en bas de page HUB. |

### 7.2 Classes Tailwind autorisées

| Token | Usage |
|---|---|
| `bg-background` / `text-foreground` | Fond et texte principal |
| `bg-card` / `text-card-foreground` | Cartes |
| `bg-primary` / `text-primary-foreground` | Boutons d'action principaux |
| `bg-muted` / `text-muted-foreground` | Éléments secondaires |
| `bg-accent` / `text-accent-foreground` | Accents (CTA orange) |
| `border-border` | Bordures |
| `text-destructive` | Erreurs |

### 7.3 Composants shadcn/ui à installer initialement

```
accordion, alert, alert-dialog, aspect-ratio, avatar, badge, button,
card, checkbox, collapsible, dialog, dropdown-menu, form, input,
label, navigation-menu, popover, progress, radio-group, scroll-area,
select, separator, skeleton, slider, switch, tabs, textarea, toast,
toggle, tooltip
```

Installer avec : `npx shadcn@latest add <component>` (CLI compatible Tailwind 4)

⚠️ Une fois généré, **ne jamais éditer manuellement** les fichiers dans `components/ui/`. Si besoin de customiser : créer un wrapper dans `components/conseil/`.

---

## 8. Variables d'environnement

```env
# .env.local (dev local — NE PAS COMMITER)
NEXT_PUBLIC_API_BASE_URL=https://api.hellopro.fr/v1
NEXT_PUBLIC_GTM_ID=GTM-XXXXXXX
NEXT_PUBLIC_GA_MEASUREMENT_ID=G-XXXXXXXXXX
NEXT_PUBLIC_HOTJAR_ID=1234567

# Côté serveur uniquement
CONSEILS_API_TOKEN=<token-pour-bo-readonly>
INVALID_PAGE_REDIRECT_URL=https://www.hellopro.fr/404.html
```

> ⚠️ **Production / Docker** : `CONSEILS_API_TOKEN` est défini dans **`RAG-HP-PUB/.env`** (racine du monorepo). Le `docker-compose.yml` charge ce fichier via `env_file: ./.env` — ne pas dupliquer la variable dans `.env.production` du service.

**Toujours** maintenir un `.env.example` à jour avec les clés (valeurs vides). Pas de secrets dans le code.

---

## 9. Données : dev local vs production

| Phase | Source des données |
|---|---|
| **Phase 6** (templates statiques) | Fixtures en dur dans `data/mocks/page-{prix,top,autre}.ts` |
| **Phase 8** (dynamisation) | API HelloPro via routes proxy Next.js `app/api/conseils/[slug]/route.ts` |
| **Prod** | API HelloPro (même routes proxy, basée sur env vars) |

**Règle** : le composant `ConseilTemplate` doit **fonctionner identiquement** avec une fixture ou avec des données API. Pas de logique conditionnelle "si dev / si prod" dans les composants.

---

## 10. Tests

### 10.1 Quoi tester

- **Chaque bloc** : rendu avec différentes données, accessibilité de base, cas limites (props vides).
- **BlockRenderer** : couverture exhaustive (un test par type de bloc).
- **Pages** : test d'intégration avec fixture mockée.
- **API routes** : tests d'intégration (success, error, edge cases).

### 10.2 Outils

```bash
npm test              # Lance tous les tests Vitest
npm run test:watch    # Mode watch
npm run test:coverage # Avec couverture
```

### 10.3 Couverture minimale exigée

- Composants conseil : **80%** minimum
- BlockRenderer : **100%**
- Routes API : **70%** minimum

---

## 11. Conventions de code

### 11.1 Imports

- Toujours utiliser l'alias `@/` (configuré dans `tsconfig.json`).
- Ordre des imports : externes → `@/types` → `@/lib` → `@/hooks` → `@/components` → relatifs.

### 11.2 Nommage

| Élément | Convention | Exemple |
|---|---|---|
| Composant | PascalCase | `TextBlock.tsx` |
| Hook | camelCase, préfixe `use` | `useConseilPage.ts` |
| Fonction utilitaire | camelCase | `extractTOC.ts` |
| Type / Interface | PascalCase | `ConseilBlock`, `ConseilPage` |
| Constante | UPPER_SNAKE_CASE | `MAX_BLOCKS_PER_PAGE` |
| Dossier | kebab-case | `components/conseil/blocks/` |

### 11.3 Props

- Toujours typer explicitement (pas de `any`).
- Préférer interfaces à types pour les props (sauf union).
- Destructurer dans la signature.

```typescript
// ✅ Bon
interface TextBlockProps {
  data: TextBlockData;
}
export function TextBlock({ data }: TextBlockProps) { ... }

// ❌ Mauvais
export function TextBlock(props: any) { ... }
```

### 11.4 Commits — Conventional Commits bilingues

Voir la section « Commit messages » du `CLAUDE.md` racine, ou lancer `/commit-msg`.

Format : `<type>(<scope>): <description EN> / <description FR>`

Exemples :
- `feat(conseils): add TextBlock component / ajoute le composant TextBlock`
- `fix(blocks): correct image aspect ratio / corrige le ratio des images`
- `refactor(api): extract conseils fetcher / extrait le fetcher conseils`

Scopes valides pour ce service : `conseils`, `blocks`, `api`, `hero`, `sidebar`, `infra`, `tests`, `docs`, `hub`.

---

## 11bis. Template HUB « projet » (2e template du service)

Le service héberge un **second template**, indépendant des pages conseils : les
pages HUB « projet », sur le même sous-domaine.

| Élément | Valeur |
|---|---|
| URL publique | `https://conseils.hellopro.fr/<slug>-<id>-projet.html` |
| Route interne | `app/hub/[hubSlug]/page.tsx` |
| Rendu | Prérendu au build via `generateStaticParams`, puis `revalidate = 86400`. Pas `force-static` : il gèle les `fetch`, ce qui figerait les rubriques du méga-menu (voir §11bis.1) |
| Source de contenu | **`data/hub/*.ts`** — statique. Les projets HUB **ne sont pas en base SQL** : pas de BFF, pas de transformer, pas de token API |
| Modèle de données | `types/hub.ts` → `HubPage`, à **slots nommés** (pas de `BlockRenderer`) |
| Registry | `data/hub/index.ts`, indexé par l'**id numérique de l'URL** |
| JSON-LD | `app/@head/hub/[hubSlug]/page.tsx` — `Article` + `BreadcrumbList` + `FAQPage` |
| Pages | 1000 poules pondeuses, 1001 food truck, 1002 laverie automatique |

### 11bis.1 Routing — le piège à connaître

`app/[slugWithId]/` est un segment dynamique **à la racine** du sous-domaine et
exige un suffixe `-<digits>`. Une URL en `-projet.html` y tomberait et partirait
en `redirect(hellopro.fr/404.php)`. On **ne peut pas** ajouter un second segment
dynamique frère (l'App Router refuse deux slugs au même niveau).

D'où un **rewrite dédié**, qui doit rester **AVANT** la règle conseils dans
`next.config.js` (premier match gagnant) :

```js
{ source: '/:hubSlug([^/]+)-projet\\.html', destination: '/hub/:hubSlug' },
```

Le namespace `-projet.html` est neuf côté HelloPro → aucune collision possible
avec les slugs conseils. L'URL publique reste inchangée (rewrite interne).
Le découpage `slug` / `id` est fait en TS par `parseHubSlug()` (exportée et testée).

### 11bis.2 Règles des fichiers de données

1. **Aucun JSX, aucun composant importé.** Les icônes passent par un nom
   (`HubIconName`) résolu par `lib/hub/icons.ts`. Sinon un fichier de contenu
   devient un fichier React, illisible pour un non-dev.
2. **Aucun `import` d'image.** Chemins string sous `public/images/hub/<slug>/`,
   avec `width`/`height` obligatoires (CLS + `next/image` en Server Component).
3. **Ajouter une page = créer `data/hub/<slug>.ts` + l'enregistrer dans le registry.**
   Si ça oblige à toucher un composant, c'est le modèle de données qu'il faut
   revoir, pas le template. `__tests__/data/hub/registry.test.ts` boucle sur
   `listHubPages()` : toute nouvelle page est contrôlée automatiquement.

### 11bis.3 Transverses

Les pages HUB réutilisent `SiteHeader`, `SiteFooter`, `GtmFooterScripts`,
`ScrollToTopButton` de `components/conseil/`. On ne reprend **ni le header ni le
footer** du prototype Lovable.

`GtmFooterScripts` accepte une prop optionnelle **`pageTemplate`** (défaut
`'conseils'`) : les pages HUB passent **`'page_hub'`** pour être isolables dans GA4.

⚠️ Cette valeur est un **contrat avec GA4**, pas un libellé interne : des filtres et
segments sont construits dessus. La changer met les rapports à zéro sans lever
d'erreur. Verrouillée par `__tests__/components/hub/HubTemplate.test.tsx`.

### 11bis.3bis Tracking HUB — `lib/analytics/hub.ts`

Plan complet : `docs/tracking-hub.md` (+ 3 CSV : événements, GTM, recette).

**RÈGLE : aucun composant de `components/hub/` n'écrit dans le dataLayer.** Tout
passe par `pushHubEvent(event, group, params)`. Un `grep pushHubEvent` donne
l'inventaire exhaustif des points de mesure ; un `dataLayer.push` éparpillé, non.

- **Vocabulaire dédié `hub_*`.** Ne JAMAIS pousser `quote_form_funnel`,
  `quote_funnel_validation`, `Popup_Appel_Offre` ni `eec.add` depuis le HUB : ces
  noms déclenchent les tags des KPI devis, et l'analyse d'impact du template
  conseils compte ses leads sur `quote_funnel_validation`.
- **`HubEventParams` est une liste FERMÉE** — c'est la garde anti-PII. Passer un
  `email` est une erreur de typecheck, pas une revue de code à faire. Ne pas
  remplacer par un `Record<string, unknown>`.
- **La conversion (`hub_form_submission`) se reconnaît à
  `res.status === 201 || corps?.statut === 'enregistre'`**, jamais au seul code
  HTTP : l'API renvoie 200 + `statut:"enregistre"` sur certains environnements.
- **Deux portées de déduplication** : `pushHubEventOnce` (une fois par CHARGEMENT
  de page, registre au niveau du module) et un `useRef` local (une fois par
  PARCOURS, vidé au `reset()`). Les confondre rend invisible le second parcours
  d'un même visiteur.
- `hub_group` distingue `projet` / `guide` / `engagement` et accompagne **tous**
  les événements. `hub_guide_download` est émis par les DEUX tunnels — le
  questionnaire offre aussi le guide.

**`hub_entry_point` — les DEUX tunnels le portent** (depuis le 2026-08-25). Chacun a
son module d'événement (`lib/hub/guideDialogEvent.ts`, `lib/hub/assistantDialogEvent.ts`)
qui transporte l'emplacement dans le `detail`, parce qu'il n'existe qu'UNE instance de
chaque dialog : la provenance ne peut pas être fixée à la construction. Les déclencheurs
(`GuideButton`, `AssistantButton`) l'exigent en prop — le rendre optionnel garantirait
qu'on l'oublie sur un bouton et que ses conversions soient attribuées ailleurs, en
silence. ⚠️ Ne PAS importer un dialog depuis `triggers.tsx` ou `StickyCta.tsx` : ces
boutons sont rendus dès le chargement, ça annulerait le découpage de bundle. C'est toute
la raison d'être de ces deux modules minuscules.

**Raccourci « lead déjà connu SUR CETTE PAGE »** (cookie `hub_lead`, liste
d'`id_page_hub`, cf. `lib/hub/leadEmailCookie.ts`) :
`GuideDownloadDialog` va directement à l'écran de téléchargement, **sans formulaire
et sans appel API**. Ce parcours émet `hub_guide_shortcut` puis `hub_guide_download`
(`hub_lead_path: 'deja_converti'`) — et surtout **ni `hub_form_view`, ni `hub_email_check`,
ni `hub_form_submission`** : un re-téléchargement n'est pas une conversion, et une
vue de formulaire jamais présenté écraserait le taux du tunnel guide.

### 11bis.4 Composants

```
components/hub/
  HubTemplate.tsx        orchestrateur (Server)
  primitives.tsx         HubSection, CategoryTag, HubIcon, HubTitle, CheckBullet
  HubHero.tsx            image priority (LCP), h1, features — slot `formSlot`
  ValueProps.tsx         'use client' — rotation décorative, 4 descriptions TOUJOURS rendues
  ThematiqueBloc.tsx     la brique réutilisable — layouts overlay-left/right, grid, carousel
                         ⚠️ `grid` n'est plus utilisé par AUCUNE page depuis le
                         2026-08-07 (les blocs de cartes sont tous en `carousel`).
                         Le code du layout reste en place, mais il n'est plus
                         couvert que par ThematiqueBloc.test.tsx : le vérifier à
                         l'écran avant de le remettre en service sur une page.
  Banners.tsx            AccompagnementBanner + GuideCta (même gabarit)
  RessourcesGrid.tsx / GrandesEtapes.tsx
  EditoSection.tsx       ordre : intro → bodyHtml → items → note. Quand l'intro
                         ANNONCE la liste (elle finit par « : »), poser
                         `itemsPosition: 'after-intro'` dans les données, sinon
                         le corps s'intercale entre l'annonce et la liste.
  HowItWorks.tsx / AccompagnementSplit.tsx / FinalCta.tsx
  AssistantForm.tsx      'use client' — étape 1 inline dans le hero, suite en dialog
  GuideDownloadDialog.tsx / LeadPopup.tsx / StickyCta.tsx   'use client' — surcouches
  HubOverlays.tsx        'use client' — charge guide+pop-up en LAZY (ssr:false),
                         armés au 1er clic guide / 1er scroll (hors bundle initial,
                         sans fenêtre morte grâce à `autoOpenOnMount` du dialog guide)
  triggers.tsx           'use client' — GuideButton / AssistantButton
components/ui/dialog.tsx  primitive Radix (écrite à la main, pas via la CLI shadcn)
lib/hub/sanitize.ts       allowlist stricte, zéro attribut conservé
lib/hub/icons.ts          nom → composant lucide
```

**Contenus partagés entre pages.** `data/hub/_shared.ts` porte les blocs dont le
texte est identique d'une verticale à l'autre — aujourd'hui `HOW_IT_WORKS`
(parcours « Comment ça marche ? », validé comme référence pour tous les
templates). Une page l'utilise par étalement, en n'y ajoutant que ce qui lui est
propre : `howItWorks: { ...HOW_IT_WORKS, afterEditoId: 'edito-budget' }`.
⚠️ N'y placer QUE du contenu réellement générique : les 3 pages HUB (élevage, food
truck, laverie) n'ont rien en commun côté sujet, seulement côté parcours HelloPro.
Un texte qui mentionne un métier n'a rien à faire dans ce fichier.

**Règle de frontière client.** Les sections restent des Server Components ; les
boutons qui ouvrent un dialog sont isolés dans `triggers.tsx`. Seul le bouton est
hydraté, pas la section. Un Server Component ne pouvant pas passer de callback à
un enfant client, les dialogs sont joints par **événement window** :
`hp:open-assistant-dialog` et `hp:open-guide-dialog`. Les surcouches sont montées
**une seule fois** par `HubTemplate`.

**Deux invariants SEO à ne pas casser :**
- Les carrousels de blocs thématiques (équipements, réglementation) sont en
  **scroll-snap CSS**, sans JS : toutes les cartes sont dans le HTML initial. Ne
  pas les remplacer par embla ou équivalent — c'est ce qui rend les liens du
  maillage interne visibles au crawl sans exécution de script.
- `ValueProps` rend **toujours** les 4 descriptions ; la rotation ne change que
  l'accent visuel. Ne jamais revenir à un `max-h-0` qui sort le texte du rendu utile.

`HubSectionNav` rend de vraies ancres `<a href="#id">` en SSR (8 liens internes
crawlables) ; le JS n'ajoute que le surlignage et le défilement doux. `matchMedia`
et `IntersectionObserver` sont appelés en optionnel — absents de jsdom.

### 11bis.5 État (POC)

Objectif : valider la rentabilité du workflow, pas livrer une V1.

- Intégration **terminée** : toutes les sections du prototype sont portées.
- **`AssistantForm` est branché** (2026-07-31) sur `POST /api/demande` (route
  proxy → `page_conseil.php`, Bearer `CONSEILS_API_TOKEN` gardé côté serveur).
  Parcours à 2 appels (spec `spec_hub/hub_formulaire.txt`) : e-mail → APPEL 1
  (201 e-mail reconnu → remerciement direct ; 200 → étape coordonnées) →
  APPEL 2 → 201. Route : validation Zod, limites de longueur (§10 spec), parse
  tolérant + 502 sur réponse non-JSON (erreur SQL), fallback dev sans token
  (200/201 simulés). Front : verrou anti double-clic, `referer` tronqué à 500,
  libellés de questions/réponses envoyés tels quels. Étape coordonnées :
  **Civilité** (radios Monsieur/Madame, facultative), **Nom + Prénom** (reliés par
  « _ » → `nom_prenom = "Nom_Prénom"`, re-séparables dans le BO), **Téléphone
  international** via
  `components/hub/PhoneField.tsx` (`react-international-phone`, indicateur pays),
  **Code postal**. Le **pays** choisi dans l'indicateur est envoyé dans
  `coordonnees.pays`. ⚡ **Chargé en LAZY** via `components/hub/PhoneFieldLazy.tsx`
  (`next/dynamic`, `ssr:false`) : `react-international-phone` (+ son CSS) est la lib
  la plus lourde du HUB mais ne sert qu'à l'étape coordonnées → sortie du bundle
  initial (gain INP/TBT), son chunk n'est chargé qu'à l'affichage du champ.
  `AssistantForm` et `GuideSteps` importent donc depuis `PhoneFieldLazy`, et les
  tests mockent `@/components/hub/PhoneFieldLazy` (isole la lib + son CSS) — pense à
  `npm install react-international-phone`.
  ⚠️ **2 colonnes serveur à créer** : `coordonnees.civilite` et `coordonnees.pays`
  (déclarées dans le Zod de la route pour ne pas être supprimées ; le serveur les
  ignore tant que les colonnes n'existent pas). `nom_prenom`/`telephone`/
  `code_postal`/`adresse` tombent sur des colonnes existantes.
- **`GuideDownloadDialog` est branché** (2026-07-31) sur le **même** `POST /api/demande`
  que le projet (un seul endpoint HP sert les deux formulaires, spec
  `spec_hub/hub_guide.txt`). Parcours : e-mail → APPEL 1
  (201 reconnu → téléchargement ; 200 → coordonnées) → APPEL 2 → 201 →
  écran de téléchargement (visuel + bouton). Spécificités guide : **pas de
  `reponses`** ; l'étape coordonnées reprend le **même design que le projet**
  (civilité, Prénom + Nom → `nom_prenom` relié par « _ », téléphone `PhoneField`
  avec indicateur pays → `pays`, code postal ; pas d'adresse).
  ⚠️ **`id_page_hub` = l'id de l'URL, pour LES DEUX tunnels** (2026-08-25). Le
  guide envoyait `page.id + 1000` ; le BO ne connaissant que 1000-1002, ses leads
  arrivaient non rattachés. **La distinction guide/projet se lit à l'ABSENCE de
  lignes dans `hub_demande_reponse`** — le questionnaire produit toujours au moins
  une réponse, le guide aucune. Ne pas ajouter de question au tunnel guide sans
  introduire un champ explicite : la distinction casserait en silence. Détail dans
  `data/hub/index.ts`.
  La route `/api/demande` rend `reponses`/`adresse` optionnels et déclare
  `civilite`/`pays`.
- **Lead connu (drapeau cookie), PAR PROJET** : après un enregistrement réel
  (**201**), on ajoute l'`id_page_hub` à un cookie 30 j
  (`lib/hub/leadEmailCookie.ts`, `hub_lead=1000.1002`) — **jamais l'e-mail** (le
  mail ne part que dans le corps de `POST /api/demande`, pas dans un cookie
  renvoyé à chaque requête). Tant que l'id figure dans la liste :
  `GuideDownloadDialog` va **directement** à l'écran de téléchargement (sans appel,
  puisqu'on n'a plus l'e-mail à ré-envoyer) ; `LeadPopup` **ne s'affiche pas** au
  scroll. Le questionnaire projet (`AssistantForm`) **n'a PAS** ce raccourci :
  l'étape e-mail y est **toujours** affichée.
  API : `markLeadKnown(idPageHub)` / `isLeadKnown(idPageHub)`.
  ⚠️ **La portée par projet n'est pas un détail** (corrigée le 2026-08-24) : le
  drapeau valait `1`, sans notion de page. Un visiteur converti sur l'élevage
  obtenait ensuite le guide laverie sans laisser son e-mail, donc **sans qu'aucun
  lead laverie ne soit créé** — alors que les leads sont rappelés selon le projet
  consulté. Ne pas re-globaliser ce drapeau pour « épargner un champ » au
  visiteur : le champ coûte moins cher que le contact perdu, et l'API reconnaît
  l'adresse (201 immédiat, pas de coordonnées redemandées).
- **Téléchargement auto** : `lib/hub/useAutoDownload.ts` déclenche le download à
  l'affichage de l'écran de remerciement (guide, pop-up, projet). **No-op tant que
  `fileUrl = '#'`** ; cross-origin nécessitera `Content-Disposition: attachment`.
- **`LeadPopup` est branché** (2026-07-31) sur le **même parcours guide** que
  `GuideDownloadDialog` (même `id_page_hub` = `page.id`, mêmes leads).
  Son écran e-mail garde son design riche (bandeau, livre, pastille) ; le bouton
  est grisé tant que l'e-mail n'est pas valide, puis APPEL 1 → 201 (reconnu)
  téléchargement / 200 → coordonnées → APPEL 2 → téléchargement.
- **Flux guide factorisé** : la logique 2 appels vit dans le hook
  `lib/hub/useGuideLead.ts` ; les étapes coordonnées + téléchargement sont les
  composants partagés `components/hub/GuideSteps.tsx` (`Field`, `CoordinatesStep`,
  `DownloadStep`), utilisés par `GuideDownloadDialog` **et** `LeadPopup`. Seul
  l'écran e-mail diffère entre les deux (label + champ pour le dialog, design riche
  bandeau/livre pour la pop-up ; plus de consentement).
- Les articles ne sont pas encore reliés : les liens « Lire l'article » / « En
  savoir plus » ouvrent le questionnaire au lieu d'exposer des liens morts. À
  remplacer par les vraies URLs conseils quand elles seront connues.
- **`public/images/hub/` n'existe pas encore** : les ~30 chemins d'images des
  données ne résolvent rien (assets Lovable à exporter). N'empêche pas le build.
- Contenu : une contradiction chiffrée subsiste sur le budget « 500 poules »
  entre le bloc budget et l'edito budget — à trancher.

---

## 12. Sécurité

- ❌ **Jamais** de secrets dans le code (cf. `.claude/rules/security.md` et le hook `secret-scanner.py`).
- ❌ **Jamais** de `dangerouslySetInnerHTML` non sandboxé.
- ⚠️ **NE PAS importer `isomorphic-dompurify`.** Le paquet est déclaré dans `package.json` mais importé par **aucun** fichier — et il ne peut pas l'être : il embarque jsdom, dont webpack casse la résolution de `browser/default-stylesheet.css` (réécriture de `__dirname`). Symptôme au `docker build` : `ENOENT: /app/browser/default-stylesheet.css` pendant « Collecting page data », build en échec. C'est la raison pour laquelle **tous** les sanitizers du service sont écrits à la main : `lib/hub/sanitize.ts`, `FaqBlock`, `TableauHtmlBlock`, `EstimationContent`, `Suppliers`, `ConseilTemplate`. Modèle à suivre : allowlist de balises + reconstruction de la balise depuis son seul nom (donc **zéro attribut conservé**, aucun vecteur `href`/`src`/`on*`).
- ✅ Toutes les routes API valident leurs inputs avec Zod.
- ✅ CORS désactivé par défaut sur les routes API internes.
- ✅ Les uploads d'images (si besoin) passent par le backend, pas direct depuis le front.

---

## 13. Performance

- **ISR** activé sur les pages conseils (`revalidate: 3600` par défaut, ajustable par slug).
- **Images** : toujours via `<Image>` de Next.js, jamais `<img>` natif.
- **Lazy load** systématique des blocs sous la ligne de flottaison (`dynamic()` ou `<Suspense>`).
- **YouTube** : iframe lazy via `loading="lazy"` ou wrapper "click to load".
- **Fonts** : `next/font` uniquement (pas de `@import` dans CSS).

---

## 14. Analytics

À porter depuis `nextjs-formulaire-hp` :
- `lib/analytics/gtm.ts` → `trackEvent`, `trackLeadSubmitted`...
- `lib/analytics/ga4.ts`
- `lib/analytics/hotjar.ts`

Events spécifiques conseils à prévoir :
- `conseil_page_view` (slug, pageType)
- `conseil_cta_click` (cta_position, cta_label)
- `conseil_devis_started`
- `conseil_devis_submitted`
- `conseil_faq_opened` (question)

---

## 15. Déploiement

| Environnement | Branche | URL |
|---|---|---|
| Dev | branche de travail (`features/<sujet>`) | `localhost:3000` (root) |
| Intégration | **`features/poc`** | — |
| Production | ⚠️ à confirmer | `https://conseils.hellopro.fr` |

⚠️ **`features/poc` est la branche d'intégration du monorepo**, pas `develop`.
C'est d'elle qu'on part pour créer une branche de travail, et c'est elle que
ciblent les PR. Les mentions de `develop` et `main` qui figuraient ici décrivaient
un modèle qui n'a pas été retenu — elles ont fait perdre du temps au moins une
fois. Ce qui reste à documenter : vers quoi `features/poc` est promue pour arriver
en production, et s'il existe un environnement de préproduction.

Pipeline CI/CD : aligné avec `nextjs-formulaire-hp` (voir `.github/workflows/`).

Dockerfile : multi-stage Alpine, output standalone (cf. §6).

---

## 16. Collaboration à 2 devs

### 16.1 Règles d'or

1. **Une branche = un dev = un scope.** Jamais 2 personnes sur la même branche.
2. **PR obligatoire** pour merge sur `features/poc`. Reviewer = l'autre dev.
3. **Découpage par responsabilité, pas par fichier.** Voir tableau §16.3.
4. **Standup async quotidien** : ce qui a été fait / ce qui sera fait / fichiers à risque.
5. **Avant de toucher un fichier partagé** (BlockRenderer, types/, design tokens) : pinger l'autre.
6. **Pair coding pour les décisions structurelles** (nouveau type de bloc, refactor API).

### 16.2 Workflow git

```
features/poc                        ← branche d'INTÉGRATION du monorepo (les PR mergent ici)
  features/hub-projet                 (Erick — template HUB « projet »)
  features/template-conseils-service  ← scaffold initial conseils
  features/conseils-fondations        (Erick — Lot A, cf. §16.3)
  features/conseils-riches            (Partenaire — Lot B, cf. §16.3)
```

**Règle de travail** : partir de `features/poc`, et la merger dans sa branche
**avant chaque push** — le monorepo héberge plusieurs services, les autres équipes
y poussent en parallèle.

```bash
git checkout features/poc && git pull origin features/poc
git checkout features/<sujet> && git merge features/poc
```

Un merge de `features/poc` dans sa branche est donc NORMAL et attendu : le diff de
la PR contre `features/poc` ne contient que le travail de la branche.

### 16.3 Découpage du travail (post-audit Lovable 2026-05-22)

Le découpage est figé sur la base de l'audit des 3 templates Lovable nettoyés (cf. `outputs/audit-templates-lovable.md`).

#### Lot A — Erick (11 blocs)

Fondations partagées + blocs simples + spécifique prix.

| Bloc | Catégorie | Priorité |
|---|---|---|
| `SiteHeader` | Structure | 🔥 J1 |
| `SiteFooter` | Structure | 🔥 J1 |
| `Sidebar` (TOC auto) | Structure | 🔥 J2 |
| `RichText` | Rédactionnel | 🔥 J2 |
| `H2Section` | Rédactionnel | 🔥 J2 |
| `Hero` (variantes guide/compare) | Structure | J3-4 |
| `InlineCTA` | Assemblage | J4 |
| `ProsCons` | Assemblage | J5 |
| `FAQ` (avec variants) | Assemblage | J5 |
| `AuthorBlock` (avec variants) | Assemblage | J6 |
| `PriceTable` | Spécifique prix | J6 |

#### Lot B — Partenaire (12 blocs)

Blocs riches + spécifique autre + spécifique top.

| Bloc | Catégorie | Priorité |
|---|---|---|
| `TypeSection` | Assemblage | 🔥 J1 |
| `QuoteFormBlock` | Assemblage | J2-3 |
| `Brochure` | Assemblage | J3 |
| `Crossell` | Assemblage | J4 |
| `Suppliers` (compact) | Assemblage | J4 |
| `RulesTable` | Spécifique autre | J5 |
| `HeroSuppliersCarousel` | Spécifique top | J5 |
| `ManufacturerCard` (méta-bloc) | Spécifique top | 🔥 J6-7 |
| `NextStepCTA` | Spécifique top | J7 |
| `DownloadDossier` | Spécifique top | J8 |
| `CitedProducts` | Spécifique top | J8 |
| `GoFurther` | Spécifique top | J8 |

#### Travaux partagés (pair-coding obligatoire)

- `types/conseils.ts` — union `ConseilBlock` et schémas Zod par bloc
- `BlockRenderer.tsx` — switch exhaustif
- Design tokens (`app/globals.css`) — synchro Lovable
- `ConseilTemplate.tsx` — orchestrateur principal (pageType → blocs)
- `lib/api/conseils.ts` — fetcher API + parse URL `<slug>-<id>.html`
- Contrat API `GET /api/conseils/:id` (consolidation `ManufacturerCard` côté backend)

### 16.4 Avant de commiter — checklist

```bash
npm run typecheck       # 0 erreur TS
npm run lint            # 0 erreur ESLint
npm test                # Tous tests verts
npm run build           # Build production OK
```

Les hooks `.claude/hooks/nextjs-conseils-prepush-build.sh` (à créer sur le modèle de celui du formulaire) appliquent ça automatiquement.

---

## 17. Catalogue des blocs (issu de l'audit Lovable 2026-05-22)

> 📋 Source : `outputs/audit-templates-lovable.md` — audit des 3 templates Lovable nettoyés (`Template conseil {prix,autre,top}`).
>
> **Stratégie de mapping BO → Next.js (à confirmer)** : certains blocs Next.js sont **1:1 avec un bloc BO** (`RichText` ↔ texte WYSIWYG), d'autres sont **consolidés par l'API** à partir de plusieurs blocs BO primitifs (`ManufacturerCard` = consolidation de blocs titre + image + texte + pros-cons). Voir §20 décision en attente.

Légende : ✅ Fait | 🚧 En cours | ⏳ TODO | ❌ Bloqué

### Structure (présents sur les 3 templates)

| Bloc Next.js | Source données | Status | Owner | Notes |
|---|---|:---:|---|---|
| `SiteHeader` | Site (config global) | ⏳ TODO | Erick (Lot A) | Logo, search, nav, menu |
| `SiteFooter` | Site (config global) | ⏳ TODO | Erick (Lot A) | Variantes default / top à factoriser |
| `Hero` | Page (title, subtitle, image, breadcrumb, author, date, readTime) | ⏳ TODO | Erick (Lot A) | Slot droite : `QuoteForm` ou `SuppliersCarousel` selon `pageType` |
| `Sidebar` (TOC) | Auto-généré depuis blocs `h2-section` | ⏳ TODO | Erick (Lot A) | Sticky, ancres `#id` |

### Contenu rédactionnel (présents sur les 3 templates)

| Bloc Next.js | Source données | Status | Owner | Notes |
|---|---|:---:|---|---|
| `RichText` | Bloc BO `texte` (HTML formaté) | ⏳ TODO | Erick (Lot A) | Plugin `@tailwindcss/typography` à valider |
| `H2Section` | Bloc BO `h2` (id, title, intro) | ⏳ TODO | Erick (Lot A) | Ancre `#id` pour sommaire |

### Assemblage commun (prix + autre)

| Bloc Next.js | Source données | Status | Owner | Notes |
|---|---|:---:|---|---|
| `TypeSection` | Consolidation BO (h3 + image + texte + ul + cta) | ⏳ TODO | Partenaire (Lot B) | Déjà bien paramétrable côté Lovable |
| `ProsCons` | Bloc BO `pros-cons` | ⏳ TODO | Erick (Lot A) | 2 colonnes ✅/❌ |
| `FAQ` | Bloc BO `faq` | ⏳ TODO | Erick (Lot A) | Accordéon shadcn, variantes default/top |
| `QuoteFormBlock` | Données formulaire (mêmes que `nextjs-formulaire-hp`) | ⏳ TODO | Partenaire (Lot B) | Réutiliser composants du formulaire |
| `InlineCTA` | Bloc BO `cta` (title, subtitle, ctaLabel) | ⏳ TODO | Erick (Lot A) | Déjà paramétrable, simple à porter |
| `Brochure` | Bloc BO `brochure` (title, description, bullets, image) | ⏳ TODO | Partenaire (Lot B) | Form email + bullets |
| `Crossell` | Liste produits + articles connexes (API) | ⏳ TODO | Partenaire (Lot B) | 2 sous-sections : produits cités + articles |
| `AuthorBlock` | Profil auteur (nom, photo, bio, LinkedIn) | ⏳ TODO | Erick (Lot A) | Variantes default/top |
| `Suppliers` (compact) | Liste fournisseurs (3 cartes) | ⏳ TODO | Partenaire (Lot B) | Vue compacte fin de page prix/autre |

### Spécifique pageType = `prix`

| Bloc Next.js | Source données | Status | Owner | Notes |
|---|---|:---:|---|---|
| `PriceTable` | Tableau BO (colonnes : type, prix/place, surface, prix/m²) | ⏳ TODO | Erick (Lot A) | Mutualisation possible avec `RulesTable` → bloc `Table` générique |

### Spécifique pageType = `autre`

| Bloc Next.js | Source données | Status | Owner | Notes |
|---|---|:---:|---|---|
| `RulesTable` | Tableau BO (colonnes : obligation, caractère, détail, référence) | ⏳ TODO | Partenaire (Lot B) | Idem ci-dessus (mutualisation possible) |

### Spécifique pageType = `top`

| Bloc Next.js | Source données | Status | Owner | Notes |
|---|---|:---:|---|---|
| `HeroSuppliersCarousel` | Liste fabricants light (rank, badge, name, shortDesc, logo) | ⏳ TODO | Partenaire (Lot B) | Slot droite du Hero quand `pageType === 'top'` |
| `ManufacturerCard` | **Méta-bloc consolidé** par API (rank, name, badge, origin, description, ranges[], pros[], cons[], location, founded, employees, sectors) | ⏳ TODO | Partenaire (Lot B) | 🔥 Le plus complexe — coordination backend obligatoire |
| `NextStepCTA` | Bloc BO `next-step-cta` (options produits avec images) | ⏳ TODO | Partenaire (Lot B) | CTA centre avec sélection produit |
| `DownloadDossier` | Bloc BO `dossier` (title, description, bullets) | ⏳ TODO | Partenaire (Lot B) | Proche de `Brochure` — mutualisation à arbitrer |
| `CitedProducts` | Liste produits (tag, title, price) | ⏳ TODO | Partenaire (Lot B) | 4 produits cités dans l'article |
| `GoFurther` | Liste liens articles connexes | ⏳ TODO | Partenaire (Lot B) | 4 liens pour aller plus loin |

### Totaux

- **23 blocs au total**
- **Lot A (Erick)** : 11 blocs (4 structure + 2 rédactionnel + 4 assemblage + 1 spécifique prix)
- **Lot B (Partenaire)** : 12 blocs (5 assemblage + 1 spécifique autre + 6 spécifiques top)

---

## 18. Commandes utiles

```bash
# Setup initial
nvm use
npm install

# Dev
npm run dev              # http://localhost:3000 (root, pas de basePath)

# Tests
npm test
npm run test:watch
npm run test:coverage

# Qualité
npm run typecheck
npm run lint
npm run lint:fix
npm run format

# Build
npm run build
npm run start            # serve le build

# Docker (local)
docker build -t nextjs-conseils-hp -f Dockerfile .
docker run -p 3000:3000 --env-file .env.local nextjs-conseils-hp

# shadcn/ui (compatible Tailwind 4)
npx shadcn@latest add <component>
```

---

## 19. Liens utiles

- Skill de référence : `hellopro-nextjs` (toutes les conventions Next.js du formulaire HP applicables ici)
- CLAUDE.md racine du monorepo : `RAG-HP-PUB/CLAUDE.md`
- Service jumeau : `apps-microservices/nextjs-formulaire-hp/`
- Règles Claude Code : `.claude/rules/`
- Hooks : `.claude/hooks/`
- Agents : `.claude/agents/`

---

## 20. Historique des décisions importantes

| Date | Décision | Pourquoi |
|---|---|---|
| 2026-05-12 | Stack: Next.js 15 + React 19 + Tailwind 4 + Node 22 | Service Docker isolé → versions indépendantes du formulaire HP. Stack moderne, ecosystem mature en 2026, future-proof. Copie directe des composants Lovable sans downgrade |
| 2026-05-12 | Pattern: BlockRenderer (composition dynamique) | Le BO stocke les blocs en table ordonnée, le front doit refléter l'ordre |
| 2026-05-12 | Lovable code source d'inspiration design, pas de portage TanStack | Migration vers Next.js, on conserve uniquement composants + design tokens |
| 2026-05-12 | npm comme package manager (pas bun) | Cohérence avec le reste du monorepo |
| 2026-05-12 | Tokens HSL synchronisés avec formulaire HP (mais déclarés en `@theme` TW4) | Cohérence UX cross-services malgré stacks différentes |
| **2026-05-22** | **Pas de basePath — service monté sur sous-domaine** `conseils.hellopro.fr` | Préservation totale du SEO existant : les URLs `<slug>-<id>.html` du site PHP actuel restent strictement identiques. Pattern différent du formulaire HP (qui utilise un sous-chemin `/formulaire`) |
| **2026-05-22** | **URL pattern `<slug>-<id>.html`** parsé en runtime, ID = clé de fetch API | Hérité de l'ancien site PHP. Catch-all `[slugWithId]/page.tsx` qui regex-parse le suffixe `-<digits>.html`. Slug non canonique → 301 vers slug canonique (Phase 8) |
| **2026-05-22** | **Catalogue final 23 blocs Next.js** (Lot A = 11, Lot B = 12) | Issu de l'audit des 3 templates Lovable nettoyés. Voir §17 et `outputs/audit-templates-lovable.md` |
| **2026-05-22** | **Branche scaffold renommée `features/template-conseils-service`** | Plus claire pour un binôme arrivant en cours de projet |
| **2026-07-28** | **2e template dans le service : HUB « projet »** (`/<slug>-<id>-projet.html`) | Même sous-domaine, mais contenu statique et composition figée → ne rentre pas dans le pattern BlockRenderer des conseils. Voir §11bis |
| **2026-07-28** | **Rewrite `-projet.html` → `/hub/:hubSlug`, placé AVANT la règle conseils** | `[slugWithId]` est à la racine et exige `-<digits>` : sans rewrite, toute URL HUB partait en 404. Impossible d'ajouter un segment dynamique frère (App Router). Namespace `-projet` neuf → zéro collision |
| **2026-07-28** | **Données HUB statiques (`data/hub/`), pas d'API pour le contenu** | Les projets HUB n'existent pas en base SQL. Pages prérendues au build |
| **2026-07-29** | **`revalidate = 86400` au lieu de `force-static`** | Les rubriques du méga-menu sont lues en direct depuis `mega-menu.php` (même source que www.hellopro.fr). `force-static` force le cache des `fetch` et annule la revalidation : le menu aurait été gelé au build |
| **2026-07-29** | **Aucune dimension d'image dans le modèle** (`HubImage` = `{src, alt}`) | Toutes les images sont rendues en `fill` dans une boîte de taille imposée. Des `width`/`height` saisis à la main ont produit trois ratios faux, invisibles au typecheck comme au build |
| **2026-07-29** | **Correction doc : la branche d'intégration est `features/poc`** | §15 et §16.2 décrivaient `develop`/`main`, un modèle non retenu. La doc périmée a provoqué une fausse alerte sur un merge parfaitement légitime |
| **2026-07-28** | **Modèle HubPage à slots nommés, pas de BlockRenderer** | Les 3 pages partagent un template figé ; seul le contenu varie. Une liste de blocs ordonnée n'apporterait rien et rendrait les fichiers de contenu illisibles |
| **2026-07-28** | **Icônes par nom (`lib/hub/icons.ts`), images par chemin string** | Garde `data/hub/*.ts` éditable sans connaître React. Même approche que `lib/categoryIcons.tsx` |
| **2026-07-28** | **`GtmFooterScripts` reçoit `pageTemplate?` (défaut `'conseils'`)** | Isole les pages HUB des conseils dans GA4. Changement additif : aucun appelant existant impacté |
| **2026-07-28** | **Formulaires HUB en UI mock pour le POC** | Objectif = valider la rentabilité du workflow. Conséquence assumée : aucun lead collecté, POC mesurable en trafic seulement |
| **2026-07-28** | **Les 22 composants morts du prototype Lovable ne sont pas portés** | `KitProjet`, `ValueProps`, `ProjectSteps`, `AccompagnementCta` et 18 autres étaient définis mais jamais montés par `ProjectHub` |

### Décisions en attente (à arbitrer avec le binôme avant code)

| # | Sujet | Options |
|---|---|---|
| 1 | Variants UI (FAQ, Author, Footer entre prix/autre vs top) | A. Un seul composant avec `variant?: 'default' \| 'top'` (recommandé) — B. Composants séparés |
| 2 | Table générique | A. 1 bloc `Table` paramétrable (PriceTable + RulesTable factorisés) — B. 2 blocs distincts |
| 3 | Brochure + DownloadDossier | A. Mutualiser en un seul bloc paramétrable — B. Garder distinct |
| 4 | TOC Sidebar | A. Auto-généré depuis les `H2Section` côté front — B. Items éditables côté BO |
| 5 | Plugin `@tailwindcss/typography` pour `RichText` | À installer dès le démarrage du Lot A ou plus tard |
| 6 | Stratégie de mapping BO → Next.js | A. Blocs BO primitifs + consolidation côté API (`ManufacturerCard`, `TypeSection`) — B. Enrichir le BO avec des blocs composés |

### Dette technique à régler

| # | Sujet | Owner | Quand |
|---|---|---|---|
| 1 | Scaffold initial contient encore `basePath: '/conseils'` et route group `(conseils)/` → à corriger | Erick | Avant merge de `features/template-conseils-service` |

---

> 📌 **Ce fichier vit avec le projet.** Toute décision d'architecture ou convention découverte en cours de route doit y être ajoutée, idéalement dans la même PR que le changement.
