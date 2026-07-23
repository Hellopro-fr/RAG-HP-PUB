import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { loadDatasetUrlsGenerator } from "./functions.js";

const collect = async (gen: AsyncGenerator<string>) => {
  const out: string[] = [];
  for await (const u of gen) out.push(u);
  return out.sort();
};

test("yields row urls + collapsed-sidecar urls, skips __ files", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "ldu-"));
  const prevCwd = process.cwd();
  try {
    const cwd = path.join(tmp, "current");
    const dsDir = path.join(tmp, "prev", "storage", "datasets", "ex.tld");
    fs.mkdirSync(cwd, { recursive: true });
    fs.mkdirSync(dsDir, { recursive: true });
    fs.writeFileSync(path.join(dsDir, "0.json"), JSON.stringify({ url: "https://ex.tld/p" }));
    fs.writeFileSync(path.join(dsDir, "1.json"), JSON.stringify({ url: "https://ex.tld/q" }));
    fs.writeFileSync(path.join(dsDir, "__collapsed_urls.json"),
      JSON.stringify(["https://ex.tld/p?utm=1", "https://ex.tld/p?sid=2"]));
    process.chdir(cwd);
    const urls = await collect(loadDatasetUrlsGenerator("prev", "ex.tld"));
    assert.deepEqual(urls, [
      "https://ex.tld/p", "https://ex.tld/p?sid=2", "https://ex.tld/p?utm=1", "https://ex.tld/q",
    ]);
  } finally {
    process.chdir(prevCwd);
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
