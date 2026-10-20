/**
 * A312 — BO-known seed (identity class `bo_known`).
 *
 * The BO sends the domain's ACTIVE SFPI set (raw `url_sfpi`, byte-exact); crawler-service writes
 * it to `<job>/known_urls.json` and passes `--knownUrlsFile=<path>`. main.ts reads it with
 * readKnownUrlsFile(), injects it in Phase 1 (UrlConsolidator.addBoKnown, SET update_bo_known:<id>)
 * and seeds the injected URLs in Phase 2 through seedBoKnown().
 *
 * Lives outside main.ts because main.ts is not importable (it runs at load: Redis, process.exit),
 * so this logic is unit-tested in tests/boKnownSeed.test.ts. Only `node:fs` is imported: the
 * seed's collaborators (request queue, regional and extension filters, nonHtml gate) are injected
 * by the caller.
 *
 * The URL is seeded RAW and never re-cleaned: the BO matches SFPI rows by exact key, so a cleaned
 * URL would never retire its row (spec section 3.5, motif F16).
 */
import { readFileSync } from 'node:fs';

export const BO_KNOWN_SOURCE = 'bo_known';
export const BO_KNOWN_UNIQUE_KEY_PREFIX = 'bo_known:';
export const BO_KNOWN_ORIGIN = 'bo_known';
export const BO_KNOWN_REASON_NOT_ELIGIBLE = 'not_eligible';

/**
 * Reads the BO-known URL list. No path (option absent: the domain is not in the BO allowlist)
 * => [] silently. Missing or unreadable file, invalid JSON, or a JSON value that is not an array
 * => [] and one console.warn: the crawl goes on without bo_known (fails open). Only non-empty
 * strings are kept, unchanged and in order; dropped entries cost one console.warn.
 */
export function readKnownUrlsFile(filePath: string | undefined): string[] {
    if (!filePath) {
        return [];
    }
    let parsed: unknown;
    try {
        parsed = JSON.parse(readFileSync(filePath, 'utf-8'));
    } catch (e) {
        console.warn(`[bo_known] known URLs file unreadable or invalid JSON (${filePath}): ${e}`);
        return [];
    }
    if (!Array.isArray(parsed)) {
        console.warn(`[bo_known] known URLs file is not a JSON array (${filePath}), ignored`);
        return [];
    }
    const urls = parsed.filter((u): u is string => typeof u === 'string' && u.length > 0);
    if (urls.length !== parsed.length) {
        console.warn(`[bo_known] ${parsed.length - urls.length} entry(ies) dropped from ${filePath} (not a non-empty string)`);
    }
    return urls;
}

/** Queue request of a bo_known seed: raw URL, identity prefixed so it never merges with another source. */
export function buildBoKnownRequest(raw: string): { url: string; uniqueKey: string; userData: { source: string; rawUrl: string } } {
    return {
        url: raw,
        uniqueKey: BO_KNOWN_UNIQUE_KEY_PREFIX + raw,
        userData: { source: BO_KNOWN_SOURCE, rawUrl: raw },
    };
}

/**
 * Seeds the bo_known URLs. Per URL, in this order: regional path excluded => skippedRegional;
 * ignored extension => skippedExt; nonHtml exemption (when a gate is given; no check is ever
 * made); addRequest, a rejection => rejected (logged, never thrown).
 */
export async function seedBoKnown(
    urls: string[],
    deps: {
        addRequest(req: ReturnType<typeof buildBoKnownRequest>): Promise<unknown>;
        isExcludedRegional(url: string): boolean;
        hasIgnoredExtension(url: string): boolean;
        addExempt?(url: string): void;
    },
): Promise<{ seeded: number; skippedRegional: number; skippedExt: number; rejected: number }> {
    let seeded = 0;
    let skippedRegional = 0;
    let skippedExt = 0;
    let rejected = 0;
    for (const raw of urls) {
        if (deps.isExcludedRegional(raw)) {
            skippedRegional++;
            continue;
        }
        if (deps.hasIgnoredExtension(raw)) {
            skippedExt++;
            continue;
        }
        deps.addExempt?.(raw);
        try {
            await deps.addRequest(buildBoKnownRequest(raw));
            seeded++;
        } catch (e) {
            rejected++;
            console.warn(`[bo_known] seed rejected for ${raw}: ${e}`);
        }
    }
    return { seeded, skippedRegional, skippedExt, rejected };
}
