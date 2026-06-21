/**
 * Phase-2 tier-2 per-param engine for limitQuestionMark. Buffers each ?-page's
 * content; groups by "URL with param p removed"; when two members differ in p
 * (value-vs-value, Strategy A, or value-vs-absent, Strategy B) it cleans both via
 * content-extractor and classifies same/different/unusable. A param commits to
 * toRemove only on same-majority (the one destructive action); "different" is
 * ruled content-shaping (kept). Transient extractor failures (503/timeout/network)
 * do NOT consume a comparison — the group is kept to retry on a later variant
 * (mirrors diezTier2). See spec §5.
 */
import { createRequire } from "node:module";
import { context } from "./context.js";
import { ContentExtractorClient, ContentExtractorError } from "./class/ContentExtractorClient.js";
import { normalizeForCompare, shingleSet, jaccard, classifyPair } from "./contentSimilarity.js";
import type { PairVerdict } from "./contentSimilarity.js";

const _require = createRequire(import.meta.url);

export const QM_TIER2_TRIGGER = 20;     // domainSpecificCount to activate
const MIN_PAIRS = 3;
const RATIO = 0.8;
const CONTENT_CAP = 150;                 // max buffered page contents
const CANDIDATE_TOP_K = 8;               // most-frequent candidate params tracked
const DEFAULT_AT = 95;                   // countQuestionMark margin before the 100 stop

/** URL with param p removed, params sorted, normalized. */
export const baseKeyWithout = (url: string, p: string): string => {
    try {
        const u = new URL(url);
        u.searchParams.delete(p);
        u.searchParams.sort();
        return u.toString();
    } catch {
        return url;
    }
};

const baseKeyAbsent = (url: string): string => {
    try {
        const u = new URL(url);
        u.searchParams.sort();
        return u.toString();
    } catch {
        return url;
    }
};

const hasParam = (url: string, p: string): boolean => {
    try { return new URL(url).searchParams.has(p); } catch { return false; }
};
const paramValue = (url: string, p: string): string | null => {
    try { return new URL(url).searchParams.get(p); } catch { return null; }
};

/** Most-frequent-first candidate params, skipping decided / toRemove / toKeep; top-K. */
const candidateParams = (): string[] => {
    const t = context.qmTier2;
    const toRemove = new Set(context.config.toRemove.map((s) => s.toLowerCase()));
    const toKeep = new Set(context.config.toKeep.map((s) => s.toLowerCase()));
    return Array.from(context.questionMarkObservations.paramFrequency.entries())
        .sort((a, b) => b[1] - a[1])
        .map(([name]) => name)
        .filter((name) => !t.decided.has(name) && !toRemove.has(name.toLowerCase()) && !toKeep.has(name.toLowerCase()))
        .slice(0, CANDIDATE_TOP_K);
};

type AdjudicateResult = PairVerdict | "error";

const adjudicate = async (a: string, b: string, client: ContentExtractorClient): Promise<AdjudicateResult> => {
    try {
        const [ca, cb] = await Promise.all([client.clean(a), client.clean(b)]);
        if (!ca || !cb) return "unusable";
        return classifyPair(jaccard(shingleSet(normalizeForCompare(ca)), shingleSet(normalizeForCompare(cb))));
    } catch (e) {
        // Transient infra failure (503 admission / timeout / network): cannot measure now.
        // Terminal failures (413/422/500) and unknown throws are a genuine "unusable".
        if (e instanceof ContentExtractorError && e.transient) return "error";
        return "unusable";
    }
};

/**
 * Buffer a ?-page and adjudicate any pair this completes. For each candidate
 * param p: register the URL under groups[p][baseKey] (baseKey = url minus p when
 * p present, or the url itself when p absent). A member differing in pval from an
 * already-buffered sibling triggers one adjudication; the group is then freed. A
 * transient extractor failure leaves the group intact for a later retry.
 */
export const recordQmTier2Sample = async (
    url: string,
    content: string,
    client: ContentExtractorClient | null,
): Promise<void> => {
    if (!client || !content) return;
    const t = context.qmTier2;
    if (!t.contentByUrl.has(url) && t.contentByUrl.size < CONTENT_CAP) {
        t.contentByUrl.set(url, content);
    }
    if (!t.contentByUrl.has(url)) return; // cap reached; cannot compare this one

    for (const p of candidateParams()) {
        const present = hasParam(url, p);
        const baseKey = present ? baseKeyWithout(url, p) : baseKeyAbsent(url);
        const pval = present ? paramValue(url, p) : null;

        let group = t.groups.get(p);
        if (!group) { group = new Map(); t.groups.set(p, group); }
        let members = group.get(baseKey);
        if (!members) { members = []; group.set(baseKey, members); }
        if (members.some((m) => m.url === url)) continue;

        const sibling = members.find((m) => m.pval !== pval && t.contentByUrl.has(m.url));
        members.push({ pval, url });

        if (sibling) {
            const verdict = await adjudicate(t.contentByUrl.get(sibling.url)!, t.contentByUrl.get(url)!, client);
            if (verdict === "error") continue; // transient: don't tally, keep the group to retry on a later variant
            const tally = t.tally.get(p) ?? { same: 0, different: 0, unusable: 0 };
            if (verdict === "match") tally.same++;
            else if (verdict === "mismatch") tally.different++;
            else tally.unusable++;
            t.tally.set(p, tally);
            group.delete(baseKey); // free
        }
    }
};

/** True → commit p to toRemove. Rules content-shaping (different-majority) as a side effect. */
export const maybeCommitParam = (p: string): boolean => {
    const t = context.qmTier2;
    const tally = t.tally.get(p);
    if (!tally) return false;
    const compared = tally.same + tally.different;
    if (compared < MIN_PAIRS) return false;
    if (tally.same / compared >= RATIO) return true;
    if (tally.different / compared >= RATIO && !t.decided.has(p)) {
        t.decided.add(p);
        t.contentShaping.push(p);
        console.log(`[questionmark] Tier 2: '${p}' content-shaping (different=${tally.different}/${compared}), keeping.`);
    }
    return false;
};

/** Append p to toRemove + addedToRemove + decided, rewrite the queue, persist. */
export const commitToRemoveParam = (p: string, storagePath: string): void => {
    const t = context.qmTier2;
    if (context.config.toRemove.some((x) => x.toLowerCase() === p.toLowerCase())) {
        t.decided.add(p);
        return;
    }
    context.config.toRemove.push(p);
    t.addedToRemove.push(p);
    t.decided.add(p);

    const tally = t.tally.get(p);
    const compared = tally ? tally.same + tally.different : 0;
    console.log(`[questionmark] Tier 2 decision: '${p}' -> toRemove (${tally?.same ?? 0}/${compared} same).`);

    try {
        const { parseJsonFiles, getAllRequestQueues } = _require("./functions.js");
        const queues: string[] = getAllRequestQueues(context.config.crawleeStorageName);
        if (Array.isArray(queues) && queues.length > 0) {
            parseJsonFiles(queues, context.config.skipQuestionMark, context.config.skipDiez, {
                toRemove: [p],
                toKeep: context.config.toKeep,
            });
        }
    } catch (e) {
        console.warn(`[questionmark] Queue rewrite skipped for '${p}': ${(e as Error).message}`);
    }

    const { writeQmDecisionFile } = _require("./questionMarkDecision.js");
    writeQmDecisionFile(storagePath, "tier2");
};

/**
 * Zero-touch bounded default. Near the 100 ceiling, disable the limitQuestionMark
 * stop and turn ON the 5000-item backstop (breakLimit=false) so a facet trap can't
 * explode. Committed toRemove strips stay; never the skipQuestionMark sledgehammer.
 */
export const maybeDefaultAtCeiling = (storagePath: string): void => {
    const t = context.qmTier2;
    if (t.defaulted) return;
    if (context.countQuestionMark < DEFAULT_AT) return;
    context.config.bypassQuestionMark = true; // live-config stop (Task 4) honors this
    context.config.breakLimit = false;        // enable the 5000-dataset-item backstop
    t.defaulted = true;
    console.log(`[questionmark] Tier 2 default at ${context.countQuestionMark} ? URLs — bypass + 5000 backstop (no human).`);
    const { writeQmDecisionFile } = _require("./questionMarkDecision.js");
    writeQmDecisionFile(storagePath, "defaulted");
};
