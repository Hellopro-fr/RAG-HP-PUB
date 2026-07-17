# nextjs-conseils-hp — Pages conseils HelloPro

> **Service Next.js 15 du monorepo RAG-HP-PUB** (conteneur Docker isolé)
> Remplacement progressif des pages conseils PHP actuelles (`conseils.hellopro.fr`) par un nouveau template moderne, hébergé sur GCP, monté en reverse proxy sur `www.hellopro.fr/conseils/{slug}`.
>
> ⚠️ **Lire intégralement ce fichier au début de CHAQUE session Claude Code** avant d'écrire du code (rule `.claude/rules/config-freshness.md`).

---

## 0. Contexte projet

| Élément | Valeur |
|---|---|
| Service | `nextjs-conseils-hp` |
| Localisation | `apps-microservices/nextjs-conseils-hp/` (monorepo RAG-HP-PUB) |
| URL publique | `https://www.hellopro.fr/conseils/{slug}` (via reverse proxy nginx) |
| basePath Next.js | `/conseils` |
| Service jumeau de référence | `nextjs-formulaire-hp` (suivre ses conventions) |
| Skill associée | `hellopro-nextjs` (à consulter pour les patterns standards) |
| Backend données | API HelloPro (proxy via routes API Next.js) |
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
  page.tsx                         # / → redirige vers /conseils
  not-found.tsx
  (conseils)/                      # Route group
    layout.tsx                     # Layout conseils (si breadcrumb, navigation commune)
    [slug]/
      page.tsx                     # Server Component (fetch données)
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
// app/(conseils)/[slug]/page.tsx
import { Metadata } from 'next';
import { fetchConseilPage } from '@/lib/api/conseils';
import { ConseilTemplate } from '@/components/conseil/ConseilTemplate';
import { notFound } from 'next/navigation';

export const revalidate = 3600; // ISR 1h, ajustable par page

type PageProps = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const page = await fetchConseilPage(slug);
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
  const { slug } = await params;
  const page = await fetchConseilPage(slug);
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

## 6. Routage & basePath

```javascript
// next.config.js
const nextConfig = {
  basePath: '/conseils',
  assetPrefix: '/conseils',
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

**URLs internes** : toujours utiliser `<Link>` de Next.js ou `router.push()`. `basePath` est appliqué automatiquement.

**Assets** : utiliser le helper `getAssetPath()` (à porter depuis `nextjs-formulaire-hp`).

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
| Dev | `features/conseils-*` | `localhost:3000/conseils` |
| Staging | `develop` | `https://staging.hellopro.fr/conseils` |
| Production | `main` | `https://www.hellopro.fr/conseils` |

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
main         ← prod
develop      ← intégration continue (PRs mergent ici)
  features/conseils-init       (Erick)
  features/conseils-blocs-text (Erick)
  features/conseils-blocs-media (partenaire)
  features/conseils-pageType-prix (Erick)
  features/conseils-pageType-top (partenaire)
```

### 16.3 Découpage du travail (proposition initiale)

| Erick | Partenaire | Partagé (pair-coding) |
|---|---|---|
| BlockRenderer + types | (review) | Architecture initiale |
| H2/H3/TextBlock | ImageBlock + variantes | `types/conseils.ts` |
| CTABlock, FaqBlock | VideoBlock, TableauHtmlBlock | Design tokens |
| ProsConsBlock | TableauPrixBlock | API client générique |
| ResumeBlock | ProduitsBlock | Layout (Header, Footer) |
| Spécifique prix (Simulator, Curve) | Spécifique top + autre (TopFabricants, RulesTable) | Hero, Sidebar |

### 16.4 Avant de commiter — checklist

```bash
npm run typecheck       # 0 erreur TS
npm run lint            # 0 erreur ESLint
npm test                # Tous tests verts
npm run build           # Build production OK
```

Les hooks `.claude/hooks/nextjs-conseils-prepush-build.sh` (à créer sur le modèle de celui du formulaire) appliquent ça automatiquement.

---

## 17. Catalogue des blocs (à jour à chaque ajout)

| Type BO | Composant | Status | Owner | Notes |
|---|---|:---:|---|---|
| `h2` | `H2Block` | ⏳ TODO | Erick | Avec `id` pour ancre sommaire |
| `h3` | `H3Block` | ⏳ TODO | Erick | Avec `id` pour ancre sommaire |
| `texte` | `TextBlock` | ⏳ TODO | Erick | Variants : avec/sans estimation, avec/sans CTA |
| `pros-cons` | `ProsConsBlock` | ⏳ TODO | Erick | 2 colonnes : ✅ avantages, ❌ inconvénients |
| `resume` | `ResumeBlock` | ⏳ TODO | Erick | Box "L'essentiel à retenir" + bullet points |
| `image` | `ImageBlock` | ⏳ TODO | Partenaire | Avec légende optionnelle |
| `texte-image` | `TexteImageBlock` | ⏳ TODO | Partenaire | Layout 50/50 responsive |
| `image-texte` | `ImageTexteBlock` | ⏳ TODO | Partenaire | Inverse du précédent |
| `image-image` | `ImageImageBlock` | ⏳ TODO | Partenaire | 2 images côte à côte |
| `video` | `VideoBlock` | ⏳ TODO | Partenaire | YouTube embed lazy |
| `cta` | `CTABlock` | ⏳ TODO | Erick | Bandeau orange "Estimez le prix de..." |
| `produits` | `ProduitsBlock` | ⏳ TODO | Partenaire | Reçoit `productIds[]`, fetch côté serveur |
| `tableau-html` | `TableauHtmlBlock` | ⏳ TODO | Partenaire | DOMPurify obligatoire |
| `tableau-prix` | `TableauPrixBlock` | ⏳ TODO | Partenaire | 2 colonnes simples |
| `faq` | `FaqBlock` | ⏳ TODO | Erick | shadcn Accordion |

### Blocs spécifiques au type de page

| Type page | Composant | Status | Owner |
|---|---|:---:|---|
| `prix` | `PriceSimulator` | ⏳ | Erick |
| `prix` | `PriceCurve` | ⏳ | Erick |
| `prix` | `Comparator` | ⏳ | Erick |
| `top` | `TopFabricantsCards` | ⏳ | Partenaire |
| `autre` | `RulesTable` | ⏳ | Partenaire |

Légende : ✅ Fait | 🚧 En cours | ⏳ TODO | ❌ Bloqué

---

## 18. Commandes utiles

```bash
# Setup initial
nvm use
npm install

# Dev
npm run dev              # http://localhost:3000/conseils

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
| 2026-05-12 | basePath = `/conseils` | Reverse proxy nginx, même pattern que `/formulaire` |
| 2026-05-12 | npm comme package manager (pas bun) | Cohérence avec le reste du monorepo |
| 2026-05-12 | Tokens HSL synchronisés avec formulaire HP (mais déclarés en `@theme` TW4) | Cohérence UX cross-services malgré stacks différentes |

---

> 📌 **Ce fichier vit avec le projet.** Toute décision d'architecture ou convention découverte en cours de route doit y être ajoutée, idéalement dans la même PR que le changement.
