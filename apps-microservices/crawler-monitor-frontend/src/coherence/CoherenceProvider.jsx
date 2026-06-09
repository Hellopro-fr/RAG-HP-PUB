import { createContext, useMemo, useState, useCallback, useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  useJobsQuery,
  useCapacityQuery,
  useCapacityPlanningQuery,
} from '../hooks/queries';
import { RULES } from './rules';

export const CoherenceContext = createContext(null);

// FIX A: évaluation découplée du flux 1 Hz (tick toutes les EVAL_INTERVAL_MS)
const EVAL_INTERVAL_MS = 5000;
// FIX B: une violation doit persister >= HYSTERESIS_MS avant d'être affichée
const HYSTERESIS_MS = 4000;

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

/**
 * Stable key for a single violation used by the hysteresis map.
 * Combines ruleId + itemKey (per-item rules) + kind/message to distinguish
 * violations of the same rule on different items.
 */
function violationKey(ruleId, violation) {
  return `${ruleId}|${violation.itemKey ?? ''}|${violation.data?.kind ?? violation.message}`;
}

/**
 * Deep-equality check for verdicts objects via a stable JSON projection.
 * Projects { ruleId: [{itemKey, message, data}][] } and compares as JSON.
 */
function verdictsEqual(a, b) {
  if (a === b) return true;
  const project = (v) =>
    Object.fromEntries(
      Object.entries(v).map(([ruleId, violations]) => [
        ruleId,
        violations.map((viol) => ({
          itemKey: viol.itemKey,
          message: viol.message,
          data: viol.data,
        })),
      ]),
    );
  try {
    return JSON.stringify(project(a)) === JSON.stringify(project(b));
  } catch {
    return false;
  }
}

export function CoherenceProvider({ token, replicas, children }) {
  const queryClient = useQueryClient();
  // Read sources from React Query caches. `useCapacityPlanningQuery` uses a
  // fixed '1h' window for coherence checks — the CapacityPlanning page uses
  // whatever window the user picks (separate cache key per window, no conflict).
  const jobsQuery = useJobsQuery(token);
  const capacityQuery = useCapacityQuery(token);
  const capacityPlanningQuery = useCapacityPlanningQuery(token, '1h');

  // FIX A: garde la dernière valeur de replicas dans un ref mis à jour à chaque render.
  // Cela permet à sources de ne lire replicas qu'au rythme du tick (pas au rythme 1 Hz).
  const replicasRef = useRef(replicas);
  replicasRef.current = replicas;

  // FIX A: tick incrémenté toutes les EVAL_INTERVAL_MS pour déclencher une réévaluation.
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const i = setInterval(() => setTick((t) => t + 1), EVAL_INTERVAL_MS);
    return () => clearInterval(i);
  }, []);

  // FIX A: sources dépend du tick (+ données REST qui, elles, peuvent changer
  // indépendamment du tick). replicasRef.current est lu à l'intérieur du memo
  // au moment du tick — pas en dep directe, pour rompre le couplage 1 Hz.
  const sources = useMemo(
    () => ({
      replicas: replicasRef.current || {},
      jobs: jobsQuery.data ?? null,
      capacity: capacityQuery.data ?? null,
      capacityPlanning: capacityPlanningQuery.data ?? null,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tick, jobsQuery.data, capacityQuery.data, capacityPlanningQuery.data],
  );

  // FIX B: hystérésis — une violation doit persister HYSTERESIS_MS avant affichage.
  // seenSinceRef: Map<clé, timestamp première observation continue>
  const seenSinceRef = useRef(new Map());

  // Calcule rawVerdicts puis applique l'hystérésis pour produire verdicts filtré.
  // prevVerdictsRef permet de stabiliser l'identité de l'objet verdicts exposé.
  const prevVerdictsRef = useRef({});

  const verdicts = useMemo(() => {
    const rawVerdicts = runRules(sources);
    const now = Date.now();
    const seenSince = seenSinceRef.current;

    // Collecte toutes les clés présentes dans rawVerdicts
    const presentKeys = new Set();
    for (const [ruleId, violations] of Object.entries(rawVerdicts)) {
      for (const v of violations) {
        presentKeys.add(violationKey(ruleId, v));
      }
    }

    // Enregistre les nouvelles violations, purge les disparues
    for (const key of seenSince.keys()) {
      if (!presentKeys.has(key)) seenSince.delete(key);
    }
    for (const key of presentKeys) {
      if (!seenSince.has(key)) seenSince.set(key, now);
    }

    // Filtre : ne garder que les violations persistantes (>= HYSTERESIS_MS)
    const filtered = {};
    for (const [ruleId, violations] of Object.entries(rawVerdicts)) {
      filtered[ruleId] = violations.filter((v) => {
        const key = violationKey(ruleId, v);
        const since = seenSince.get(key);
        return since !== undefined && now - since >= HYSTERESIS_MS;
      });
    }

    // FIX A (stabilisation): réutilise la référence précédente si le contenu est identique
    if (verdictsEqual(filtered, prevVerdictsRef.current)) {
      return prevVerdictsRef.current;
    }
    prevVerdictsRef.current = filtered;
    return filtered;
  }, [sources]);

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

  // FIX C: l'effet auto-retry référence verdicts stabilisé (post-hystérésis).
  // Avec verdicts stable, le cleanup n'annule plus le setTimeout chaque seconde.
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
  // Timestamp of last evaluation — recomputed when verdicts change (i.e. sources
  // changed and rules re-ran). Stable across unrelated re-renders.
  const lastEvaluatedAt = useMemo(() => Date.now(), [verdicts]);

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
