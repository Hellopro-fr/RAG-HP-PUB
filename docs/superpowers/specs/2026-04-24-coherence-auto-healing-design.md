# Coherence Auto-Healing Framework — Design

**Date** : 2026-04-24
**Branche** : `features/refont-crawler-monitoring`
**Scope** : `apps-microservices/crawler-monitor-frontend`
**Type** : nouveau module (pilote + framework extensible)

---

## 1. Contexte et objectif

### Problème observé

Le dashboard crawler-monitor affiche plusieurs métriques issues de sources hétérogènes (WebSocket live state, REST API avec cache Redis, différents hooks React Query). Ces sources peuvent diverger dans le temps, produisant des affichages incohérents sans que l'utilisateur (ops, SRE) ne sache distinguer un vrai problème infrastructure d'une désync transitoire.

**Exemple déclencheur** :
- ReplicaMonitor affiche `6 replicas actifs`
- CapacityBar affiche `5/7 slots libres` (donc `max_global_jobs = 7`)

Deux chiffres contradictoires côte à côte — soit un replica est tombé (incident), soit la config `MAX_GLOBAL_JOBS=7` n'a pas été suivie d'un scale-up des replicas (slot "phantom"). L'utilisateur doit deviner, puis aller chercher dans Redis pour confirmer.

### Objectif

Construire un **framework de détection et remédiation légère d'incohérences de données** côté dashboard, piloté par un catalogue de règles extensible. Le framework doit :

1. Détecter les incohérences connues entre sources
2. Les afficher de manière non-invasive (pastille inline) ET consultable (page santé)
3. Proposer des actions réactives : auto-retry léger pour les désyncs transitoires, actions manuelles (refresh / copy / ignore) pour diagnostic
4. Rester trivialement extensible : ajouter une nouvelle règle = un fichier + un test

### Non-objectifs (explicite)

- ❌ Auto-fix côté serveur (ex: redémarrer un replica mort) — trop risqué sans review humaine
- ❌ Observabilité backend (`/api/coherence/report`) — hors scope v1, à ajouter si besoin émerge
- ❌ Historique persistant des violations — nécessite backend storage
- ❌ Notifications push / Slack / email — déjà couvert par `AlertsBanner` pour les critical events

---

## 2. Architecture

### Localisation du framework

**Frontend-only** pour le pilote. Les 4 règles MVP ont toutes leurs sources déjà fetched côté browser (via WebSocket ou React Query) — aucune raison d'ajouter un endpoint backend dans un premier temps.

Le design laisse la porte ouverte à un mode hybride (règles `scope: 'server'` qui lisent un `/api/coherence/check`) sans imposer cette complexité maintenant. **YAGNI** appliqué.

### Composants

```
┌─────────────────────────────────────────────────────────────┐
│  <CoherenceProvider>   (mount dans App.jsx, à l'intérieur   │
│                         de QueryClientProvider et           │
│                         BrowserRouter — tous deux mountés   │
│                         dans main.jsx)                       │
│                                                              │
│  props (sources) entrées :                                   │
│    - replicas             (App.jsx WS state)                │
│    - capacity             (useCapacityQuery cache)          │
│    - jobs                 (useJobsQuery cache)              │
│    - capacityPlanning     (useCapacityPlanningQuery cache)  │
│                                                              │
│  exécute (useMemo dependency sur sources) :                  │
│    verdicts = RULES.map(rule => ({ id, violations }))        │
│                                                              │
│  expose via Context :                                        │
│    - verdicts (map ruleId → violations[])                    │
│    - ignoredRules (Set<ruleId>)                              │
│    - setIgnored(ruleId, value)                               │
│    - retryState (map ruleId → { attempts, lastTriedAt })     │
└──────────────┬──────────────────────────────────────────────┘
               │
       ┌───────┴────────┐
       ▼                ▼
  useCoherenceVerdict(ruleId, itemKey?)     useCoherenceSummary()
  (consommateur ponctuel : pastille)         (page /health)
```

### Arborescence des nouveaux fichiers

```
src/coherence/
├── rules/
│   ├── index.js                            → export RULES (array)
│   ├── replicas_vs_max_slots.js + .test.js
│   ├── replica_job_mapping.js + .test.js
│   ├── peak_ram_exceeds_allocated.js + .test.js
│   └── running_count_parity.js + .test.js
├── CoherenceProvider.jsx + .test.jsx       → wrapper + context
├── hooks.js                                → useCoherenceVerdict, useCoherenceSummary
├── types.js                                → JSDoc type aliases partagés
├── __fixtures__/
│   └── mocks.js                            → mkReplica, mkJob, mkCapacity helpers
└── components/
    ├── CoherencePastille.jsx + .test.jsx   → <CoherencePastille ruleId itemKey? />
    └── CoherenceHealthPage.jsx + .test.jsx → page /health
```

### Fichiers existants modifiés

| Fichier | Modification |
|---|---|
| `src/App.jsx` | Monter `<CoherenceProvider>` (avec replicas/jobs/capacity/capacityPlanning passés en props). Ajout route `/health`. |
| `src/lib/navigation.js` | Entrée "Santé système" dans section "Opérations" avec icône `HeartPulse`, route `/health`. |
| `src/components/CapacityBar.jsx` | Pastille à droite de "X/Y slots" pour `replicas_vs_max_slots`. |
| `src/components/ReplicaMonitor.jsx` | Pastille per-item dans le header de chaque card replica pour `replica_job_mapping`. |
| `src/pages/CapacityPlanningPage.jsx` | Pastille per-item dans la cellule "Peak" pour `peak_ram_exceeds_allocated`. |
| `src/pages/Overview.jsx` | Pastille à côté du StatCard "En cours" pour `running_count_parity`. |
| `package.json` | Dev deps : `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `jsdom`. Script `test`. |
| `vitest.config.js` | Nouveau fichier (config jsdom + setup). |

### Signature d'une règle

```js
/**
 * @typedef Rule
 * @property {string} id                — slug unique (ex: 'replicas_vs_max_slots')
 * @property {string} label             — label humain court (affiché dans /health)
 * @property {string} description       — explication longue
 * @property {'info'|'warning'|'critical'} severity
 * @property {Array<'replicas'|'capacity'|'jobs'|'capacityPlanning'>} sources
 * @property {(sources) => Violation[]} evaluate  — pure function, retourne []
 *                                                  si pas de violation
 * @property {AutoRetryConfig?} autoRetry
 * @property {{ path: string, label: string }?} attachUiHint
 *   — ex: { path: '/', label: 'Overview · Capacity bar' }
 *   — utilisé par le bouton "Voir dans l'UI" de /health pour linker vers
 *     l'endroit principal où la pastille inline est ancrée. Optionnel.
 */

/**
 * @typedef Violation
 * @property {string?} itemKey          — si per-item (ex: replicaId), undefined si global
 * @property {string} message           — message humain affiché dans tooltip + /health
 * @property {object?} data             — données brutes pour debugging / copy-to-clipboard
 */

/**
 * @typedef AutoRetryConfig
 * @property {number} maxAttempts       — ex: 2
 * @property {number} delayMs           — ex: 3000
 * @property {Array<Array<string>>} invalidate  — React Query keys à invalider
 *   ex: [['capacity'], ['jobs']]
 */
```

### Cadence d'évaluation

**Pas de timer, pas de polling**. Les règles sont des fonctions pures évaluées via `useMemo` sur les sources. Re-run uniquement quand :
- Un heartbeat WS met à jour `replicas` (App.jsx setReplicas)
- Une React Query mute son cache (`useCapacityQuery`, `useJobsQuery`, `useCapacityPlanningQuery`)

Zéro surcoût CPU quand rien ne bouge.

**Note sur le champ `sources` d'une règle** : c'est principalement de la documentation / information pour la page `/health`. En pratique, l'implémentation évalue toutes les règles à chaque changement de n'importe quelle source (coût négligeable sur 4 règles × comparaisons triviales). Une optimisation future qui filtre par `sources` reste possible sans casser le contrat.

### Flux auto-retry

1. Rule évaluée → violation détectée
2. Si règle a `autoRetry` et pas encore atteint `maxAttempts` pour ce `ruleId` :
   - `retryState[ruleId] = { attempts: N, lastTriedAt: now }`
   - Schedule (via `setTimeout`) après `delayMs` :
     - Invalide les React Query keys listées
     - Force une nouvelle évaluation
3. Si nouvelle évaluation retourne `[]` (healed) → reset `retryState[ruleId]`
4. Si toujours violée après `maxAttempts` → cesse de retry, verdict reste affiché avec chip "🔁 N refetch sans effet"

Le reset du compteur se fait quand la violation **disparaît** (pas quand la donnée change). Cela évite un bouclage si une violation persistante remet le compteur à 0 à chaque heartbeat.

---

## 3. UX

### Pastille inline

**Composant** : `<CoherencePastille ruleId itemKey? className? />`

- **Visuel** : icône 14×14px colorée selon severity via tokens
  - `info` → icône `Info`, `text-info`
  - `warning` → icône `AlertTriangle`, `text-warning`
  - `critical` → icône `AlertCircle`, `text-destructive`
- **Hover** : Tooltip primitive (existant) avec le `message` de la violation + phrase "Cliquer pour diagnostic"
- **Click** : `navigate('/health#rule-' + ruleId)` — ouvre la page santé scrollée sur la règle
- **Pas de violation** : render `null` (aucun espace réservé, zéro placeholder)
- **Pour les règles per-item** : filtre les violations où `v.itemKey === props.itemKey`

### Attachement dans l'UI existante

| Règle | Composant hôte | Placement |
|---|---|---|
| `replicas_vs_max_slots` | `CapacityBar` | à droite de "X/Y slots" (global) |
| `replica_job_mapping` | `ReplicaMonitor` | dans le header de chaque card replica (per-item) |
| `peak_ram_exceeds_allocated` | `CapacityPlanningPage` | dans la cellule "Peak" de la table (per-item) |
| `running_count_parity` | `Overview` | à côté du StatCard "En cours" (global) |

### Page `/health`

**Route** : `/health`
**Sidebar** : nouvelle entrée dans section "Opérations" sous "Journal d'audit"
**Icône sidebar** : `HeartPulse` (lucide)
**Description** : "Cohérence des données affichées"

**Layout** :

```
┌─────────────────────────────────────────────────────────────┐
│ 🩺 Cohérence des données                                     │
│ 4 règles · évaluées il y a Xs                                │
│                                                              │
│ ┌─ Total ──┐ ┌─ Warning ─┐ ┌─ Critical ─┐ ┌─ OK ────┐       │
│ │    4     │ │     2     │ │      0     │ │    2    │       │
│ └──────────┘ └───────────┘ └────────────┘ └─────────┘       │
│                                                              │
│ ── Violations (2) ── [expanded par défaut]                   │
│                                                              │
│ ┌─ replicas_vs_max_slots · ⚠ warning ─────────────┐         │
│ │ Replicas vs slots configurés                     │ ← id=rule-replicas_vs_max_slots
│ │                                                   │         │
│ │ 7 slots configurés mais 6 replicas vivants —     │         │
│ │ 1 slot(s) inutilisable(s)                        │         │
│ │                                                   │         │
│ │ Sources : replicas (WS), capacity (REST)         │         │
│ │ Impact : 1 slot inutilisable → throughput        │         │
│ │          max dégradé                              │         │
│ │                                                   │         │
│ │ [📋 Copier contexte]  [🔕 Ignorer session]       │         │
│ │                     [↗ Voir dans l'UI]           │         │
│ └───────────────────────────────────────────────────┘         │
│                                                              │
│ ┌─ peak_ram_exceeds_allocated · ⓘ info ──────────┐         │
│ │ Peak RAM > allocation                          │         │
│ │                                                 │         │
│ │ 2 replicas concernés :                         │         │
│ │  · crawler-abc : peak 7.2 GB > allocated 6 GB  │         │
│ │  · crawler-def : peak 6.4 GB > allocated 6 GB  │         │
│ │                                                 │         │
│ │ [📋 Copier] [🔕 Ignorer]                      │         │
│ └─────────────────────────────────────────────────┘         │
│                                                              │
│ ── OK (2) ── [collapsed par défaut]                          │
│ ✓ replica_job_mapping                                        │
│ ✓ running_count_parity                                       │
│                                                              │
│ ── Ignorées (0) ── [hidden si vide]                          │
└─────────────────────────────────────────────────────────────┘
```

- Chaque card violation = `<Card>` avec bordure colorée selon severity
- Hash `#rule-<id>` : sur arrivée, scroll vers la card et ajout d'un `ring-2 ring-ring` pendant 2s
- Actions visibles selon règle (bouton Rafraîchir seulement si `autoRetry` défini)

### Topbar indicator

**Skip pour MVP.** Notation pour futur : petite icône `HeartPulse` dans Topbar à droite de Cmd+K, badge rouge si violations > 0, clic → `/health`. Peut s'ajouter sans refacto une fois la page `/health` stabilisée.

---

## 4. Catalogue des règles MVP

### 4.1 `replicas_vs_max_slots`

- **Severity** : `warning`
- **Type** : global (1 violation max)
- **Sources** : `replicas`, `capacity`
- **Détecte** : replicas vivants < `max_global_jobs` → N slots inutilisables
- **AutoRetry** : ❌ non (pas transitoire)

```js
evaluate: ({ replicas, capacity }) => {
  if (!capacity?.max_global_jobs) return [];
  const max = capacity.max_global_jobs;
  const alive = Object.values(replicas).filter(r =>
    r?.replicaId && Date.now() - (r.timestamp ?? 0) < 30_000
  ).length;
  if (alive === 0) return [];        // cold start guard
  if (alive >= max) return [];       // OK ou sur-provisioning (autre règle future)
  return [{
    message: `${max} slots configurés mais ${alive} replicas vivants — ${max - alive} slot(s) inutilisable(s)`,
    data: { alive, max, phantom: max - alive },
  }];
}
```

**Edge cases** :
- `alive === 0` : cold start (WS pas connecté) → skip
- `alive > max` : sur-provisioning, pas cette règle (autre règle future hors MVP)
- Heartbeat stale (>30s) : déjà filtré par le cutoff

---

### 4.2 `replica_job_mapping`

- **Severity** : `warning`
- **Type** : per-item (violations multiples possibles, une par replica)
- **Sources** : `replicas`, `jobs`
- **Détecte** :
  - (a) replica avec `cpu > 30%` mais sans `jobId` → ghost crawler
  - (b) replica avec `jobId` pointant vers un job qui n'est plus `running` dans la liste → désync
- **AutoRetry** : ✅ pour variant (b), `delayMs: 3000`, `maxAttempts: 2`, invalidate `['jobs']`

```js
evaluate: ({ replicas, jobs }) => {
  const violations = [];
  const liveReplicas = Object.values(replicas).filter(r =>
    r?.replicaId && Date.now() - (r.timestamp ?? 0) < 30_000
  );
  const runningJobIds = new Set(
    (jobs ?? []).filter(j => j.status === 'running').map(j => j.id)
  );
  for (const r of liveReplicas) {
    if ((r.cpu ?? 0) > 0.3 && !r.jobId) {
      violations.push({
        itemKey: r.replicaId,
        message: `Replica ${r.replicaId.slice(0,12)} actif (CPU ${(r.cpu*100).toFixed(0)}%) mais sans jobId`,
        data: { replicaId: r.replicaId, cpu: r.cpu, kind: 'replica_without_job' },
      });
    }
    if (r.jobId && !runningJobIds.has(r.jobId)) {
      violations.push({
        itemKey: r.replicaId,
        message: `Replica sur job ${r.jobId.slice(0,12)} mais ce job n'est plus running dans la liste`,
        data: { replicaId: r.replicaId, jobId: r.jobId, kind: 'stale_job_reference' },
      });
    }
  }
  return violations;
}
```

**Edge cases** :
- CPU threshold 30% : arbitraire, à ajuster si Playwright init cause des bursts légitimes
- Job avec `end_time < 10s` : skip (viens juste de finir, cache REST rattrape)
- Replica en `restarting_oom` : skip (`jobId` peut être stale légitimement)

---

### 4.3 `peak_ram_exceeds_allocated`

- **Severity** : `info`
- **Type** : per-item
- **Sources** : `capacityPlanning`
- **Détecte** : dans les stats agrégées, `peak > allocated` → bug de tracking backend
- **AutoRetry** : ❌ non (bug backend, refetch ne corrigera rien)

```js
evaluate: ({ capacityPlanning }) => {
  const replicas = capacityPlanning?.replicas ?? [];
  const violations = [];
  for (const r of replicas) {
    if (!r.allocated || !r.peak) continue;
    if (r.peak <= r.allocated) continue;
    if (r.peak / r.allocated < 1.02) continue;   // tolérance 2% arrondi
    violations.push({
      itemKey: r.replicaId,
      message: `Peak ${(r.peak/1024/1024/1024).toFixed(2)} GB > alloué ${(r.allocated/1024/1024/1024).toFixed(2)} GB — tracking backend incohérent`,
      data: { replicaId: r.replicaId, peak: r.peak, allocated: r.allocated },
    });
  }
  return violations;
}
```

**Edge cases** :
- Tolérance 2% : compense l'arrondi `fmtBytes` et le jitter cgroup
- Severity `info` et pas `warning` : signal, pas incident ops

---

### 4.4 `running_count_parity`

- **Severity** : `info`
- **Type** : global
- **Sources** : `capacity`, `jobs`
- **Détecte** : `capacity.running_jobs` ≠ count des jobs `status === 'running'`
- **AutoRetry** : ✅ `delayMs: 3000`, `maxAttempts: 2`, invalidate `[['capacity'], ['jobs']]`

```js
evaluate: ({ capacity, jobs }) => {
  if (capacity?.running_jobs == null || !jobs) return [];
  const backendRunning = capacity.running_jobs;
  const listRunning = jobs.filter(j => j.status === 'running').length;
  if (backendRunning === listRunning) return [];
  if (Math.abs(backendRunning - listRunning) <= 1) return [];   // tolérance race
  return [{
    message: `CapacityBar ${backendRunning} en cours, liste en affiche ${listRunning} — désync REST`,
    data: { backendRunning, listRunning, diff: backendRunning - listRunning },
  }];
}
```

**Edge cases** :
- Tolérance ±1 : React Query peut avoir des refetch décalés de 1-2s
- Severity `info` : n'alarme pas, juste transparent

---

## 5. Actions de healing

### Auto-retry automatique

Activé par le champ `autoRetry` de la règle. Flux décrit en section 2 (Architecture). Matrice :

| Règle | autoRetry | Raison |
|---|---|---|
| `replicas_vs_max_slots` | ❌ | replica mort ne ressuscite pas par refetch |
| `replica_job_mapping` | ✅ | variant `stale_job_reference` = désync REST/WS typiquement résolue en 3s |
| `peak_ram_exceeds_allocated` | ❌ | bug backend, refetch inutile |
| `running_count_parity` | ✅ | désync transitoire classique |

### Actions manuelles dans `/health`

Sur chaque card violation :

| Action | Dispo | Effet |
|---|---|---|
| **🔄 Rafraîchir** | règles `autoRetry` uniquement | Invalide les React Query keys immédiatement (bypass delay) |
| **📋 Copier contexte** | toutes | `navigator.clipboard.writeText(JSON.stringify({ ruleId, violations, ts, userAgent, url }, null, 2))` |
| **🔕 Ignorer pour cette session** | toutes | Ajoute `ruleId` au Set `ignoredRules` du context. Pastilles disparaissent. Dans `/health`, la règle passe en section "Ignorées" avec bouton "Réactiver". **Pas de localStorage** — refresh = reset (YAGNI) |
| **↗ Voir dans l'UI** | règles avec `attachUiHint` | Navigation vers la page où la pastille est ancrée, avec scroll hint |

### Pas d'actions sur la pastille

La pastille inline = indicateur silencieux. Aucun menu, aucun bouton. Clic = `navigate('/health#rule-<id>')`. Toutes les actions sont centralisées dans `/health`.

---

## 6. Testing strategy

### Stack

- **Vitest** (aligné Vite, speed, API Jest-compatible)
- **@testing-library/react** pour components + provider
- **jsdom** environnement
- Pas de MSW : mock direct via `queryClient.setQueryData` ou props

### Répartition prévue

| Cible | Type | Nombre | Priorité |
|---|---|---|---|
| Les 4 règles | unit (fonction pure) | ~16 (4×4) | 🔴 must |
| CoherenceProvider + hooks | integration RTL | 3-4 | 🟡 should |
| CoherencePastille | component RTL | 3-4 | 🟡 should |
| CoherenceHealthPage | smoke | 2 | 🟢 nice |
| Auto-retry timer | unit `vi.useFakeTimers` | 2-3 | 🟡 should |
| **Total MVP** | | **~28** | |

### Conventions

- Un `.test.js` à côté de chaque source
- Helpers partagés dans `src/coherence/__fixtures__/mocks.js` (exports `mkReplica`, `mkJob`, `mkCapacity`, `mkCapacityPlanningData`)
- Script `yarn test` dans `package.json`
- CI : à câbler quand le projet aura un runner CI (hors scope spec)

### Pattern de test d'une règle

```js
import { describe, it, expect } from 'vitest';
import rule from './replicas_vs_max_slots';
import { mkReplica } from '../__fixtures__/mocks';

describe('replicas_vs_max_slots', () => {
  it('returns [] when alive matches max', () => { ... });
  it('returns [] on cold start (no replicas)', () => { ... });
  it('flags phantom slots when alive < max', () => { ... });
  it('ignores stale heartbeats (>30s)', () => { ... });
});
```

### Ce qu'on ne teste pas

- Rendu pixel-perfect de `/health` (hors scope, pas de visual regression tooling en place)
- Workflow de navigation complet (React Router E2E lourd pour peu de valeur)
- Combinaisons cartésiennes de violations (chaque règle testée isolée)
- Performance du framework (règles triviales, pas d'enjeu CPU)

---

## 7. Risques et mitigations

| Risque | Mitigation |
|---|---|
| Faux positifs fréquents (tolérances mal calibrées) | Severity `info` par défaut quand incertain. Ajustement des thresholds après retour terrain. |
| Auto-retry boucle infinie si backend en erreur | `maxAttempts: 2` strict. Après ça, violation reste affichée sans retry. |
| Pastilles partout rendent l'UI bruyante | Tolérances et cold-start guards stricts. Si > 3 violations simultanées sans incident, ré-évaluer les règles. |
| Règle mal écrite fait crash le Provider | Chaque `evaluate()` est try/catch dans le framework. Crash d'une règle → logged, verdict = `[]`. |
| Ignore session facilement oublié | `/health` montre la section "Ignorées" en permanence si non vide. Pas de masquage total. |

---

## 8. Volumétrie estimée

- **Code nouveau** : ~500 lignes (4 règles × ~80 lignes + provider + hooks + 2 components + page /health)
- **Tests** : ~400 lignes (~28 tests)
- **Modifications fichiers existants** : ~50 lignes total (6 fichiers)
- **Dev deps ajoutées** : vitest, @testing-library/react, @testing-library/jest-dom, jsdom
- **Changements backend** : aucun

---

## 9. Plan de livraison suggéré

À confirmer lors de l'écriture du plan d'implémentation, suggestion en commits :

1. Setup vitest + premier smoke test
2. Types + architecture du registre + CoherenceProvider (sans règles)
3. Règle 1 (`replicas_vs_max_slots`) + sa pastille dans CapacityBar
4. Règle 2 (`replica_job_mapping`) + pastille per-item dans ReplicaMonitor
5. Règle 3 (`peak_ram_exceeds_allocated`) + pastille dans CapacityPlanning
6. Règle 4 (`running_count_parity`) + pastille dans Overview
7. Page `/health` + entrée sidebar
8. Auto-retry (hook + tests fake timers)
9. Actions manuelles dans `/health` (copy / ignore / refresh)

Chaque étape livrable et testable indépendamment.
