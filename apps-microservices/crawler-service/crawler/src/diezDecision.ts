/**
 * Auto-decision engine for limitDiez.
 *
 * Phase 1: tier-1 only (URL-structure heuristic).
 * Tier 2 (content comparison via content-extractor) is deferred to phase 2.
 *
 * See docs/superpowers/specs/2026-04-17-limitdiez-auto-decision-design.md.
 */

export type Classification = "anchor" | "spa" | "ambiguous";

/**
 * Classify a URL fragment (the part after `#`, caller already stripped it).
 * Pure function — no side effects, no context access.
 *
 * Rules applied top-to-bottom, first match wins:
 *   1. Empty → anchor
 *   2. Starts with `/` → spa
 *   3. Contains `/` anywhere → spa
 *   4. Has `&` + `=` or starts with `?` → spa
 *   5. HTML id convention (length ≤ 50, ^[a-zA-Z][a-zA-Z_-]*$) → anchor
 *   6. Short alphanumeric (length ≤ 20, ^[a-zA-Z0-9_-]+$) → anchor
 *   7. Anything else → ambiguous
 *
 * Before matching: URL-decode (decodeURIComponent), then strip one leading `!`.
 */
export const classifyFragment = (fragment: string): Classification => {
    let frag: string;
    try {
        frag = decodeURIComponent(fragment);
    } catch {
        // Malformed encoding — fall back to raw.
        frag = fragment;
    }
    if (frag.startsWith("!")) frag = frag.slice(1);

    if (frag.length === 0) return "anchor";
    if (frag.startsWith("/")) return "spa";
    if (frag.includes("/")) return "spa";
    if ((frag.includes("&") && frag.includes("=")) || frag.startsWith("?")) return "spa";
    if (frag.length <= 50 && /^[a-zA-Z][a-zA-Z_-]*$/.test(frag)) return "anchor";
    if (frag.length <= 20 && /^[a-zA-Z0-9_-]+$/.test(frag)) return "anchor";
    return "ambiguous";
};

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

/**
 * Write the decision marker atomically (tmp → rename) with fsync before rename.
 * Ensures durability on power-loss / OOM-triggered restart.
 */
const writeDecisionFile = (
    storagePath: string,
    decision: "skipDiez" | "bypassDiez",
    tier: 1 | 2
): void => {
    const c = context.diezClassification;
    const payload = {
        decision,
        tier,
        committedAt: new Date().toISOString(),
        counts: {
            anchor: c.anchor,
            spa: c.spa,
            ambiguous: c.ambiguous,
            total: c.total,
        },
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
export const commitSkipDiez = (storagePath: string): void => {
    if (context.diezDecisionCommitted) return;

    const c = context.diezClassification;
    context.config.skipDiez = true;
    context.diezDecisionCommitted = true;

    writeDecisionFile(storagePath, "skipDiez", 1);

    console.log(
        `[diez] Tier 1 decision: skipDiez (anchor=${c.anchor} spa=${c.spa} ambiguous=${c.ambiguous} / total=${c.total})`
    );

    // Rewrite already-queued URLs to strip '#'. Lazy require avoids ESM circular dep at load time.
    try {
        const { parseJsonFiles, getAllRequestQueues } = _require("./functions.js");
        const queueName = context.config.crawleeStorageName;
        const queues: string[] = getAllRequestQueues(queueName);
        if (Array.isArray(queues) && queues.length > 0) {
            parseJsonFiles(queues, context.config.skipQuestionMark, true, {
                toKeep: context.config.toKeep,
                toRemove: context.config.toRemove,
            });
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
export const commitBypassDiez = (storagePath: string): void => {
    if (context.diezDecisionCommitted) return;

    const c = context.diezClassification;
    context.config.bypassDiez = true;
    context.diezDecisionCommitted = true;

    writeDecisionFile(storagePath, "bypassDiez", 1);

    console.log(
        `[diez] Tier 1 decision: bypassDiez (anchor=${c.anchor} spa=${c.spa} ambiguous=${c.ambiguous} / total=${c.total})`
    );
};
