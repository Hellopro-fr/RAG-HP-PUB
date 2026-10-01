import { execSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { fileURLToPath } from "node:url";
import { TimingRecorder } from "../class/TimingRecorder.js";
import type { PageTimingEntry, PoolSample } from "../timing/types.js";

let passed = 0;
let failed = 0;

function assert(cond: boolean, msg: string): void {
    if (cond) passed++;
    else { failed++; console.error(`FAIL: ${msg}`); }
}

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function mkEntry(i: number, navMs: number, detectMs: number): PageTimingEntry {
    return {
        url: `https://example.com/${i}`,
        t: 1_000_000 + i * 100,
        wait_ms: 0,
        nav_ms: navMs,
        pre_detect_ms: 5,
        detect_ms: detectMs,
        post_ms: 10,
        total_ms: navMs + detectMs + 15,
        detect_ok: true,
    };
}

function mkPool(t: number, active: number, pending: number): PoolSample {
    return {
        t,
        crawlee: { currentConcurrency: 3, desiredConcurrency: 3, maxConcurrency: 5 },
        detect: { activeCount: active, pendingCount: pending },
        memory: { used_mb: 100, budget_mb: 1000, ratio: 0.1 },
        rolling: { pages_per_min: 30 },
    };
}

// 1. Happy path: 5 entries, finalize, both files exist and are well-formed
async function test1(): Promise<void> {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "timing-int-"));
    const r = new TimingRecorder({ crawlId: "int-1", outputDir: dir, detectMaxConcurrency: 5 });
    for (let i = 1; i <= 5; i++) r.recordPage(mkEntry(i, 3000, 500));
    r.recordPoolSample(mkPool(1, 5, 2));
    r.recordPoolSample(mkPool(2, 5, 1));
    await r.finalize();

    const jsonl = fs.readFileSync(path.join(dir, "timing.jsonl"), "utf-8").trim().split("\n");
    assert(jsonl.length === 5, `5 JSONL lines, got ${jsonl.length}`);

    const sum = JSON.parse(fs.readFileSync(path.join(dir, "timing-summary.json"), "utf-8"));
    assert(sum.pages_total === 5, "summary pages_total = 5");
    assert(sum.phases.nav_ms.share_of_total_pct > sum.phases.detect_ms.share_of_total_pct,
        "nav_ms is the dominant phase (3000ms vs 500ms detect)");
    assert(sum.pool.detect_saturated_pct === 100,
        `both samples saturated (active=5, pending>0); got ${sum.pool.detect_saturated_pct}`);
}

// 2. Crash simulation: write 3 entries, do NOT call finalize, run post-hoc tool
async function test2(): Promise<void> {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "timing-int-"));
    // Don't keep the recorder reference — simulate orphaned state.
    {
        const r = new TimingRecorder({
            crawlId: "int-2", outputDir: dir, detectMaxConcurrency: 5,
            summaryFlushMs: 0, // disable periodic flush
        });
        r.recordPage(mkEntry(1, 100, 50));
        r.recordPage(mkEntry(2, 200, 60));
        r.recordPage(mkEntry(3, 300, 70));
        // Don't call finalize. fd will be closed by GC eventually but the
        // already-flushed JSONL bytes are durable.
    }

    // Read what's on disk (should be 3 lines from the writes).
    const jsonlPath = path.join(dir, "timing.jsonl");
    const jsonl = fs.readFileSync(jsonlPath, "utf-8").trim().split("\n");
    assert(jsonl.length === 3, `crash trace has 3 lines, got ${jsonl.length}`);

    // Now run the post-hoc tool to reconstruct the summary.
    const cliPath = path.join(__dirname, "..", "tools", "timing-summary.ts");
    execSync(`npx tsx ${cliPath} ${jsonlPath}`, { stdio: "pipe" });
    const sum = JSON.parse(fs.readFileSync(path.join(dir, "timing-summary.json"), "utf-8"));
    assert(sum.pages_total === 3, "post-hoc summary recovered 3 pages");
}

(async () => {
    await test1();
    await test2();
    console.log(`timing_integration: ${passed} passed, ${failed} failed`);
    if (failed > 0 || passed === 0) process.exit(1);
})();
