/**
 * Phase-2 tier-2 content-comparison engine. Buffers ONE {frag, content} per
 * fragment-stripped base; when a 2nd distinct '#'-variant of that base arrives,
 * cleans both via content-extractor and classifies the pair (match/mismatch/
 * unusable), tallying crawl-wide. skipDiez (destructive) requires positive
 * match-evidence; mismatch-majority → bypassDiez. See spec §5.
 */
import { context } from "./context.js";
import { ContentExtractorClient } from "./class/ContentExtractorClient.js";
import { normalizeForCompare, shingleSet, jaccard, classifyPair } from "./contentSimilarity.js";
import type { PairVerdict } from "./contentSimilarity.js";

const MIN_COMPARED = 3;
const DECIDE_RATIO = 0.8;
const BUFFER_CAP = 50;

export const baseUrlKey = (url: string): string => {
    try {
        const u = new URL(url);
        u.hash = "";
        return u.toString();
    } catch {
        const i = url.indexOf("#");
        return i === -1 ? url : url.slice(0, i);
    }
};

const fragOf = (url: string): string => {
    const i = url.indexOf("#");
    return i === -1 ? "" : url.slice(i + 1);
};

const adjudicate = async (a: string, b: string, client: ContentExtractorClient): Promise<PairVerdict> => {
    try {
        const [ca, cb] = await Promise.all([client.clean(a), client.clean(b)]);
        if (!ca || !cb) return "unusable"; // empty-or-empty is non-comparable
        const sim = jaccard(shingleSet(normalizeForCompare(ca)), shingleSet(normalizeForCompare(cb)));
        return classifyPair(sim);
    } catch {
        return "unusable"; // 413/422/500/timeout/network → cannot decide
    }
};

/**
 * Record a '#'-bearing page's content for tier-2. On the 2nd distinct variant
 * of a base, adjudicate the pair and update the crawl-wide tally.
 */
export const recordTier2Sample = async (
    url: string,
    content: string,
    client: ContentExtractorClient | null,
): Promise<void> => {
    if (!client || !content) return;
    const t = context.diezTier2;
    const base = baseUrlKey(url);
    const frag = fragOf(url);
    const existing = t.buffer.get(base);

    if (existing) {
        if (existing.frag === frag) return; // same variant seen again — no signal
        const verdict = await adjudicate(existing.content, content, client);
        t.compared++;
        if (verdict === "match") t.matches++;
        else if (verdict === "mismatch") t.mismatches++;
        else t.unusable++;
        t.buffer.delete(base); // free the buffered content
        return;
    }

    if (t.buffer.size < BUFFER_CAP) {
        t.buffer.set(base, { frag, content });
    }
};

export const maybeCommitTier2 = (): "skipDiez" | "bypassDiez" | null => {
    const t = context.diezTier2;
    if (t.compared < MIN_COMPARED) return null;
    if (t.matches / t.compared >= DECIDE_RATIO) return "skipDiez";
    if (t.mismatches / t.compared >= DECIDE_RATIO) return "bypassDiez";
    return null;
};

export const tier2Evidence = () => {
    const t = context.diezTier2;
    return { compared: t.compared, matches: t.matches, mismatches: t.mismatches, unusable: t.unusable };
};
