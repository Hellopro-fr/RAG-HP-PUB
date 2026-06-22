/**
 * Tier-1 observer for limitQuestionMark.
 *
 * Phase 1: observation only (records domain-specific param frequency + samples).
 * Phase 1.5: persists observations to {storage_path}/_questionmark_observations.json
 *            at crawl end, so offline audits can read per-param frequency without
 *            URL replay. Schema is forward-compatible with phase-2 tier-2 state.
 * Phase 2 (deferred) will add content comparison + toRemove commits.
 *
 * See docs/superpowers/specs/2026-04-17-limitquestionmark-auto-decision-design.md.
 */

import fs from "node:fs";
import path from "node:path";
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
export const getQuestionMarkDecisionMode = (
    isError?: string
): "escalated" | "defaulted-bypassed" | "tier2-resolved" | "observed" | "unused" => {
    if (isError === "limitQuestionMark") return "escalated";
    if (!context.questionMarkObservationEnabled) return "unused";
    if (context.qmTier2.defaulted) return "defaulted-bypassed";
    if (context.qmTier2.addedToRemove.length > 0) return "tier2-resolved";
    if (context.questionMarkObservations.domainSpecificCount === 0) return "unused";
    return "observed";
};

const QM_DECISION_FILE = "_questionmark_decision.json";

/**
 * Persist the tier-2 per-param decision (atomic tmp+fsync+rename) on every commit
 * and on default. Reflects the latest cumulative state.
 */
export const writeQmDecisionFile = (storagePath: string, source: "tier2" | "defaulted"): void => {
    try {
        const t = context.qmTier2;
        const pairStats: Record<string, { same: number; different: number; unusable: number }> = {};
        for (const [p, s] of t.tally) pairStats[p] = s;
        const deferred = Array.from(t.tally.keys()).filter((p) => !t.decided.has(p));
        const payload = {
            addedToRemove: t.addedToRemove,
            contentShaping: t.contentShaping,
            deferred,
            pairStats,
            source,
            committedAt: new Date().toISOString(),
        };
        const finalPath = path.join(storagePath, QM_DECISION_FILE);
        const tmpPath = `${finalPath}.tmp`;
        fs.writeFileSync(tmpPath, JSON.stringify(payload, null, 2));
        const fd = fs.openSync(tmpPath, "r+");
        try { fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
        fs.renameSync(tmpPath, finalPath);
    } catch (e) {
        console.warn(`[questionmark] Failed to persist decision: ${(e as Error).message}`);
    }
};

/**
 * At startup, merge a previously committed addedToRemove into context.config.toRemove
 * (dedupe, case-insensitive), so OOM_RELAUNCH resumes with resolved params stripped.
 * Returns true if a decision file was loaded.
 */
export const readQmPersistedDecision = (storagePath: string): boolean => {
    const filePath = path.join(storagePath, QM_DECISION_FILE);
    if (!fs.existsSync(filePath)) return false;
    try {
        const payload = JSON.parse(fs.readFileSync(filePath, "utf-8")) as { addedToRemove?: string[] };
        const added = Array.isArray(payload.addedToRemove) ? payload.addedToRemove : [];
        const present = new Set(context.config.toRemove.map((s) => s.toLowerCase()));
        for (const p of added) {
            if (!present.has(p.toLowerCase())) {
                context.config.toRemove.push(p);
                present.add(p.toLowerCase());
            }
        }
        console.log(`[questionmark] Loaded persisted decision: addedToRemove=${JSON.stringify(added)}`);
        return true;
    } catch (e) {
        console.warn(`[questionmark] Failed to parse ${filePath}: ${(e as Error).message}`);
        return false;
    }
};

const OBSERVATIONS_FILE = "_questionmark_observations.json";

/**
 * Serialize the tier-1 observer state to {storage_path}/_questionmark_observations.json.
 *
 * Called from main.ts gracefulShutdown after _callback_payload.json has been written.
 * Self-contained: never throws — failure is logged but does not propagate, so a
 * sidecar write error cannot poison the crawl-end critical path.
 *
 * Atomic via tmp + rename (mirrors the _callback_payload.json fsync pattern at the
 * caller). Schema is intentionally a strict superset of what audit scripts read:
 *   { paramFrequency: { name: count }, samplesByParam: { name: [url, ...] },
 *     domainSpecificCount: number, persistedAt: ISO-8601 }
 */
export const persistObservations = (storagePath: string): void => {
    try {
        const obs = context.questionMarkObservations;
        const payload = {
            paramFrequency: Object.fromEntries(obs.paramFrequency),
            samplesByParam: Object.fromEntries(obs.samplesByParam),
            domainSpecificCount: obs.domainSpecificCount,
            persistedAt: new Date().toISOString(),
        };

        const finalPath = path.join(storagePath, OBSERVATIONS_FILE);
        const tmpPath = `${finalPath}.tmp`;

        fs.writeFileSync(tmpPath, JSON.stringify(payload, null, 2));
        // Open the tmp file r+ rather than r so fsync is permitted on Windows
        // (Windows rejects fsync on read-only handles; POSIX tolerates it).
        const fd = fs.openSync(tmpPath, "r+");
        try { fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
        fs.renameSync(tmpPath, finalPath);
    } catch (e) {
        console.warn(`[questionmark] Failed to persist observations: ${(e as Error).message}`);
    }
};
