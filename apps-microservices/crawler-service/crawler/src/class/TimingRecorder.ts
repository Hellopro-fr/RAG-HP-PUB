import * as fs from "node:fs";
import * as path from "node:path";
import {
    addPage,
    addPoolSample,
    buildSummary,
    createAggregator,
} from "../timing/aggregator.js";
import type {
    AggregatorState,
    PageTimingEntry,
    PoolSample,
} from "../timing/types.js";

export interface TimingRecorderOptions {
    crawlId: string;
    outputDir: string;
    detectMaxConcurrency: number;
    summaryFlushMs?: number;
    fsyncEveryN?: number;
    resumePolicy?: "replay" | "overwrite";
}

export class TimingRecorder {
    private state: AggregatorState;
    private outputDir: string;
    private jsonlPath: string;
    private summaryPath: string;
    private fd: number;
    private writeCount = 0;
    private fsyncEveryN: number;
    private flushTimer: NodeJS.Timeout | null = null;
    private finalized = false;

    constructor(opts: TimingRecorderOptions) {
        const flushMs = opts.summaryFlushMs ?? 30000;
        this.fsyncEveryN = opts.fsyncEveryN ?? 50;
        this.state = createAggregator(opts.crawlId, opts.detectMaxConcurrency);
        this.outputDir = opts.outputDir;
        this.jsonlPath = path.join(opts.outputDir, "timing.jsonl");
        this.summaryPath = path.join(opts.outputDir, "timing-summary.json");

        fs.mkdirSync(opts.outputDir, { recursive: true });

        const policy = opts.resumePolicy ?? "replay";
        if (fs.existsSync(this.jsonlPath)) {
            if (policy === "replay") {
                const existing = fs.readFileSync(this.jsonlPath, "utf-8");
                for (const line of existing.split("\n")) {
                    if (!line.trim()) continue;
                    try {
                        const entry = JSON.parse(line) as PageTimingEntry;
                        addPage(this.state, entry);
                    } catch {
                        // Skip malformed lines silently — partial trace from a crash.
                    }
                }
                this.fd = fs.openSync(this.jsonlPath, "a");
            } else {
                this.fd = fs.openSync(this.jsonlPath, "w");
            }
        } else {
            this.fd = fs.openSync(this.jsonlPath, "w");
        }

        if (flushMs > 0) {
            this.flushTimer = setInterval(() => this._writeSummary(), flushMs);
        }
    }

    recordPage(entry: PageTimingEntry): void {
        addPage(this.state, entry);
        const line = JSON.stringify(entry) + "\n";
        fs.writeSync(this.fd, line);
        this.writeCount++;
        if (this.writeCount % this.fsyncEveryN === 0) {
            try { fs.fsyncSync(this.fd); } catch { /* best-effort */ }
        }
    }

    recordPoolSample(sample: PoolSample): void {
        addPoolSample(this.state, sample);
    }

    private _writeSummary(): void {
        const summary = buildSummary(this.state);
        const tmpPath = `${this.summaryPath}.tmp`;
        fs.writeFileSync(tmpPath, JSON.stringify(summary, null, 2));
        fs.renameSync(tmpPath, this.summaryPath);
    }

    async finalize(): Promise<void> {
        if (this.finalized) return;
        this.finalized = true;
        if (this.flushTimer) {
            clearInterval(this.flushTimer);
            this.flushTimer = null;
        }
        try { fs.fsyncSync(this.fd); } catch { /* best-effort */ }
        try { fs.closeSync(this.fd); } catch { /* best-effort */ }
        this._writeSummary();
    }

    /**
     * Returns the current summary without writing it to disk. Useful for the
     * end-of-run console block in main.ts.
     */
    snapshot() {
        return buildSummary(this.state);
    }
}
