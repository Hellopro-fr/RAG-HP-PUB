import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { cleanDatasetFragments } from "./functions.js";

const withDataset = (name: string, rows: Record<string, unknown>[], fn: () => void) => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "cdf-"));
  const prevCwd = process.cwd();
  try {
    const dir = path.join(tmp, "storage", "datasets", name);
    fs.mkdirSync(dir, { recursive: true });
    rows.forEach((r, i) => fs.writeFileSync(path.join(dir, `${i}.json`), JSON.stringify(r)));
    process.chdir(tmp);
    fn();
  } finally {
    process.chdir(prevCwd);
    fs.rmSync(tmp, { recursive: true, force: true });
  }
};
const listUrls = (name: string) => {
  const dir = path.join("storage", "datasets", name);
  return fs.readdirSync(dir).filter(f => f.endsWith(".json") && !f.startsWith("__"))
    .map(f => JSON.parse(fs.readFileSync(path.join(dir, f), "utf-8")).url).sort();
};

test("flag ON: facet variants with identical content collapse to bare base", () => {
  process.env.DIEZ_PERCLASS_ENABLED = "true";
  process.env.DATASET_CANONICAL_DEDUP_ENABLED = "true";
  withDataset("ex.tld", [
    { url: "https://ex.tld/p", content: "<body><h1>Perceuse</h1></body>" },
    { url: "https://ex.tld/p?utm_source=g", content: "<body><h1>Perceuse</h1></body>" },
    { url: "https://ex.tld/p?sid=42", content: "<body><h1>Perceuse</h1></body>" },
  ], () => {
    const res = cleanDatasetFragments(["ex.tld"]);
    assert.deepEqual(listUrls("ex.tld"), ["https://ex.tld/p"]);
    assert.equal(res.removed, 2);
    const collapsed = JSON.parse(fs.readFileSync("storage/datasets/ex.tld/__collapsed_urls.json", "utf-8"));
    assert.deepEqual(collapsed.sort(), ["https://ex.tld/p?sid=42", "https://ex.tld/p?utm_source=g"]);
    assert.equal(res.collapsedPairs.length, 2);
  });
  delete process.env.DATASET_CANONICAL_DEDUP_ENABLED;
  delete process.env.DIEZ_PERCLASS_ENABLED;
});

test("flag ON: distinct-content facets kept; pagination never merged", () => {
  process.env.DIEZ_PERCLASS_ENABLED = "true";
  process.env.DATASET_CANONICAL_DEDUP_ENABLED = "true";
  withDataset("ex.tld", [
    { url: "https://ex.tld/c?color=red", content: "<body>RED shoes</body>" },
    { url: "https://ex.tld/c?color=blue", content: "<body>BLUE shoes</body>" },
    { url: "https://ex.tld/c?page=1", content: "<body>page one</body>" },
    { url: "https://ex.tld/c?page=2", content: "<body>page two</body>" },
  ], () => {
    const res = cleanDatasetFragments(["ex.tld"]);
    assert.equal(listUrls("ex.tld").length, 4);
    assert.equal(res.removed, 0);
  });
  delete process.env.DATASET_CANONICAL_DEDUP_ENABLED;
  delete process.env.DIEZ_PERCLASS_ENABLED;
});

test("flag OFF: only #-fragment identical siblings collapse (legacy behavior)", () => {
  process.env.DIEZ_PERCLASS_ENABLED = "true";
  delete process.env.DATASET_CANONICAL_DEDUP_ENABLED;
  withDataset("ex.tld", [
    { url: "https://ex.tld/p#a", content: "<body>same</body>" },
    { url: "https://ex.tld/p#b", content: "<body>same</body>" },
    { url: "https://ex.tld/p?utm=1", content: "<body>same</body>" },
  ], () => {
    cleanDatasetFragments(["ex.tld"]);
    const urls = listUrls("ex.tld");
    assert.ok(urls.includes("https://ex.tld/p?utm=1"));
    assert.ok(urls.includes("https://ex.tld/p"));
    assert.ok(!fs.existsSync("storage/datasets/ex.tld/__collapsed_urls.json"));
  });
  delete process.env.DIEZ_PERCLASS_ENABLED;
});

test("flag ON: SPA hash routes — distinct root preserved, dup route collapsed, no duplicate-url survivors", () => {
  process.env.DIEZ_PERCLASS_ENABLED = "true";
  process.env.DATASET_CANONICAL_DEDUP_ENABLED = "true";
  withDataset("ex.tld", [
    { url: "https://ex.tld/app", content: "<body><h1>Home dashboard</h1></body>" },
    { url: "https://ex.tld/app#/products", content: "<body><h1>Product catalog</h1></body>" },
    { url: "https://ex.tld/app#/products?sort=asc", content: "<body><h1>Product catalog</h1></body>" },
  ], () => {
    const res = cleanDatasetFragments(["ex.tld"]);
    const urls = listUrls("ex.tld");
    assert.equal(res.removed, 1);
    assert.ok(urls.includes("https://ex.tld/app"));
    assert.ok(urls.includes("https://ex.tld/app#/products"));
    assert.equal(new Set(urls).size, urls.length); // no duplicate-url survivors
  });
  delete process.env.DATASET_CANONICAL_DEDUP_ENABLED;
  delete process.env.DIEZ_PERCLASS_ENABLED;
});

test("flag ON: empty/whitespace content never collapses (loss-proof)", () => {
  process.env.DIEZ_PERCLASS_ENABLED = "true";
  process.env.DATASET_CANONICAL_DEDUP_ENABLED = "true";
  withDataset("ex.tld", [
    { url: "https://ex.tld/a?x=1", content: "" },
    { url: "https://ex.tld/a?y=2", content: "   " },
  ], () => {
    const res = cleanDatasetFragments(["ex.tld"]);
    assert.equal(res.removed, 0);
    assert.equal(listUrls("ex.tld").length, 2);
  });
  delete process.env.DATASET_CANONICAL_DEDUP_ENABLED;
  delete process.env.DIEZ_PERCLASS_ENABLED;
});
