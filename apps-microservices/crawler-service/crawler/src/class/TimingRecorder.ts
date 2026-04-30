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
    /** Crawl identifier propagated into the summary file. */
    crawlId: string;
    /** Directory where timing.jsonl and timing-summary.json are written. */
    outputDir: string;
    /** Cap from DetectionLangueClient — used to compute detect_saturated_pct. */
    detectMaxConcurrency: number;
    /** Periodic summary flush interval (ms). 0 disables. Default 30000. */
    summaryFlushMs?: number;
    /** Call fsync once per N writes for crash durability. Default 50. */
    fsyncEveryN?: number;
    /** "replay" reads existing timing.jsonl into the aggregator before appending; "overwrite" truncates. Default "replay". */
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
            this.flushTimer = setInterval(() => {
                try {
                    this._writeSummary();
                } catch (err) {
                    console.error("TimingRecorder: periodic flush failed", err);
                }
            }, flushMs);
        }
    }

    /**
     * Record one page handler outcome. Best-effort: swallows disk errors
     * with console.error so the route handler is never broken by
     * observability code. After finalize(), this is a no-op.
     */
    recordPage(entry: PageTimingEntry): void {
        addPage(this.state, entry);
        if (this.fd < 0) return;
        try {
            const line = JSON.stringify(entry) + "\n";
            fs.writeSync(this.fd, line);
            this.writeCount++;
            if (this.writeCount % this.fsyncEveryN === 0) {
                try { fs.fsyncSync(this.fd); } catch { /* best-effort */ }
            }
        } catch (err) {
            console.error("TimingRecorder: recordPage write failed", err);
        }
    }

    /**
     * Record one pool snapshot. Aggregator-only; never writes to JSONL
     * (samples are not persisted across restarts).
     */
    recordPoolSample(sample: PoolSample): void {
        addPoolSample(this.state, sample);
    }

    private _writeSummary(): void {
        const summary = buildSummary(this.state);
        const tmpPath = `${this.summaryPath}.tmp`;
        fs.writeFileSync(tmpPath, JSON.stringify(summary, null, 2));
        fs.renameSync(tmpPath, this.summaryPath);
    }

    /**
     * Stop the periodic flush timer, fsync + close the JSONL fd, and write
     * one final summary. Idempotent — safe to call from multiple exit paths.
     */
    async finalize(): Promise<void> {
        if (this.finalized) return;
        this.finalized = true;
        if (this.flushTimer) {
            clearInterval(this.flushTimer);
            this.flushTimer = null;
        }
        if (this.fd >= 0) {
            try { fs.fsyncSync(this.fd); } catch { /* best-effort */ }
            try { fs.closeSync(this.fd); } catch { /* best-effort */ }
            this.fd = -1;
        }
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
