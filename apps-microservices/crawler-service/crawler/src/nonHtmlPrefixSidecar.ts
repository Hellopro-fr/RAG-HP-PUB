/**
 * `__nonhtml_prefixes.json` — the durable record of the non-HTML URL prefixes the crawler
 * learned (R23 (2)): one entry per `host/parent-dir` key, plus the isolated non-HTML URLs
 * (no usable parent dir, or below the learning threshold).
 *
 * Shape (exact bytes, no indentation, no trailing newline):
 *   {"version":1,"prefixes":{"<key>":{"nonHtml":N,"confirmedAt":"<iso>"|null}},"urls":["<url>",…]}
 *
 * Persisted keys: not vetoed by an HTML response AND (blocking OR still in unresolved probation).
 * The key always contains a "/" (host + dir), so object-key reordering of integer-like keys
 * cannot happen and the Map insertion order survives the JSON round trip.
 *
 * The `__` prefix is load-bearing, like `__unjudged_urls.json` (unjudgedUrls.ts): the dataset
 * readers skip `__`-prefixed names and `_count_files_in_dir` ignores them. The tmp name
 * (`<file>.tmp`) starts with `__` and does not end in `.json`, so a leftover stays invisible.
 *
 * Pure (de)serialisation + path helpers + two tiny I/O wrappers. Nothing here throws into the
 * crawl: a failed write degrades to a `console.warn`.
 */
import fs from "node:fs";
import path from "node:path";
import { isKeyBlocking, normalizeUrlIdentity, type NonHtmlPrefixState } from "./nonHtmlPrefix.js";

export const NONHTML_PREFIX_SIDECAR = "__nonhtml_prefixes.json";
export const NONHTML_SIDECAR_VERSION = 1;

export interface SidecarData {
    prefixes: Map<string, { nonHtml: number; confirmedAt: string | null }>;
    urls: string[];
}

const emptyData = (): SidecarData => ({ prefixes: new Map(), urls: [] });

const isPlainObject = (v: unknown): v is Record<string, unknown> =>
    typeof v === "object" && v !== null && !Array.isArray(v);

/** Exact-byte serialisation of the persistable part of the state. */
export function serializeNonHtmlPrefixState(state: NonHtmlPrefixState): string {
    const prefixes: Record<string, { nonHtml: number; confirmedAt: string | null }> = {};
    for (const [key, entry] of state.prefixes) {
        if (entry.sawHtml) continue;
        const probing = entry.probation !== null && !entry.probation.resolved;
        if (!isKeyBlocking(entry, state.params) && !probing) continue;
        prefixes[key] = { nonHtml: entry.nonHtml, confirmedAt: entry.confirmedAt };
    }
    // R23 I-2: an isolated URL still in probation stays persisted, like a key in probation.
    const urls = [...new Set([...state.isolated, ...state.loadedIsolated, ...state.isolatedProbation])]
        .slice(0, state.params.isolatedMax);
    return JSON.stringify({ version: NONHTML_SIDECAR_VERSION, prefixes, urls });
}

/** Tolerant reader: anything unexpected degrades to "less data", never to an exception. */
export function parseNonHtmlPrefixSidecar(raw: string | null): SidecarData {
    if (raw === null) return emptyData();
    let json: unknown;
    try { json = JSON.parse(raw); } catch { return emptyData(); }
    if (!isPlainObject(json) || json.version !== NONHTML_SIDECAR_VERSION) return emptyData();

    const data = emptyData();
    if (isPlainObject(json.prefixes)) {
        for (const [key, value] of Object.entries(json.prefixes)) {
            if (!isPlainObject(value)) continue;
            const nonHtml = value.nonHtml;
            if (typeof nonHtml !== "number" || !Number.isInteger(nonHtml) || nonHtml < 0) continue;
            const confirmedAt = typeof value.confirmedAt === "string" ? value.confirmedAt : null;
            data.prefixes.set(key, { nonHtml, confirmedAt });
        }
    }
    if (Array.isArray(json.urls)) {
        data.urls = json.urls.filter((u): u is string => typeof u === "string" && u !== "");
    }
    return data;
}

/**
 * Merge sidecar data into the state; returns the number of prefix keys added.
 * Call order imposed on the caller: "current" FIRST, then "previous" — a key the current crawl
 * already confirmed is skipped (not put back in probation by the previous crawl's copy).
 */
export function loadSidecarInto(
    state: NonHtmlPrefixState,
    data: SidecarData,
    origin: "current" | "previous",
): number {
    let added = 0;
    for (const [key, value] of data.prefixes) {
        if (state.prefixes.has(key)) continue;
        state.prefixes.set(key, origin === "current"
            ? { nonHtml: value.nonHtml, sawHtml: false, confirmed: true, confirmedAt: value.confirmedAt, probation: null }
            : {
                nonHtml: value.nonHtml, sawHtml: false, confirmed: false, confirmedAt: value.confirmedAt,
                probation: { admitted: 0, probeUrl: null, resolved: false },
            });
        added++;
    }
    // R23 I-2: "previous" URLs go to probation (one probe each), unless "current" already loaded
    // them as kept; "current" URLs (OOM relaunch) load as kept, like "current" keys load confirmed.
    for (const u of data.urls) {
        const n = normalizeUrlIdentity(u);
        if (origin === "previous" && state.loadedIsolated.has(n)) continue;
        if (state.loadedIsolated.size + state.isolatedProbation.size >= state.params.isolatedMax) break;
        (origin === "current" ? state.loadedIsolated : state.isolatedProbation).add(n);
    }
    return added;
}

/** Same relative convention as unjudgedUrls.ts (cwd = storagePath). */
export function currentSidecarPath(domain: string): string {
    return `storage/datasets/${domain}/${NONHTML_PREFIX_SIDECAR}`;
}

/**
 * Previous crawl's sidecar, resolved like `loadDatasetUrlsGenerator` resolves its dataset
 * (functions.ts, `path.resolve('..', previousId)` then original domain name, then dots => hyphens).
 * `null` when neither file exists.
 */
export function resolvePreviousSidecarPath(previousId: string, domain: string, cwd: string = process.cwd()): string | null {
    const base = path.resolve(cwd, "..", previousId, "storage", "datasets");
    for (const name of [domain, domain.replace(/\./g, "-")]) {
        const file = path.join(base, name, NONHTML_PREFIX_SIDECAR);
        if (fs.existsSync(file)) return file;
    }
    return null;
}

/** `null` for a null path, an absent file or any read error. */
export function readSidecarFile(file: string | null): string | null {
    if (file === null) return null;
    try { return fs.readFileSync(file, "utf-8"); } catch { return null; }
}

/**
 * tmp + rename (the crawl can be SIGKILLed mid-write; same reason as unjudgedUrls.ts).
 * Never throws: a failure is a warning, the crawl goes on (the in-memory state is unaffected).
 */
export function writeSidecarFile(file: string, text: string): void {
    const tmp = `${file}.tmp`;
    try {
        fs.mkdirSync(path.dirname(file), { recursive: true });
        fs.writeFileSync(tmp, text);
        fs.renameSync(tmp, file);
    } catch (e) {
        console.warn(`[nonhtml-prefix] sidecar write failed: ${(e as Error).message}`);
        try { fs.rmSync(tmp, { force: true }); } catch { /* best effort: do not leave a stale tmp */ }
    }
}
