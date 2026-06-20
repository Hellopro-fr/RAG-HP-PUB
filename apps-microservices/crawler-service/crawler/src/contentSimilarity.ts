/**
 * Phase-2 tier-2 text comparison. We compare two cleaned-text outputs (from
 * content-extractor /clean format=text) with Jaccard similarity over word
 * trigrams. A route change is a LARGE difference; load-to-load dynamic noise
 * (reviews, timestamps) is a SMALL one — the dead-band separates them.
 * Text only — a structural fingerprint would vote "match" on shared-template
 * SPA routes (the data-loss direction). See spec §5.2.
 */

const MATCH_SIM = 0.85;
const MISMATCH_SIM = 0.50;
const SHINGLE_K = 3;

export type PairVerdict = "match" | "mismatch" | "unusable";

export const normalizeForCompare = (text: string): string =>
    text.toLowerCase().replace(/\s+/g, " ").trim();

/** Word-level k-shingles (k=3). Short texts fall back to their word set. */
export const shingleSet = (text: string): Set<string> => {
    const words = normalizeForCompare(text).split(" ").filter(Boolean);
    const set = new Set<string>();
    if (words.length < SHINGLE_K) {
        for (const w of words) set.add(w);
        return set;
    }
    for (let i = 0; i + SHINGLE_K <= words.length; i++) {
        set.add(words.slice(i, i + SHINGLE_K).join(" "));
    }
    return set;
};

export const jaccard = (a: Set<string>, b: Set<string>): number => {
    if (a.size === 0 && b.size === 0) return 1;
    if (a.size === 0 || b.size === 0) return 0;
    let inter = 0;
    for (const x of a) if (b.has(x)) inter++;
    const union = a.size + b.size - inter;
    return union === 0 ? 1 : inter / union;
};

export const classifyPair = (sim: number): PairVerdict => {
    if (sim >= MATCH_SIM) return "match";
    if (sim < MISMATCH_SIM) return "mismatch";
    return "unusable";
};
