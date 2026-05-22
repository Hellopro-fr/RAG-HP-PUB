# nextjs-conseils-hp — Pages conseils HelloPro

> **Service Next.js 15 du monorepo RAG-HP-PUB** (conteneur Docker isolé)
> Remplacement progressif des pages conseils PHP actuelles (`conseils.hellopro.fr`) par un nouveau template moderne, hébergé sur GCP, monté en reverse proxy sur le **sous-domaine** `conseils.hellopro.fr/<slug>-<id>.html`. Les URLs existantes restent strictement identiques (préservation totale du SEO).
>
> ⚠️ **Lire intégralement ce fichier au début de CHAQUE session Claude Code** avant d'écrire du code (rule `.claude/rules/config-freshness.md`).

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
# .env.local (NE PAS COMMITER)
NEXT_PUBLIC_API_BASE_URL=https://api.hellopro.fr/v1
NEXT_PUBLIC_GTM_ID=GTM-XXXXXXX
NEXT_PUBLIC_GA_MEASUREMENT_ID=G-XXXXXXXXXX
NEXT_PUBLIC_HOTJAR_ID=1234567

# Côté serveur uniquement
CONSEILS_API_TOKEN=<token-pour-bo-readonly>
INVALID_PAGE_REDIRECT_URL=https://www.hellopro.fr/404.html
```

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

Voir `.claude/rules/commit-messages.md` du repo racine.

Format : `<type>(<scope>): <description EN> / <description FR>`

Exemples :
- `feat(conseils): add TextBlock component / ajoute le composant TextBlock`
- `fix(blocks): correct image aspect ratio / corrige le ratio des images`
- `refactor(api): extract conseils fetcher / extrait le fetcher conseils`

Scopes valides pour ce service : `conseils`, `blocks`, `api`, `hero`, `sidebar`, `infra`, `tests`, `docs`.

---

## 12. Sécurité

- ❌ **Jamais** de secrets dans le code (cf. `.claude/rules/security.md` et le hook `secret-scanner.py`).
- ❌ **Jamais** de `dangerouslySetInnerHTML` non sandboxé. Pour le `tableau-html`, utiliser DOMPurify côté serveur.
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
| Dev | `features/conseils-*` | `localhost:3000` (root) |
| Staging | `develop` | `https://staging-conseils.hellopro.fr` |
| Production | `main` | `https://conseils.hellopro.fr` |

Pipeline CI/CD : aligné avec `nextjs-formulaire-hp` (voir `.github/workflows/`).

Dockerfile : multi-stage Alpine, output standalone (cf. §6).

---

## 16. Collaboration à 2 devs

### 16.1 Règles d'or

1. **Une branche = un dev = un scope.** Jamais 2 personnes sur la même branche.
2. **PR obligatoire** pour merge sur `develop`. Reviewer = l'autre dev.
3. **Découpage par responsabilité, pas par fichier.** Voir tableau §16.3.
4. **Standup async quotidien** : ce qui a été fait / ce qui sera fait / fichiers à risque.
5. **Avant de toucher un fichier partagé** (BlockRenderer, types/, design tokens) : pinger l'autre.
6. **Pair coding pour les décisions structurelles** (nouveau type de bloc, refactor API).

### 16.2 Workflow git

```
main                                ← prod
develop                             ← intégration continue (PRs mergent ici)
  features/template-conseils-service  ← scaffold initial (Erick, PR ouverte)
  features/conseils-fondations        (Erick — Lot A : Header/Footer/Sidebar/RichText/H2/Hero/InlineCTA/ProsCons/FAQ/AuthorBlock/PriceTable)
  features/conseils-riches            (Partenaire — Lot B : TypeSection/QuoteFormBlock/Brochure/Crossell/Suppliers/RulesTable/HeroSuppliersCarousel/ManufacturerCard/NextStepCTA/DownloadDossier/CitedProducts/GoFurther)
```

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
