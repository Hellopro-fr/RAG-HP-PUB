/**
 * `__unjudged_urls.json` — the durable record of every URL the crawler navigated
 * but for which detection produced NO linguistic verdict (`verdictUnavailable`,
 * routes.ts).
 *
 * Why it has to exist: suppressing the false `not_french` verdict removed the
 * BRAKE, not the deletion. `script_process_update_crawling.php` runs a second
 * reconciliation that is pure set subtraction — Milvus URLs minus the URLs
 * present in the new dataset (`recuperer_urls_orphelines_sans_slash`, :724,
 * :1014, :1077) — then `archiver_urls_milvus` + `desactiver_produit`. A page
 * with no verdict writes no dataset row, so it is an orphan BY CONSTRUCTION and
 * is deactivated anyway. This sidecar is the list the BO must add to the
 * "recrawled" side BEFORE subtracting, exactly as it already does for
 * `__collapsed_urls.json` (read at :558-569, merged at :720 and :1010).
 *
 * Shape: a flat JSON array of URL strings, in the SAME namespace as a dataset
 * row's `url` — the BO builds its recrawled side with
 * `array_map(fn($item) => $item['url'], $otherUrlsContent)` and merges the
 * collapsed sidecar into it unchanged. Trailing slashes need no normalisation
 * here: `recuperer_urls_orphelines_sans_slash` `trim($url, "/")`s BOTH sides of
 * the diff before comparing.
 *
 * The `__` prefix is load-bearing. `_count_files_in_dir`
 * (`app/core/crawler_manager.py:146-161`) skips every `__`-prefixed name, so
 * this file can never inflate `stored_files_count`. That count staying at 0/1 is
 * what makes the BO answer `insufficientData` and stop before touching a single
 * fiche on a TOTAL detection outage — the one case that already works today.
 */
import fs from "node:fs";

export const UNJUDGED_SIDECAR = "__unjudged_urls.json";

/** Dataset dir. Same relative convention as `cleanDatasetFragments` (cwd = storagePath). */
const sidecarPath = (datasetName: string): string =>
    `storage/datasets/${datasetName}/${UNJUDGED_SIDECAR}`;

/** Tolerant reader: anything that is not an array of non-empty strings -> []. */
export const parseUnjudgedSidecar = (raw: unknown): string[] =>
    Array.isArray(raw) ? raw.filter((u): u is string => typeof u === "string" && u !== "") : [];

const read = (file: string): string[] => {
    try { return parseUnjudgedSidecar(JSON.parse(fs.readFileSync(file, "utf-8"))); }
    catch { return []; } // absent or corrupt -> start fresh
};

/**
 * tmp + rename, never a bare write: the crawl can be SIGKILLed (this service has
 * an OOM history) and a half-written file would leave the BO with unparseable
 * JSON — i.e. no protection at all — on the very run where it matters most.
 * The tmp name is `__`-prefixed too, so a leftover is still invisible to
 * `stored_files_count`.
 */
const write = (file: string, urls: string[]): void => {
    const tmp = `${file}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(urls));
    fs.renameSync(tmp, file);
};

/**
 * Create the sidecar as `[]` if it does not exist yet. Presence is itself a
 * signal the BO needs: an ABSENT file means "this crawler predates the fix, you
 * cannot tell", an EMPTY one means "detection answered for every page, subtract
 * freely". Never clobbers an existing file (an OOM relaunch must keep pass-1
 * entries).
 */
export const ensureUnjudgedSidecar = (datasetName: string | undefined): void => {
    if (!datasetName) return;
    const file = sidecarPath(datasetName);
    try {
        if (fs.existsSync(file)) return;
        fs.mkdirSync(`storage/datasets/${datasetName}`, { recursive: true });
        write(file, []);
    } catch (e) {
        console.warn(`[unjudged] Failed to initialise ${file}: ${e}`);
    }
};

/**
 * Append URLs that got no verdict, deduplicated, and flush immediately.
 *
 * Read-merge-write on EVERY call rather than one write at shutdown: a SIGKILLed
 * update crawl is precisely when the orphan set is most dangerous, so the file
 * has to be correct at all times, not at exit. The merge is also what carries
 * pass-1 entries across an OOM relaunch — same reason as the `__collapsed_urls`
 * merge (functions.ts:2047).
 *
 * A URL recorded here that later gets a verdict on a Crawlee retry stays in the
 * list. That is the safe direction: a spurious entry only means "do not
 * deactivate a page we did read", while a missing one means deactivating a page
 * nobody managed to read.
 *
 * ponytail: rewrites the whole file per unjudged page (O(n^2) bytes). Fine while
 * "no verdict" is the exception; buffer + flush on a timer if a full outage ever
 * makes it the rule.
 */
export const recordUnjudgedUrls = (
    datasetName: string | undefined,
    urls: (string | undefined | null)[],
): void => {
    if (!datasetName) return;
    const file = sidecarPath(datasetName);
    try {
        const merged = read(file);
        const seen = new Set(merged);
        let added = 0;
        for (const u of urls) {
            if (!u || seen.has(u)) continue;
            seen.add(u);
            merged.push(u);
            added++;
        }
        if (added === 0) return; // nothing new (Crawlee retry of the same request)
        fs.mkdirSync(`storage/datasets/${datasetName}`, { recursive: true });
        write(file, merged);
    } catch (e) {
        console.warn(`[unjudged] Failed to record unjudged URL(s) in ${file}: ${e}`);
    }
};
