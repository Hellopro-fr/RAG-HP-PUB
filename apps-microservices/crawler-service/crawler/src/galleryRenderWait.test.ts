import { test } from "node:test";
import assert from "node:assert/strict";
import {
    resolveGalleryRenderWaitMs,
    waitForGalleryRender,
    GALLERY_PLACEHOLDER_SELECTOR,
    GALLERY_RENDERED_SELECTOR,
} from "./galleryRenderWait.js";

type Call = { method: string; args: unknown[] };

function fakePage(opts: { hasPlaceholder?: boolean; evaluateRejects?: boolean; waitRejects?: boolean }) {
    const calls: Call[] = [];
    const page = {
        evaluate: async (expr: string) => {
            calls.push({ method: "evaluate", args: [expr] });
            if (opts.evaluateRejects) throw new Error("Target page, context or browser has been closed");
            return Boolean(opts.hasPlaceholder);
        },
        waitForSelector: async (selector: string, options: unknown) => {
            calls.push({ method: "waitForSelector", args: [selector, options] });
            if (opts.waitRejects) throw new Error("Timeout 15000ms exceeded.");
            return null;
        },
    };
    return { page, calls };
}

function fakeLog() {
    const lines: string[] = [];
    return { log: { info: (m: string) => lines.push(m) }, lines };
}

test("resolveGalleryRenderWaitMs: default 15000 on missing/invalid", () => {
    assert.equal(resolveGalleryRenderWaitMs(undefined), 15000);
    assert.equal(resolveGalleryRenderWaitMs(""), 15000);
    assert.equal(resolveGalleryRenderWaitMs("abc"), 15000);
    assert.equal(resolveGalleryRenderWaitMs("-5"), 15000);
});

test("resolveGalleryRenderWaitMs: 0 disables, positive kept", () => {
    assert.equal(resolveGalleryRenderWaitMs("0"), 0);
    assert.equal(resolveGalleryRenderWaitMs("8000"), 8000);
});

test("waitForGalleryRender: no placeholder -> skipped, no wait", async () => {
    const { page, calls } = fakePage({ hasPlaceholder: false });
    const { log, lines } = fakeLog();
    assert.equal(await waitForGalleryRender(page, "u", log, 15000), "skipped");
    assert.deepEqual(calls.map((c) => c.method), ["evaluate"]);
    assert.ok(String(calls[0].args[0]).includes(GALLERY_PLACEHOLDER_SELECTOR));
    assert.equal(lines.length, 0);
});

test("waitForGalleryRender: placeholder -> waits for the rendered frame", async () => {
    const { page, calls } = fakePage({ hasPlaceholder: true });
    const { log, lines } = fakeLog();
    assert.equal(await waitForGalleryRender(page, "u", log, 15000), "rendered");
    assert.deepEqual(calls[1], {
        method: "waitForSelector",
        args: [GALLERY_RENDERED_SELECTOR, { state: "attached", timeout: 15000 }],
    });
    assert.equal(GALLERY_RENDERED_SELECTOR, ".fotorama__stage__frame");
    assert.equal(lines.length, 0);
});

test("waitForGalleryRender: 0 -> disabled, no DOM query", async () => {
    const { page, calls } = fakePage({ hasPlaceholder: true });
    const { log } = fakeLog();
    assert.equal(await waitForGalleryRender(page, "u", log, 0), "disabled");
    assert.equal(calls.length, 0);
});

test("waitForGalleryRender: wait timeout is swallowed and logged once", async () => {
    const { page } = fakePage({ hasPlaceholder: true, waitRejects: true });
    const { log, lines } = fakeLog();
    assert.equal(await waitForGalleryRender(page, "https://x/p", log, 15000), "timeout");
    assert.equal(lines.length, 1);
    assert.ok(lines[0].startsWith("[gallery-wait]"));
});

test("waitForGalleryRender: placeholder probe error is swallowed", async () => {
    const { page, calls } = fakePage({ evaluateRejects: true });
    const { log } = fakeLog();
    assert.equal(await waitForGalleryRender(page, "u", log, 15000), "error");
    assert.deepEqual(calls.map((c) => c.method), ["evaluate"]);
});
