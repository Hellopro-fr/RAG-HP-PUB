/**
 * Auto-decision engine for limitDiez.
 *
 * Phase 1: tier-1 only (URL-structure heuristic).
 * Tier 2 (content comparison via content-extractor) is deferred to phase 2.
 *
 * See docs/superpowers/specs/2026-04-17-limitdiez-auto-decision-design.md.
 */

import { classifyFragment } from "./diezClassify.js";
export { classifyFragment } from "./diezClassify.js";
export type { Classification } from "./diezClassify.js";

import { context } from "./context.js";

const MIN_SAMPLES = 5;
const MAX_SAMPLES = 100;
const CONFIDENCE_THRESHOLD = 0.9;
const AMBIGUOUS_PROMOTE_RATIO = 0.4;
const AMBIGUOUS_PROMOTE_MIN_TOTAL = 20;
const TIER2_SAMPLE_CAP = 50;

export type DecisionOutcome = "skipDiez" | "bypassDiez" | "promoteTier2" | "escalate" | null;

/**
 * Classify a URL (must contain '#') and record into the context counters.
 * No-op if the URL has no '#' or if a decision was already committed.
 */
export const recordClassification = (url: string): void => {
    if (context.diezDecisionCommitted) return;
    const hashIdx = url.indexOf("#");
    if (hashIdx === -1) return;
    const fragment = url.slice(hashIdx + 1);

    const classification = classifyFragment(fragment);
    context.diezClassification[classification]++;
    context.diezClassification.total++;

    if (classification === "ambiguous" && context.diezClassification.samplesForTier2.length < TIER2_SAMPLE_CAP) {
        context.diezClassification.samplesForTier2.push(url);
    }
};

/**
 * Inspect current counters and decide whether to commit a decision.
 *
 * Returns:
 *   "skipDiez"     — anchor confidence ≥ 90% (caller should flip skipDiez flag + rewrite queue)
 *   "bypassDiez"   — spa confidence ≥ 90% (caller should flip bypassDiez flag)
 *   "promoteTier2" — ambiguous ratio ≥ 40% at total ≥ 20 (phase 2 hook; phase 1 caller ignores)
 *   "escalate"     — reached MAX_SAMPLES with no confident decision (caller lets today's limitDiez fire)
 *   null           — keep collecting
 */
export const maybeCommitDecision = (): DecisionOutcome => {
    if (context.diezDecisionCommitted) return null;

    const c = context.diezClassification;
    if (c.total < MIN_SAMPLES) return null;

    const anchorRatio = c.anchor / c.total;
    const spaRatio = c.spa / c.total;
    const ambiguousRatio = c.ambiguous / c.total;

    if (anchorRatio >= CONFIDENCE_THRESHOLD) return "skipDiez";
    if (spaRatio >= CONFIDENCE_THRESHOLD) return "bypassDiez";

    if (ambiguousRatio >= AMBIGUOUS_PROMOTE_RATIO && c.total >= AMBIGUOUS_PROMOTE_MIN_TOTAL) {
        return "promoteTier2";
    }

    if (c.total >= MAX_SAMPLES) return "escalate";

    return null;
};

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const _require = createRequire(import.meta.url);

const DECISION_FILE = "_diez_decision.json";

interface DecisionMeta {
    tier?: 1 | 2;
    source?: "tier1" | "tier2" | "default";
    evidence?: { compared: number; matches: number; mismatches: number; unusable: number };
}

// Last committed source, for getDiezDecisionMode. In-memory; the durable record is _diez_decision.json.
let _committedSource: "tier1" | "tier2" | "default" = "tier1";

/**
 * Write the decision marker atomically (tmp → rename) with fsync before rename.
 * Ensures durability on power-loss / OOM-triggered restart.
 */
const writeDecisionFile = (
    storagePath: string,
    decision: "skipDiez" | "bypassDiez",
    meta: DecisionMeta = {},
): void => {
    const c = context.diezClassification;
    const payload = {
        decision,
        tier: meta.tier ?? 1,
        source: meta.source ?? "tier1",
        committedAt: new Date().toISOString(),
        counts: { anchor: c.anchor, spa: c.spa, ambiguous: c.ambiguous, total: c.total },
        evidence: meta.evidence ?? null,
    };
    const finalPath = path.join(storagePath, DECISION_FILE);
    const tmpPath = `${finalPath}.tmp`;
    fs.writeFileSync(tmpPath, JSON.stringify(payload, null, 2));
    // Open with "r+" (read-write) so fsyncSync has a writable fd on all platforms.
    const fd = fs.openSync(tmpPath, "r+");
    try { fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
    fs.renameSync(tmpPath, finalPath);
};

/**
 * Commit "anchor" decision: strip '#' from already-queued URLs and prevent
 * future limitDiez accounting by setting skipDiez = true.
 *
 * Idempotent: no-op when diezDecisionCommitted is already true.
 */
export const commitSkipDiez = (storagePath: string, meta: DecisionMeta = {}): void => {
    if (context.diezDecisionCommitted) return;
    const c = context.diezClassification;
    context.config.skipDiez = true;
    context.diezDecisionCommitted = true;
    _committedSource = meta.source ?? "tier1";
    writeDecisionFile(storagePath, "skipDiez", { tier: meta.tier ?? 1, source: meta.source ?? "tier1", evidence: meta.evidence });
    console.log(`[diez] Decision: skipDiez (source=${meta.source ?? "tier1"} anchor=${c.anchor} spa=${c.spa} ambiguous=${c.ambiguous} / total=${c.total})`);
    // Rewrite already-queued URLs to strip '#'. Lazy require avoids ESM circular dep at load time.
    try {
        const { parseJsonFiles, getAllRequestQueues } = _require("./functions.js");
        const queueName = context.config.crawleeStorageName;
        const queues: string[] = getAllRequestQueues(queueName);
        if (Array.isArray(queues) && queues.length > 0) {
            parseJsonFiles(queues, context.config.skipQuestionMark, true, { toKeep: context.config.toKeep, toRemove: context.config.toRemove });
            console.log(`[diez] Rewrote ${queues.length} queued request file(s) to strip '#'.`);
        }
    } catch (e) {
        console.warn(`[diez] Queue rewrite skipped: ${(e as Error).message}`);
    }
};

/**
 * Commit "spa" decision: keep '#' URLs as-is but stop the limitDiez counter
 * from triggering a stop by setting bypassDiez = true.
 *
 * Idempotent: no-op when diezDecisionCommitted is already true.
 */
export const commitBypassDiez = (storagePath: string, meta: DecisionMeta = {}): void => {
    if (context.diezDecisionCommitted) return;
    const c = context.diezClassification;
    context.config.bypassDiez = true;
    context.diezDecisionCommitted = true;
    _committedSource = meta.source ?? "tier1";
    writeDecisionFile(storagePath, "bypassDiez", { tier: meta.tier ?? 1, source: meta.source ?? "tier1", evidence: meta.evidence });
    console.log(`[diez] Decision: bypassDiez (source=${meta.source ?? "tier1"} anchor=${c.anchor} spa=${c.spa} ambiguous=${c.ambiguous} / total=${c.total})`);
};

/**
 * At crawl startup, check for a previously persisted decision and apply it.
 * Called from main.ts after process.chdir(storagePath).
 * Returns true if a decision was loaded and applied.
 */
export const readPersistedDecision = (storagePath: string): boolean => {
    const filePath = path.join(storagePath, DECISION_FILE);
    if (!fs.existsSync(filePath)) return false;

    try {
        const raw = fs.readFileSync(filePath, "utf-8");
        const payload = JSON.parse(raw) as { decision?: string; tier?: number; source?: string };
        // Restore the committed source so getDiezDecisionMode reports the true mode
        // (tier2-*/defaulted-*) after an OOM relaunch, not the "tier1" default.
        // Legacy files (pre-phase-2, no source field) fall back to "tier1".
        const source: "tier1" | "tier2" | "default" =
            payload.source === "tier2" || payload.source === "default" ? payload.source : "tier1";

        if (payload.decision === "skipDiez") {
            context.config.skipDiez = true;
            context.diezDecisionCommitted = true;
            _committedSource = source;
            console.log(`[diez] Loaded persisted decision: skipDiez (tier ${payload.tier ?? "?"}, source ${source})`);
            return true;
        }
        if (payload.decision === "bypassDiez") {
            context.config.bypassDiez = true;
            context.diezDecisionCommitted = true;
            _committedSource = source;
            console.log(`[diez] Loaded persisted decision: bypassDiez (tier ${payload.tier ?? "?"}, source ${source})`);
            return true;
        }

        console.warn(`[diez] Persisted decision file has unknown 'decision' value: ${payload.decision}`);
        return false;
    } catch (e) {
        console.warn(`[diez] Failed to parse ${filePath}: ${(e as Error).message}`);
        return false;
    }
};

/**
 * Called from main.ts startup. If CLI flags already set skipDiez or bypassDiez,
 * mark the decision as committed so recordClassification becomes a no-op.
 * Spec §4.0 activation guard.
 */
export const applyCliFlagGuard = (): void => {
    if (context.config.skipDiez || context.config.bypassDiez) {
        context.diezDecisionCommitted = true;
        console.log(
            `[diez] CLI flag present (skipDiez=${context.config.skipDiez} bypassDiez=${context.config.bypassDiez}). Tier 1 disabled.`
        );
    }
};

/**
 * Compute the diezDecisionMode to surface in _callback_payload.json.
 * Called at crawl end, after isError is finalized.
 *
 * Returns:
 *   "escalated"            — isError === "limitDiez" (Tier 3 fired, today's email path)
 *   "tier1-skipdiez"       — Tier 1 committed skipDiez during the crawl
 *   "tier1-bypassdiez"     — Tier 1 committed bypassDiez during the crawl
 *   "tier2-skipdiez"       — Tier 2 committed skipDiez during the crawl
 *   "tier2-bypassdiez"     — Tier 2 committed bypassDiez during the crawl
 *   "defaulted-bypassdiez" — default fallback committed bypassDiez
 *   "unused"               — crawl completed without needing a decision
 */
export const getDiezDecisionMode = (isError: string | undefined): string => {
    if (isError === "limitDiez") return "escalated";
    if (!context.diezDecisionCommitted) return "unused";
    const verb = context.config.skipDiez ? "skipdiez" : context.config.bypassDiez ? "bypassdiez" : "unused";
    if (verb === "unused") return "unused";
    if (_committedSource === "default") return "defaulted-bypassdiez";
    if (_committedSource === "tier2") return `tier2-${verb}`;
    return `tier1-${verb}`;
};
