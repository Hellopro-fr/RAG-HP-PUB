#!/usr/bin/env node
/**
 * R23 (2) — replay instrument to derive K (NONHTML_PREFIX_MIN).
 *
 * Input: two JSON exports of `GET /admin/dataset/{crawl_id}` (kind=pdf = non-HTML
 * responses, kind=main = HTML pages), or bare arrays of their records.
 * For each K = 1..10 it replays recordNonHtml / recordHtml / decide of
 * nonHtmlPrefix.ts (consumed as signed) on a state built with minNonHtml = K.
 *
 * Replay order (a CONTRACT GAP, chosen here): the endpoint serves the FILE mtime,
 * not the row `timestamp`, and main rows carry no timestamp at all. Rows are merged
 * by `mtime` ascending; ties: non-HTML first (pessimistic for false positives),
 * then file name, then input rank. An mtime reset by a stash/restore flattens the
 * order — then the table is only an approximation.
 *
 * Free instrument: internal data only, no network.
 */
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import {
    NONHTML_PREFIX_DEFAULTS,
    createNonHtmlPrefixState,
    decide,
    recordHtml,
    recordNonHtml,
} from "../nonHtmlPrefix.js";
import { hasIgnoredExtensionForSeed } from "../seedExtensionFilter.js";

export interface ExportRecord {
    url: string;
    mtime: string;
    file: string;
}

export interface ReplayRow {
    url: string;
    kind: "nonhtml" | "html";
    mtime: string;
    file: string;
    seq: number;
}

export interface KResult {
    k: number;
    /** keys that crossed K (recordNonHtml => "learned") */
    keysLearned: number;
    /** learned keys that later saw HTML (recordHtml => "released") = false positives */
    keysReleased: number;
    /** non-HTML URLs decide() would have blocked after learning (ignored extensions excluded) */
    avoidedNonHtml: number;
    /** HTML pages requested while their key was blocking (the harm if released late) */
    htmlBlocked: number;
    /** "isolated" events of recordNonHtml (sidecar size driver) */
    isolated: number;
    nonHtmlRows: number;
    htmlRows: number;
}

const toRecord = (x: unknown): ExportRecord | null => {
    if (typeof x !== "object" || x === null) return null;
    const o = x as Record<string, unknown>;
    if (typeof o.url !== "string" || o.url === "") return null;
    return {
        url: o.url,
        mtime: typeof o.mtime === "string" ? o.mtime : "",
        file: typeof o.file === "string" ? o.file : "",
    };
};

/** Accepts a page object `{records}`, a bare array of records, or an array of pages. */
export function extractRecords(input: unknown): ExportRecord[] {
    const out: ExportRecord[] = [];
    const visit = (x: unknown): void => {
        if (Array.isArray(x)) {
            x.forEach(visit);
            return;
        }
        if (typeof x === "object" && x !== null && Array.isArray((x as { records?: unknown }).records)) {
            ((x as { records: unknown[] }).records).forEach(visit);
            return;
        }
        const r = toRecord(x);
        if (r) out.push(r);
    };
    visit(input);
    return out;
}

export function buildReplayRows(nonHtml: ExportRecord[], html: ExportRecord[]): ReplayRow[] {
    const rows: ReplayRow[] = [
        ...nonHtml.map((r, i): ReplayRow => ({ ...r, kind: "nonhtml", seq: i })),
        ...html.map((r, i): ReplayRow => ({ ...r, kind: "html", seq: nonHtml.length + i })),
    ];
    const rank = (r: ReplayRow) => (r.kind === "nonhtml" ? 0 : 1);
    const cmp = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);
    return rows.sort(
        (a, b) => cmp(a.mtime, b.mtime) || rank(a) - rank(b) || cmp(a.file, b.file) || a.seq - b.seq,
    );
}

export function replayForK(rows: ReplayRow[], k: number): KResult {
    const state = createNonHtmlPrefixState({ ...NONHTML_PREFIX_DEFAULTS, minNonHtml: k });
    const never = () => false; // no exemption: the replay has no previous dataset
    const res: KResult = {
        k, keysLearned: 0, keysReleased: 0, avoidedNonHtml: 0, htmlBlocked: 0,
        isolated: 0, nonHtmlRows: 0, htmlRows: 0,
    };
    for (const row of rows) {
        if (row.kind === "nonhtml") {
            res.nonHtmlRows++;
            if (decide(state, row.url, never) === "block") {
                // a blocked URL is never fetched, hence never recorded
                if (!hasIgnoredExtensionForSeed(row.url)) res.avoidedNonHtml++;
                continue;
            }
            const ev = recordNonHtml(state, row.url, "1970-01-01T00:00:00.000Z");
            if (ev === "learned") res.keysLearned++;
            else if (ev === "isolated") res.isolated++;
        } else {
            res.htmlRows++;
            if (decide(state, row.url, never) === "block") res.htmlBlocked++;
            if (recordHtml(state, row.url) === "released") res.keysReleased++;
        }
    }
    return res;
}

export function replayAll(rows: ReplayRow[], kMin = 1, kMax = 10): KResult[] {
    const out: KResult[] = [];
    for (let k = kMin; k <= kMax; k++) out.push(replayForK(rows, k));
    return out;
}

export function formatReport(results: KResult[]): string {
    const cols = (c: string[]) => c.map((v, i) => v.padStart(i === 0 ? 2 : 13)).join("  ").trimStart();
    const lines = [cols(["K", "learned", "released", "avoided", "html_blocked", "isolated"])];
    for (const r of results) {
        lines.push(cols([r.k, r.keysLearned, r.keysReleased, r.avoidedNonHtml, r.htmlBlocked, r.isolated].map(String)));
    }
    return lines.join("\n") + "\n";
}

const USAGE =
    "Usage: nonHtmlPrefixReplay.ts <pdf-export.json> <main-export.json>\n" +
    "  Exports of GET /admin/dataset/{crawl_id}?kind=pdf and ?kind=main (paginate: limit<=100, concatenate the pages).";

export function main(argv: string[]): number {
    if (argv.length !== 2) {
        console.error(USAGE);
        return 2;
    }
    let pdf: unknown;
    let mainData: unknown;
    try {
        pdf = JSON.parse(fs.readFileSync(path.resolve(argv[0]), "utf-8"));
        mainData = JSON.parse(fs.readFileSync(path.resolve(argv[1]), "utf-8"));
    } catch (e) {
        console.error(`Cannot read export: ${(e as Error).message}`);
        return 1;
    }
    const rows = buildReplayRows(extractRecords(pdf), extractRecords(mainData));
    console.log(`# rows: ${rows.length} (order: mtime asc, non-HTML first on ties)`);
    console.log(formatReport(replayAll(rows)).trimEnd());
    return 0;
}

const samePath = (a: string, b: string) =>
    process.platform === "win32" ? path.resolve(a).toLowerCase() === path.resolve(b).toLowerCase()
        : path.resolve(a) === path.resolve(b);

// Run only when launched directly (never on import, e.g. from the test file).
if (process.argv[1] !== undefined && samePath(process.argv[1], fileURLToPath(import.meta.url))) {
    process.exit(main(process.argv.slice(2)));
}
