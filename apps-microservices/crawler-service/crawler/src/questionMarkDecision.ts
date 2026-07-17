/**
 * Tier-1 observer for limitQuestionMark.
 *
 * Phase 1: observation only (records domain-specific param frequency + samples).
 * Phase 2 (deferred) will add content comparison + toRemove commits.
 *
 * See docs/superpowers/specs/2026-04-17-limitquestionmark-auto-decision-design.md.
 */

import { context } from "./context.js";

const SAMPLE_CAP_PER_PARAM = 50;

/**
 * Record a URL's query parameters into the observation state.
 *
 * Called for every URL that is about to be (or has been) pushed to the Crawlee dataset,
 * post Tier-0 processing (after ALWAYS_REMOVE_PARAMS stripping). Only URLs that still
 * contain `?` at this stage carry domain-specific params — those are what we record.
 *
 * No-op when observation is disabled (human already set skipQuestionMark / bypassQuestionMark)
 * or the URL has no `?`.
 */
export const recordQuestionMarkObservation = (url: string): void => {
    if (!context.questionMarkObservationEnabled) return;
    const qIdx = url.indexOf("?");
    if (qIdx === -1) return;

    // Extract query string; strip fragment if present.
    let query = url.slice(qIdx + 1);
    const hashIdx = query.indexOf("#");
    if (hashIdx !== -1) query = query.slice(0, hashIdx);
    if (query.length === 0) return;

    // Iterate the param names without URL-decoding the whole URL (which could throw on
    // legitimately weird but non-malformed edges). Use URLSearchParams on the query only.
    let paramNames: string[];
    try {
        const sp = new URLSearchParams(query);
        paramNames = Array.from(new Set(sp.keys())); // dedupe repeated keys in same URL
    } catch {
        // Malformed query string — ignore this URL rather than throw in the hot path.
        return;
    }
    if (paramNames.length === 0) return;

    const obs = context.questionMarkObservations;
    obs.domainSpecificCount++;

    for (const name of paramNames) {
        obs.paramFrequency.set(name, (obs.paramFrequency.get(name) ?? 0) + 1);

        const samples = obs.samplesByParam.get(name);
        if (!samples) {
            obs.samplesByParam.set(name, [url]);
        } else if (samples.length < SAMPLE_CAP_PER_PARAM) {
            samples.push(url);
        }
        // else: silently drop additional samples beyond the cap
    }
};

/**
 * Called at crawler startup. If the human already set skipQuestionMark or bypassQuestionMark
 * via the data_crawling_dspi → CLI args chain, disable the observer for this run.
 * Respects explicit human choices (spec §9.3).
 */
export const applyCliFlagGuard = (): void => {
    if (context.config.skipQuestionMark || context.config.bypassQuestionMark) {
        context.questionMarkObservationEnabled = false;
        console.log(
            `[questionmark] CLI flag present (skipQuestionMark=${context.config.skipQuestionMark} bypassQuestionMark=${context.config.bypassQuestionMark}). Observer disabled.`
        );
    }
};

/**
 * Compute the questionMarkDecisionMode value for the _callback_payload.json.
 * Phase 1 values: "escalated" | "unused" | "observed".
 * Phase 2 will add "tier2-resolved" when content comparison commits params.
 */
export const getQuestionMarkDecisionMode = (isError?: string): "escalated" | "unused" | "observed" => {
    if (isError === "limitQuestionMark") return "escalated";
    if (!context.questionMarkObservationEnabled) return "unused";
    if (context.questionMarkObservations.domainSpecificCount === 0) return "unused";
    return "observed";
};
