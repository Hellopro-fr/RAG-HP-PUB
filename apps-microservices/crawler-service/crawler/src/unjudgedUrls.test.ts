import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { ensureUnjudgedSidecar, recordUnjudgedUrls, UNJUDGED_SIDECAR } from "./unjudgedUrls.js";

/** Temp storage root + chdir, same harness as functions.canonicalDedup.test.ts. */
const withStorage = (fn: (dir: string) => void) => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "unjudged-"));
    const prevCwd = process.cwd();
    try {
        process.chdir(tmp);
        fn(path.join("storage", "datasets", "ex.tld"));
    } finally {
        process.chdir(prevCwd);
        fs.rmSync(tmp, { recursive: true, force: true });
    }
};
const readSidecar = (dir: string) =>
    JSON.parse(fs.readFileSync(path.join(dir, UNJUDGED_SIDECAR), "utf-8"));

test("records both identities, deduplicated, and creates the dataset dir if absent", () => {
    withStorage((dir) => {
        // No redirect: request.url === loadedUrl -> one entry, not two.
        recordUnjudgedUrls("ex.tld", ["https://ex.tld/a", "https://ex.tld/a"]);
        assert.deepEqual(readSidecar(dir), ["https://ex.tld/a"]);

        // Redirect: the seeded identity (Milvus) AND the loaded one are both kept.
        recordUnjudgedUrls("ex.tld", ["https://ex.tld/old", "https://ex.tld/new"]);
        assert.deepEqual(readSidecar(dir), [
            "https://ex.tld/a", "https://ex.tld/old", "https://ex.tld/new",
        ]);
    });
});

test("merges instead of clobbering (OOM relaunch keeps pass-1 entries)", () => {
    withStorage((dir) => {
        fs.mkdirSync(dir, { recursive: true });
        fs.writeFileSync(path.join(dir, UNJUDGED_SIDECAR), JSON.stringify(["https://ex.tld/pass1"]));
        recordUnjudgedUrls("ex.tld", ["https://ex.tld/pass2"]);
        assert.deepEqual(readSidecar(dir), ["https://ex.tld/pass1", "https://ex.tld/pass2"]);
    });
});

test("a corrupt sidecar is replaced, never propagated as an empty protection list", () => {
    withStorage((dir) => {
        fs.mkdirSync(dir, { recursive: true });
        fs.writeFileSync(path.join(dir, UNJUDGED_SIDECAR), "{ truncated");
        recordUnjudgedUrls("ex.tld", ["https://ex.tld/a", null, undefined, ""]);
        assert.deepEqual(readSidecar(dir), ["https://ex.tld/a"]);
    });
});

test("ensureUnjudgedSidecar writes [] when absent — 'detection answered' ≠ 'crawler predates the fix'", () => {
    withStorage((dir) => {
        ensureUnjudgedSidecar("ex.tld");
        assert.deepEqual(readSidecar(dir), []);
    });
});

test("ensureUnjudgedSidecar never clobbers an existing record", () => {
    withStorage((dir) => {
        recordUnjudgedUrls("ex.tld", ["https://ex.tld/a"]);
        ensureUnjudgedSidecar("ex.tld"); // e.g. an OOM relaunch re-running startup
        assert.deepEqual(readSidecar(dir), ["https://ex.tld/a"]);
    });
});

test("the sidecar is invisible to stored_files_count (the '__' exclusion the BO's insufficientData rests on)", () => {
    withStorage((dir) => {
        fs.mkdirSync(dir, { recursive: true });
        fs.writeFileSync(path.join(dir, "0.json"), JSON.stringify({ url: "https://ex.tld/a" }));
        recordUnjudgedUrls("ex.tld", ["https://ex.tld/b"]);
        // Same predicate as _count_files_in_dir (crawler_manager.py:155) and
        // cleanDatasetFragments (functions.ts:1956): '__'-prefixed names are not rows.
        const counted = fs.readdirSync(dir).filter((f) => !f.startsWith("__"));
        assert.deepEqual(counted, ["0.json"]);
    });
});

test("a no-name dataset is a no-op, not a 'storage/datasets/undefined' write", () => {
    withStorage(() => {
        recordUnjudgedUrls(undefined, ["https://ex.tld/a"]);
        ensureUnjudgedSidecar("");
        assert.equal(fs.existsSync("storage"), false);
    });
});
