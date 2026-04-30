import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { TimingRecorder } from "../class/TimingRecorder.js";
import type { PageTimingEntry, PoolSample } from "../timing/types.js";

let passed = 0;
let failed = 0;

function assert(cond: boolean, msg: string) {
    if (cond) passed++;
    else { failed++; console.error(`FAIL: ${msg}`); }
}

function tmpDir(): string {
    return fs.mkdtempSync(path.join(os.tmpdir(), "timing-rec-"));
}

function mkEntry(i: number): PageTimingEntry {
    return {
        url: `https://x/${i}`, t: 1000 + i, wait_ms: 1, nav_ms: 100, pre_detect_ms: 1,
        detect_ms: 50, post_ms: 1, total_ms: 153, detect_ok: true,
    };
}

function mkSample(t: number): PoolSample {
    return {
        t,
        crawlee: { currentConcurrency: 1, desiredConcurrency: 1, maxConcurrency: 5 },
        detect: { activeCount: 1, pendingCount: 0 },
        memory: { used_mb: 100, budget_mb: 1000, ratio: 0.1 },
        rolling: { pages_per_min: 30 },
    };
}

// 1. JSONL line per recordPage call
async function test1() {
    const dir = tmpDir();
    const r = new TimingRecorder({ crawlId: "t1", outputDir: dir, detectMaxConcurrency: 5 });
    r.recordPage(mkEntry(1));
    r.recordPage(mkEntry(2));
    await r.finalize();
    const lines = fs.readFileSync(path.join(dir, "timing.jsonl"), "utf-8").trim().split("\n");
    assert(lines.length === 2, `2 JSONL lines, got ${lines.length}`);
    assert(JSON.parse(lines[0]).url === "https://x/1", "first line url");
}

// 2. finalize writes timing-summary.json with correct shape
async function test2() {
    const dir = tmpDir();
    const r = new TimingRecorder({ crawlId: "t2", outputDir: dir, detectMaxConcurrency: 5 });
    r.recordPage(mkEntry(1));
    r.recordPoolSample(mkSample(1));
    await r.finalize();
    const sum = JSON.parse(fs.readFileSync(path.join(dir, "timing-summary.json"), "utf-8"));
    assert(sum.crawl_id === "t2", "crawl_id captured");
    assert(sum.pages_total === 1, "pages_total = 1");
    assert(typeof sum.phases.detect_ms.median === "number", "phase shape present");
    assert(typeof sum.pool.crawlee_avg_concurrency === "number", "pool shape present");
}

// 3. periodic flush writes summary mid-run
async function test3() {
    const dir = tmpDir();
    const r = new TimingRecorder({
        crawlId: "t3", outputDir: dir, detectMaxConcurrency: 5,
        summaryFlushMs: 50,
    });
    r.recordPage(mkEntry(1));
    await new Promise((res) => setTimeout(res, 120)); // allow 2 ticks
    const sumPath = path.join(dir, "timing-summary.json");
    assert(fs.existsSync(sumPath), "summary written by periodic timer");
    const sum = JSON.parse(fs.readFileSync(sumPath, "utf-8"));
    assert(sum.pages_total === 1, "periodic summary reflects 1 page");
    await r.finalize();
}

// 4. replay policy reads existing JSONL into aggregator
async function test4() {
    const dir = tmpDir();
    fs.writeFileSync(path.join(dir, "timing.jsonl"),
        JSON.stringify(mkEntry(1)) + "\n" + JSON.stringify(mkEntry(2)) + "\n");
    const r = new TimingRecorder({
        crawlId: "t4", outputDir: dir, detectMaxConcurrency: 5,
        resumePolicy: "replay",
    });
    r.recordPage(mkEntry(3));
    await r.finalize();
    const sum = JSON.parse(fs.readFileSync(path.join(dir, "timing-summary.json"), "utf-8"));
    assert(sum.pages_total === 3, `replay: 3 pages total, got ${sum.pages_total}`);
    const lines = fs.readFileSync(path.join(dir, "timing.jsonl"), "utf-8").trim().split("\n");
    assert(lines.length === 3, "JSONL contains 2 prior + 1 new = 3 lines");
}

// 5. overwrite policy truncates JSONL
async function test5() {
    const dir = tmpDir();
    fs.writeFileSync(path.join(dir, "timing.jsonl"),
        JSON.stringify(mkEntry(1)) + "\n");
    const r = new TimingRecorder({
        crawlId: "t5", outputDir: dir, detectMaxConcurrency: 5,
        resumePolicy: "overwrite",
    });
    r.recordPage(mkEntry(99));
    await r.finalize();
    const lines = fs.readFileSync(path.join(dir, "timing.jsonl"), "utf-8").trim().split("\n");
    assert(lines.length === 1, "overwrite: only 1 line after restart");
    assert(JSON.parse(lines[0]).url === "https://x/99", "overwrite: kept new entry only");
}

(async () => {
    await test1();
    await test2();
    await test3();
    await test4();
    await test5();
    console.log(`TimingRecorder: ${passed} passed, ${failed} failed`);
    if (failed > 0 || passed === 0) process.exit(1);
})();
