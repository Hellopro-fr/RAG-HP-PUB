import { execSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { fileURLToPath } from "node:url";

let passed = 0;
let failed = 0;

function assert(cond: boolean, msg: string): void {
    if (cond) passed++;
    else { failed++; console.error(`FAIL: ${msg}`); }
}

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const cliPath = path.join(__dirname, "..", "tools", "timing-summary.ts");

// 1. Empty JSONL produces zero-page summary
{
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "timing-tool-"));
    const jsonl = path.join(dir, "timing.jsonl");
    fs.writeFileSync(jsonl, "");
    execSync(`npx tsx ${cliPath} ${jsonl}`, { stdio: "pipe" });
    const sum = JSON.parse(fs.readFileSync(path.join(dir, "timing-summary.json"), "utf-8"));
    assert(sum.pages_total === 0, "empty input -> 0 pages");
}

// 2. Three-page JSONL produces correct totals
{
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "timing-tool-"));
    const jsonl = path.join(dir, "timing.jsonl");
    const lines = [
        { url: "https://x/1", t: 1000, wait_ms: 0, nav_ms: 100, pre_detect_ms: 0, detect_ms: 50, post_ms: 0, total_ms: 150 },
        { url: "https://x/2", t: 1200, wait_ms: 0, nav_ms: 200, pre_detect_ms: 0, detect_ms: 60, post_ms: 0, total_ms: 260 },
        { url: "https://x/3", t: 1500, wait_ms: 0, nav_ms: 300, pre_detect_ms: 0, detect_ms: 70, post_ms: 0, total_ms: 370 },
    ];
    fs.writeFileSync(jsonl, lines.map((l: object) => JSON.stringify(l)).join("\n") + "\n");
    execSync(`npx tsx ${cliPath} ${jsonl}`, { stdio: "pipe" });
    const sum = JSON.parse(fs.readFileSync(path.join(dir, "timing-summary.json"), "utf-8"));
    assert(sum.pages_total === 3, "3 pages aggregated");
    assert(sum.phases.nav_ms.median === 200, `nav median = 200, got ${sum.phases.nav_ms.median}`);
}

// 3. --out flag overrides output path
{
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "timing-tool-"));
    const jsonl = path.join(dir, "timing.jsonl");
    fs.writeFileSync(jsonl, "");
    const outPath = path.join(dir, "custom-out.json");
    execSync(`npx tsx ${cliPath} ${jsonl} --out ${outPath}`, { stdio: "pipe" });
    assert(fs.existsSync(outPath), "--out path was used");
    assert(!fs.existsSync(path.join(dir, "timing-summary.json")), "default path NOT written when --out is given");
}

console.log(`timing_summary_tool: ${passed} passed, ${failed} failed`);
if (failed > 0 || passed === 0) process.exit(1);
