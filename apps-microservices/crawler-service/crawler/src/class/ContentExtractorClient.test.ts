import { test } from "node:test";
import assert from "node:assert/strict";
import { ContentExtractorClient } from "./ContentExtractorClient.js";

const err = (status: number) => Object.assign(new Error(`HTTP ${status}`), { response: { status } });

test("returns content on 200 (empty allowed)", async () => {
    const c = new ContentExtractorClient("http://x", async () => ({ data: { content: "" } }));
    assert.equal(await c.clean("<p>hi</p>"), "");
    const c2 = new ContentExtractorClient("http://x", async () => ({ data: { content: "main text" } }));
    assert.equal(await c2.clean("<p>hi</p>"), "main text");
});

test("throws on 413/422 without retry", async () => {
    let calls = 0;
    const c = new ContentExtractorClient("http://x", async () => { calls++; throw err(413); });
    await assert.rejects(() => c.clean("<p>x</p>"));
    assert.equal(calls, 1);
});

test("retries once on 500 then throws", async () => {
    let calls = 0;
    const c = new ContentExtractorClient("http://x", async () => { calls++; throw err(500); });
    await assert.rejects(() => c.clean("<p>x</p>"));
    assert.equal(calls, 2);
});
