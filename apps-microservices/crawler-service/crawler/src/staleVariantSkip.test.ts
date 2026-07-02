import { test } from "node:test";
import assert from "node:assert/strict";
import { NonRetryableError } from "crawlee";
import { StaleVariantSkip, QUEUE_PURGE_ENABLED } from "./staleVariantSkip.js";

test("StaleVariantSkip is a NonRetryableError carrying a stable marker + url", () => {
    const e = new StaleVariantSkip("https://x.fr/p?ref=1", "https://x.fr/p");
    assert.ok(e instanceof NonRetryableError);
    assert.ok(e.message.includes("StaleVariantSkip"));
    assert.ok(e.message.includes("https://x.fr/p?ref=1"));
    assert.equal(e.stripped, "https://x.fr/p");
});

test("QUEUE_PURGE_ENABLED defaults to a boolean", () => {
    assert.equal(typeof QUEUE_PURGE_ENABLED, "boolean");
});
