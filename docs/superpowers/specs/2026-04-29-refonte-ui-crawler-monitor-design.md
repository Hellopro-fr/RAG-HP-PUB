# Spec — Refonte UI complète crawler-monitor-frontend

**Date :** 2026-04-29  
**Branche :** `features/refont-crawler-monitoring`  
**Service :** `apps-microservices/crawler-monitor-frontend/`  
**Référence design :** `C:\Users\Fetra\Downloads\design_handoff_crawlee_monitor\`

---

## 1. Objectif

Refonte visuelle complète du dashboard de monitoring crawler. Passer d'une UI fonctionnelle mais basique à un design premium inspiré de Linear/Vercel/Stripe — dense, data-first, pixel-perfect, fidèle au design handoff fourni.

**Ce qui ne change pas :** logique métier, hooks React Query, routing, backend API.  
**Ce qui change :** tout le rendu visuel — tokens CSS, composants layout, primitives UI, pages.

---

## 2. Stack

- Vite + React (JSX)
- Tailwind CSS 3.4+ (avec tokens oklch custom)
- shadcn/ui (composants de base conservés, theming via CSS vars)
- React Router (routes inchangées)
- React Query (hooks inchangés)
- Lucide React (icônes)

---

## 3. Design System

### 3.1 Tokens CSS (`src/index.css`)

Remplacement complet des variables CSS existantes par des valeurs oklch.

**Light mode :**
```css
:root {
  --bg-0: oklch(0.985 0.002 250);
  --bg-1: oklch(0.975 0.003 250);
  --bg-2: oklch(0.96 0.004 250);
  --surface: #ffffff;
  --ink-0: oklch(0.18 0.012 255);
  --ink-1: oklch(0.32 0.010 255);
  --ink-2: oklch(0.52 0.008 255);
  --ink-3: oklch(0.68 0.006 255);
  --hairline: oklch(0.92 0.004 255);
  --hairline-strong: oklch(0.86 0.005 255);
  --accent: oklch(0.55 0.20 268);
  --accent-soft: oklch(0.96 0.025 268);
  --accent-ink: oklch(0.42 0.18 268);
  --ok: oklch(0.58 0.13 155);
  --ok-soft: oklch(0.96 0.04 155);
  --warn: oklch(0.72 0.15 75);
  --warn-soft: oklch(0.97 0.04 75);
  --err: oklch(0.58 0.18 25);
  --err-soft: oklch(0.96 0.04 25);
  --info: oklch(0.62 0.13 230);
  --info-soft: oklch(0.96 0.04 230);
  --shadow-sm: 0 1px 0 rgba(20,24,40,.04);
  --shadow-md: 0 1px 2px rgba(20,24,40,.04), 0 4px 12px -4px rgba(20,24,40,.06);
}
```

**Dark mode (classe `.dark` sur `<html>`) :**
```css
.dark {
  --bg-0: oklch(0.14 0.008 255);
  --bg-1: oklch(0.16 0.008 255);
  --bg-2: oklch(0.20 0.008 255);
  --surface: oklch(0.18 0.008 255);
  --ink-0: oklch(0.92 0.006 255);
  --ink-1: oklch(0.75 0.006 255);
  --ink-2: oklch(0.58 0.005 255);
  --ink-3: oklch(0.42 0.004 255);
  --hairline: oklch(0.26 0.006 255);
  --hairline-strong: oklch(0.32 0.006 255);
  --ok: oklch(0.72 0.13 155);
  --warn: oklch(0.78 0.13 75);
  --err: oklch(0.72 0.16 25);
  --info: oklch(0.74 0.12 230);
}
```

### 3.2 `tailwind.config.js`

```js
theme: {
  extend: {
    colors: {
      bg: { 0: 'var(--bg-0)', 1: 'var(--bg-1)', 2: 'var(--bg-2)' },
      surface: 'var(--surface)',
      ink: { 0: 'var(--ink-0)', 1: 'var(--ink-1)', 2: 'var(--ink-2)', 3: 'var(--ink-3)' },
      hairline: { DEFAULT: 'var(--hairline)', strong: 'var(--hairline-strong)' },
      accent: { DEFAULT: 'var(--accent)', soft: 'var(--accent-soft)', ink: 'var(--accent-ink)' },
      ok: { DEFAULT: 'var(--ok)', soft: 'var(--ok-soft)' },
      warn: { DEFAULT: 'var(--warn)', soft: 'var(--warn-soft)' },
      err: { DEFAULT: 'var(--err)', soft: 'var(--err-soft)' },
      info: { DEFAULT: 'var(--info)', soft: 'var(--info-soft)' },
    },
    fontFamily: {
      sans: ['Inter', 'system-ui', 'sans-serif'],
      display: ['Inter Tight', 'Inter', 'sans-serif'],
      mono: ['JetBrains Mono', 'monospace'],
    },
    borderRadius: { sm: '6px', md: '8px', lg: '12px', xl: '16px' },
    boxShadow: { sm: 'var(--shadow-sm)', md: 'var(--shadow-md)' },
  }
}
```

### 3.3 Typographie

| Usage | Taille | Poids | Lettre-spacing |
|-------|--------|-------|----------------|
| H1 page | 26px | 600 | -0.025em |
| H1 focus (Job Details) | 30px | 600 | -0.03em |
| KPI large | 28px | 600 | -0.025em |
| KPI medium | 22px | 600 | -0.025em |
| KPI small | 17px | 600 | -0.02em |
| Card title | 13px | 600 | normal |
| Body | 13px | 400 | normal |
| Table cell | 12px | 400/500 | normal |
| Mono caption | 11–11.5px | 400/500 | normal |
| Label section | 10–11px | 600 | 0.05–0.08em |

### 3.4 Animations

```css
@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: 0.4; transform: scale(0.75); }
}

@keyframes shimmer {
  from { background-position: -200% 0; }
  to   { background-position: 200% 0; }
}
```

---

## 4. Composants à créer

### 4.1 Nouveaux primitives (`src/components/ui/`)

| Composant | Étape | Props |
|-----------|-------|-------|
| `Pill.jsx` | Overview | `tone` (ok/warn/err/accent/info/neutral), `dot`, `pulse` |
| `StatTile.jsx` | Overview | `label`, `value`, `delta`, `deltaTone`, `spark`, `sub` |
| `Sparkline.jsx` | Overview | `data[]`, `w`, `h`, `color`, `fill` |
| `Timeline.jsx` | Overview | `data[]` (ok/run/fail par heure) |
| `CapacityRing.jsx` | Overview | `used`, `total` — SVG donut 160×160, stroke 10px |
| `AreaChart.jsx` | Job Details | `data[]`, `w`, `h`, `color`, `refLine` — axes avec ticks mono |
| `LogLine.jsx` | Job Details | `t`, `lvl` (debug/info/warn/err), `msg`, `meta` — grid layout |
| `KV.jsx` | Job Details | `k`, `v`, `mono`, `tone` — séparateur hairline |
| `ProjCard.jsx` | Capacity | `label`, `value`, `tone` (accent/ok/warn) |

**Règles communes à tous les primitives :**
- Valeur numérique absente → `—` (em dash) en `font-mono text-ink-2`
- Sparkline sans données → ligne plate grise
- `StatTile` avec `value={null}` → skeleton shimmer
- Pas de gradient sauf fill SVG (opacity 0 → 0.15)

### 4.2 Layout refondus (`src/components/layout/`)

**`Sidebar.jsx`**
- Largeur fixe : 232px
- Brand logo + ⌘K search en haut
- Nav items : icône + label + badge optionnel
- État actif : `bg-bg-2` + barre gauche 2px `bg-accent`
- État hover : `bg-bg-2`
- Section "Médias" contient Albums

**`Topbar.jsx`**
- Hauteur fixe : 52px
- Breadcrumbs à gauche (séparateur `/`)
- Dark mode toggle + actions à droite

**`AppShell.jsx`**
- Grid `sidebar (232px fixe) + main (1fr)`
- Scroll uniquement dans `main`
- `bg-bg-1` sur le body

### 4.3 shadcn/ui existants

Conservés sans modification : `button`, `card`, `badge`, `tabs`, `table`, `input`, `dialog`, `dropdown-menu`, `tooltip`, `separator`, `sheet`. Theming automatique via variables CSS.

---

## 5. Pages — ordre de livraison

### Étape 1 — Foundation
**Fichiers :** `src/index.css`, `tailwind.config.js`  
Poser les tokens oklch et le mapping Tailwind. Vérifier que les composants shadcn existants s'adaptent sans modification.

### Étape 2 — Shell
**Fichiers :** `src/components/layout/Sidebar.jsx`, `Topbar.jsx`, `AppShell.jsx`  
Refondre le layout global. Toutes les pages bénéficient immédiatement du nouveau shell.

### Étape 3 — Overview (`/`)
**Fichiers :** `src/pages/Overview.jsx` + primitives Pill, StatTile, Sparkline, Timeline, CapacityRing  
- Hero header : titre + Pill statut + timestamp sync
- KPI row 5 colonnes : Total / Success / Failures / Running / Archived
- Grid 2 colonnes : Timeline (7 jours) + CapacityRing
- Crawler replicas : grid 4 colonnes mini-cards
- Jobs list scrollable

### Étape 4 — Job Details (`/jobs/:id`)
**Fichiers :** `src/components/JobDetails.jsx` + primitives AreaChart, LogLine, KV  
- Bouton retour + pills statut + H1 30px avec ID partiel mono
- KPI strip 6 colonnes : URLs / Items / Errors / Duration / Throughput / Bandwidth
- Grid `1fr 360px` : onglets (Logs/Queue/Dataset/Replay/Metrics/Callbacks) + sidebar KV
- 2 AreaCharts : RAM + CPU
- Logs : grille colorée par niveau

### Étape 5 — Domains (`/domains`)
**Fichiers :** `src/pages/DomainsPage.jsx`, `src/pages/DomainPage.jsx`  
- Hero + KPI 4 colonnes
- Toolbar : search + toggle période (24h/7j/30j) + refresh
- Table dense : Domain | Jobs | Sparkline 7j | OK | KO | OOM | % | Last run | menu
- Pagination footer mono

### Étape 6 — Capacity Planning (`/capacity-planning`)
**Fichiers :** `src/pages/CapacityPlanningPage.jsx` + ProjCard  
- Hero + pill "simulation" + toggle période
- KPI 4 colonnes : Alloué / Peak réel / Gaspillage / Efficience
- AreaChart RAM avec ligne dashed rouge (capacité max)
- Replicas table + barres d'efficience
- Simulateur : slider + 3 ProjCards (accent/ok/warn) + note warning

### Étape 7 — Health (`/health`)
**Fichiers :** `src/pages/` + `src/coherence/components/CoherenceHealthPage.jsx`  
- Hero + Pill "tout vert" ou err
- KPI 4 colonnes : Total / Warnings / Critique / OK
- Liste verticale de règles : icône check/warn/err + ID mono + description + valeur mesurée mono + timestamp

### Étape 8 — Audit (`/audit`)
**Fichiers :** `src/pages/AuditPage.jsx`  
- Hero + dot pulse "live"
- Toolbar : toggle 24h + filtres + search + export
- Table : Quand (mono) | User (avatar + mono) | Action (Pill) | Status (Pill) | Target | Metadata (mono) | IP (mono)
- WebSocket live-tail conservé, rendu LogLine-style

### Étape 9 — Albums (`/albums`, `/albums/:domain`)
**Fichiers :** `src/pages/AlbumsPage.jsx`, `src/pages/AlbumDetailPage.jsx`, `src/components/albums/`  
- Aligner visuellement les composants albums existants avec le nouveau design system
- Conserver la logique des 4 modes d'affichage (stack/coverflow/reel/dial)
- Appliquer tokens, Pill, KV, typography scale

### Étape 10 — Dark mode
**Fichiers :** `src/index.css` (tokens `.dark` déjà définis à l'étape 1)  
- Vérification visuelle page par page
- `ThemeProvider` + `ThemeToggle` existants, aucune modification
- Tester chaque Pill tone, AreaChart, StatTile en dark

### Étape 11 — Mobile responsive (`< 640px`)
**Fichiers :** tous les composants layout + pages  
- Sidebar repliée en drawer (sheet shadcn existant)
- Tab bar bottom : Vue / Alerts (badge) / Domaines / Santé
- KPI grids → 2×2
- Tables → scroll horizontal ou vue condensée
- Timeline → 30 barres max

---

## 6. Interactions & états

| Élément | État | Rendu |
|---------|------|-------|
| Nav item sidebar | hover | `bg-bg-2` |
| Nav item sidebar | actif | `bg-bg-2` + barre gauche 2px `bg-accent` |
| Ligne table | hover | `bg-bg-2` |
| Onglet | actif | underline 2px `bg-accent` |
| Bouton primary | hover | opacity 90% |
| Card interactive | hover | `shadow-md` |
| Audit live | running | dot `pulse-dot` animation |

---

## 7. Règles stylistiques strictes

- Jamais de gradient (sauf fill SVG opacity 0→0.15)
- Jamais d'emoji dans l'UI
- Toujours `tabular-nums` sur les valeurs numériques
- `font-semibold` max (pas de `font-bold`)
- Radius : pills `rounded-sm`, cards `rounded-lg`, boutons `rounded-md`
- Padding cards : 18–20px systématiquement
- Espacement grille : multiples de 4px

---

## 8. Data flow

- Hooks React Query dans `src/hooks/queries.js` : **conservés sans modification**
- Routes dans `src/lib/navigation.js` : **conservées sans modification**
- WebSocket Audit : logique conservée, rendu seul refait
- Albums : hooks portés depuis `features/albums-photo-image-control`, aucune modification

---

## 9. Fichiers de référence design

| Fichier | Contenu |
|---------|---------|
| `design_files/app.jsx` | Tokens CSS + primitives de base |
| `design_files/screens-overview.jsx` | Overview complet |
| `design_files/screens-others.jsx` | Domains, Capacity, Health, Audit |
| `design_files/screens-extra.jsx` | Job Details, Dark mode, Mobile |
| `README.md` | Spec complète du handoff |
