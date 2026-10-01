import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { writeCanonicalDedupAudit } from "./auditSidecars.js";

test("writes and merges canonical dedup audit", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "cda-"));
  try {
    writeCanonicalDedupAudit(tmp, {
      collapsed: [{ collapsed: "https://ex.tld/p?utm=1", base: "https://ex.tld/p" }],
      removed: 1, rewritten: 0,
    });
    const merged = writeCanonicalDedupAudit(tmp, {
      collapsed: [{ collapsed: "https://ex.tld/p?sid=2", base: "https://ex.tld/p" }],
      removed: 1, rewritten: 0,
    });
    assert.equal(merged.collapsedTotal, 2);
    const j = JSON.parse(fs.readFileSync(path.join(tmp, "_canonical_dedup_audit.json"), "utf-8"));
    assert.equal(j.collapsed_candidates.length, 2);
    assert.equal(j.removed, 2);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("no candidates → no file", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "cda-"));
  try {
    const r = writeCanonicalDedupAudit(tmp, { collapsed: [], removed: 0, rewritten: 0 });
    assert.equal(r.collapsedTotal, 0);
    assert.ok(!fs.existsSync(path.join(tmp, "_canonical_dedup_audit.json")));
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});
