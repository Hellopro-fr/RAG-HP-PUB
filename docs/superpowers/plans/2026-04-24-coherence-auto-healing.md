# Coherence Auto-Healing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a frontend-only framework that detects data incoherences in the crawler-monitor dashboard (pilot: 4 rules on replicas/jobs/capacity), shows them inline + on a dedicated `/health` page, and offers lightweight auto-retry + manual actions.

**Architecture:** `<CoherenceProvider>` wraps the app inside App.jsx, receives `replicas` (WS state) + reads React Query caches, runs rules (pure functions) via `useMemo`, exposes verdicts via React Context. Inline `<CoherencePastille>` components subscribe via hook. Page `/health` lists all rules + violations.

**Tech Stack:** React 19 + Vite 7 + Tailwind 3 + shadcn/ui (radix primitives already present) + @tanstack/react-query + react-router-dom v6. Tests: Vitest + @testing-library/react + jsdom (new dev deps).

**Spec:** `docs/superpowers/specs/2026-04-24-coherence-auto-healing-design.md`

**Working directory:** `/home/fetrawsl/project/RAG-HP-PUB-coherence/apps-microservices/crawler-monitor-frontend`

---

## Task 1: Setup test infrastructure (Vitest + RTL)

**Goal:** Add Vitest + React Testing Library + jsdom, replace the placeholder `node --test` script, verify with one smoke test.

**Files:**
- Modify: `apps-microservices/crawler-monitor-frontend/package.json` (add devDeps, replace `test` script)
- Create: `apps-microservices/crawler-monitor-frontend/vitest.config.js`
- Create: `apps-microservices/crawler-monitor-frontend/src/setupTests.js`
- Create: `apps-microservices/crawler-monitor-frontend/src/coherence/__fixtures__/smoke.test.js` (temporary, deleted in Task 2)

**Acceptance Criteria:**
- [ ] `yarn test` runs Vitest (not `node --test`)
- [ ] Smoke test passes
- [ ] Existing `yarn build` still succeeds
- [ ] No runtime regression (app still starts with `yarn dev`)

**Verify:** `yarn test 2>&1 | tail -10` → "1 test passed"

**Steps:**

- [ ] **Step 1: Install dev dependencies**

Run inside `apps-microservices/crawler-monitor-frontend/`:

```bash
yarn add -D vitest@^3 @testing-library/react@^16 @testing-library/jest-dom@^6 jsdom@^25
```

- [ ] **Step 2: Create `vitest.config.js`**

```js
// apps-microservices/crawler-monitor-frontend/vitest.config.js
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.js'],
    globals: true,
    include: ['src/**/*.{test,spec}.{js,jsx}'],
  },
});
```

- [ ] **Step 3: Create `src/setupTests.js`**

```js
// apps-microservices/crawler-monitor-frontend/src/setupTests.js
import '@testing-library/jest-dom/vitest';
```

- [ ] **Step 4: Update `package.json` test script**

Replace the existing `"test"` script. Locate this line in `scripts`:

```json
"test": "node --test tests/*.test.js"
```

Replace with:

```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 5: Create smoke test**

```js
// apps-microservices/crawler-monitor-frontend/src/coherence/__fixtures__/smoke.test.js
import { describe, it, expect } from 'vitest';

describe('test infra smoke', () => {
  it('runs basic arithmetic', () => {
    expect(1 + 1).toBe(2);
  });

  it('has jsdom environment', () => {
    expect(typeof window).toBe('object');
    expect(typeof document).toBe('object');
  });
});
```

- [ ] **Step 6: Run the test suite**

```bash
yarn test
```

Expected output (excerpt):
```
 ✓ src/coherence/__fixtures__/smoke.test.js (2 tests)
 Test Files  1 passed (1)
 Tests       2 passed (2)
```

- [ ] **Step 7: Verify build still works**

```bash
yarn build
```

Expected: no errors, `dist/` generated.

- [ ] **Step 8: Commit**

```bash
git add \
  apps-microservices/crawler-monitor-frontend/package.json \
  apps-microservices/crawler-monitor-frontend/yarn.lock \
  apps-microservices/crawler-monitor-frontend/vitest.config.js \
  apps-microservices/crawler-monitor-frontend/src/setupTests.js \
  apps-microservices/crawler-monitor-frontend/src/coherence/__fixtures__/smoke.test.js
git commit -m "chore(crawler-monitor-frontend): setup vitest + RTL for coherence tests"
```

---

## Task 2: Types, rule signature, and first rule (replicas_vs_max_slots)

**Goal:** Establish the rule contract (JSDoc types) and ship the first rule + its unit tests. Pure functions, no UI yet.

**Files:**
- Create: `src/coherence/types.js` (JSDoc typedefs)
- Create: `src/coherence/rules/index.js` (RULES export)
- Create: `src/coherence/rules/replicas_vs_max_slots.js`
- Create: `src/coherence/rules/replicas_vs_max_slots.test.js`
- Create: `src/coherence/__fixtures__/mocks.js` (helpers `mkReplica`, `mkCapacity`)
- Delete: `src/coherence/__fixtures__/smoke.test.js` (smoke from Task 1 no longer needed)

**Acceptance Criteria:**
- [ ] `RULES` array exported from `src/coherence/rules/index.js` contains 1 rule
- [ ] Rule returns `[]` when alive matches max
- [ ] Rule returns `[]` on cold start (no live replicas)
- [ ] Rule flags phantom slots when alive < max
- [ ] Rule ignores stale heartbeats (> 30s)
- [ ] All tests pass

**Verify:** `yarn test src/coherence/rules/replicas_vs_max_slots.test.js` → all green

**Steps:**

- [ ] **Step 1: Create types file (JSDoc for editor hints)**

```js
// apps-microservices/crawler-monitor-frontend/src/coherence/types.js
/**
 * @typedef {'info'|'warning'|'critical'} Severity
 *
 * @typedef {'replicas'|'capacity'|'jobs'|'capacityPlanning'} SourceName
 *
 * @typedef {Object} Sources
 * @property {Object<string, any>} replicas          WS heartbeat state
 * @property {{running_jobs, max_global_jobs, is_full}|null} capacity
 * @property {Array<{id, status, start_time, end_time}>|null} jobs
 * @property {{replicas, totals}|null} capacityPlanning
 *
 * @typedef {Object} Violation
 * @property {string=} itemKey      Undefined for global rules; set for per-item
 * @property {string} message       Human-readable message
 * @property {Object=} data         Raw context (for debugging / copy-to-clipboard)
 *
 * @typedef {Object} AutoRetryConfig
 * @property {number} maxAttempts
 * @property {number} delayMs
 * @property {Array<Array<string>>} invalidate   React Query keys
 *
 * @typedef {Object} UiHint
 * @property {string} path                        Route to navigate to
 * @property {string} label                       Human label for the link
 *
 * @typedef {Object} Rule
 * @property {string} id
 * @property {string} label
 * @property {string} description
 * @property {Severity} severity
 * @property {SourceName[]} sources
 * @property {(sources: Sources) => Violation[]} evaluate
 * @property {AutoRetryConfig=} autoRetry
 * @property {UiHint=} attachUiHint
 */

export {};
```

- [ ] **Step 2: Create mock fixtures**

```js
// apps-microservices/crawler-monitor-frontend/src/coherence/__fixtures__/mocks.js
/**
 * Shared test fixtures for coherence rules.
 * Helpers return shapes that mirror the real props/query data.
 */

export const mkReplica = (id, overrides = {}) => ({
  replicaId: id,
  cpu: 0,
  ram: 0,
  totalRam: 6 * 1024 * 1024 * 1024,
  jobId: null,
  timestamp: Date.now(),
  ...overrides,
});

export const mkCapacity = (overrides = {}) => ({
  running_jobs: 0,
  max_global_jobs: 7,
  is_full: false,
  ...overrides,
});

export const mkJob = (id, overrides = {}) => ({
  id,
  status: 'running',
  start_time: new Date().toISOString(),
  end_time: null,
  ...overrides,
});

export const mkCapacityPlanningData = (replicas = []) => ({
  replicas,
  totals: {
    total_allocated: replicas.reduce((s, r) => s + (r.allocated ?? 0), 0),
    total_peak_worst: replicas.reduce((s, r) => s + (r.peak ?? 0), 0),
    total_avg: 0,
    waste: 0,
    waste_pct: 0,
    efficiency: 0,
    replica_count: replicas.length,
  },
  window: '1h',
  window_ms: 3600000,
  generated_at: new Date().toISOString(),
});
```

- [ ] **Step 3: Create the first rule**

```js
// apps-microservices/crawler-monitor-frontend/src/coherence/rules/replicas_vs_max_slots.js
/** @type {import('../types').Rule} */
const rule = {
  id: 'replicas_vs_max_slots',
  label: 'Replicas vs slots configurés',
  description:
    'Détecte les slots "phantom" — configuration MAX_GLOBAL_JOBS supérieure ' +
    'au nombre de replicas vivants. Un replica est considéré vivant si son ' +
    'heartbeat est reçu dans les 30 dernières secondes.',
  severity: 'warning',
  sources: ['replicas', 'capacity'],
  attachUiHint: { path: '/', label: 'Vue d\'ensemble · Capacity bar' },
  evaluate: ({ replicas, capacity }) => {
    if (!capacity?.max_global_jobs) return [];
    const max = capacity.max_global_jobs;
    const alive = Object.values(replicas || {}).filter(
      (r) => r?.replicaId && Date.now() - (r.timestamp ?? 0) < 30_000,
    ).length;
    if (alive === 0) return []; // cold start — skip
    if (alive >= max) return []; // OK (over-provisioning is a separate concern)
    return [
      {
        message: `${max} slots configurés mais ${alive} replicas vivants — ${
          max - alive
        } slot(s) inutilisable(s)`,
        data: { alive, max, phantom: max - alive },
      },
    ];
  },
};

export default rule;
```

- [ ] **Step 4: Write the failing tests**

```js
// apps-microservices/crawler-monitor-frontend/src/coherence/rules/replicas_vs_max_slots.test.js
import { describe, it, expect } from 'vitest';
import rule from './replicas_vs_max_slots';
import { mkReplica, mkCapacity } from '../__fixtures__/mocks';

const mkReplicasDict = (list) =>
  Object.fromEntries(list.map((r) => [r.replicaId, r]));

describe('replicas_vs_max_slots', () => {
  it('returns [] when alive matches max', () => {
    const replicas = mkReplicasDict([
      mkReplica('r1'),
      mkReplica('r2'),
    ]);
    const capacity = mkCapacity({ max_global_jobs: 2 });
    expect(rule.evaluate({ replicas, capacity })).toEqual([]);
  });

  it('returns [] on cold start (no replicas)', () => {
    expect(
      rule.evaluate({ replicas: {}, capacity: mkCapacity({ max_global_jobs: 7 }) }),
    ).toEqual([]);
  });

  it('flags phantom slots when alive < max', () => {
    const replicas = mkReplicasDict([
      mkReplica('r1'),
      mkReplica('r2'),
      mkReplica('r3'),
    ]);
    const capacity = mkCapacity({ max_global_jobs: 7 });
    const result = rule.evaluate({ replicas, capacity });
    expect(result).toHaveLength(1);
    expect(result[0].data).toEqual({ alive: 3, max: 7, phantom: 4 });
    expect(result[0].message).toMatch(/7 slots configurés mais 3 replicas/);
  });

  it('ignores stale heartbeats (>30s)', () => {
    const replicas = mkReplicasDict([
      mkReplica('alive'),
      mkReplica('dead', { timestamp: Date.now() - 45_000 }),
    ]);
    const capacity = mkCapacity({ max_global_jobs: 1 });
    // alive count = 1, max = 1 → OK
    expect(rule.evaluate({ replicas, capacity })).toEqual([]);
  });

  it('returns [] when capacity data is missing', () => {
    const replicas = mkReplicasDict([mkReplica('r1')]);
    expect(rule.evaluate({ replicas, capacity: null })).toEqual([]);
    expect(rule.evaluate({ replicas, capacity: {} })).toEqual([]);
  });

  it('returns [] when alive exceeds max (over-provisioning, not this rule)', () => {
    const replicas = mkReplicasDict([mkReplica('r1'), mkReplica('r2'), mkReplica('r3')]);
    const capacity = mkCapacity({ max_global_jobs: 2 });
    expect(rule.evaluate({ replicas, capacity })).toEqual([]);
  });
});
```

- [ ] **Step 5: Create the registry**

```js
// apps-microservices/crawler-monitor-frontend/src/coherence/rules/index.js
import replicasVsMaxSlots from './replicas_vs_max_slots';

/** @type {import('../types').Rule[]} */
export const RULES = [replicasVsMaxSlots];
```

- [ ] **Step 6: Delete the smoke test from Task 1**

```bash
rm apps-microservices/crawler-monitor-frontend/src/coherence/__fixtures__/smoke.test.js
```

- [ ] **Step 7: Run the tests**

```bash
yarn test src/coherence/rules/replicas_vs_max_slots.test.js
```

Expected: `6 passed`

- [ ] **Step 8: Commit**

```bash
git add apps-microservices/crawler-monitor-frontend/src/coherence/
git commit -m "feat(coherence): types + rule replicas_vs_max_slots with unit tests"
```

---

## Task 3: CoherenceProvider + hooks + mount in App

**Goal:** Ship the context provider that runs rules on source changes, expose verdicts via two hooks, and mount in App.jsx.

**Files:**
- Create: `src/coherence/CoherenceProvider.jsx`
- Create: `src/coherence/hooks.js`
- Create: `src/coherence/CoherenceProvider.test.jsx`
- Modify: `src/App.jsx` (wrap Suspense/Routes with `<CoherenceProvider>`)

**Acceptance Criteria:**
- [ ] `useCoherenceVerdict('replicas_vs_max_slots')` returns the violations array
- [ ] `useCoherenceSummary()` returns `{ total, byStatus, verdicts, ignoredRules, setIgnored }`
- [ ] Rule errors are caught — a throwing rule logs and returns `[]`, others still work
- [ ] `ignoredRules` can be toggled via `setIgnored(id, true/false)`
- [ ] App.jsx still renders without regression

**Verify:**
- `yarn test src/coherence/CoherenceProvider.test.jsx` → all green
- `yarn dev` in browser → dashboard loads normally

**Steps:**

- [ ] **Step 1: Write the hooks file**

```js
// apps-microservices/crawler-monitor-frontend/src/coherence/hooks.js
import { useContext } from 'react';
import { CoherenceContext } from './CoherenceProvider';

/**
 * Get violations for a specific rule, optionally filtered by itemKey for per-item rules.
 * Returns [] if rule is ignored, unknown, or has no violations.
 */
export function useCoherenceVerdict(ruleId, itemKey) {
  const ctx = useContext(CoherenceContext);
  if (!ctx) return [];
  if (ctx.ignoredRules.has(ruleId)) return [];
  const violations = ctx.verdicts[ruleId] ?? [];
  if (itemKey === undefined) return violations;
  return violations.filter((v) => v.itemKey === itemKey);
}

/**
 * Get the full summary for the /health page.
 */
export function useCoherenceSummary() {
  const ctx = useContext(CoherenceContext);
  if (!ctx) {
    return {
      verdicts: {},
      ignoredRules: new Set(),
      setIgnored: () => {},
      lastEvaluatedAt: 0,
      retryState: {},
      manualRetry: () => {},
    };
  }
  return ctx;
}
```

- [ ] **Step 2: Write the provider**

```jsx
// apps-microservices/crawler-monitor-frontend/src/coherence/CoherenceProvider.jsx
import { createContext, useMemo, useState, useCallback } from 'react';
import {
  useJobsQuery,
  useCapacityQuery,
  useCapacityPlanningQuery,
} from '../hooks/queries';
import { RULES } from './rules';

export const CoherenceContext = createContext(null);

/**
 * Runs all coherence rules against the current sources.
 * Each rule's evaluate() is wrapped in try/catch: a bug in one rule does not
 * break the framework. Errors are logged; the rule's verdict becomes [].
 */
function runRules(sources) {
  const result = {};
  for (const rule of RULES) {
    try {
      const v = rule.evaluate(sources);
      result[rule.id] = Array.isArray(v) ? v : [];
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error(`[coherence] rule ${rule.id} threw:`, err);
      result[rule.id] = [];
    }
  }
  return result;
}

export function CoherenceProvider({ token, replicas, children }) {
  // Read sources from React Query caches. `useCapacityPlanningQuery` uses a
  // fixed '1h' window for coherence checks — the CapacityPlanning page uses
  // whatever window the user picks (separate cache key per window, no conflict).
  const jobsQuery = useJobsQuery(token);
  const capacityQuery = useCapacityQuery(token);
  const capacityPlanningQuery = useCapacityPlanningQuery(token, '1h');

  const sources = useMemo(
    () => ({
      replicas: replicas || {},
      jobs: jobsQuery.data ?? null,
      capacity: capacityQuery.data ?? null,
      capacityPlanning: capacityPlanningQuery.data ?? null,
    }),
    [replicas, jobsQuery.data, capacityQuery.data, capacityPlanningQuery.data],
  );

  const verdicts = useMemo(() => runRules(sources), [sources]);

  const [ignoredRules, setIgnoredRules] = useState(() => new Set());
  const setIgnored = useCallback((ruleId, value) => {
    setIgnoredRules((prev) => {
      const next = new Set(prev);
      if (value) next.add(ruleId);
      else next.delete(ruleId);
      return next;
    });
  }, []);

  const byStatus = useMemo(() => {
    let info = 0, warning = 0, critical = 0;
    for (const rule of RULES) {
      if (ignoredRules.has(rule.id)) continue;
      const hasViolation = (verdicts[rule.id] ?? []).length > 0;
      if (!hasViolation) continue;
      if (rule.severity === 'critical') critical += 1;
      else if (rule.severity === 'warning') warning += 1;
      else info += 1;
    }
    return { info, warning, critical };
  }, [verdicts, ignoredRules]);

  const total = RULES.length;
  const lastEvaluatedAt = Date.now();

  // Placeholder — Task 9 replaces with real retry state + manualRetry
  const retryState = {};
  const manualRetry = useCallback(() => {}, []);

  const value = useMemo(
    () => ({
      verdicts,
      ignoredRules,
      setIgnored,
      byStatus,
      total,
      lastEvaluatedAt,
      retryState,
      manualRetry,
    }),
    [verdicts, ignoredRules, setIgnored, byStatus, total, lastEvaluatedAt, retryState, manualRetry],
  );

  return (
    <CoherenceContext.Provider value={value}>
      {children}
    </CoherenceContext.Provider>
  );
}
```

- [ ] **Step 3: Write the provider tests**

```jsx
// apps-microservices/crawler-monitor-frontend/src/coherence/CoherenceProvider.test.jsx
import { describe, it, expect } from 'vitest';
import { render, renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CoherenceProvider } from './CoherenceProvider';
import { useCoherenceVerdict, useCoherenceSummary } from './hooks';
import { mkReplica } from './__fixtures__/mocks';

const mkWrapper = ({ token = 'tok', replicas = {}, seed } = {}) => {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  if (seed?.capacity) qc.setQueryData(['capacity'], seed.capacity);
  if (seed?.jobs) qc.setQueryData(['jobs'], seed.jobs);
  if (seed?.capacityPlanning)
    qc.setQueryData(['capacityPlanning', '1h'], seed.capacityPlanning);

  return function Wrapper({ children }) {
    return (
      <QueryClientProvider client={qc}>
        <CoherenceProvider token={token} replicas={replicas}>
          {children}
        </CoherenceProvider>
      </QueryClientProvider>
    );
  };
};

describe('CoherenceProvider', () => {
  it('runs replicas_vs_max_slots and exposes the violation', () => {
    const wrapper = mkWrapper({
      replicas: { r1: mkReplica('r1') },
      seed: { capacity: { max_global_jobs: 3, running_jobs: 0 } },
    });
    const { result } = renderHook(() => useCoherenceVerdict('replicas_vs_max_slots'), { wrapper });
    expect(result.current).toHaveLength(1);
    expect(result.current[0].data.phantom).toBe(2);
  });

  it('returns [] when sources have no issues', () => {
    const wrapper = mkWrapper({
      replicas: { r1: mkReplica('r1'), r2: mkReplica('r2') },
      seed: { capacity: { max_global_jobs: 2, running_jobs: 0 } },
    });
    const { result } = renderHook(() => useCoherenceVerdict('replicas_vs_max_slots'), { wrapper });
    expect(result.current).toEqual([]);
  });

  it('ignored rule returns [] even if violated', () => {
    const wrapper = mkWrapper({
      replicas: { r1: mkReplica('r1') },
      seed: { capacity: { max_global_jobs: 3, running_jobs: 0 } },
    });
    const { result } = renderHook(
      () => {
        const verdict = useCoherenceVerdict('replicas_vs_max_slots');
        const summary = useCoherenceSummary();
        return { verdict, summary };
      },
      { wrapper },
    );
    // Initially violated
    expect(result.current.verdict).toHaveLength(1);
    // Ignore it
    act(() => result.current.summary.setIgnored('replicas_vs_max_slots', true));
    expect(result.current.verdict).toEqual([]);
    // Un-ignore
    act(() => result.current.summary.setIgnored('replicas_vs_max_slots', false));
    expect(result.current.verdict).toHaveLength(1);
  });

  it('renders children without crashing', () => {
    const wrapper = mkWrapper();
    const { container } = render(<div data-testid="child">hello</div>, { wrapper });
    expect(container.textContent).toContain('hello');
  });

  it('summary counts violations by severity excluding ignored', () => {
    const wrapper = mkWrapper({
      replicas: { r1: mkReplica('r1') },
      seed: { capacity: { max_global_jobs: 3, running_jobs: 0 } },
    });
    const { result } = renderHook(() => useCoherenceSummary(), { wrapper });
    expect(result.current.byStatus.warning).toBe(1);
    act(() => result.current.setIgnored('replicas_vs_max_slots', true));
    expect(result.current.byStatus.warning).toBe(0);
  });
});
```

- [ ] **Step 4: Mount provider in App.jsx**

Locate the `return` statement in `src/App.jsx` which currently looks like:

```jsx
  return (
    <AppShell
      badges={{ failedCallbacks: failedCallbackCount }}
      onLogout={handleLogout}
      onRefresh={handleManualRefresh}
      isRefreshing={isJobsLoading}
    >
      <Suspense fallback={<PageFallback />}>
        <Routes>
          ...
        </Routes>
      </Suspense>
    </AppShell>
  );
```

Add the import at the top of the file:

```jsx
import { CoherenceProvider } from './coherence/CoherenceProvider';
```

And wrap `<AppShell>` content with the provider:

```jsx
  return (
    <CoherenceProvider token={token} replicas={replicas}>
      <AppShell
        badges={{ failedCallbacks: failedCallbackCount }}
        onLogout={handleLogout}
        onRefresh={handleManualRefresh}
        isRefreshing={isJobsLoading}
      >
        <Suspense fallback={<PageFallback />}>
          <Routes>
            ...  {/* keep exactly as before */}
          </Routes>
        </Suspense>
      </AppShell>
    </CoherenceProvider>
  );
```

- [ ] **Step 5: Run tests**

```bash
yarn test src/coherence/
```

Expected: `11 passed` (6 from rule + 5 from provider)

- [ ] **Step 6: Run dev server smoke**

```bash
yarn dev
```

Open `http://localhost:5173`, verify dashboard loads. Check DevTools console: no errors. Ctrl+C to stop.

- [ ] **Step 7: Commit**

```bash
git add \
  apps-microservices/crawler-monitor-frontend/src/coherence/CoherenceProvider.jsx \
  apps-microservices/crawler-monitor-frontend/src/coherence/CoherenceProvider.test.jsx \
  apps-microservices/crawler-monitor-frontend/src/coherence/hooks.js \
  apps-microservices/crawler-monitor-frontend/src/App.jsx
git commit -m "feat(coherence): CoherenceProvider + hooks, mount in App"
```

---

## Task 4: CoherencePastille component + wire to CapacityBar

**Goal:** Ship the `<CoherencePastille>` component and wire the first rule's pastille next to the slots count in `CapacityBar`.

**Files:**
- Create: `src/coherence/components/CoherencePastille.jsx`
- Create: `src/coherence/components/CoherencePastille.test.jsx`
- Modify: `src/components/CapacityBar.jsx` (import + add pastille next to `{capacity.running_jobs} / {capacity.max_global_jobs}`)

**Acceptance Criteria:**
- [ ] Renders `null` when no violation
- [ ] Renders a warning icon when violated
- [ ] Tooltip displays the violation message
- [ ] Click navigates to `/health#rule-<id>`
- [ ] `itemKey` filter works for per-item rules
- [ ] `CapacityBar` shows the pastille when `replicas_vs_max_slots` violates

**Verify:**
- `yarn test src/coherence/components/CoherencePastille.test.jsx` → all green
- Manual: `yarn dev`, check CapacityBar — if 6 replicas alive and max=7, pastille appears with tooltip

**Steps:**

- [ ] **Step 1: Write the pastille component**

```jsx
// apps-microservices/crawler-monitor-frontend/src/coherence/components/CoherencePastille.jsx
import { Link } from 'react-router-dom';
import { Info, AlertTriangle, AlertCircle } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipTrigger } from '../../components/ui/tooltip';
import { cn } from '../../lib/utils';
import { useCoherenceVerdict } from '../hooks';
import { RULES } from '../rules';

const ICON_BY_SEVERITY = {
  info: Info,
  warning: AlertTriangle,
  critical: AlertCircle,
};

const COLOR_BY_SEVERITY = {
  info: 'text-info',
  warning: 'text-warning',
  critical: 'text-destructive',
};

/**
 * Inline pastille that appears next to a metric when a coherence rule is violated.
 * Renders null (zero placeholder) when OK. Click → /health#rule-<id>.
 *
 * @param {{ ruleId: string, itemKey?: string, className?: string }} props
 */
export function CoherencePastille({ ruleId, itemKey, className }) {
  const violations = useCoherenceVerdict(ruleId, itemKey);
  if (violations.length === 0) return null;

  const rule = RULES.find((r) => r.id === ruleId);
  if (!rule) return null;

  const Icon = ICON_BY_SEVERITY[rule.severity] ?? AlertTriangle;
  const color = COLOR_BY_SEVERITY[rule.severity] ?? 'text-warning';
  const message = violations[0].message; // show first violation's message; /health shows all

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          to={`/health#rule-${ruleId}`}
          aria-label={`Incohérence détectée : ${message}`}
          className={cn('inline-flex shrink-0 hover:opacity-80', color, className)}
        >
          <Icon className="h-3.5 w-3.5" />
        </Link>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs">
        <div className="font-medium">{rule.label}</div>
        <div className="mt-0.5 text-xs">{message}</div>
        <div className="mt-1 text-[10px] text-muted-foreground">
          Cliquer pour diagnostic
        </div>
      </TooltipContent>
    </Tooltip>
  );
}
```

- [ ] **Step 2: Write pastille tests**

```jsx
// apps-microservices/crawler-monitor-frontend/src/coherence/components/CoherencePastille.test.jsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TooltipProvider } from '../../components/ui/tooltip';
import { CoherenceProvider } from '../CoherenceProvider';
import { CoherencePastille } from './CoherencePastille';
import { mkReplica } from '../__fixtures__/mocks';

const renderWith = (ui, { replicas = {}, capacity = null } = {}) => {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  if (capacity) qc.setQueryData(['capacity'], capacity);
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <TooltipProvider>
          <CoherenceProvider token="tok" replicas={replicas}>
            {ui}
          </CoherenceProvider>
        </TooltipProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
};

describe('CoherencePastille', () => {
  it('renders nothing when no violation', () => {
    const { container } = renderWith(
      <CoherencePastille ruleId="replicas_vs_max_slots" />,
      {
        replicas: { r1: mkReplica('r1'), r2: mkReplica('r2') },
        capacity: { max_global_jobs: 2, running_jobs: 0 },
      },
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders an icon + link when violated', () => {
    renderWith(<CoherencePastille ruleId="replicas_vs_max_slots" />, {
      replicas: { r1: mkReplica('r1') },
      capacity: { max_global_jobs: 3, running_jobs: 0 },
    });
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/health#rule-replicas_vs_max_slots');
    expect(link).toHaveAttribute(
      'aria-label',
      expect.stringMatching(/Incohérence/),
    );
  });

  it('renders nothing for unknown rule id', () => {
    const { container } = renderWith(<CoherencePastille ruleId="nope_not_a_rule" />);
    expect(container.innerHTML).toBe('');
  });

  it('filters by itemKey (per-item rule)', () => {
    // This test will be more valuable once per-item rules exist (Task 5+).
    // For now, assert that passing an unknown itemKey yields nothing.
    const { container } = renderWith(
      <CoherencePastille ruleId="replicas_vs_max_slots" itemKey="whatever" />,
      {
        replicas: { r1: mkReplica('r1') },
        capacity: { max_global_jobs: 3, running_jobs: 0 },
      },
    );
    // replicas_vs_max_slots is global (no itemKey) → filter yields [] → null
    expect(container.innerHTML).toBe('');
  });
});
```

- [ ] **Step 3: Run pastille tests**

```bash
yarn test src/coherence/components/CoherencePastille.test.jsx
```

Expected: `4 passed`

- [ ] **Step 4: Wire pastille into CapacityBar**

In `src/components/CapacityBar.jsx`, locate the block that displays slots:

```jsx
            <span className={cn('font-mono text-sm font-bold', capacity.is_full ? 'text-destructive' : 'text-success')}>
              {capacity.running_jobs} / {capacity.max_global_jobs} slots
            </span>
```

Add the import at the top of the file:

```jsx
import { CoherencePastille } from '../coherence/components/CoherencePastille';
```

And modify the span to include the pastille:

```jsx
            <span className={cn('flex items-center gap-1.5 font-mono text-sm font-bold', capacity.is_full ? 'text-destructive' : 'text-success')}>
              {capacity.running_jobs} / {capacity.max_global_jobs} slots
              <CoherencePastille ruleId="replicas_vs_max_slots" />
            </span>
```

- [ ] **Step 5: Smoke test in browser**

```bash
yarn dev
```

Open `http://localhost:5173`. If no violations, no pastille. To fake a violation for visual check, open DevTools → React Query Devtools → manually set `capacity.max_global_jobs` to a high number (e.g. 99). Pastille should appear with warning icon + tooltip on hover.

- [ ] **Step 6: Commit**

```bash
git add \
  apps-microservices/crawler-monitor-frontend/src/coherence/components/ \
  apps-microservices/crawler-monitor-frontend/src/components/CapacityBar.jsx
git commit -m "feat(coherence): CoherencePastille component wired to CapacityBar"
```

---

## Task 5: Rule `replica_job_mapping` + per-item pastille in ReplicaMonitor

**Goal:** Detect ghost replicas (cpu>30% no jobId) and stale job references; show pastille in each replica card header.

**Files:**
- Create: `src/coherence/rules/replica_job_mapping.js`
- Create: `src/coherence/rules/replica_job_mapping.test.js`
- Modify: `src/coherence/rules/index.js` (export the new rule)
- Modify: `src/components/ReplicaMonitor.jsx` (add pastille per replica card)

**Acceptance Criteria:**
- [ ] Rule flags `cpu > 30%` + no `jobId` → `kind: replica_without_job`
- [ ] Rule flags `jobId` pointing to a non-running job → `kind: stale_job_reference`
- [ ] Rule ignores replicas with status `restarting_oom`
- [ ] `itemKey` is set to `replicaId` for each violation
- [ ] ReplicaMonitor shows pastille in header of affected replica cards only

**Verify:** `yarn test src/coherence/rules/replica_job_mapping.test.js` → all green

**Steps:**

- [ ] **Step 1: Write the rule**

```js
// apps-microservices/crawler-monitor-frontend/src/coherence/rules/replica_job_mapping.js
/** @type {import('../types').Rule} */
const rule = {
  id: 'replica_job_mapping',
  label: 'Cohérence replica ↔ job',
  description:
    'Détecte les replicas qui tournent à fort CPU sans jobId rattaché (ghost ' +
    'crawler) ou qui référencent un jobId qui n\'est plus en running dans la liste ' +
    'REST (désync heartbeat vs REST).',
  severity: 'warning',
  sources: ['replicas', 'jobs'],
  attachUiHint: { path: '/', label: 'Vue d\'ensemble · Replicas' },
  evaluate: ({ replicas, jobs }) => {
    const violations = [];
    const liveReplicas = Object.values(replicas || {}).filter(
      (r) => r?.replicaId && Date.now() - (r.timestamp ?? 0) < 30_000,
    );
    const runningJobIds = new Set(
      (jobs ?? [])
        .filter((j) => j?.status === 'running')
        .map((j) => j.id),
    );

    for (const r of liveReplicas) {
      // Skip replicas that are restarting after OOM — jobId can legitimately
      // be stale during the restart window.
      if (r.status === 'restarting_oom') continue;

      // (a) high CPU but no jobId → ghost crawler
      if ((r.cpu ?? 0) > 0.3 && !r.jobId) {
        violations.push({
          itemKey: r.replicaId,
          message: `Replica ${String(r.replicaId).slice(0, 12)} actif (CPU ${(
            r.cpu * 100
          ).toFixed(0)}%) mais sans jobId rattaché`,
          data: { replicaId: r.replicaId, cpu: r.cpu, kind: 'replica_without_job' },
        });
      }

      // (b) jobId points to a job no longer running in the REST list
      if (r.jobId && !runningJobIds.has(r.jobId)) {
        violations.push({
          itemKey: r.replicaId,
          message: `Replica travaille sur job ${String(r.jobId).slice(
            0,
            12,
          )} mais ce job n'est plus "running" dans la liste`,
          data: {
            replicaId: r.replicaId,
            jobId: r.jobId,
            kind: 'stale_job_reference',
          },
        });
      }
    }
    return violations;
  },
  autoRetry: {
    maxAttempts: 2,
    delayMs: 3000,
    invalidate: [['jobs']],
  },
};

export default rule;
```

- [ ] **Step 2: Write the tests**

```js
// apps-microservices/crawler-monitor-frontend/src/coherence/rules/replica_job_mapping.test.js
import { describe, it, expect } from 'vitest';
import rule from './replica_job_mapping';
import { mkReplica, mkJob } from '../__fixtures__/mocks';

const replicasDict = (list) =>
  Object.fromEntries(list.map((r) => [r.replicaId, r]));

describe('replica_job_mapping', () => {
  it('returns [] when all replicas have a valid jobId pointing to running jobs', () => {
    const replicas = replicasDict([mkReplica('r1', { jobId: 'j1', cpu: 0.5 })]);
    const jobs = [mkJob('j1')];
    expect(rule.evaluate({ replicas, jobs })).toEqual([]);
  });

  it('flags replica with CPU > 30% but no jobId (ghost crawler)', () => {
    const replicas = replicasDict([mkReplica('r1', { cpu: 0.45, jobId: null })]);
    const jobs = [];
    const result = rule.evaluate({ replicas, jobs });
    expect(result).toHaveLength(1);
    expect(result[0].itemKey).toBe('r1');
    expect(result[0].data.kind).toBe('replica_without_job');
  });

  it('does NOT flag replica with low CPU and no jobId (idle replica)', () => {
    const replicas = replicasDict([mkReplica('r1', { cpu: 0.1, jobId: null })]);
    const jobs = [];
    expect(rule.evaluate({ replicas, jobs })).toEqual([]);
  });

  it('flags stale jobId reference (job not in running list)', () => {
    const replicas = replicasDict([mkReplica('r1', { cpu: 0.3, jobId: 'j_old' })]);
    const jobs = [mkJob('j_new')];
    const result = rule.evaluate({ replicas, jobs });
    expect(result.some((v) => v.data.kind === 'stale_job_reference')).toBe(true);
  });

  it('skips replicas with status restarting_oom', () => {
    const replicas = replicasDict([
      mkReplica('r1', { status: 'restarting_oom', jobId: 'old_job', cpu: 0.5 }),
    ]);
    const jobs = [];
    expect(rule.evaluate({ replicas, jobs })).toEqual([]);
  });

  it('skips stale-heartbeat replicas (>30s)', () => {
    const replicas = replicasDict([
      mkReplica('r1', { cpu: 0.8, jobId: null, timestamp: Date.now() - 60_000 }),
    ]);
    const jobs = [];
    expect(rule.evaluate({ replicas, jobs })).toEqual([]);
  });

  it('returns multiple violations for multiple replicas', () => {
    const replicas = replicasDict([
      mkReplica('r1', { cpu: 0.5, jobId: null }),
      mkReplica('r2', { cpu: 0.4, jobId: null }),
    ]);
    const jobs = [];
    const result = rule.evaluate({ replicas, jobs });
    expect(result).toHaveLength(2);
    expect(result.map((v) => v.itemKey).sort()).toEqual(['r1', 'r2']);
  });
});
```

- [ ] **Step 3: Register the rule**

Update `src/coherence/rules/index.js`:

```js
import replicasVsMaxSlots from './replicas_vs_max_slots';
import replicaJobMapping from './replica_job_mapping';

/** @type {import('../types').Rule[]} */
export const RULES = [replicasVsMaxSlots, replicaJobMapping];
```

- [ ] **Step 4: Wire pastille into ReplicaMonitor**

In `src/components/ReplicaMonitor.jsx`, locate the card header block for each replica:

```jsx
                <div className="mb-3 flex items-center justify-between">
                  <div className="flex min-w-0 flex-1 items-center gap-2">
                    <div className={cn('h-2.5 w-2.5 shrink-0 rounded-full', statusClass)} />
                    <span className="truncate font-mono text-xs font-semibold text-foreground">
                      {String(replica.replicaId || '').substring(0, 12)}
                    </span>
                  </div>
                  <Cpu className="h-4 w-4 shrink-0 text-primary" />
                </div>
```

Add the import at the top:

```jsx
import { CoherencePastille } from '../coherence/components/CoherencePastille';
```

And modify the header to include the pastille after the replica ID:

```jsx
                <div className="mb-3 flex items-center justify-between">
                  <div className="flex min-w-0 flex-1 items-center gap-2">
                    <div className={cn('h-2.5 w-2.5 shrink-0 rounded-full', statusClass)} />
                    <span className="truncate font-mono text-xs font-semibold text-foreground">
                      {String(replica.replicaId || '').substring(0, 12)}
                    </span>
                    <CoherencePastille ruleId="replica_job_mapping" itemKey={replica.replicaId} />
                  </div>
                  <Cpu className="h-4 w-4 shrink-0 text-primary" />
                </div>
```

- [ ] **Step 5: Run tests**

```bash
yarn test src/coherence/
```

Expected: `18 passed` (6 + 5 + 4 + 7 — mapping rule adds 7, registry is indirectly tested via provider)

- [ ] **Step 6: Commit**

```bash
git add \
  apps-microservices/crawler-monitor-frontend/src/coherence/rules/replica_job_mapping.js \
  apps-microservices/crawler-monitor-frontend/src/coherence/rules/replica_job_mapping.test.js \
  apps-microservices/crawler-monitor-frontend/src/coherence/rules/index.js \
  apps-microservices/crawler-monitor-frontend/src/components/ReplicaMonitor.jsx
git commit -m "feat(coherence): rule replica_job_mapping + pastille in ReplicaMonitor"
```

---

## Task 6: Rule `peak_ram_exceeds_allocated` + per-item pastille in CapacityPlanning

**Goal:** Detect backend tracking bug where peak > allocated; show pastille in the Peak table cell per replica.

**Files:**
- Create: `src/coherence/rules/peak_ram_exceeds_allocated.js`
- Create: `src/coherence/rules/peak_ram_exceeds_allocated.test.js`
- Modify: `src/coherence/rules/index.js`
- Modify: `src/pages/CapacityPlanningPage.jsx` (pastille in Peak cell)

**Acceptance Criteria:**
- [ ] Rule returns `[]` when `peak <= allocated`
- [ ] Rule returns violation when `peak > allocated * 1.02`
- [ ] Rule ignores 2% tolerance
- [ ] Pastille appears next to Peak value in table row

**Verify:** `yarn test src/coherence/rules/peak_ram_exceeds_allocated.test.js` → all green

**Steps:**

- [ ] **Step 1: Write the rule**

```js
// apps-microservices/crawler-monitor-frontend/src/coherence/rules/peak_ram_exceeds_allocated.js
const GB = 1024 * 1024 * 1024;
const TOLERANCE = 1.02; // 2% — compensates rounding / cgroup jitter

/** @type {import('../types').Rule} */
const rule = {
  id: 'peak_ram_exceeds_allocated',
  label: 'Peak RAM > allocation',
  description:
    'Dans les stats agrégées du capacity planning, peak ne devrait jamais ' +
    'dépasser allocated (hard limit cgroup). Si ça arrive, c\'est un bug de ' +
    'tracking côté backend, pas un incident ops.',
  severity: 'info',
  sources: ['capacityPlanning'],
  attachUiHint: { path: '/capacity-planning', label: 'Capacity Planning · table replicas' },
  evaluate: ({ capacityPlanning }) => {
    const replicas = capacityPlanning?.replicas ?? [];
    const violations = [];
    for (const r of replicas) {
      if (!r.allocated || !r.peak) continue;
      if (r.peak <= r.allocated) continue;
      if (r.peak / r.allocated < TOLERANCE) continue;
      violations.push({
        itemKey: r.replicaId,
        message: `Peak ${(r.peak / GB).toFixed(2)} GB > alloué ${(r.allocated / GB).toFixed(2)} GB — tracking backend incohérent`,
        data: {
          replicaId: r.replicaId,
          peak: r.peak,
          allocated: r.allocated,
          ratio: r.peak / r.allocated,
        },
      });
    }
    return violations;
  },
};

export default rule;
```

- [ ] **Step 2: Write the tests**

```js
// apps-microservices/crawler-monitor-frontend/src/coherence/rules/peak_ram_exceeds_allocated.test.js
import { describe, it, expect } from 'vitest';
import rule from './peak_ram_exceeds_allocated';

const mkCPReplica = (id, peakGB, allocatedGB) => ({
  replicaId: id,
  peak: peakGB * 1024 * 1024 * 1024,
  allocated: allocatedGB * 1024 * 1024 * 1024,
});

describe('peak_ram_exceeds_allocated', () => {
  it('returns [] when peak <= allocated', () => {
    const capacityPlanning = {
      replicas: [mkCPReplica('r1', 4, 6)],
    };
    expect(rule.evaluate({ capacityPlanning })).toEqual([]);
  });

  it('returns [] within 2% tolerance', () => {
    // 6.08 / 6 = 1.0133 → within 2% tolerance
    const capacityPlanning = {
      replicas: [mkCPReplica('r1', 6.08, 6)],
    };
    expect(rule.evaluate({ capacityPlanning })).toEqual([]);
  });

  it('flags when peak > allocated beyond tolerance', () => {
    // 7.2 / 6 = 1.2 → 20% over, exceeds 2% tolerance
    const capacityPlanning = {
      replicas: [mkCPReplica('r1', 7.2, 6)],
    };
    const result = rule.evaluate({ capacityPlanning });
    expect(result).toHaveLength(1);
    expect(result[0].itemKey).toBe('r1');
    expect(result[0].data.ratio).toBeCloseTo(1.2);
  });

  it('returns [] when capacityPlanning is null', () => {
    expect(rule.evaluate({ capacityPlanning: null })).toEqual([]);
  });

  it('skips replicas with missing allocated or peak', () => {
    const capacityPlanning = {
      replicas: [
        { replicaId: 'r_no_alloc', peak: 5 * 1024 * 1024 * 1024 },
        { replicaId: 'r_no_peak', allocated: 6 * 1024 * 1024 * 1024 },
      ],
    };
    expect(rule.evaluate({ capacityPlanning })).toEqual([]);
  });

  it('returns multiple violations for multiple offending replicas', () => {
    const capacityPlanning = {
      replicas: [
        mkCPReplica('r_ok', 5, 6),
        mkCPReplica('r_bad1', 7, 6),
        mkCPReplica('r_bad2', 8, 6),
      ],
    };
    const result = rule.evaluate({ capacityPlanning });
    expect(result).toHaveLength(2);
    expect(result.map((v) => v.itemKey).sort()).toEqual(['r_bad1', 'r_bad2']);
  });
});
```

- [ ] **Step 3: Register the rule**

Update `src/coherence/rules/index.js`:

```js
import replicasVsMaxSlots from './replicas_vs_max_slots';
import replicaJobMapping from './replica_job_mapping';
import peakRamExceedsAllocated from './peak_ram_exceeds_allocated';

/** @type {import('../types').Rule[]} */
export const RULES = [
  replicasVsMaxSlots,
  replicaJobMapping,
  peakRamExceedsAllocated,
];
```

- [ ] **Step 4: Wire pastille into CapacityPlanningPage**

In `src/pages/CapacityPlanningPage.jsx`, locate the Peak cell in the per-replica table row:

```jsx
                      <TableCell className="text-right font-mono text-info">{fmtBytes(r.peak)}</TableCell>
```

Add the import at the top:

```jsx
import { CoherencePastille } from '../coherence/components/CoherencePastille';
```

And modify the cell:

```jsx
                      <TableCell className="text-right font-mono text-info">
                        <span className="inline-flex items-center gap-1">
                          {fmtBytes(r.peak)}
                          <CoherencePastille
                            ruleId="peak_ram_exceeds_allocated"
                            itemKey={r.replicaId}
                          />
                        </span>
                      </TableCell>
```

- [ ] **Step 5: Run tests**

```bash
yarn test src/coherence/rules/
```

Expected: all rule tests pass (6 + 7 + 6 = 19)

- [ ] **Step 6: Commit**

```bash
git add \
  apps-microservices/crawler-monitor-frontend/src/coherence/rules/peak_ram_exceeds_allocated.js \
  apps-microservices/crawler-monitor-frontend/src/coherence/rules/peak_ram_exceeds_allocated.test.js \
  apps-microservices/crawler-monitor-frontend/src/coherence/rules/index.js \
  apps-microservices/crawler-monitor-frontend/src/pages/CapacityPlanningPage.jsx
git commit -m "feat(coherence): rule peak_ram_exceeds_allocated + pastille in CapacityPlanning"
```

---

## Task 7: Rule `running_count_parity` + pastille on Overview StatCard

**Goal:** Detect REST/WS desync between `capacity.running_jobs` and the list count; pastille next to "En cours" StatCard.

**Files:**
- Create: `src/coherence/rules/running_count_parity.js`
- Create: `src/coherence/rules/running_count_parity.test.js`
- Modify: `src/coherence/rules/index.js`
- Modify: `src/pages/Overview.jsx` (pastille near "En cours" StatCard)

**Acceptance Criteria:**
- [ ] Rule returns `[]` when counts match (within ±1 tolerance)
- [ ] Rule returns violation when abs(diff) > 1
- [ ] Rule has `autoRetry` config with `['capacity']` and `['jobs']` keys
- [ ] Pastille appears next to the "En cours" stat card value

**Verify:** `yarn test src/coherence/rules/running_count_parity.test.js` → all green

**Steps:**

- [ ] **Step 1: Write the rule**

```js
// apps-microservices/crawler-monitor-frontend/src/coherence/rules/running_count_parity.js
/** @type {import('../types').Rule} */
const rule = {
  id: 'running_count_parity',
  label: 'Parité running jobs REST/UI',
  description:
    'capacity.running_jobs (REST) doit correspondre au nombre de jobs ' +
    'status=running dans la liste. Un écart > 1 indique une désync REST qui ' +
    'devrait se résoudre au prochain refetch.',
  severity: 'info',
  sources: ['capacity', 'jobs'],
  attachUiHint: { path: '/', label: 'Vue d\'ensemble · StatCard En cours' },
  evaluate: ({ capacity, jobs }) => {
    if (capacity?.running_jobs == null || !jobs) return [];
    const backendRunning = capacity.running_jobs;
    const listRunning = jobs.filter((j) => j?.status === 'running').length;
    if (backendRunning === listRunning) return [];
    if (Math.abs(backendRunning - listRunning) <= 1) return []; // race tolerance
    return [
      {
        message: `CapacityBar indique ${backendRunning} jobs en cours, la liste en affiche ${listRunning} — désync REST`,
        data: {
          backendRunning,
          listRunning,
          diff: backendRunning - listRunning,
        },
      },
    ];
  },
  autoRetry: {
    maxAttempts: 2,
    delayMs: 3000,
    invalidate: [['capacity'], ['jobs']],
  },
};

export default rule;
```

- [ ] **Step 2: Write the tests**

```js
// apps-microservices/crawler-monitor-frontend/src/coherence/rules/running_count_parity.test.js
import { describe, it, expect } from 'vitest';
import rule from './running_count_parity';
import { mkJob } from '../__fixtures__/mocks';

describe('running_count_parity', () => {
  it('returns [] when counts match exactly', () => {
    const capacity = { running_jobs: 3 };
    const jobs = [mkJob('a'), mkJob('b'), mkJob('c')];
    expect(rule.evaluate({ capacity, jobs })).toEqual([]);
  });

  it('returns [] within ±1 tolerance', () => {
    const capacity = { running_jobs: 3 };
    const jobs = [mkJob('a'), mkJob('b'), mkJob('c'), mkJob('d')];
    expect(rule.evaluate({ capacity, jobs })).toEqual([]);
  });

  it('flags mismatch beyond tolerance', () => {
    const capacity = { running_jobs: 5 };
    const jobs = [mkJob('a'), mkJob('b')];
    const result = rule.evaluate({ capacity, jobs });
    expect(result).toHaveLength(1);
    expect(result[0].data).toEqual({ backendRunning: 5, listRunning: 2, diff: 3 });
  });

  it('returns [] when capacity is missing', () => {
    expect(rule.evaluate({ capacity: null, jobs: [mkJob('a')] })).toEqual([]);
    expect(rule.evaluate({ capacity: {}, jobs: [mkJob('a')] })).toEqual([]);
  });

  it('returns [] when jobs is missing', () => {
    expect(rule.evaluate({ capacity: { running_jobs: 3 }, jobs: null })).toEqual([]);
  });

  it('ignores non-running jobs', () => {
    const capacity = { running_jobs: 1 };
    const jobs = [
      mkJob('running1', { status: 'running' }),
      mkJob('finished1', { status: 'finished' }),
      mkJob('failed1', { status: 'failed' }),
    ];
    // backend=1, listRunning=1 → OK
    expect(rule.evaluate({ capacity, jobs })).toEqual([]);
  });

  it('has autoRetry configured with both query keys', () => {
    expect(rule.autoRetry).toBeDefined();
    expect(rule.autoRetry.maxAttempts).toBe(2);
    expect(rule.autoRetry.invalidate).toEqual([['capacity'], ['jobs']]);
  });
});
```

- [ ] **Step 3: Register the rule**

Update `src/coherence/rules/index.js`:

```js
import replicasVsMaxSlots from './replicas_vs_max_slots';
import replicaJobMapping from './replica_job_mapping';
import peakRamExceedsAllocated from './peak_ram_exceeds_allocated';
import runningCountParity from './running_count_parity';

/** @type {import('../types').Rule[]} */
export const RULES = [
  replicasVsMaxSlots,
  replicaJobMapping,
  peakRamExceedsAllocated,
  runningCountParity,
];
```

- [ ] **Step 4: Wire pastille into Overview**

In `src/pages/Overview.jsx`, locate the KPI row with StatCards:

```jsx
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <StatCard title="Total"    value={globalStats.total}    icon={Server}      variant="default" />
        <StatCard title="Succès"   value={globalStats.finished} icon={CheckCircle} variant="success" />
        <StatCard title="Échecs"   value={globalStats.failed}   icon={XCircle}     variant="destructive" />
        <StatCard title="En cours" value={globalStats.running}  icon={Zap}         variant="info" />
        <StatCard title="Archivés" value={globalStats.archived} icon={Archive}     variant="default" />
      </div>
```

Add the import at the top:

```jsx
import { CoherencePastille } from '../coherence/components/CoherencePastille';
```

Wrap the "En cours" StatCard to overlay the pastille. Since StatCard does not accept a trailing child, create a small wrapper via `div`:

```jsx
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <StatCard title="Total"    value={globalStats.total}    icon={Server}      variant="default" />
        <StatCard title="Succès"   value={globalStats.finished} icon={CheckCircle} variant="success" />
        <StatCard title="Échecs"   value={globalStats.failed}   icon={XCircle}     variant="destructive" />
        <div className="relative">
          <StatCard title="En cours" value={globalStats.running} icon={Zap} variant="info" />
          <div className="absolute right-2 top-2">
            <CoherencePastille ruleId="running_count_parity" />
          </div>
        </div>
        <StatCard title="Archivés" value={globalStats.archived} icon={Archive}     variant="default" />
      </div>
```

- [ ] **Step 5: Run tests**

```bash
yarn test src/coherence/
```

Expected: all tests pass (26+)

- [ ] **Step 6: Commit**

```bash
git add \
  apps-microservices/crawler-monitor-frontend/src/coherence/rules/running_count_parity.js \
  apps-microservices/crawler-monitor-frontend/src/coherence/rules/running_count_parity.test.js \
  apps-microservices/crawler-monitor-frontend/src/coherence/rules/index.js \
  apps-microservices/crawler-monitor-frontend/src/pages/Overview.jsx
git commit -m "feat(coherence): rule running_count_parity + pastille on Overview StatCard"
```

---

## Task 8: Page `/health` + sidebar entry

**Goal:** Ship the diagnostic page listing all rules with their state, violation details, and hash-scroll support. Add entry in sidebar.

**Files:**
- Create: `src/coherence/components/CoherenceHealthPage.jsx`
- Create: `src/coherence/components/CoherenceHealthPage.test.jsx`
- Modify: `src/lib/navigation.js` (add `/health` entry)
- Modify: `src/App.jsx` (add lazy import + Route)

**Acceptance Criteria:**
- [ ] Page renders at `/health`
- [ ] Shows KPI row: total, warning, critical, OK counts
- [ ] "Violations" section expands by default, "OK" collapses
- [ ] Each rule card shows id, label, severity, source, message, data
- [ ] Hash `#rule-<id>` scrolls to + highlights the card for 2s
- [ ] Sidebar shows new "Santé système" entry under Opérations

**Verify:**
- `yarn test src/coherence/components/CoherenceHealthPage.test.jsx` → all green
- Manual: `yarn dev`, navigate to `/health` via sidebar — page renders

**Steps:**

- [ ] **Step 1: Write the page component**

```jsx
// apps-microservices/crawler-monitor-frontend/src/coherence/components/CoherenceHealthPage.jsx
import { useEffect, useRef, useState } from 'react';
import { useLocation, Link } from 'react-router-dom';
import { HeartPulse, AlertTriangle, AlertCircle, Info, CheckCircle, ChevronDown, ChevronRight } from 'lucide-react';
import { Card } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { cn } from '../../lib/utils';
import { useCoherenceSummary } from '../hooks';
import { RULES } from '../rules';

const SEVERITY_ICON = {
  info: Info,
  warning: AlertTriangle,
  critical: AlertCircle,
};

const SEVERITY_COLOR = {
  info: 'text-info border-info/40 bg-info/5',
  warning: 'text-warning border-warning/40 bg-warning/5',
  critical: 'text-destructive border-destructive/40 bg-destructive/5',
};

export default function CoherenceHealthPage() {
  const { hash } = useLocation();
  const { verdicts, ignoredRules, setIgnored, byStatus, total, lastEvaluatedAt } =
    useCoherenceSummary();
  const [showOk, setShowOk] = useState(false);
  const highlightRef = useRef(null);

  // Hash scroll + 2s highlight ring
  useEffect(() => {
    if (!hash) return;
    const id = hash.replace('#', '');
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    el.classList.add('ring-2', 'ring-ring');
    const t = setTimeout(() => {
      el.classList.remove('ring-2', 'ring-ring');
    }, 2000);
    return () => clearTimeout(t);
  }, [hash]);

  // Categorize rules: violated, ok, ignored
  const violated = [];
  const ok = [];
  const ignored = [];
  for (const rule of RULES) {
    if (ignoredRules.has(rule.id)) {
      ignored.push(rule);
    } else if ((verdicts[rule.id] ?? []).length > 0) {
      violated.push(rule);
    } else {
      ok.push(rule);
    }
  }

  const copyContext = (rule, rviolations) => {
    const payload = {
      ruleId: rule.id,
      label: rule.label,
      severity: rule.severity,
      violations: rviolations,
      timestamp: new Date().toISOString(),
      url: window.location.href,
      userAgent: navigator.userAgent,
    };
    navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
  };

  return (
    <div ref={highlightRef} className="p-4 space-y-4">
      <Card className="p-4">
        <div className="flex items-center gap-3">
          <HeartPulse className="h-5 w-5 text-primary" />
          <div>
            <h1 className="text-base font-semibold">Cohérence des données</h1>
            <p className="text-xs text-muted-foreground font-mono">
              {total} règles · évalué il y a {Math.max(0, Math.round((Date.now() - lastEvaluatedAt) / 1000))}s
            </p>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiBox label="Total" value={total} />
          <KpiBox label="Warning" value={byStatus.warning} cls="text-warning" />
          <KpiBox label="Critical" value={byStatus.critical} cls="text-destructive" />
          <KpiBox label="OK" value={ok.length} cls="text-success" />
        </div>
      </Card>

      {violated.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Violations ({violated.length})
          </h2>
          {violated.map((rule) => (
            <RuleViolationCard
              key={rule.id}
              rule={rule}
              violations={verdicts[rule.id] ?? []}
              onCopy={() => copyContext(rule, verdicts[rule.id] ?? [])}
              onIgnore={() => setIgnored(rule.id, true)}
            />
          ))}
        </div>
      )}

      <div className="space-y-3">
        <button
          type="button"
          onClick={() => setShowOk((s) => !s)}
          className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground"
        >
          {showOk ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          OK ({ok.length})
        </button>
        {showOk && (
          <ul className="space-y-1 text-sm">
            {ok.map((rule) => (
              <li key={rule.id} className="flex items-center gap-2 text-muted-foreground">
                <CheckCircle className="h-3.5 w-3.5 text-success" />
                <span className="font-mono">{rule.id}</span>
                <span>— {rule.label}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {ignored.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Ignorées ({ignored.length})
          </h2>
          <ul className="space-y-2">
            {ignored.map((rule) => (
              <li key={rule.id} className="flex items-center justify-between rounded-md border border-border bg-muted/30 px-3 py-2 text-sm">
                <span>
                  <span className="font-mono">{rule.id}</span> — {rule.label}
                </span>
                <Button variant="outline" size="sm" onClick={() => setIgnored(rule.id, false)}>
                  Réactiver
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function KpiBox({ label, value, cls = 'text-foreground' }) {
  return (
    <div className="rounded-md border border-border bg-muted/30 p-3">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={cn('font-mono text-2xl font-bold', cls)}>{value}</div>
    </div>
  );
}

function RuleViolationCard({ rule, violations, onCopy, onIgnore }) {
  const Icon = SEVERITY_ICON[rule.severity] ?? AlertTriangle;
  const color = SEVERITY_COLOR[rule.severity] ?? SEVERITY_COLOR.warning;
  return (
    <Card id={`rule-${rule.id}`} className={cn('p-4 border-2 transition-shadow', color)}>
      <div className="flex items-start gap-3">
        <Icon className="h-5 w-5 shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0 space-y-2">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-sm">{rule.id}</span>
              <span className="rounded bg-background/50 px-1.5 py-0.5 text-[10px] uppercase">
                {rule.severity}
              </span>
            </div>
            <div className="mt-0.5 font-semibold">{rule.label}</div>
            <div className="mt-1 text-xs text-muted-foreground">{rule.description}</div>
          </div>

          <div className="space-y-1">
            {violations.map((v, i) => (
              <div key={i} className="rounded bg-background/50 p-2 text-sm">
                {v.itemKey && <span className="font-mono text-xs text-muted-foreground">[{v.itemKey}] </span>}
                {v.message}
              </div>
            ))}
          </div>

          <div className="text-[11px] text-muted-foreground">
            Sources : {rule.sources.join(', ')}
          </div>

          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Button variant="outline" size="sm" onClick={onCopy}>📋 Copier contexte</Button>
            <Button variant="outline" size="sm" onClick={onIgnore}>🔕 Ignorer session</Button>
            {rule.attachUiHint && (
              <Button variant="outline" size="sm" asChild>
                <Link to={rule.attachUiHint.path}>↗ {rule.attachUiHint.label}</Link>
              </Button>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
```

- [ ] **Step 2: Write the smoke test**

```jsx
// apps-microservices/crawler-monitor-frontend/src/coherence/components/CoherenceHealthPage.test.jsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TooltipProvider } from '../../components/ui/tooltip';
import { CoherenceProvider } from '../CoherenceProvider';
import CoherenceHealthPage from './CoherenceHealthPage';
import { mkReplica } from '../__fixtures__/mocks';

const renderPage = ({ replicas = {}, capacity = null } = {}) => {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  if (capacity) qc.setQueryData(['capacity'], capacity);
  return render(
    <MemoryRouter initialEntries={['/health']}>
      <QueryClientProvider client={qc}>
        <TooltipProvider>
          <CoherenceProvider token="tok" replicas={replicas}>
            <CoherenceHealthPage />
          </CoherenceProvider>
        </TooltipProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
};

describe('CoherenceHealthPage', () => {
  it('renders header and KPI row', () => {
    renderPage();
    expect(screen.getByText(/Cohérence des données/i)).toBeInTheDocument();
    expect(screen.getByText(/règles ·/i)).toBeInTheDocument();
  });

  it('lists violating rule with its label and message', () => {
    renderPage({
      replicas: { r1: mkReplica('r1') },
      capacity: { max_global_jobs: 3, running_jobs: 0 },
    });
    expect(screen.getByText(/Replicas vs slots/i)).toBeInTheDocument();
    expect(screen.getByText(/3 slots configurés mais 1 replicas/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Update navigation.js**

```js
// apps-microservices/crawler-monitor-frontend/src/lib/navigation.js
import {
  LayoutDashboard, Globe, Mail, SlidersHorizontal, FileText, HeartPulse,
} from 'lucide-react';

export const NAV_ITEMS = [
  {
    section: 'Supervision',
    items: [
      { to: '/',                  label: 'Vue d\'ensemble',  icon: LayoutDashboard, description: 'KPI, timeline, replicas, liste des jobs' },
      { to: '/domains',           label: 'Domaines',         icon: Globe,            description: 'Activité agrégée par domaine crawlé' },
      { to: '/callbacks',         label: 'Callbacks',        icon: Mail,             description: 'Webhooks en échec à rejouer', badgeKey: 'failedCallbacks' },
    ],
  },
  {
    section: 'Opérations',
    items: [
      { to: '/capacity-planning', label: 'Capacity planning', icon: SlidersHorizontal, description: 'RAM allouée vs utilisée · dimensionnement' },
      { to: '/audit',             label: 'Journal d\'audit',  icon: FileText,          description: 'Historique des actions sensibles' },
      { to: '/health',            label: 'Santé système',     icon: HeartPulse,        description: 'Cohérence des données affichées' },
    ],
  },
];

const ROUTE_LABELS = {
  '/':                 'Vue d\'ensemble',
  '/domains':          'Domaines',
  '/callbacks':        'Callbacks',
  '/audit':            'Journal d\'audit',
  '/capacity-planning':'Capacity planning',
  '/health':           'Santé système',
};

export function resolveBreadcrumbs(pathname) {
  if (!pathname || pathname === '/') {
    return [{ label: 'Vue d\'ensemble' }];
  }
  const parts = pathname.split('/').filter(Boolean);
  const crumbs = [{ label: 'Vue d\'ensemble', to: '/' }];

  if (ROUTE_LABELS[pathname]) {
    crumbs.push({ label: ROUTE_LABELS[pathname] });
    return crumbs;
  }

  if (parts[0] === 'jobs' && parts[1]) {
    crumbs.push({ label: `Job ${parts[1].slice(0, 8)}`, to: `/jobs/${parts[1]}` });
    if (parts[2] === 'queue')   crumbs.push({ label: 'Queue' });
    if (parts[2] === 'dataset') crumbs.push({ label: 'Dataset' });
    if (parts[2] === 'replay')  crumbs.push({ label: 'Replay' });
    return crumbs;
  }

  if (parts[0] === 'domains' && parts[1]) {
    crumbs.push({ label: 'Domaines', to: '/domains' });
    crumbs.push({ label: decodeURIComponent(parts[1]) });
    return crumbs;
  }

  let acc = '';
  for (const p of parts) {
    acc += '/' + p;
    crumbs.push({ label: p, to: acc });
  }
  if (crumbs.length > 1) delete crumbs[crumbs.length - 1].to;
  return crumbs;
}

export const FLAT_NAV = NAV_ITEMS.flatMap(s => s.items);
```

- [ ] **Step 4: Add route in App.jsx**

In `src/App.jsx`, add the lazy import near the others:

```jsx
const CoherenceHealthPage = lazy(() => import('./coherence/components/CoherenceHealthPage'));
```

And add the route inside `<Routes>`, just before the fallback `<Route path="*" .../>`:

```jsx
          <Route path="/health" element={<CoherenceHealthPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
```

- [ ] **Step 5: Run tests**

```bash
yarn test src/coherence/
```

Expected: all tests pass, including 2 new smoke tests for the page.

- [ ] **Step 6: Browser smoke test**

```bash
yarn dev
```

1. Login, go to `http://localhost:5173/health` — page renders with 4 rules.
2. Check sidebar — "Santé système" entry visible under Opérations.
3. If a pastille is visible somewhere, click it → navigates to `/health#rule-<id>`, card highlighted 2s.

- [ ] **Step 7: Commit**

```bash
git add \
  apps-microservices/crawler-monitor-frontend/src/coherence/components/CoherenceHealthPage.jsx \
  apps-microservices/crawler-monitor-frontend/src/coherence/components/CoherenceHealthPage.test.jsx \
  apps-microservices/crawler-monitor-frontend/src/lib/navigation.js \
  apps-microservices/crawler-monitor-frontend/src/App.jsx
git commit -m "feat(coherence): /health page + sidebar entry"
```

---

## Task 9: Auto-retry engine + manual actions wiring

**Goal:** Wire the auto-retry mechanism inside CoherenceProvider (opt-in via rule's `autoRetry` field), expose manual refresh/retry actions on `/health`, add "Refresh" button per rule card when applicable.

**Files:**
- Modify: `src/coherence/CoherenceProvider.jsx` (add retry state + effect)
- Modify: `src/coherence/CoherenceProvider.test.jsx` (add timer tests)
- Modify: `src/coherence/components/CoherenceHealthPage.jsx` (add "Refresh" button + "retry N/M" chip)

**Acceptance Criteria:**
- [ ] When a rule with `autoRetry` is violated, `queryClient.invalidateQueries` is called after `delayMs`
- [ ] Max `maxAttempts` retries per rule per violation streak
- [ ] Retry count resets when violation disappears
- [ ] Manual refresh button on `/health` invokes the invalidation immediately
- [ ] "🔁 N/M refetch sans effet" chip after max attempts
- [ ] Tests use `vi.useFakeTimers` to verify scheduling

**Verify:**
- `yarn test src/coherence/CoherenceProvider.test.jsx` → all green including timer tests
- Manual: `yarn dev`, trigger a `running_count_parity` violation artificially (DevTools), observe auto-retry in Network tab

**Steps:**

- [ ] **Step 1: Update CoherenceProvider with retry state + effect**

Replace the placeholder `retryState = {}` + `manualRetry` in `src/coherence/CoherenceProvider.jsx` with real logic. The full updated provider:

```jsx
// apps-microservices/crawler-monitor-frontend/src/coherence/CoherenceProvider.jsx
import { createContext, useMemo, useState, useCallback, useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  useJobsQuery,
  useCapacityQuery,
  useCapacityPlanningQuery,
} from '../hooks/queries';
import { RULES } from './rules';

export const CoherenceContext = createContext(null);

function runRules(sources) {
  const result = {};
  for (const rule of RULES) {
    try {
      const v = rule.evaluate(sources);
      result[rule.id] = Array.isArray(v) ? v : [];
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error(`[coherence] rule ${rule.id} threw:`, err);
      result[rule.id] = [];
    }
  }
  return result;
}

export function CoherenceProvider({ token, replicas, children }) {
  const queryClient = useQueryClient();
  const jobsQuery = useJobsQuery(token);
  const capacityQuery = useCapacityQuery(token);
  const capacityPlanningQuery = useCapacityPlanningQuery(token, '1h');

  const sources = useMemo(
    () => ({
      replicas: replicas || {},
      jobs: jobsQuery.data ?? null,
      capacity: capacityQuery.data ?? null,
      capacityPlanning: capacityPlanningQuery.data ?? null,
    }),
    [replicas, jobsQuery.data, capacityQuery.data, capacityPlanningQuery.data],
  );

  const verdicts = useMemo(() => runRules(sources), [sources]);

  const [ignoredRules, setIgnoredRules] = useState(() => new Set());
  const setIgnored = useCallback((ruleId, value) => {
    setIgnoredRules((prev) => {
      const next = new Set(prev);
      if (value) next.add(ruleId);
      else next.delete(ruleId);
      return next;
    });
  }, []);

  // retryState: { [ruleId]: { attempts, lastTriedAt, exhausted } }
  const [retryState, setRetryState] = useState({});
  const timersRef = useRef({}); // ruleId -> timerId

  // Invalidate queries listed in rule.autoRetry.invalidate
  const invalidateFor = useCallback(
    (rule) => {
      if (!rule?.autoRetry?.invalidate) return;
      for (const key of rule.autoRetry.invalidate) {
        queryClient.invalidateQueries({ queryKey: key });
      }
    },
    [queryClient],
  );

  // Auto-retry effect: watches verdicts, schedules retries for violated rules
  // with autoRetry and not yet exhausted / ignored.
  useEffect(() => {
    for (const rule of RULES) {
      if (!rule.autoRetry) continue;
      if (ignoredRules.has(rule.id)) continue;

      const violated = (verdicts[rule.id] ?? []).length > 0;
      const state = retryState[rule.id] ?? { attempts: 0, lastTriedAt: 0, exhausted: false };

      if (!violated) {
        // Healed — reset retry state for this rule (if we have any)
        if (state.attempts > 0 || state.exhausted) {
          if (timersRef.current[rule.id]) {
            clearTimeout(timersRef.current[rule.id]);
            delete timersRef.current[rule.id];
          }
          setRetryState((prev) => {
            if (!prev[rule.id]) return prev;
            const next = { ...prev };
            delete next[rule.id];
            return next;
          });
        }
        continue;
      }

      // Violated. If exhausted or timer already pending, do nothing.
      if (state.exhausted) continue;
      if (timersRef.current[rule.id]) continue;

      // Schedule a retry after delayMs
      const timerId = setTimeout(() => {
        delete timersRef.current[rule.id];
        invalidateFor(rule);
        setRetryState((prev) => {
          const prior = prev[rule.id] ?? { attempts: 0, lastTriedAt: 0, exhausted: false };
          const attempts = prior.attempts + 1;
          const exhausted = attempts >= rule.autoRetry.maxAttempts;
          return { ...prev, [rule.id]: { attempts, lastTriedAt: Date.now(), exhausted } };
        });
      }, rule.autoRetry.delayMs);
      timersRef.current[rule.id] = timerId;
    }
    // Cleanup timers on unmount
    return () => {
      for (const id of Object.values(timersRef.current)) clearTimeout(id);
      timersRef.current = {};
    };
  }, [verdicts, ignoredRules, invalidateFor, retryState]);

  // Manual retry: user clicks "Refresh" in /health — bypasses delay, invalidates now.
  const manualRetry = useCallback(
    (ruleId) => {
      const rule = RULES.find((r) => r.id === ruleId);
      if (!rule) return;
      invalidateFor(rule);
      setRetryState((prev) => {
        const prior = prev[ruleId] ?? { attempts: 0, lastTriedAt: 0, exhausted: false };
        return {
          ...prev,
          [ruleId]: { ...prior, lastTriedAt: Date.now(), exhausted: false },
        };
      });
    },
    [invalidateFor],
  );

  const byStatus = useMemo(() => {
    let info = 0, warning = 0, critical = 0;
    for (const rule of RULES) {
      if (ignoredRules.has(rule.id)) continue;
      const hasViolation = (verdicts[rule.id] ?? []).length > 0;
      if (!hasViolation) continue;
      if (rule.severity === 'critical') critical += 1;
      else if (rule.severity === 'warning') warning += 1;
      else info += 1;
    }
    return { info, warning, critical };
  }, [verdicts, ignoredRules]);

  const total = RULES.length;
  const lastEvaluatedAt = Date.now();

  const value = useMemo(
    () => ({
      verdicts,
      ignoredRules,
      setIgnored,
      byStatus,
      total,
      lastEvaluatedAt,
      retryState,
      manualRetry,
    }),
    [verdicts, ignoredRules, setIgnored, byStatus, total, lastEvaluatedAt, retryState, manualRetry],
  );

  return (
    <CoherenceContext.Provider value={value}>
      {children}
    </CoherenceContext.Provider>
  );
}
```

- [ ] **Step 2: Add timer tests to the provider test file**

Append to `src/coherence/CoherenceProvider.test.jsx`:

```jsx
import { vi } from 'vitest';

describe('CoherenceProvider autoRetry', () => {
  it('schedules invalidate after delayMs on violation', async () => {
    vi.useFakeTimers();
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    const spy = vi.spyOn(qc, 'invalidateQueries');
    qc.setQueryData(['capacity'], { running_jobs: 5 });
    qc.setQueryData(['jobs'], [
      { id: 'a', status: 'running' },
      { id: 'b', status: 'running' },
    ]);
    // 5 vs 2 → running_count_parity violates (diff=3 > 1 tolerance)

    const Wrapper = ({ children }) => (
      <QueryClientProvider client={qc}>
        <CoherenceProvider token="tok" replicas={{}}>
          {children}
        </CoherenceProvider>
      </QueryClientProvider>
    );

    const { result } = renderHook(() => useCoherenceSummary(), { wrapper: Wrapper });

    // At mount: no invalidate yet
    expect(spy).not.toHaveBeenCalled();
    // Fast-forward 3000ms (delayMs)
    await act(async () => {
      vi.advanceTimersByTime(3000);
    });
    // Should have called invalidate for capacity AND jobs (running_count_parity.autoRetry.invalidate)
    const calledKeys = spy.mock.calls.map((c) => c[0].queryKey);
    expect(calledKeys).toContainEqual(['capacity']);
    expect(calledKeys).toContainEqual(['jobs']);
    expect(result.current.retryState.running_count_parity?.attempts).toBe(1);
    vi.useRealTimers();
  });

  it('stops retrying after maxAttempts', async () => {
    vi.useFakeTimers();
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    qc.setQueryData(['capacity'], { running_jobs: 5 });
    qc.setQueryData(['jobs'], [{ id: 'a', status: 'running' }]);

    const Wrapper = ({ children }) => (
      <QueryClientProvider client={qc}>
        <CoherenceProvider token="tok" replicas={{}}>
          {children}
        </CoherenceProvider>
      </QueryClientProvider>
    );
    const { result } = renderHook(() => useCoherenceSummary(), { wrapper: Wrapper });

    // Advance enough for 3 tick cycles (only 2 should run, maxAttempts=2)
    await act(async () => { vi.advanceTimersByTime(3000); });
    await act(async () => { vi.advanceTimersByTime(3000); });
    await act(async () => { vi.advanceTimersByTime(3000); });

    expect(result.current.retryState.running_count_parity?.exhausted).toBe(true);
    expect(result.current.retryState.running_count_parity?.attempts).toBe(2);
    vi.useRealTimers();
  });
});
```

- [ ] **Step 3: Update /health page with retry chip + manual refresh button**

In `src/coherence/components/CoherenceHealthPage.jsx`, update the `RuleViolationCard` component to show retry state and Refresh button:

Replace the `RuleViolationCard` function with:

```jsx
function RuleViolationCard({ rule, violations, retryState, onCopy, onIgnore, onManualRetry }) {
  const Icon = SEVERITY_ICON[rule.severity] ?? AlertTriangle;
  const color = SEVERITY_COLOR[rule.severity] ?? SEVERITY_COLOR.warning;
  const rs = retryState ?? { attempts: 0, exhausted: false };
  const canRefresh = !!rule.autoRetry;

  return (
    <Card id={`rule-${rule.id}`} className={cn('p-4 border-2 transition-shadow', color)}>
      <div className="flex items-start gap-3">
        <Icon className="h-5 w-5 shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0 space-y-2">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-sm">{rule.id}</span>
              <span className="rounded bg-background/50 px-1.5 py-0.5 text-[10px] uppercase">
                {rule.severity}
              </span>
              {rs.exhausted && (
                <span className="rounded bg-background/50 px-1.5 py-0.5 text-[10px] font-mono">
                  🔁 {rs.attempts}/{rule.autoRetry.maxAttempts} refetch sans effet
                </span>
              )}
              {!rs.exhausted && rs.attempts > 0 && (
                <span className="rounded bg-background/50 px-1.5 py-0.5 text-[10px] font-mono">
                  🔁 retry {rs.attempts}/{rule.autoRetry.maxAttempts}
                </span>
              )}
            </div>
            <div className="mt-0.5 font-semibold">{rule.label}</div>
            <div className="mt-1 text-xs text-muted-foreground">{rule.description}</div>
          </div>

          <div className="space-y-1">
            {violations.map((v, i) => (
              <div key={i} className="rounded bg-background/50 p-2 text-sm">
                {v.itemKey && <span className="font-mono text-xs text-muted-foreground">[{v.itemKey}] </span>}
                {v.message}
              </div>
            ))}
          </div>

          <div className="text-[11px] text-muted-foreground">
            Sources : {rule.sources.join(', ')}
          </div>

          <div className="flex flex-wrap items-center gap-2 pt-1">
            {canRefresh && (
              <Button variant="outline" size="sm" onClick={onManualRetry}>🔄 Rafraîchir</Button>
            )}
            <Button variant="outline" size="sm" onClick={onCopy}>📋 Copier contexte</Button>
            <Button variant="outline" size="sm" onClick={onIgnore}>🔕 Ignorer session</Button>
            {rule.attachUiHint && (
              <Button variant="outline" size="sm" asChild>
                <Link to={rule.attachUiHint.path}>↗ {rule.attachUiHint.label}</Link>
              </Button>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
```

And update the render of violated cards in `CoherenceHealthPage` (it already passes other props; now add `retryState` and `onManualRetry`):

```jsx
  const { verdicts, ignoredRules, setIgnored, byStatus, total, lastEvaluatedAt, retryState, manualRetry } =
    useCoherenceSummary();
```

```jsx
          {violated.map((rule) => (
            <RuleViolationCard
              key={rule.id}
              rule={rule}
              violations={verdicts[rule.id] ?? []}
              retryState={retryState[rule.id]}
              onCopy={() => copyContext(rule, verdicts[rule.id] ?? [])}
              onIgnore={() => setIgnored(rule.id, true)}
              onManualRetry={() => manualRetry(rule.id)}
            />
          ))}
```

- [ ] **Step 4: Run all tests**

```bash
yarn test src/coherence/
```

Expected: all tests pass, including the 2 new timer tests.

- [ ] **Step 5: Browser smoke**

```bash
yarn dev
```

1. Trigger a `running_count_parity` violation via DevTools React Query Devtools:
   - Set `capacity` data `running_jobs: 99`
   - Keep `jobs` as-is (likely a few running)
   - Violation should appear on `/health`
2. Click "🔄 Rafraîchir" — Network tab shows both capacity and jobs endpoints refetch.
3. Chip "🔁 retry X/2" appears after 3s if violation persists.

- [ ] **Step 6: Commit**

```bash
git add \
  apps-microservices/crawler-monitor-frontend/src/coherence/CoherenceProvider.jsx \
  apps-microservices/crawler-monitor-frontend/src/coherence/CoherenceProvider.test.jsx \
  apps-microservices/crawler-monitor-frontend/src/coherence/components/CoherenceHealthPage.jsx
git commit -m "feat(coherence): auto-retry engine + manual refresh/ignore actions on /health"
```

---

## Summary of deliverables

After all 9 tasks:

- `src/coherence/` module created with 4 rules, provider, hooks, 2 components
- ~28 tests passing (unit + integration + smoke)
- Inline pastilles on: CapacityBar, ReplicaMonitor, CapacityPlanning table, Overview StatCard
- `/health` page with KPI row, violation cards, OK/Ignored sections, manual actions
- Auto-retry opt-in on 2 of 4 rules with timer-based retry + manual refresh
- Sidebar entry "Santé système"
- Zero backend changes
- `yarn test` now runs Vitest with ~28 passing tests

Each task produces a commit; the branch gains 9 commits on `features/refont-crawler-monitoring`.
