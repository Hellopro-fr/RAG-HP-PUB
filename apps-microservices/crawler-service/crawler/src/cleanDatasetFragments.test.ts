import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { cleanDatasetFragments } from "./functions.js";

test("strips # and dedupes dataset rows; missing dir no-op", () => {
    const name = "test-clean.example";
    const dir = path.join("storage", "datasets", name);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "1.json"), JSON.stringify({ url: "https://x.fr/p#a", content: "c1", title: "t" }));
    fs.writeFileSync(path.join(dir, "2.json"), JSON.stringify({ url: "https://x.fr/p#b", content: "c2", title: "t" })); // dup of #a once stripped
    fs.writeFileSync(path.join(dir, "3.json"), JSON.stringify({ url: "https://x.fr/q", content: "c3", title: "t" }));

    const res = cleanDatasetFragments([name, "does-not-exist"]);
    assert.equal(res.rewritten >= 1, true);
    assert.equal(res.removed, 1); // one of the two p#x files removed

    const remaining = fs.readdirSync(dir).filter(f => f.endsWith(".json"));
    const urls = remaining.map(f => JSON.parse(fs.readFileSync(path.join(dir, f), "utf-8")).url).sort();
    assert.deepEqual(urls, ["https://x.fr/p", "https://x.fr/q"]);

    fs.rmSync(dir, { recursive: true, force: true });
});
