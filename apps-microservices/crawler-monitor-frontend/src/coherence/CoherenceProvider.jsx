import { createContext, useMemo, useState, useCallback, useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
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
  const queryClient = useQueryClient();
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
