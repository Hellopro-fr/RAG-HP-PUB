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
