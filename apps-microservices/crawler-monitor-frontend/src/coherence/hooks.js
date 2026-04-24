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
