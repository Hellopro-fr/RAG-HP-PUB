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
import { baseKeyWithout, baseKeyAbsent, hasParam, LANGUAGE_PARAMS } from "./urlBase.js";

const _require = createRequire(import.meta.url);

export const QM_TIER2_TRIGGER = 20;     // domainSpecificCount to activate
const MIN_PAIRS = 3;
const RATIO = 0.8;
const CONTENT_CAP = 150;                 // max buffered page contents
const CANDIDATE_TOP_K = 8;               // most-frequent candidate params tracked
const DEFAULT_AT = 95;                   // countQuestionMark margin before the 100 stop

// baseKeyWithout / baseKeyAbsent / hasParam now live in urlBase.ts (shared with
// facetCap / filterOnSeen). Re-exported below so existing importers (routes.ts,
// questionMarkTier2.test.ts) keep working unchanged.
export { baseKeyWithout };

const paramValue = (url: string, p: string): string | null => {
    try { return new URL(url).searchParams.get(p); } catch { return null; }
};

// A language param must never become a tier-2 candidate: `toRemove` strips it from
// newly-discovered links AND rewrites the already-queued ones, which undoes the `?lang=fr`
// propagation mid-crawl on the very session-i18n sites it rescues. Candidates are ranked by
// descending frequency with no language allowlist, so on a site serving its own `?lang=de`
// (our own injected `lang=fr` is already exempt — routes.ts feeds `facetUrl`) `lang` can top
// the list and a same-majority verdict commits it. Case-insensitive on purpose: erring wide
// here costs at most one un-stripped cosmetic param; erring narrow costs the propagation.
const LANGUAGE_PARAMS_LC = new Set(LANGUAGE_PARAMS.map((s) => s.toLowerCase()));

/** Most-frequent-first candidate params, skipping language / decided / toRemove / toKeep; top-K. */
const candidateParams = (): string[] => {
    const t = context.qmTier2;
    const toRemove = new Set(context.config.toRemove.map((s) => s.toLowerCase()));
    const toKeep = new Set(context.config.toKeep.map((s) => s.toLowerCase()));
    return Array.from(context.questionMarkObservations.paramFrequency.entries())
        .sort((a, b) => b[1] - a[1])
        .map(([name]) => name)
        .filter((name) => !LANGUAGE_PARAMS_LC.has(name.toLowerCase()))
        .filter((name) => !t.decided.has(name) && !toRemove.has(name.toLowerCase()) && !toKeep.has(name.toLowerCase()))
        .slice(0, CANDIDATE_TOP_K);
};

type AdjudicateResult = PairVerdict | "error";

const adjudicate = async (a: string, b: string, client: ContentExtractorClient): Promise<AdjudicateResult> => {
    try {
        const [ca, cb] = await Promise.all([client.clean(a), client.clean(b)]);
        if (!ca || !cb) return "unusable";
        const verdict = classifyPair(jaccard(shingleSet(normalizeForCompare(ca)), shingleSet(normalizeForCompare(cb))));
        // B1 veto: only trust a /clean "match" when the RAW HTML is also highly similar.
        // a/b are the buffered full page.content() HTML. If raw differs materially, the
        // discriminator lives in the region /clean dropped (e.g. a search results grid)
        // -> do NOT count as same (errs toward keep = no loss). /clean strips boilerplate
        // AND result grids, so two different search/listing pages can clean to identical
        // chrome text (false match). High default errs toward KEEP; tune from prod.
        // Env read at CALL time (like diezClassify.perClassEnabled) so it stays tunable.
        if (verdict === "match") {
            const rawSameSim = parseFloat(process.env.QM_RAW_SAME_SIM ?? "0.97");
            const rawSim = jaccard(shingleSet(normalizeForCompare(a)), shingleSet(normalizeForCompare(b)));
            if (rawSim < rawSameSim) return "unusable";
        }
        return verdict;
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

/**
 * Append p to toRemove + addedToRemove + decided, rewrite the queue, persist.
 *
 * DELIBERATELY carries no language guard of its own. It has exactly one caller
 * (`routes.ts:1004`), which only ever passes a key of `context.qmTier2.tally`, and the tally
 * is only ever keyed by `candidateParams()` inside `recordQmTier2Sample`. The tally is
 * in-memory (`context.qmTier2` is never rehydrated from disk), so the clause in
 * `candidateParams()` is upstream of every write and a guard here could not fire — it would
 * be untestable dead code, and a test written against it would go green while proving nothing
 * about the live path.
 *
 * The "a `lang` already committed survives the OOM relaunch" argument is real but does NOT
 * land here: that path is `readQmPersistedDecision` (`questionMarkDecision.ts`), which merges
 * the persisted `addedToRemove` straight into `context.config.toRemove` and never calls this
 * function. That is where the second guard lives.
 */
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
