import { test } from "node:test";
import assert from "node:assert/strict";
import { stripFragment, canonicalGroupKey, queryParamCount, canonicalDedupEnabled } from "./canonicalBase.js";

test("stripFragment removes #...", () => {
  assert.equal(stripFragment("https://x.tld/p?a=1#sec"), "https://x.tld/p?a=1");
  assert.equal(stripFragment("https://x.tld/p"), "https://x.tld/p");
});

test("canonicalGroupKey drops non-pagination query + fragment, keeps pagination", () => {
  const k = canonicalGroupKey;
  assert.equal(k("https://x.tld/c?utm_source=g"), "https://x.tld/c");
  assert.equal(k("https://x.tld/c?color=red"), "https://x.tld/c");
  assert.equal(k("https://x.tld/c#frag"), "https://x.tld/c");
  assert.equal(k("https://x.tld/c"), "https://x.tld/c");
  assert.equal(k("https://x.tld/c?page=2"), "https://x.tld/c?page=2");
  assert.notEqual(k("https://x.tld/c?page=1"), k("https://x.tld/c?page=2"));
});

test("queryParamCount counts params; bare = 0", () => {
  assert.equal(queryParamCount("https://x.tld/c"), 0);
  assert.equal(queryParamCount("https://x.tld/c?a=1&b=2"), 2);
});

test("parse-fail fallbacks", () => {
  assert.equal(stripFragment("not a url#x"), "not a url");
  assert.equal(canonicalGroupKey("not a url"), "not a url");
  assert.equal(queryParamCount("not a url"), Infinity);
});

test("flag default off, reads env true", () => {
  delete process.env.DATASET_CANONICAL_DEDUP_ENABLED;
  assert.equal(canonicalDedupEnabled(), false);
  process.env.DATASET_CANONICAL_DEDUP_ENABLED = "true";
  assert.equal(canonicalDedupEnabled(), true);
  delete process.env.DATASET_CANONICAL_DEDUP_ENABLED;
});
