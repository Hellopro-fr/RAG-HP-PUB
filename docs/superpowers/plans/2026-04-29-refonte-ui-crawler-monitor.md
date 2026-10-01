# Refonte UI Crawler Monitor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refondre visuellement le dashboard crawler-monitor-frontend vers un design premium (Linear/Vercel/Stripe) en suivant pixel-perfect le design handoff fourni, sans toucher à la logique métier ni aux hooks React Query.

**Architecture:** Approche B — design system d'abord (tokens oklch + tailwind), puis shell (Sidebar/Topbar/AppShell), puis pages dans l'ordre Overview → Job Details → Domains → Capacity → Health → Audit → Albums → Dark Mode → Mobile. Les primitives UI sont créées à la première page qui en a besoin, réutilisées ensuite sans modification.

**Tech Stack:** React (JSX), Vite, Tailwind CSS 3.4+, shadcn/ui, React Router, React Query, Vitest + Testing Library, Lucide React.

**Repo :** `apps-microservices/crawler-monitor-frontend/` dans `/home/fetrawsl/project/RAG-HP-PUB/`  
**Branche :** `features/refont-crawler-monitoring`  
**Design handoff :** `/mnt/c/Users/Fetra/Downloads/design_handoff_crawlee_monitor/design_files/`  
**Spec :** `docs/superpowers/specs/2026-04-29-refonte-ui-crawler-monitor-design.md`

---

## File Map

```
src/
├── index.css                              MODIFY — remplacer vars HSL par oklch
├── App.jsx                                MODIFY — bg-bg-1 sur le root
├── components/
│   ├── layout/
│   │   ├── AppShell.jsx                   MODIFY — grid sidebar+main
│   │   ├── Sidebar.jsx                    MODIFY — refonte complète
│   │   └── Topbar.jsx                     MODIFY — refonte complète
│   └── ui/
│       ├── Pill.jsx                       CREATE — badge statut tonal
│       ├── StatTile.jsx                   CREATE — KPI tile avec sparkline
│       ├── Sparkline.jsx                  CREATE — mini chart SVG inline
│       ├── Timeline.jsx                   CREATE — activité empilée par heure
│       ├── CapacityRing.jsx               CREATE — donut SVG 160px
│       ├── AreaChart.jsx                  CREATE — time-series avec axes
│       ├── LogLine.jsx                    CREATE — ligne de log colorée
│       ├── KV.jsx                         CREATE — key-value avec séparateur
│       └── ProjCard.jsx                   CREATE — carte projection capacity
├── pages/
│   ├── Overview.jsx                       MODIFY — refonte complète
│   ├── DomainsPage.jsx                    MODIFY — table dense + sparklines
│   ├── DomainPage.jsx                     MODIFY — détail domaine
│   ├── CapacityPlanningPage.jsx           MODIFY — area chart + simulateur
│   ├── AuditPage.jsx                      MODIFY — table live-tail
│   ├── AlbumsPage.jsx                     MODIFY — aligner design system
│   └── AlbumDetailPage.jsx               MODIFY — aligner design system
├── components/
│   └── JobDetails.jsx                     MODIFY — refonte complète
└── coherence/components/
    └── CoherenceHealthPage.jsx            MODIFY — aligner design system
tailwind.config.js                         MODIFY — ajouter tokens oklch
```

---

## Task 0 : Foundation — tokens oklch + tailwind

**Goal :** Remplacer les variables CSS HSL par les tokens oklch du design system, étendre tailwind.config.js, vérifier que les composants shadcn existants s'adaptent.

**Files :**
- Modify : `src/index.css`
- Modify : `tailwind.config.js`
- Reference : `/mnt/c/Users/Fetra/Downloads/design_handoff_crawlee_monitor/design_files/app.jsx` (section `:root`)

**Acceptance Criteria :**
- [ ] `yarn build` passe sans erreur
- [ ] Les classes `bg-bg-1`, `text-ink-0`, `bg-ok-soft`, `text-err` sont disponibles en Tailwind
- [ ] Le ThemeProvider existant applique `.dark` sur `<html>` et les dark tokens sont actifs

**Verify :** `cd apps-microservices/crawler-monitor-frontend && yarn build` → exit 0

**Steps :**

- [ ] **Step 1 : Remplacer `src/index.css`**

Conserver les imports de fonts et les `@layer base` shadcn existants. Remplacer **uniquement** le bloc `:root { ... }` et ajouter le bloc `.dark { ... }` :

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Inter+Tight:wght@600&family=JetBrains+Mono:wght@400;500&display=swap');

@layer base {
  :root {
    /* Design system oklch */
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

    /* shadcn compatibility aliases */
    --background: var(--bg-1);
    --foreground: var(--ink-0);
    --border: var(--hairline);
    --input: var(--hairline);
    --ring: var(--accent);
    --primary: var(--accent);
    --primary-foreground: #fff;
    --secondary: var(--bg-2);
    --secondary-foreground: var(--ink-1);
    --muted: var(--bg-2);
    --muted-foreground: var(--ink-2);
    --card: var(--surface);
    --card-foreground: var(--ink-0);
    --popover: var(--surface);
    --popover-foreground: var(--ink-0);
    --destructive: var(--err);
    --destructive-foreground: #fff;
    --radius: 8px;
  }

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
    --ok-soft: oklch(0.22 0.04 155);
    --warn: oklch(0.78 0.13 75);
    --warn-soft: oklch(0.22 0.04 75);
    --err: oklch(0.72 0.16 25);
    --err-soft: oklch(0.22 0.04 25);
    --info: oklch(0.74 0.12 230);
    --info-soft: oklch(0.22 0.04 230);
    --surface: oklch(0.18 0.008 255);
    --background: var(--bg-1);
    --foreground: var(--ink-0);
    --border: var(--hairline);
    --card: var(--surface);
    --card-foreground: var(--ink-0);
    --popover: var(--surface);
    --popover-foreground: var(--ink-0);
    --muted: var(--bg-2);
    --muted-foreground: var(--ink-2);
    --primary: var(--accent);
    --secondary: var(--bg-2);
    --secondary-foreground: var(--ink-1);
  }

  * { border-color: var(--hairline); }
  body { background: var(--bg-1); color: var(--ink-0); font-family: Inter, system-ui, sans-serif; }
}

@layer utilities {
  .font-display { font-family: 'Inter Tight', Inter, sans-serif; }
  .font-mono    { font-family: 'JetBrains Mono', monospace; }
  .tabular-nums { font-variant-numeric: tabular-nums; }
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: 0.4; transform: scale(0.75); }
}
@keyframes shimmer {
  from { background-position: -200% 0; }
  to   { background-position: 200% 0; }
}
.animate-pulse-dot { animation: pulse-dot 1.5s ease-in-out infinite; }
.animate-shimmer {
  background: linear-gradient(90deg, var(--bg-2) 25%, var(--bg-0) 50%, var(--bg-2) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}
```

- [ ] **Step 2 : Mettre à jour `tailwind.config.js`**

Ajouter les tokens dans `theme.extend.colors` **en plus** des couleurs shadcn existantes (ne pas les supprimer — elles sont utilisées par shadcn) :

```js
// Dans theme.extend.colors, ajouter :
bg: {
  0: 'var(--bg-0)',
  1: 'var(--bg-1)',
  2: 'var(--bg-2)',
},
surface: 'var(--surface)',
ink: {
  0: 'var(--ink-0)',
  1: 'var(--ink-1)',
  2: 'var(--ink-2)',
  3: 'var(--ink-3)',
},
hairline: {
  DEFAULT: 'var(--hairline)',
  strong: 'var(--hairline-strong)',
},
ok:   { DEFAULT: 'var(--ok)',   soft: 'var(--ok-soft)'   },
warn: { DEFAULT: 'var(--warn)', soft: 'var(--warn-soft)' },
err:  { DEFAULT: 'var(--err)',  soft: 'var(--err-soft)'  },
info: { DEFAULT: 'var(--info)', soft: 'var(--info-soft)' },
// Remplacer la valeur accent existante :
accent: {
  DEFAULT:    'var(--accent)',
  soft:       'var(--accent-soft)',
  ink:        'var(--accent-ink)',
  foreground: 'hsl(var(--accent-foreground))',
},

// Dans theme.extend.fontFamily :
fontFamily: {
  sans:    ['Inter', 'system-ui', 'sans-serif'],
  display: ['Inter Tight', 'Inter', 'sans-serif'],
  mono:    ['JetBrains Mono', 'monospace'],
},

// Dans theme.extend.borderRadius (remplacer les valeurs existantes) :
borderRadius: {
  lg:  '12px',
  md:  '8px',
  sm:  '6px',
  xl:  '16px',
  '2xl': '20px',
  full: '9999px',
},

// Dans theme.extend.boxShadow :
boxShadow: {
  sm: 'var(--shadow-sm)',
  md: 'var(--shadow-md)',
},
```

- [ ] **Step 3 : Vérifier le build**

```bash
cd apps-microservices/crawler-monitor-frontend && yarn build
```
Attendu : exit 0, aucune erreur de compilation.

- [ ] **Step 4 : Commit**

```bash
git add apps-microservices/crawler-monitor-frontend/src/index.css \
        apps-microservices/crawler-monitor-frontend/tailwind.config.js
git commit -m "feat(refont): design system oklch tokens + tailwind extension"
```

---

## Task 1 : Shell — Sidebar + Topbar + AppShell

**Goal :** Refondre le layout global (AppShell, Sidebar 232px, Topbar 52px) avec le nouveau design system. Toutes les pages bénéficient immédiatement du nouveau shell.

**Files :**
- Modify : `src/components/layout/AppShell.jsx`
- Modify : `src/components/layout/Sidebar.jsx`
- Modify : `src/components/layout/Topbar.jsx`
- Reference : `/mnt/c/Users/Fetra/Downloads/design_handoff_crawlee_monitor/design_files/app.jsx` (composants Sidebar, Topbar)

**Acceptance Criteria :**
- [ ] Sidebar : largeur 232px fixe, nav items avec barre active 2px accent, badges, ⌘K
- [ ] Topbar : hauteur 52px, breadcrumbs gauche, dark toggle droite
- [ ] AppShell : grid sidebar+main, scroll uniquement dans main
- [ ] `yarn build` passe
- [ ] `yarn test` passe (tests existants non cassés)

**Verify :** `cd apps-microservices/crawler-monitor-frontend && yarn test` → tous les tests existants passent

**Steps :**

- [ ] **Step 1 : Refondre `AppShell.jsx`**

```jsx
// src/components/layout/AppShell.jsx
import Sidebar from './Sidebar';
import Topbar from './Topbar';

export default function AppShell({ children }) {
  return (
    <div className="flex h-screen overflow-hidden bg-bg-1">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Topbar />
        <main className="flex-1 overflow-y-auto p-5">
          {children}
        </main>
      </div>
    </div>
  );
}
```

- [ ] **Step 2 : Refondre `Sidebar.jsx`**

Lire le fichier existant pour identifier les routes et icônes utilisées. Remplacer le rendu en conservant la logique de navigation :

```jsx
// src/components/layout/Sidebar.jsx
import { NavLink, useLocation } from 'react-router-dom';
import { useCommandPalette } from '../CommandPalette'; // hook existant si disponible

const NAV = [
  { to: '/',                    icon: 'LayoutDashboard', label: 'Vue d\'ensemble' },
  { to: '/domains',             icon: 'Globe',           label: 'Domaines' },
  { to: '/capacity-planning',   icon: 'BarChart2',       label: 'Capacité' },
  { to: '/health',              icon: 'HeartPulse',      label: 'Santé' },
  { to: '/audit',               icon: 'ClipboardList',   label: 'Audit',   badge: null },
  { to: '/albums',              icon: 'Images',          label: 'Médias' },
];

function NavItem({ to, icon: Icon, label, badge }) {
  return (
    <NavLink
      to={to}
      end={to === '/'}
      className={({ isActive }) =>
        `relative flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] transition-colors
         ${isActive
           ? 'bg-bg-2 text-ink-0 font-medium before:absolute before:left-0 before:top-1/2 before:-translate-y-1/2 before:h-5 before:w-0.5 before:rounded-full before:bg-accent'
           : 'text-ink-1 hover:bg-bg-2 hover:text-ink-0'}`
      }
    >
      <span className="w-4 h-4 flex-shrink-0">{/* lucide icon via className */}</span>
      <span className="flex-1 truncate">{label}</span>
      {badge != null && (
        <span className="text-[10px] font-semibold tabular-nums bg-err text-white px-1.5 py-0.5 rounded-full">
          {badge}
        </span>
      )}
    </NavLink>
  );
}

export default function Sidebar() {
  return (
    <aside className="w-[232px] flex-shrink-0 flex flex-col bg-surface border-r border-hairline h-full">
      {/* Brand */}
      <div className="h-[52px] flex items-center px-4 border-b border-hairline">
        <span className="font-display font-semibold text-[15px] text-ink-0 tracking-tight">
          Crawler
        </span>
        <span className="ml-1 text-[15px] text-ink-2">Monitor</span>
      </div>

      {/* Search */}
      <button className="mx-3 mt-3 flex items-center gap-2 px-3 h-8 rounded-md border border-hairline text-[12px] text-ink-3 hover:bg-bg-2 transition-colors">
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
        </svg>
        <span className="flex-1 text-left">Rechercher…</span>
        <kbd className="text-[10px] text-ink-3 border border-hairline rounded px-1">⌘K</kbd>
      </button>

      {/* Nav */}
      <nav className="flex-1 px-2 py-3 flex flex-col gap-0.5 overflow-y-auto">
        {NAV.map(item => <NavItem key={item.to} {...item} />)}
      </nav>
    </aside>
  );
}
```

- [ ] **Step 3 : Refondre `Topbar.jsx`**

```jsx
// src/components/layout/Topbar.jsx
import { useLocation } from 'react-router-dom';
import Breadcrumbs from './Breadcrumbs';
import ThemeToggle from '../ThemeToggle';

export default function Topbar() {
  return (
    <header className="h-[52px] flex-shrink-0 flex items-center px-5 border-b border-hairline bg-surface gap-4">
      <div className="flex-1 min-w-0">
        <Breadcrumbs />
      </div>
      <div className="flex items-center gap-2">
        <ThemeToggle />
      </div>
    </header>
  );
}
```

- [ ] **Step 4 : Vérifier les tests existants**

```bash
cd apps-microservices/crawler-monitor-frontend && yarn test
```
Attendu : tous les tests existants passent (les tests ne testent pas le shell directement).

- [ ] **Step 5 : Commit**

```bash
git add apps-microservices/crawler-monitor-frontend/src/components/layout/
git commit -m "feat(refont): AppShell + Sidebar + Topbar refonte design system"
```

---

## Task 2 : Primitives Overview — Pill, StatTile, Sparkline, Timeline, CapacityRing

**Goal :** Créer les 5 primitives nécessaires à la page Overview. Ces composants sont ensuite réutilisés sans modification dans toutes les pages suivantes.

**Files :**
- Create : `src/components/ui/Pill.jsx`
- Create : `src/components/ui/StatTile.jsx`
- Create : `src/components/ui/Sparkline.jsx`
- Create : `src/components/ui/Timeline.jsx`
- Create : `src/components/ui/CapacityRing.jsx`
- Create : `tests/ui-primitives.test.jsx`
- Reference : `/mnt/c/Users/Fetra/Downloads/design_handoff_crawlee_monitor/design_files/app.jsx`

**Acceptance Criteria :**
- [ ] `Pill` rend avec chaque tone (ok/warn/err/accent/info/neutral), avec/sans dot, avec/sans pulse
- [ ] `StatTile` rend le skeleton quand `value={null}`
- [ ] `Sparkline` rend une ligne plate quand `data=[]`
- [ ] `Timeline` rend sans erreur avec `data=[]`
- [ ] `CapacityRing` calcule correctement le strokeDashoffset
- [ ] `yarn test` passe

**Verify :** `cd apps-microservices/crawler-monitor-frontend && yarn test tests/ui-primitives.test.jsx` → PASS

**Steps :**

- [ ] **Step 1 : Créer `Pill.jsx`**

```jsx
// src/components/ui/Pill.jsx
const TONES = {
  ok:      'bg-ok-soft text-ok border-ok/20',
  warn:    'bg-warn-soft text-warn border-warn/20',
  err:     'bg-err-soft text-err border-err/20',
  accent:  'bg-accent-soft text-accent-ink border-accent/20',
  info:    'bg-info-soft text-info border-info/20',
  neutral: 'bg-bg-2 text-ink-1 border-hairline',
};
const DOT_TONES = {
  ok: 'bg-ok', warn: 'bg-warn', err: 'bg-err',
  accent: 'bg-accent', info: 'bg-info', neutral: 'bg-ink-2',
};

export default function Pill({ tone = 'neutral', dot = false, pulse = false, children, className = '' }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-sm border text-[11px] font-medium ${TONES[tone]} ${className}`}>
      {dot && (
        <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${DOT_TONES[tone]} ${pulse ? 'animate-pulse-dot' : ''}`} />
      )}
      {children}
    </span>
  );
}
```

- [ ] **Step 2 : Créer `Sparkline.jsx`**

```jsx
// src/components/ui/Sparkline.jsx
export default function Sparkline({ data = [], w = 64, h = 24, color = 'var(--accent)', fill = true }) {
  if (!data.length) {
    return <svg width={w} height={h}><line x1={0} y1={h/2} x2={w} y2={h/2} stroke="var(--hairline)" strokeWidth={1}/></svg>;
  }
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / range) * (h - 4) - 2;
    return `${x},${y}`;
  });
  const polyline = pts.join(' ');
  const area = `${pts[0].split(',')[0]},${h} ${polyline} ${pts[pts.length-1].split(',')[0]},${h}`;
  return (
    <svg width={w} height={h} className="overflow-visible">
      {fill && (
        <defs>
          <linearGradient id={`sg-${color.replace(/[^a-z]/gi,'')}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.15}/>
            <stop offset="100%" stopColor={color} stopOpacity={0}/>
          </linearGradient>
        </defs>
      )}
      {fill && <polygon points={area} fill={`url(#sg-${color.replace(/[^a-z]/gi,'')})`}/>}
      <polyline points={polyline} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}
```

- [ ] **Step 3 : Créer `StatTile.jsx`**

```jsx
// src/components/ui/StatTile.jsx
import Sparkline from './Sparkline';

export default function StatTile({ label, value, delta, deltaTone, spark, sub, accent }) {
  const isLoading = value == null;
  return (
    <div className="bg-surface rounded-lg p-5 shadow-sm border border-hairline flex flex-col gap-3 min-w-0">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-2">{label}</span>
        {spark && !isLoading && <Sparkline data={spark} />}
      </div>
      {isLoading ? (
        <div className="h-7 w-24 rounded animate-shimmer" />
      ) : (
        <span className="font-display text-[28px] font-semibold tabular-nums tracking-tight text-ink-0 leading-none">
          {value}
        </span>
      )}
      <div className="flex items-center gap-2 min-h-[16px]">
        {delta != null && !isLoading && (
          <span className={`text-[11px] font-medium tabular-nums ${
            deltaTone === 'ok' ? 'text-ok' : deltaTone === 'err' ? 'text-err' : 'text-ink-2'
          }`}>
            {delta}
          </span>
        )}
        {sub && !isLoading && <span className="text-[11px] text-ink-2">{sub}</span>}
      </div>
      {accent != null && (
        <div className="h-0.5 w-full bg-hairline rounded-full overflow-hidden">
          <div className="h-full bg-accent rounded-full" style={{ width: `${Math.min(100, accent)}%` }} />
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4 : Créer `Timeline.jsx`**

```jsx
// src/components/ui/Timeline.jsx
// data : [{ label: '00h', ok: 12, run: 3, fail: 1 }, ...]
const BAR_H = 40;

export default function Timeline({ data = [] }) {
  if (!data.length) return <div className="h-10 bg-bg-2 rounded animate-shimmer" />;
  const maxTotal = Math.max(...data.map(d => (d.ok || 0) + (d.run || 0) + (d.fail || 0)), 1);
  return (
    <div className="flex items-end gap-0.5 h-[48px]">
      {data.map((d, i) => {
        const total = (d.ok || 0) + (d.run || 0) + (d.fail || 0);
        const height = Math.round((total / maxTotal) * BAR_H);
        if (!total) return <div key={i} className="flex-1 h-1 bg-hairline rounded-sm" />;
        const okH   = Math.round((d.ok  / total) * height);
        const runH  = Math.round((d.run / total) * height);
        const failH = height - okH - runH;
        return (
          <div key={i} className="flex-1 flex flex-col-reverse rounded-sm overflow-hidden" style={{ height }}>
            {d.fail > 0 && <div style={{ height: failH }} className="bg-err" />}
            {d.run  > 0 && <div style={{ height: runH  }} className="bg-warn" />}
            {d.ok   > 0 && <div style={{ height: okH   }} className="bg-ok" />}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 5 : Créer `CapacityRing.jsx`**

```jsx
// src/components/ui/CapacityRing.jsx
const SIZE = 160;
const STROKE = 10;
const R = (SIZE - STROKE) / 2;
const CIRC = 2 * Math.PI * R;

export default function CapacityRing({ used = 0, total = 1, label = 'Utilisé' }) {
  const pct = Math.min(1, used / total);
  const offset = CIRC * (1 - pct);
  const tone = pct > 0.9 ? 'var(--err)' : pct > 0.7 ? 'var(--warn)' : 'var(--ok)';
  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width={SIZE} height={SIZE} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={SIZE/2} cy={SIZE/2} r={R} fill="none" stroke="var(--hairline-strong)" strokeWidth={STROKE} />
        <circle
          cx={SIZE/2} cy={SIZE/2} r={R} fill="none"
          stroke={tone} strokeWidth={STROKE}
          strokeDasharray={CIRC} strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="font-display text-[28px] font-semibold tabular-nums text-ink-0 leading-none">
          {Math.round(pct * 100)}%
        </span>
        <span className="text-[11px] text-ink-2 mt-1">{label}</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 6 : Écrire les tests**

```jsx
// tests/ui-primitives.test.jsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import Pill from '../src/components/ui/Pill';
import StatTile from '../src/components/ui/StatTile';
import Sparkline from '../src/components/ui/Sparkline';
import Timeline from '../src/components/ui/Timeline';
import CapacityRing from '../src/components/ui/CapacityRing';

describe('Pill', () => {
  it('rend le texte enfant', () => {
    render(<Pill tone="ok">Actif</Pill>);
    expect(screen.getByText('Actif')).toBeTruthy();
  });
  it('rend le dot quand dot=true', () => {
    const { container } = render(<Pill tone="err" dot>Erreur</Pill>);
    expect(container.querySelector('.bg-err')).toBeTruthy();
  });
});

describe('StatTile', () => {
  it('rend le skeleton quand value=null', () => {
    const { container } = render(<StatTile label="Total" value={null} />);
    expect(container.querySelector('.animate-shimmer')).toBeTruthy();
  });
  it('rend la valeur quand fournie', () => {
    render(<StatTile label="Total" value="1 234" />);
    expect(screen.getByText('1 234')).toBeTruthy();
  });
});

describe('Sparkline', () => {
  it('rend une ligne plate quand data=[]', () => {
    const { container } = render(<Sparkline data={[]} />);
    expect(container.querySelector('line')).toBeTruthy();
  });
  it('rend une polyline avec des données', () => {
    const { container } = render(<Sparkline data={[1,2,3,2,1]} />);
    expect(container.querySelector('polyline')).toBeTruthy();
  });
});

describe('Timeline', () => {
  it('rend sans erreur avec data=[]', () => {
    render(<Timeline data={[]} />);
  });
  it('rend des barres avec des données', () => {
    const { container } = render(
      <Timeline data={[{ label: '0h', ok: 5, run: 1, fail: 0 }]} />
    );
    expect(container.querySelector('.bg-ok')).toBeTruthy();
  });
});

describe('CapacityRing', () => {
  it('rend le pourcentage correct', () => {
    render(<CapacityRing used={7} total={10} />);
    expect(screen.getByText('70%')).toBeTruthy();
  });
  it('cap à 100%', () => {
    render(<CapacityRing used={15} total={10} />);
    expect(screen.getByText('100%')).toBeTruthy();
  });
});
```

- [ ] **Step 7 : Lancer les tests**

```bash
cd apps-microservices/crawler-monitor-frontend && yarn test tests/ui-primitives.test.jsx
```
Attendu : tous les tests PASS.

- [ ] **Step 8 : Commit**

```bash
git add apps-microservices/crawler-monitor-frontend/src/components/ui/Pill.jsx \
        apps-microservices/crawler-monitor-frontend/src/components/ui/StatTile.jsx \
        apps-microservices/crawler-monitor-frontend/src/components/ui/Sparkline.jsx \
        apps-microservices/crawler-monitor-frontend/src/components/ui/Timeline.jsx \
        apps-microservices/crawler-monitor-frontend/src/components/ui/CapacityRing.jsx \
        apps-microservices/crawler-monitor-frontend/tests/ui-primitives.test.jsx
git commit -m "feat(refont): primitives UI — Pill, StatTile, Sparkline, Timeline, CapacityRing"
```

---

## Task 3 : Page Overview (`/`)

**Goal :** Refondre `Overview.jsx` avec le nouveau design — hero + KPI row + timeline + capacity + replicas + jobs list.

**Files :**
- Modify : `src/pages/Overview.jsx`
- Reference : `/mnt/c/Users/Fetra/Downloads/design_handoff_crawlee_monitor/design_files/screens-overview.jsx`

**Acceptance Criteria :**
- [ ] Hero header avec Pill statut et timestamp
- [ ] 5 StatTiles en grille horizontale
- [ ] Timeline + CapacityRing en grid 2 colonnes
- [ ] Grille 4 colonnes mini-cards replicas
- [ ] Liste scrollable des jobs
- [ ] `yarn test` passe (tests existants non cassés)

**Verify :** `cd apps-microservices/crawler-monitor-frontend && yarn test` → PASS

**Steps :**

- [ ] **Step 1 : Lire le fichier Overview existant**

Identifier les hooks utilisés : `useJobs`, `useReplicas`, `useStats` ou équivalents dans `src/hooks/queries.js`. Conserver tous les appels de hooks — seul le rendu change.

- [ ] **Step 2 : Refondre `Overview.jsx`**

Structure de base (adapter les noms de hooks à ceux trouvés dans le fichier existant) :

```jsx
// src/pages/Overview.jsx
import { useStats, useJobs, useReplicas } from '../hooks/queries';
import StatTile from '../components/ui/StatTile';
import Timeline from '../components/ui/Timeline';
import CapacityRing from '../components/ui/CapacityRing';
import Pill from '../components/ui/Pill';
import Sparkline from '../components/ui/Sparkline';

export default function Overview() {
  const { data: stats, isLoading: statsLoading } = useStats?.() ?? { data: null };
  const { data: jobs = [] }     = useJobs?.()    ?? { data: [] };
  const { data: replicas = [] } = useReplicas?.() ?? { data: [] };

  return (
    <div className="flex flex-col gap-6 max-w-[1400px]">

      {/* Hero */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-[26px] font-semibold text-ink-0 tracking-[-0.025em]">
            Vue d'ensemble
          </h1>
          <p className="text-[13px] text-ink-2 mt-0.5">
            Mis à jour {stats?.syncTime ?? '—'}
          </p>
        </div>
        <Pill tone={stats?.status === 'ok' ? 'ok' : stats?.status === 'warn' ? 'warn' : 'err'} dot>
          {stats?.status === 'ok' ? 'Opérationnel' : stats?.status ?? '—'}
        </Pill>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-5 gap-4">
        <StatTile label="Total"     value={stats?.total    ?? null} spark={stats?.totalSpark}   />
        <StatTile label="Succès"    value={stats?.success  ?? null} spark={stats?.successSpark} deltaTone="ok" delta={stats?.successRate} />
        <StatTile label="Échecs"    value={stats?.failures ?? null} deltaTone={stats?.failures > 0 ? 'err' : 'ok'} />
        <StatTile label="En cours"  value={stats?.running  ?? null} />
        <StatTile label="Archivés"  value={stats?.archived ?? null} />
      </div>

      {/* Timeline + Capacity */}
      <div className="grid grid-cols-[1fr_200px] gap-4">
        <div className="bg-surface rounded-lg border border-hairline p-5 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-2 mb-4">
            Activité 7 jours
          </p>
          <Timeline data={stats?.timeline ?? []} />
        </div>
        <div className="bg-surface rounded-lg border border-hairline p-5 shadow-sm flex flex-col items-center gap-2">
          <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-2">
            Capacité
          </p>
          <CapacityRing used={stats?.ramUsed ?? 0} total={stats?.ramTotal ?? 1} label="RAM" />
        </div>
      </div>

      {/* Replicas */}
      {replicas.length > 0 && (
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-2 mb-3">
            Réplicas
          </p>
          <div className="grid grid-cols-4 gap-3">
            {replicas.map(r => (
              <div key={r.id} className="bg-surface rounded-lg border border-hairline p-4 shadow-sm">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[12px] font-medium text-ink-0 font-mono truncate">{r.name}</span>
                  <Pill tone={r.status === 'ok' ? 'ok' : r.status === 'busy' ? 'warn' : 'err'} dot>
                    {r.status}
                  </Pill>
                </div>
                <Sparkline data={r.cpuSpark ?? []} w={80} h={20} color="var(--accent)" />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Jobs list */}
      <div className="bg-surface rounded-lg border border-hairline shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-hairline">
          <p className="text-[13px] font-semibold text-ink-0">Jobs récents</p>
        </div>
        <div className="divide-y divide-hairline">
          {jobs.slice(0, 20).map(job => (
            <div key={job.id} className="flex items-center gap-4 px-5 py-3 hover:bg-bg-2 transition-colors">
              <Pill tone={job.status === 'succeeded' ? 'ok' : job.status === 'running' ? 'accent' : job.status === 'failed' ? 'err' : 'neutral'}>
                {job.status}
              </Pill>
              <span className="flex-1 text-[13px] text-ink-0 truncate font-mono">{job.domain}</span>
              <span className="text-[11px] text-ink-2 tabular-nums font-mono">{job.duration ?? '—'}</span>
              <span className="text-[11px] text-ink-3 tabular-nums font-mono">{job.startedAt}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3 : Adapter les noms de hooks**

Lire `src/hooks/queries.js` et remplacer `useStats`, `useJobs`, `useReplicas` par les vrais noms de hooks. Adapter les accès aux propriétés (`stats.total` etc.) selon la shape réelle des données.

- [ ] **Step 4 : Vérifier le build et les tests**

```bash
cd apps-microservices/crawler-monitor-frontend && yarn build && yarn test
```
Attendu : exit 0, tous les tests passent.

- [ ] **Step 5 : Commit**

```bash
git add apps-microservices/crawler-monitor-frontend/src/pages/Overview.jsx
git commit -m "feat(refont): Overview page — hero + KPI + timeline + replicas + jobs"
```

---

## Task 4 : Primitives Job Details — AreaChart, LogLine, KV

**Goal :** Créer les 3 primitives nécessaires à Job Details et réutilisables dans les pages suivantes.

**Files :**
- Create : `src/components/ui/AreaChart.jsx`
- Create : `src/components/ui/LogLine.jsx`
- Create : `src/components/ui/KV.jsx`
- Modify : `tests/ui-primitives.test.jsx` (ajouter les nouveaux tests)
- Reference : `/mnt/c/Users/Fetra/Downloads/design_handoff_crawlee_monitor/design_files/screens-extra.jsx`

**Acceptance Criteria :**
- [ ] `AreaChart` rend axes + polyline + fill gradient, `refLine` en dashed si fourni
- [ ] `LogLine` colore correctement chaque niveau (debug/info/warn/err)
- [ ] `KV` rend key + value avec séparateur hairline entre chaque ligne
- [ ] `yarn test tests/ui-primitives.test.jsx` PASS

**Verify :** `cd apps-microservices/crawler-monitor-frontend && yarn test tests/ui-primitives.test.jsx` → PASS

**Steps :**

- [ ] **Step 1 : Créer `AreaChart.jsx`**

```jsx
// src/components/ui/AreaChart.jsx
const TICK_COUNT = 5;

export default function AreaChart({ data = [], w = 400, h = 120, color = 'var(--accent)', refLine }) {
  if (!data.length) return <div className="animate-shimmer rounded" style={{ width: w, height: h }} />;
  const values = data.map(d => d.v ?? d.value ?? d);
  const min = 0;
  const max = Math.max(...values, refLine ?? 0) * 1.1;
  const range = max - min || 1;
  const PAD = { top: 8, right: 8, bottom: 24, left: 36 };
  const iW = w - PAD.left - PAD.right;
  const iH = h - PAD.top - PAD.bottom;
  const xOf = i => PAD.left + (i / (values.length - 1 || 1)) * iW;
  const yOf = v => PAD.top + iH - ((v - min) / range) * iH;
  const pts = values.map((v, i) => `${xOf(i)},${yOf(v)}`).join(' ');
  const area = `${xOf(0)},${yOf(0)} ${pts} ${xOf(values.length-1)},${yOf(0)}`;
  return (
    <svg width={w} height={h}>
      <defs>
        <linearGradient id="ac-fill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.15}/>
          <stop offset="100%" stopColor={color} stopOpacity={0}/>
        </linearGradient>
      </defs>
      {/* Axes ticks */}
      {Array.from({ length: TICK_COUNT }, (_, i) => {
        const v = min + (range / (TICK_COUNT - 1)) * i;
        const y = yOf(v);
        return (
          <g key={i}>
            <line x1={PAD.left} x2={w - PAD.right} y1={y} y2={y} stroke="var(--hairline)" strokeWidth={1}/>
            <text x={PAD.left - 4} y={y + 4} textAnchor="end" className="font-mono" style={{ fontSize: 10, fill: 'var(--ink-3)' }}>
              {Math.round(v)}
            </text>
          </g>
        );
      })}
      {/* Ref line */}
      {refLine != null && (
        <line x1={PAD.left} x2={w - PAD.right} y1={yOf(refLine)} y2={yOf(refLine)}
          stroke="var(--err)" strokeWidth={1.5} strokeDasharray="4 3"/>
      )}
      {/* Fill + line */}
      <polygon points={area} fill="url(#ac-fill)"/>
      <polyline points={pts} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}
```

- [ ] **Step 2 : Créer `LogLine.jsx`**

```jsx
// src/components/ui/LogLine.jsx
const LEVEL_STYLE = {
  debug: 'text-ink-3',
  info:  'text-info',
  warn:  'text-warn',
  err:   'text-err',
  error: 'text-err',
};

export default function LogLine({ t, lvl = 'info', msg, meta }) {
  return (
    <div className="grid grid-cols-[80px_40px_1fr_auto] gap-3 px-4 py-1.5 hover:bg-bg-2 font-mono text-[11.5px]">
      <span className="text-ink-3 tabular-nums truncate">{t}</span>
      <span className={`font-medium uppercase ${LEVEL_STYLE[lvl] ?? 'text-ink-2'}`}>{lvl.slice(0,4)}</span>
      <span className="text-ink-0 truncate">{msg}</span>
      {meta && <span className="text-ink-3 tabular-nums">{meta}</span>}
    </div>
  );
}
```

- [ ] **Step 3 : Créer `KV.jsx`**

```jsx
// src/components/ui/KV.jsx
export default function KV({ rows = [] }) {
  // rows : [{ k: string, v: string|ReactNode, mono?: boolean, tone?: string }]
  return (
    <dl className="divide-y divide-hairline">
      {rows.map(({ k, v, mono, tone }, i) => (
        <div key={i} className="flex items-center gap-4 py-2.5 px-0">
          <dt className="w-36 flex-shrink-0 text-[12px] text-ink-2 truncate">{k}</dt>
          <dd className={`flex-1 min-w-0 text-[12px] truncate ${mono ? 'font-mono' : ''} ${
            tone === 'ok' ? 'text-ok' : tone === 'err' ? 'text-err' : tone === 'warn' ? 'text-warn' : 'text-ink-0'
          }`}>
            {v ?? '—'}
          </dd>
        </div>
      ))}
    </dl>
  );
}
```

- [ ] **Step 4 : Ajouter les tests dans `tests/ui-primitives.test.jsx`**

Ajouter à la fin du fichier existant :

```jsx
describe('AreaChart', () => {
  it('rend un skeleton quand data=[]', () => {
    const { container } = render(<AreaChart data={[]} />);
    expect(container.querySelector('.animate-shimmer')).toBeTruthy();
  });
  it('rend une polyline avec des données', () => {
    const { container } = render(<AreaChart data={[1,2,3]} />);
    expect(container.querySelector('polyline')).toBeTruthy();
  });
});

describe('LogLine', () => {
  it('rend le message', () => {
    render(<LogLine t="12:00:00" lvl="info" msg="Crawl démarré" />);
    expect(screen.getByText('Crawl démarré')).toBeTruthy();
  });
  it('applique la couleur err', () => {
    const { container } = render(<LogLine lvl="err" msg="Erreur" />);
    expect(container.querySelector('.text-err')).toBeTruthy();
  });
});

describe('KV', () => {
  it('rend les clés et valeurs', () => {
    render(<KV rows={[{ k: 'Statut', v: 'actif' }, { k: 'ID', v: 'abc123', mono: true }]} />);
    expect(screen.getByText('Statut')).toBeTruthy();
    expect(screen.getByText('abc123')).toBeTruthy();
  });
  it('rend — quand v=null', () => {
    render(<KV rows={[{ k: 'RAM', v: null }]} />);
    expect(screen.getByText('—')).toBeTruthy();
  });
});
```

- [ ] **Step 5 : Lancer les tests**

```bash
cd apps-microservices/crawler-monitor-frontend && yarn test tests/ui-primitives.test.jsx
```
Attendu : tous les tests PASS.

- [ ] **Step 6 : Commit**

```bash
git add apps-microservices/crawler-monitor-frontend/src/components/ui/AreaChart.jsx \
        apps-microservices/crawler-monitor-frontend/src/components/ui/LogLine.jsx \
        apps-microservices/crawler-monitor-frontend/src/components/ui/KV.jsx \
        apps-microservices/crawler-monitor-frontend/tests/ui-primitives.test.jsx
git commit -m "feat(refont): primitives UI — AreaChart, LogLine, KV"
```

---

## Task 5 : Page Job Details

**Goal :** Refondre `JobDetails.jsx` (composant pleine-page) — hero + KPI strip + onglets (Logs/Queue/Dataset/Replay/Metrics/Callbacks) + sidebar KV + 2 AreaCharts.

**Files :**
- Modify : `src/components/JobDetails.jsx`
- Reference : `/mnt/c/Users/Fetra/Downloads/design_handoff_crawlee_monitor/design_files/screens-extra.jsx`

**Acceptance Criteria :**
- [ ] Hero : bouton retour + pills statut + ID partiel en mono
- [ ] KPI strip 6 colonnes : URLs / Items / Errors / Duration / Throughput / Bandwidth
- [ ] Onglets avec compteurs, contenu scrollable
- [ ] Sidebar KV 360px avec config + pipeline steps
- [ ] 2 AreaCharts RAM + CPU visibles dans l'onglet Metrics
- [ ] `yarn test` PASS

**Verify :** `cd apps-microservices/crawler-monitor-frontend && yarn test` → PASS

**Steps :**

- [ ] **Step 1 : Lire le fichier existant**

Identifier les props reçues (id ? job ?) et les hooks internes (useLogs, useQueue, etc.).

- [ ] **Step 2 : Refondre `JobDetails.jsx`**

Structure cible (adapter les props/hooks aux vrais noms) :

```jsx
// src/components/JobDetails.jsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useJob, useLogs, useQueue } from '../hooks/queries';
import Pill from './ui/Pill';
import KV from './ui/KV';
import AreaChart from './ui/AreaChart';
import LogLine from './ui/LogLine';
import StatTile from './ui/StatTile';

const TABS = ['Logs', 'Queue', 'Dataset', 'Replay', 'Metrics', 'Callbacks'];

export default function JobDetails({ jobId }) {
  const navigate = useNavigate();
  const [tab, setTab] = useState('Logs');
  const { data: job } = useJob?.(jobId) ?? { data: null };
  const { data: logs = [] } = useLogs?.(jobId) ?? { data: [] };

  const statusTone = job?.status === 'succeeded' ? 'ok' : job?.status === 'running' ? 'accent' : job?.status === 'failed' ? 'err' : 'neutral';

  return (
    <div className="flex flex-col gap-5 h-full">
      {/* Hero */}
      <div className="flex items-start gap-4">
        <button onClick={() => navigate(-1)} className="mt-1 p-1.5 rounded-md hover:bg-bg-2 text-ink-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7"/>
          </svg>
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Pill tone={statusTone}>{job?.status ?? '—'}</Pill>
            {job?.type && <Pill tone="neutral">{job.type}</Pill>}
          </div>
          <h1 className="font-display text-[30px] font-semibold tracking-[-0.03em] text-ink-0">
            {job?.domain ?? '—'}
            {job?.id && (
              <span className="font-mono text-[16px] text-ink-2 ml-2">#{String(job.id).slice(-8)}</span>
            )}
          </h1>
          <p className="text-[12px] text-ink-2 mt-1 font-mono">{job?.startedAt}</p>
        </div>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-6 gap-3">
        <StatTile label="URLs"       value={job?.urlCount      ?? null} />
        <StatTile label="Items"      value={job?.itemCount     ?? null} />
        <StatTile label="Erreurs"    value={job?.errorCount    ?? null} deltaTone={job?.errorCount > 0 ? 'err' : 'ok'} />
        <StatTile label="Durée"      value={job?.duration      ?? null} />
        <StatTile label="Débit"      value={job?.throughput    ?? null} sub="req/s" />
        <StatTile label="Bande pass" value={job?.bandwidth     ?? null} />
      </div>

      {/* Main grid */}
      <div className="flex-1 grid grid-cols-[1fr_360px] gap-4 min-h-0">
        {/* Left — onglets */}
        <div className="bg-surface rounded-lg border border-hairline shadow-sm flex flex-col overflow-hidden">
          <div className="flex border-b border-hairline px-4">
            {TABS.map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-3 py-3 text-[12px] font-medium transition-colors border-b-2 -mb-px ${
                  tab === t
                    ? 'border-accent text-ink-0'
                    : 'border-transparent text-ink-2 hover:text-ink-0'
                }`}
              >
                {t}
              </button>
            ))}
          </div>
          <div className="flex-1 overflow-y-auto">
            {tab === 'Logs' && (
              <div className="py-1">
                {logs.map((l, i) => (
                  <LogLine key={i} t={l.time} lvl={l.level} msg={l.message} meta={l.meta} />
                ))}
              </div>
            )}
            {tab === 'Metrics' && (
              <div className="p-5 flex flex-col gap-6">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-2 mb-3">RAM</p>
                  <AreaChart data={job?.ramHistory ?? []} refLine={job?.ramAllocated} w={600} h={120} color="var(--accent)" />
                </div>
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-2 mb-3">CPU</p>
                  <AreaChart data={job?.cpuHistory ?? []} w={600} h={100} color="var(--info)" />
                </div>
              </div>
            )}
            {!['Logs', 'Metrics'].includes(tab) && (
              <div className="p-5 text-[13px] text-ink-2">Onglet {tab} — contenu à intégrer</div>
            )}
          </div>
        </div>

        {/* Right — KV sidebar */}
        <div className="flex flex-col gap-4">
          <div className="bg-surface rounded-lg border border-hairline shadow-sm p-5">
            <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-2 mb-3">Configuration</p>
            <KV rows={[
              { k: 'URL de départ', v: job?.startUrl, mono: true },
              { k: 'Crawler',       v: job?.crawlerType },
              { k: 'Concurrence',   v: job?.concurrency },
              { k: 'Max requests',  v: job?.maxRequests },
              { k: 'Système',       v: job?.system },
            ]} />
          </div>
          {job?.pipelineSteps && (
            <div className="bg-surface rounded-lg border border-hairline shadow-sm p-5">
              <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-2 mb-3">Pipeline</p>
              <div className="flex flex-col gap-1.5">
                {job.pipelineSteps.map((step, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <Pill tone={step.done ? 'ok' : step.active ? 'accent' : 'neutral'} dot>
                      {step.name}
                    </Pill>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3 : Adapter les props/hooks**

Lire le fichier `src/hooks/queries.js` et adapter `useJob`, `useLogs`, `useQueue` aux vrais noms et signatures.

- [ ] **Step 4 : Vérifier le build**

```bash
cd apps-microservices/crawler-monitor-frontend && yarn build
```

- [ ] **Step 5 : Commit**

```bash
git add apps-microservices/crawler-monitor-frontend/src/components/JobDetails.jsx
git commit -m "feat(refont): JobDetails — hero + KPI strip + onglets + AreaChart + KV sidebar"
```

---

## Task 6 : Pages Domains

**Goal :** Refondre `DomainsPage.jsx` (table dense + sparklines 7j) et `DomainPage.jsx` (détail domaine).

**Files :**
- Modify : `src/pages/DomainsPage.jsx`
- Modify : `src/pages/DomainPage.jsx`
- Reference : `/mnt/c/Users/Fetra/Downloads/design_handoff_crawlee_monitor/design_files/screens-others.jsx`

**Acceptance Criteria :**
- [ ] Hero + KPI 4 colonnes
- [ ] Toolbar : search + toggle 24h/7j/30j + refresh
- [ ] Table dense avec colonnes : Domain | Jobs | Sparkline 7j | OK | KO | OOM | % succès | Last run | menu
- [ ] Pagination footer en mono
- [ ] Hover row → `bg-bg-2`
- [ ] `yarn build` exit 0

**Verify :** `cd apps-microservices/crawler-monitor-frontend && yarn build` → exit 0

**Steps :**

- [ ] **Step 1 : Lire DomainsPage existant**

Identifier hooks (`useDomains`, `useDomainStats` ou équivalents) et la shape des données (domain.name, domain.jobs, etc.).

- [ ] **Step 2 : Refondre `DomainsPage.jsx`**

```jsx
// src/pages/DomainsPage.jsx
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useDomains } from '../hooks/queries'; // adapter nom réel
import StatTile from '../components/ui/StatTile';
import Sparkline from '../components/ui/Sparkline';
import Pill from '../components/ui/Pill';

const PERIODS = ['24h', '7j', '30j'];

export default function DomainsPage() {
  const [period, setPeriod] = useState('7j');
  const [search, setSearch] = useState('');
  const { data: domains = [], isLoading } = useDomains?.({ period }) ?? { data: [] };

  const filtered = domains.filter(d =>
    !search || d.domain?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="flex flex-col gap-6 max-w-[1400px]">
      {/* Hero */}
      <div>
        <h1 className="font-display text-[26px] font-semibold text-ink-0 tracking-[-0.025em]">Domaines</h1>
        <p className="text-[13px] text-ink-2 mt-0.5">{domains.length} domaines crawlés</p>
      </div>

      {/* KPI */}
      <div className="grid grid-cols-4 gap-4">
        <StatTile label="Total"    value={isLoading ? null : String(domains.length)} />
        <StatTile label="Actifs"   value={isLoading ? null : String(domains.filter(d => d.active).length)} />
        <StatTile label="Succès %"  value={isLoading ? null : `${Math.round(domains.reduce((a,d) => a + (d.successRate ?? 0), 0) / Math.max(domains.length,1))}%`} deltaTone="ok" />
        <StatTile label="Erreurs"  value={isLoading ? null : String(domains.reduce((a,d) => a + (d.failures ?? 0), 0))} />
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-3">
        <input
          className="h-8 px-3 text-[13px] rounded-md border border-hairline bg-surface text-ink-0 placeholder:text-ink-3 focus:outline-none focus:ring-1 focus:ring-accent flex-1 max-w-xs"
          placeholder="Rechercher un domaine…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <div className="flex rounded-md border border-hairline overflow-hidden">
          {PERIODS.map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 h-8 text-[12px] font-medium transition-colors ${
                period === p ? 'bg-bg-2 text-ink-0' : 'bg-surface text-ink-2 hover:bg-bg-2'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
        <button className="h-8 px-3 rounded-md border border-hairline bg-surface text-ink-2 hover:bg-bg-2 text-[12px] transition-colors">
          ↻
        </button>
      </div>

      {/* Table */}
      <div className="bg-surface rounded-lg border border-hairline shadow-sm overflow-hidden">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="border-b border-hairline">
              {['Domaine','Jobs','7 jours','OK','KO','OOM','Succès','Dernier run',''].map(h => (
                <th key={h} className="text-left px-4 py-3 text-[10px] font-semibold uppercase tracking-[0.06em] text-ink-2 whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {filtered.map(d => (
              <tr key={d.domain} className="hover:bg-bg-2 transition-colors">
                <td className="px-4 py-3">
                  <Link to={`/domains/${d.domain}`} className="font-mono text-accent hover:underline">
                    {d.domain}
                  </Link>
                </td>
                <td className="px-4 py-3 tabular-nums text-ink-1">{d.jobCount ?? '—'}</td>
                <td className="px-4 py-3"><Sparkline data={d.weekSpark ?? []} w={56} h={20}/></td>
                <td className="px-4 py-3 tabular-nums text-ok">{d.ok ?? '—'}</td>
                <td className="px-4 py-3 tabular-nums text-err">{d.ko ?? '—'}</td>
                <td className="px-4 py-3 tabular-nums text-warn">{d.oom ?? '—'}</td>
                <td className="px-4 py-3 tabular-nums">
                  <Pill tone={d.successRate >= 90 ? 'ok' : d.successRate >= 70 ? 'warn' : 'err'}>
                    {d.successRate != null ? `${d.successRate}%` : '—'}
                  </Pill>
                </td>
                <td className="px-4 py-3 tabular-nums font-mono text-ink-2">{d.lastRun ?? '—'}</td>
                <td className="px-4 py-3">
                  <button className="text-ink-3 hover:text-ink-1 text-[16px] leading-none">···</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {/* Pagination */}
        <div className="px-4 py-3 border-t border-hairline flex items-center justify-between">
          <span className="font-mono text-[11px] text-ink-2">{filtered.length} résultats</span>
          <div className="flex gap-1">
            <button className="h-7 px-2.5 rounded border border-hairline text-[11px] text-ink-2 hover:bg-bg-2 disabled:opacity-40">←</button>
            <span className="h-7 px-2.5 flex items-center font-mono text-[11px] text-ink-0">1</span>
            <button className="h-7 px-2.5 rounded border border-hairline text-[11px] text-ink-2 hover:bg-bg-2 disabled:opacity-40">→</button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3 : Refondre `DomainPage.jsx`**

Structure plus simple — adapter selon le contenu existant du fichier. Appliquer les mêmes patterns : hero + StatTiles + table jobs du domaine + Pill tones.

- [ ] **Step 4 : Build**

```bash
cd apps-microservices/crawler-monitor-frontend && yarn build
```

- [ ] **Step 5 : Commit**

```bash
git add apps-microservices/crawler-monitor-frontend/src/pages/DomainsPage.jsx \
        apps-microservices/crawler-monitor-frontend/src/pages/DomainPage.jsx
git commit -m "feat(refont): DomainsPage — table dense + sparklines + toolbar + pagination"
```

---

## Task 7 : Primitive ProjCard + Page Capacity Planning

**Goal :** Créer `ProjCard`, puis refondre `CapacityPlanningPage.jsx` — area chart RAM + simulateur.

**Files :**
- Create : `src/components/ui/ProjCard.jsx`
- Modify : `src/pages/CapacityPlanningPage.jsx`
- Reference : `/mnt/c/Users/Fetra/Downloads/design_handoff_crawlee_monitor/design_files/screens-others.jsx`

**Acceptance Criteria :**
- [ ] `ProjCard` rend avec tone accent/ok/warn
- [ ] Hero + pill "simulation" + toggle période
- [ ] KPI 4 colonnes : Alloué / Peak réel / Gaspillage / Efficience
- [ ] AreaChart RAM avec refLine (capacité max) en rouge dashed
- [ ] Simulateur : slider + 3 ProjCards
- [ ] `yarn build` exit 0

**Verify :** `cd apps-microservices/crawler-monitor-frontend && yarn build` → exit 0

**Steps :**

- [ ] **Step 1 : Créer `ProjCard.jsx`**

```jsx
// src/components/ui/ProjCard.jsx
const TONE_STYLE = {
  accent: 'border-accent/30 bg-accent-soft',
  ok:     'border-ok/30 bg-ok-soft',
  warn:   'border-warn/30 bg-warn-soft',
};
const TONE_TEXT = {
  accent: 'text-accent-ink',
  ok:     'text-ok',
  warn:   'text-warn',
};

export default function ProjCard({ label, value, sub, tone = 'accent' }) {
  return (
    <div className={`rounded-lg border p-4 ${TONE_STYLE[tone]}`}>
      <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-2 mb-2">{label}</p>
      <p className={`font-display text-[22px] font-semibold tabular-nums tracking-tight ${TONE_TEXT[tone]}`}>
        {value ?? '—'}
      </p>
      {sub && <p className="text-[11px] text-ink-2 mt-1">{sub}</p>}
    </div>
  );
}
```

- [ ] **Step 2 : Refondre `CapacityPlanningPage.jsx`**

```jsx
// src/pages/CapacityPlanningPage.jsx
import { useState } from 'react';
import { useCapacity } from '../hooks/queries'; // adapter nom réel
import StatTile from '../components/ui/StatTile';
import AreaChart from '../components/ui/AreaChart';
import ProjCard from '../components/ui/ProjCard';
import Pill from '../components/ui/Pill';

export default function CapacityPlanningPage() {
  const [replicas, setReplicas] = useState(4);
  const { data: cap } = useCapacity?.() ?? { data: null };

  const projected = cap ? {
    peak:    Math.round(cap.ramPerReplica * replicas),
    waste:   Math.max(0, cap.allocated - Math.round(cap.ramPerReplica * replicas)),
    eff:     cap.allocated ? Math.round((Math.round(cap.ramPerReplica * replicas) / cap.allocated) * 100) : 0,
  } : null;

  return (
    <div className="flex flex-col gap-6 max-w-[1400px]">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-[26px] font-semibold text-ink-0 tracking-[-0.025em]">Planification capacité</h1>
          <p className="text-[13px] text-ink-2 mt-0.5">Analyse et simulation des ressources</p>
        </div>
        <Pill tone="accent">Simulation</Pill>
      </div>

      <div className="grid grid-cols-4 gap-4">
        <StatTile label="Alloué total"  value={cap ? `${cap.allocated} Go` : null} />
        <StatTile label="Peak réel"     value={cap ? `${cap.peakUsed} Go` : null}  />
        <StatTile label="Gaspillage"    value={cap ? `${cap.waste} Go` : null}     deltaTone={cap?.waste > cap?.allocated * 0.2 ? 'warn' : 'ok'} />
        <StatTile label="Efficience"    value={cap ? `${cap.efficiency}%` : null}  deltaTone={cap?.efficiency >= 80 ? 'ok' : 'warn'} />
      </div>

      <div className="bg-surface rounded-lg border border-hairline shadow-sm p-5">
        <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-2 mb-4">RAM — historique</p>
        <AreaChart data={cap?.ramHistory ?? []} refLine={cap?.allocated} w={900} h={140} color="var(--accent)" />
      </div>

      <div className="bg-surface rounded-lg border border-hairline shadow-sm p-5">
        <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-2 mb-4">Simulateur</p>
        <div className="flex items-center gap-4 mb-5">
          <span className="text-[12px] text-ink-2 w-20">Réplicas</span>
          <input
            type="range" min={1} max={16} value={replicas}
            onChange={e => setReplicas(Number(e.target.value))}
            className="flex-1 accent-[var(--accent)]"
          />
          <span className="font-mono text-[13px] text-ink-0 tabular-nums w-6 text-right">{replicas}</span>
        </div>
        <div className="grid grid-cols-3 gap-4">
          <ProjCard label="RAM projetée"  value={projected ? `${projected.peak} Go` : null} tone="accent" />
          <ProjCard label="Gaspillage"    value={projected ? `${projected.waste} Go` : null} tone={projected?.waste > 10 ? 'warn' : 'ok'} />
          <ProjCard label="Efficience"    value={projected ? `${projected.eff}%` : null} tone={projected?.eff >= 80 ? 'ok' : 'warn'} />
        </div>
        {projected?.eff < 60 && (
          <p className="mt-4 text-[12px] text-warn bg-warn-soft rounded-md px-3 py-2">
            Efficience inférieure à 60% — envisager de réduire le nombre de réplicas.
          </p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3 : Build**

```bash
cd apps-microservices/crawler-monitor-frontend && yarn build
```

- [ ] **Step 4 : Commit**

```bash
git add apps-microservices/crawler-monitor-frontend/src/components/ui/ProjCard.jsx \
        apps-microservices/crawler-monitor-frontend/src/pages/CapacityPlanningPage.jsx
git commit -m "feat(refont): ProjCard + CapacityPlanning — area chart + simulateur réplicas"
```

---

## Task 8 : Page Health

**Goal :** Refondre `CoherenceHealthPage.jsx` — liste de règles d'invariants avec statuts ok/warn/err.

**Files :**
- Modify : `src/coherence/components/CoherenceHealthPage.jsx`
- Modify : `src/coherence/components/CoherencePastille.jsx` (aligner sur Pill)
- Reference : `/mnt/c/Users/Fetra/Downloads/design_handoff_crawlee_monitor/design_files/screens-others.jsx`

**Acceptance Criteria :**
- [ ] Hero + Pill statut global ("tout vert" ou err/warn)
- [ ] KPI 4 colonnes : Total / Warnings / Critique / OK
- [ ] Liste de règles : icône + ID mono + description + valeur mesurée + timestamp
- [ ] `CoherencePastille` utilise `Pill` en interne (ou style identique)
- [ ] `yarn test` PASS

**Verify :** `cd apps-microservices/crawler-monitor-frontend && yarn test` → PASS

**Steps :**

- [ ] **Step 1 : Lire `CoherenceHealthPage.jsx` existant**

Identifier la structure des données de règles (shape d'un objet rule : id, status, description, value, checkedAt, etc.).

- [ ] **Step 2 : Refondre `CoherenceHealthPage.jsx`**

Adapter selon la shape réelle des données. Structure cible :

```jsx
import StatTile from '../../components/ui/StatTile';
import Pill from '../../components/ui/Pill';
import KV from '../../components/ui/KV';

// Icône check/warn/err
function RuleIcon({ status }) {
  if (status === 'ok')   return <span className="w-4 h-4 text-ok">✓</span>;
  if (status === 'warn') return <span className="w-4 h-4 text-warn">⚠</span>;
  return <span className="w-4 h-4 text-err">✗</span>;
}

export default function CoherenceHealthPage() {
  // Conserver le hook existant (useCoherenceRules ou équivalent)
  // ... (adapter aux hooks réels trouvés dans le fichier)

  const allOk    = rules.every(r => r.status === 'ok');
  const warnings = rules.filter(r => r.status === 'warn').length;
  const critical = rules.filter(r => r.status === 'err').length;
  const ok       = rules.filter(r => r.status === 'ok').length;

  return (
    <div className="flex flex-col gap-6 max-w-[1400px]">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-[26px] font-semibold text-ink-0 tracking-[-0.025em]">Santé système</h1>
        <Pill tone={allOk ? 'ok' : critical > 0 ? 'err' : 'warn'} dot pulse={!allOk}>
          {allOk ? 'Tout vert' : critical > 0 ? `${critical} critique(s)` : `${warnings} warning(s)`}
        </Pill>
      </div>

      <div className="grid grid-cols-4 gap-4">
        <StatTile label="Total"    value={String(rules.length)} />
        <StatTile label="Warnings" value={String(warnings)} deltaTone={warnings > 0 ? 'warn' : 'ok'} />
        <StatTile label="Critique" value={String(critical)} deltaTone={critical > 0 ? 'err' : 'ok'} />
        <StatTile label="OK"       value={String(ok)} deltaTone="ok" />
      </div>

      <div className="bg-surface rounded-lg border border-hairline shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-hairline">
          <p className="text-[13px] font-semibold text-ink-0">Règles d'invariants</p>
        </div>
        <div className="divide-y divide-hairline">
          {rules.map(rule => (
            <div key={rule.id} className="flex items-start gap-4 px-5 py-4 hover:bg-bg-2 transition-colors">
              <RuleIcon status={rule.status} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="font-mono text-[11px] text-ink-2">{rule.id}</span>
                  <Pill tone={rule.status === 'ok' ? 'ok' : rule.status === 'warn' ? 'warn' : 'err'}>
                    {rule.status}
                  </Pill>
                </div>
                <p className="text-[13px] text-ink-0">{rule.description}</p>
                {rule.value != null && (
                  <p className="font-mono text-[11px] text-ink-2 mt-0.5">Valeur : {rule.value}</p>
                )}
              </div>
              <span className="font-mono text-[11px] text-ink-3 whitespace-nowrap">{rule.checkedAt}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3 : Aligner `CoherencePastille.jsx`**

Remplacer le style custom par `<Pill>` ou appliquer les mêmes classes que `Pill` pour la cohérence visuelle.

- [ ] **Step 4 : Tests**

```bash
cd apps-microservices/crawler-monitor-frontend && yarn test
```

- [ ] **Step 5 : Commit**

```bash
git add apps-microservices/crawler-monitor-frontend/src/coherence/
git commit -m "feat(refont): CoherenceHealthPage — règles invariants + Pill tones"
```

---

## Task 9 : Page Audit

**Goal :** Refondre `AuditPage.jsx` — table live-tail avec WebSocket, toolbar filtres + export.

**Files :**
- Modify : `src/pages/AuditPage.jsx`
- Reference : `/mnt/c/Users/Fetra/Downloads/design_handoff_crawlee_monitor/design_files/screens-others.jsx`

**Acceptance Criteria :**
- [ ] Hero + indicator live-tail (dot pulse)
- [ ] Toolbar : toggle 24h + search + export
- [ ] Table : Quand (mono) | User | Action (Pill) | Status (Pill) | Target | Metadata (mono) | IP (mono)
- [ ] WebSocket existant conservé, seul le rendu change
- [ ] Hover row → `bg-bg-2`
- [ ] `yarn build` exit 0

**Verify :** `cd apps-microservices/crawler-monitor-frontend && yarn build` → exit 0

**Steps :**

- [ ] **Step 1 : Lire `AuditPage.jsx` existant**

Identifier le code WebSocket (hook ou useEffect), la shape des events (event.time, event.user, event.action, event.status, event.target, event.ip, etc.).

- [ ] **Step 2 : Refondre `AuditPage.jsx`**

```jsx
// src/pages/AuditPage.jsx
// Conserver le code WebSocket existant tel quel — seul le rendu change

// Structure cible — adapter aux hooks/state réels :
return (
  <div className="flex flex-col gap-6 max-w-[1400px]">
    {/* Hero */}
    <div className="flex items-center justify-between">
      <div>
        <h1 className="font-display text-[26px] font-semibold text-ink-0 tracking-[-0.025em]">Audit</h1>
        <p className="text-[13px] text-ink-2 mt-0.5">{events.length} événements</p>
      </div>
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-ok animate-pulse-dot" />
        <span className="text-[12px] text-ink-2">Live</span>
      </div>
    </div>

    {/* Toolbar */}
    <div className="flex items-center gap-3">
      <input
        className="h-8 px-3 text-[13px] rounded-md border border-hairline bg-surface text-ink-0 placeholder:text-ink-3 focus:outline-none focus:ring-1 focus:ring-accent flex-1 max-w-xs"
        placeholder="Rechercher…" value={search} onChange={e => setSearch(e.target.value)}
      />
      <button
        onClick={() => setFilter24h(f => !f)}
        className={`h-8 px-3 rounded-md border text-[12px] font-medium transition-colors ${
          filter24h ? 'bg-bg-2 border-hairline-strong text-ink-0' : 'bg-surface border-hairline text-ink-2 hover:bg-bg-2'
        }`}
      >
        24h
      </button>
      <button className="h-8 px-3 rounded-md border border-hairline bg-surface text-ink-2 hover:bg-bg-2 text-[12px] transition-colors ml-auto">
        Exporter
      </button>
    </div>

    {/* Table */}
    <div className="bg-surface rounded-lg border border-hairline shadow-sm overflow-hidden">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="border-b border-hairline">
            {['Quand','Utilisateur','Action','Statut','Cible','Métadonnées','IP'].map(h => (
              <th key={h} className="text-left px-4 py-3 text-[10px] font-semibold uppercase tracking-[0.06em] text-ink-2 whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline">
          {filtered.map((ev, i) => (
            <tr key={ev.id ?? i} className="hover:bg-bg-2 transition-colors">
              <td className="px-4 py-3 font-mono text-ink-2 tabular-nums whitespace-nowrap">{ev.time}</td>
              <td className="px-4 py-3 font-mono text-ink-1">{ev.user ?? '—'}</td>
              <td className="px-4 py-3">
                <Pill tone="accent">{ev.action}</Pill>
              </td>
              <td className="px-4 py-3">
                <Pill tone={ev.status === 'ok' ? 'ok' : ev.status === 'err' ? 'err' : 'neutral'}>
                  {ev.status}
                </Pill>
              </td>
              <td className="px-4 py-3 text-ink-0 truncate max-w-[200px]">{ev.target ?? '—'}</td>
              <td className="px-4 py-3 font-mono text-ink-3 truncate max-w-[160px]">{ev.meta ?? '—'}</td>
              <td className="px-4 py-3 font-mono text-ink-3 tabular-nums whitespace-nowrap">{ev.ip ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </div>
);
```

- [ ] **Step 3 : Build**

```bash
cd apps-microservices/crawler-monitor-frontend && yarn build
```

- [ ] **Step 4 : Commit**

```bash
git add apps-microservices/crawler-monitor-frontend/src/pages/AuditPage.jsx
git commit -m "feat(refont): AuditPage — table live-tail + toolbar + Pill tones"
```

---

## Task 10 : Albums — alignement design system

**Goal :** Aligner les composants Albums existants (`AlbumsPage`, `AlbumDetailPage`, `src/components/albums/`) avec le nouveau design system — sans toucher à la logique des 4 modes d'affichage.

**Files :**
- Modify : `src/pages/AlbumsPage.jsx`
- Modify : `src/pages/AlbumDetailPage.jsx`
- Modify : `src/components/albums/AlbumsTable.jsx`
- Modify : `src/components/albums/AlbumHeader.jsx`
- Modify : `src/components/albums/AlbumsToolbar.jsx`

**Acceptance Criteria :**
- [ ] Typography, couleurs et spacing alignés avec le design system
- [ ] `Pill` utilisé pour les statuts à la place des badges custom
- [ ] Hover rows → `bg-bg-2`
- [ ] Les 4 modes d'affichage (stack/coverflow/reel/dial) conservés et fonctionnels
- [ ] `yarn test` PASS (tests Albums existants non cassés)

**Verify :** `cd apps-microservices/crawler-monitor-frontend && yarn test` → PASS

**Steps :**

- [ ] **Step 1 : Identifier les divergences stylistiques**

Dans chaque fichier listé, identifier :
- Couleurs hardcodées → remplacer par variables CSS (`text-ink-0`, `bg-bg-2`, etc.)
- Badges custom → remplacer par `<Pill>`
- Spacing non-4px → aligner
- Fonts : ajouter `font-mono` sur les valeurs, `tabular-nums` sur les nombres

- [ ] **Step 2 : Mettre à jour `AlbumsPage.jsx`**

Appliquer le pattern hero + KPI StatTile identique aux autres pages. Conserver le code de la table virtualisée et la logique de suppression.

- [ ] **Step 3 : Mettre à jour `AlbumDetailPage.jsx`**

Appliquer le pattern hero + `KV` pour les métadonnées. Les composants `ProductImageStrip*` (modes d'affichage) ne sont pas modifiés.

- [ ] **Step 4 : Aligner `AlbumsTable.jsx`, `AlbumHeader.jsx`, `AlbumsToolbar.jsx`**

Remplacer les couleurs/classes non-système par les tokens du design system.

- [ ] **Step 5 : Tests Albums**

```bash
cd apps-microservices/crawler-monitor-frontend && yarn test tests/AlbumsPage.test.jsx tests/AlbumDetailPage.test.jsx tests/ImageDetailSheet.test.jsx
```
Attendu : tous les tests PASS.

- [ ] **Step 6 : Commit**

```bash
git add apps-microservices/crawler-monitor-frontend/src/pages/AlbumsPage.jsx \
        apps-microservices/crawler-monitor-frontend/src/pages/AlbumDetailPage.jsx \
        apps-microservices/crawler-monitor-frontend/src/components/albums/
git commit -m "feat(refont): Albums — alignement design system (tokens, Pill, typography)"
```

---

## Task 11 : Dark mode — vérification et corrections

**Goal :** Vérifier page par page que le dark mode (classe `.dark`) est correct — les tokens sont déjà définis (Task 0), cette tâche corrige les valeurs hardcodées qui auraient échappé.

**Files :**
- Modify : tous les fichiers identifiés avec des couleurs hardcodées en dark mode

**Acceptance Criteria :**
- [ ] Aucun `#ffffff` ou `#000000` hardcodé dans les composants (sauf SVG fill="none")
- [ ] Tous les Pill tones lisibles en dark
- [ ] AreaChart axes et fills lisibles en dark
- [ ] Sidebar et Topbar corrects en dark
- [ ] `yarn build` exit 0

**Verify :** `cd apps-microservices/crawler-monitor-frontend && yarn build` → exit 0

**Steps :**

- [ ] **Step 1 : Audit des couleurs hardcodées**

```bash
cd apps-microservices/crawler-monitor-frontend && grep -r "#[0-9a-fA-F]\{3,6\}" src/ --include="*.jsx" | grep -v "fill=\"none\"" | grep -v "svg" | grep -v "node_modules"
```
Lister tous les résultats et corriger les occurrences non-SVG.

- [ ] **Step 2 : Remplacer par les tokens CSS**

Chaque couleur hardcodée → variable CSS correspondante :
- `#fff`, `white` → `var(--surface)` ou `text-white` uniquement si sur fond coloré
- `#000`, `black` → `var(--ink-0)`
- Couleurs grises → `var(--ink-1)`, `var(--ink-2)`, `var(--ink-3)`, `var(--hairline)`
- Couleurs status → `var(--ok)`, `var(--warn)`, `var(--err)`, `var(--accent)`

- [ ] **Step 3 : Build final**

```bash
cd apps-microservices/crawler-monitor-frontend && yarn build
```

- [ ] **Step 4 : Commit**

```bash
git add apps-microservices/crawler-monitor-frontend/src/
git commit -m "feat(refont): dark mode — correction couleurs hardcodées, tokens CSS partout"
```

---

## Task 12 : Mobile responsive (`< 640px`)

**Goal :** Adapter le layout pour mobile — sidebar en drawer, tab bar bottom, grilles condensées.

**Files :**
- Modify : `src/components/layout/AppShell.jsx`
- Modify : `src/components/layout/Sidebar.jsx`
- Modify : tous les fichiers pages (ajout breakpoints `sm:`)
- Reference : `/mnt/c/Users/Fetra/Downloads/design_handoff_crawlee_monitor/design_files/screens-extra.jsx` (section Mobile)

**Acceptance Criteria :**
- [ ] En dessous de 640px : sidebar masquée, accessible via bouton hamburger → Sheet shadcn
- [ ] Tab bar bottom : Vue / Alerts / Domaines / Santé
- [ ] KPI grids → `grid-cols-2` sur mobile
- [ ] Tables → scroll horizontal (`overflow-x-auto`)
- [ ] `yarn build` exit 0

**Verify :** `cd apps-microservices/crawler-monitor-frontend && yarn build` → exit 0

**Steps :**

- [ ] **Step 1 : Modifier `AppShell.jsx` pour mobile**

```jsx
// AppShell.jsx — ajouter sidebar mobile
import { useState } from 'react';
import { Sheet, SheetContent } from '../ui/sheet'; // shadcn existant

export default function AppShell({ children }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex h-screen overflow-hidden bg-bg-1">
      {/* Desktop sidebar */}
      <div className="hidden sm:flex">
        <Sidebar />
      </div>
      {/* Mobile sidebar en Sheet */}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="p-0 w-[232px]">
          <Sidebar onNavigate={() => setOpen(false)} />
        </SheetContent>
      </Sheet>
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Topbar onMenuClick={() => setOpen(true)} />
        <main className="flex-1 overflow-y-auto p-4 sm:p-5 pb-[60px] sm:pb-5">
          {children}
        </main>
        {/* Tab bar mobile */}
        <nav className="sm:hidden fixed bottom-0 left-0 right-0 bg-surface border-t border-hairline flex">
          {[
            { to: '/',       label: 'Vue',      icon: 'grid' },
            { to: '/domains', label: 'Domaines', icon: 'globe' },
            { to: '/health',  label: 'Santé',    icon: 'heart' },
            { to: '/audit',   label: 'Audit',    icon: 'list'  },
          ].map(item => (
            <NavLink key={item.to} to={item.to} end={item.to === '/'}
              className={({ isActive }) =>
                `flex-1 flex flex-col items-center justify-center py-2 text-[10px] font-medium ${
                  isActive ? 'text-accent' : 'text-ink-2'
                }`
              }
            >
              <span className="text-[18px] leading-none mb-0.5">{/* icon */}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  );
}
```

- [ ] **Step 2 : Adapter les grilles dans les pages**

Pour chaque page avec `grid-cols-5` ou `grid-cols-4`, ajouter les breakpoints mobile :
- `grid-cols-2 sm:grid-cols-4 lg:grid-cols-5`

Pour les tableaux : envelopper dans `<div className="overflow-x-auto">`.

- [ ] **Step 3 : Build final**

```bash
cd apps-microservices/crawler-monitor-frontend && yarn build && yarn test
```
Attendu : exit 0, tous les tests passent.

- [ ] **Step 4 : Commit final**

```bash
git add apps-microservices/crawler-monitor-frontend/src/
git commit -m "feat(refont): mobile responsive — drawer sidebar + tab bar + grilles condensées"
```

---

## Self-Review

**Spec coverage :**
- ✅ Section 1 (Architecture) → Task 0-1
- ✅ Section 2 (Composants) → Tasks 2 + 4 (primitives) + Task 1 (layout)
- ✅ Section 3 (Design System tokens) → Task 0
- ✅ Section 4 (Interactions) → intégré dans chaque task page (hover, actif, tabs)
- ✅ Section 5 (Data flow) → chaque task préserve les hooks existants
- ✅ Overview → Task 3
- ✅ Job Details → Task 5
- ✅ Domains → Task 6
- ✅ Capacity Planning → Task 7
- ✅ Health → Task 8
- ✅ Audit → Task 9
- ✅ Albums → Task 10
- ✅ Dark mode → Task 11
- ✅ Mobile → Task 12

**Type consistency :** `Pill` props (`tone`, `dot`, `pulse`) cohérents Tasks 2→12. `StatTile` props (`label`, `value`, `delta`, `deltaTone`, `spark`, `sub`) cohérents Tasks 2→10. `AreaChart` props (`data`, `w`, `h`, `color`, `refLine`) cohérents Tasks 4→7.
