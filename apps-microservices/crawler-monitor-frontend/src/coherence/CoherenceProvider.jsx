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
