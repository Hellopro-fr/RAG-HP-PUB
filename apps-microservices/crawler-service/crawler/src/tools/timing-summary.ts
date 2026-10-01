#!/usr/bin/env node
import * as fs from "node:fs";
import * as path from "node:path";
import {
    addPage,
    buildSummary,
    createAggregator,
} from "../timing/aggregator.js";
import type { PageTimingEntry } from "../timing/types.js";

function parseArgs(argv: string[]): { input: string; out: string | null } {
    const [, , ...args] = argv;
    if (args.length === 0) {
        console.error("Usage: timing-summary.ts <input-jsonl> [--out <path>]");
        process.exit(2);
    }
    const input: string = args[0];
    let out: string | null = null;
    for (let i = 1; i < args.length; i++) {
        if (args[i] === "--out" && i + 1 < args.length) {
            out = args[i + 1];
            i++;
        }
    }
    return { input, out };
}

function main(): void {
    const { input, out } = parseArgs(process.argv);
    const inputAbs = path.resolve(input);
    const outAbs = out
        ? path.resolve(out)
        : path.join(path.dirname(inputAbs), "timing-summary.json");

    if (!fs.existsSync(inputAbs)) {
        console.error(`Input not found: ${inputAbs}`);
        process.exit(1);
    }

    // crawlId derived from the parent dir name (e.g. storage/6066 -> "6066").
    const crawlId = path.basename(path.dirname(inputAbs));
    const detectMaxConcurrency = parseInt(process.env.DETECTION_MAX_CONCURRENCY ?? "5");
    const aggregator = createAggregator(crawlId, detectMaxConcurrency);

    const raw = fs.readFileSync(inputAbs, "utf-8");
    for (const line of raw.split("\n")) {
        if (!line.trim()) continue;
        try {
            const entry = JSON.parse(line) as PageTimingEntry;
            addPage(aggregator, entry);
        } catch (err) {
            console.error(`Skipping malformed line: ${(err as Error).message}`);
        }
    }

    const summary = buildSummary(aggregator);
    fs.writeFileSync(outAbs, JSON.stringify(summary, null, 2));
    console.log(`Wrote summary: ${outAbs} (${summary.pages_total} pages)`);
}

main();
