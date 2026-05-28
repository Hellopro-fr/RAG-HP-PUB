/**
 * qmHashTracker — helper to mirror URL counters into StatsManager.
 *
 * Background:
 *   The crawler maintains local context counters (`countQuestionMark` /
 *   `countDiez`) for every URL it processes that contains `?` or `#`. These
 *   counters drive the `limitQuestionMark` / `limitDiez` stopping decisions
 *   (see questionMarkDecision.ts / diezDecision.ts).
 *
 *   Until this helper, those counters lived only in the in-process context —
 *   they were never mirrored into the Redis-backed StatsManager, so the
 *   `filtered_qm` and `filtered_hash` values exposed in the webhook payload
 *   were always 0 (or only populated by the narrow FORBIDDEN_PARAMS path in
 *   UpdateChecker, before that side-effect was removed).
 *
 *   Symptom: BO observability dashboard reported 0 for "URLs avec point
 *   d'interrogation (?)" and "URLs avec dièse (#)" despite hundreds of crawls
 *   hitting limitQuestionMark / limitDiez.
 *
 * Behaviour:
 *   For each call with a URL `u`:
 *     - if `u` contains '?' → `statsManager.increment("filtered_qm")`
 *     - if `u` contains '#' → `statsManager.increment("filtered_hash")`
 *   Both increments are fire-and-forget (`void`) to keep the hot path
 *   non-blocking. Errors are swallowed by the StatsManager implementation.
 *
 *   When `statsManager` is undefined (e.g. during unit tests or before
 *   manager init), the helper is a no-op — no crash, no increment.
 */

import type { StatsManager } from './class/StatsManager.js';

export function trackQmHashStatsForUrl(
    url: string,
    statsManager: StatsManager | undefined,
): void {
    if (!statsManager) {
        return;
    }
    if (url.includes('?')) {
        void statsManager.increment('filtered_qm');
    }
    if (url.includes('#')) {
        void statsManager.increment('filtered_hash');
    }
}
