import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { cleanDatasetFragments } from "./functions.js";

const mkRow = (dir: string, n: string, url: string, content: string) =>
    fs.writeFileSync(path.join(dir, `${n}.json`), JSON.stringify({ url, content, title: "t" }));

test("content-collision: collapse identical, keep distinct, keep lone, ignore no-#", () => {
    process.env.DIEZ_PERCLASS_ENABLED = "true";
    const name = "test-cc.example";
    const dir = path.join("storage", "datasets", name);
    fs.rmSync(dir, { recursive: true, force: true });
    fs.mkdirSync(dir, { recursive: true });
    mkRow(dir, "1", "https://x.fr/p#a", "same body text here");
    mkRow(dir, "2", "https://x.fr/p#b", "same body text here");
    mkRow(dir, "3", "https://x.fr/q#a", "alpha body");
    mkRow(dir, "4", "https://x.fr/q#b", "beta body");
    mkRow(dir, "5", "https://x.fr/r#x", "lone body");
    mkRow(dir, "6", "https://x.fr/s", "plain body");
    try {
        const res = cleanDatasetFragments([name, "does-not-exist"]);
        assert.equal(res.removed, 1);
        assert.equal(res.rewritten, 1);
        assert.equal(res.collisionsKept, 2);
        const urls = fs.readdirSync(dir).filter(f => f.endsWith(".json"))
            .map(f => JSON.parse(fs.readFileSync(path.join(dir, f), "utf-8")).url).sort();
        assert.deepEqual(urls, [
            "https://x.fr/p", "https://x.fr/q#a", "https://x.fr/q#b",
            "https://x.fr/r#x", "https://x.fr/s",
        ]);
    } finally {
        fs.rmSync(dir, { recursive: true, force: true });
        delete process.env.DIEZ_PERCLASS_ENABLED;
    }
});

test("flag off: legacy blind strip+dedup unchanged", () => {
    delete process.env.DIEZ_PERCLASS_ENABLED;
    const name = "test-legacy.example";
    const dir = path.join("storage", "datasets", name);
    fs.rmSync(dir, { recursive: true, force: true });
    fs.mkdirSync(dir, { recursive: true });
    mkRow(dir, "1", "https://x.fr/p#a", "c1");
    mkRow(dir, "2", "https://x.fr/p#b", "c2");
    try {
        const res = cleanDatasetFragments([name]);
        assert.equal(res.removed, 1);
        const urls = fs.readdirSync(dir).filter(f => f.endsWith(".json"))
            .map(f => JSON.parse(fs.readFileSync(path.join(dir, f), "utf-8")).url);
        assert.deepEqual(urls, ["https://x.fr/p"]);
    } finally {
        fs.rmSync(dir, { recursive: true, force: true });
    }
});
