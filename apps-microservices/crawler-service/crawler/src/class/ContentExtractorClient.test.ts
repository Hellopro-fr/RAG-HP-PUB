import { test } from "node:test";
import assert from "node:assert/strict";
import { ContentExtractorClient, ContentExtractorError } from "./ContentExtractorClient.js";

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

const errWithHeaders = (status: number, headers: Record<string, string> = {}) =>
    Object.assign(new Error(`HTTP ${status}`), { response: { status, headers } });

test("503 retries (honouring Retry-After) then throws a transient error", async () => {
    let calls = 0;
    const c = new ContentExtractorClient("http://x", async () => { calls++; throw errWithHeaders(503, { "retry-after": "0" }); });
    await assert.rejects(
        () => c.clean("<p>x</p>"),
        (e: unknown) => e instanceof ContentExtractorError && e.transient === true && e.status === 503,
    );
    assert.equal(calls, 2); // one retry after the (zero) backoff
});

test("413 throws a terminal (non-transient) error without retry", async () => {
    let calls = 0;
    const c = new ContentExtractorClient("http://x", async () => { calls++; throw errWithHeaders(413); });
    await assert.rejects(
        () => c.clean("<p>x</p>"),
        (e: unknown) => e instanceof ContentExtractorError && e.transient === false,
    );
    assert.equal(calls, 1);
});

test("network error (no response) throws a transient error after one retry", async () => {
    let calls = 0;
    const c = new ContentExtractorClient("http://x", async () => { calls++; throw new Error("ECONNREFUSED"); });
    await assert.rejects(
        () => c.clean("<p>x</p>"),
        (e: unknown) => e instanceof ContentExtractorError && e.transient === true,
    );
    assert.equal(calls, 2);
});
