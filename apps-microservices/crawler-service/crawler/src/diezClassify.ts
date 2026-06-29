/**
 * Pure URL-fragment classification + per-class strip. Dependency-free (no context,
 * no fs) so functions.ts / routes.ts can import it without an import cycle
 * (diezDecision.ts pulls in context and lazy-requires functions.ts).
 *
 * classifyFragment moved here from diezDecision.ts (logic unchanged); diezDecision
 * re-exports it for back-compat.
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
 *   5. HTML id convention (length ≤ 50, ^[a-zA-Z][-a-zA-Z0-9_]*$) → anchor
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
    if (frag.length <= 50 && /^[a-zA-Z][-a-zA-Z0-9_]*$/.test(frag)) return "anchor";
    if (frag.length <= 20 && /^[a-zA-Z0-9_-]+$/.test(frag)) return "anchor";
    return "ambiguous";
};

/**
 * Per-class fragment strip: remove `#...` iff the fragment classifies as a cosmetic
 * `anchor` (incl. an empty trailing `#`); keep `spa`/`ambiguous` (routes). Pure
 * string op so the empty-`#` case is reliable.
 */
export const applyPerClassStrip = (url: string): string => {
    const i = url.indexOf("#");
    if (i === -1) return url;
    return classifyFragment(url.slice(i + 1)) === "anchor" ? url.slice(0, i) : url;
};

/** Kill-switch, read at call time (testable). */
export const perClassEnabled = (): boolean =>
    (process.env.DIEZ_PERCLASS_ENABLED ?? "false").toLowerCase() === "true";

/**
 * Cheap, stable content fingerprint for collision detection — FNV-1a over the
 * whitespace-normalized text, plus a length suffix to cut accidental collisions.
 * Used by the end-of-crawl content-collision pass to decide "same page?".
 */
export const fingerprint = (content: string): string => {
    const s = content.replace(/\s+/g, " ").trim();
    let h = 0x811c9dc5;
    for (let i = 0; i < s.length; i++) {
        h ^= s.charCodeAt(i);
        h = Math.imul(h, 0x01000193);
    }
    return (h >>> 0).toString(16) + ":" + s.length;
};
