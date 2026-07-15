import { test } from "node:test";
import assert from "node:assert/strict";
import { matchesMainSite } from "./isMainSite.js";

// The bug: `site` is the raw --site (may carry a #fragment), but Crawlee strips the
// fragment from request.url, so a raw `request.url === site` wrongly returns false.
test("fragment on site only still matches the seed (the isMainSite bug)", () => {
    assert.equal(
        matchesMainSite(
            "https://www.artemide.com/fr/privacy-policy",
            "https://www.artemide.com/fr/privacy-policy#generalPolicy-collapseGeneralIntro",
        ),
        true,
    );
});

test("identical URLs with no fragment match (unchanged behavior)", () => {
    assert.equal(
        matchesMainSite("https://automation.honeywell.com/fr/fr", "https://automation.honeywell.com/fr/fr"),
        true,
    );
});

test("fragment on both sides matches", () => {
    assert.equal(matchesMainSite("https://x.com/p#a", "https://x.com/p#b"), true);
});

test("a genuinely different page is not the seed", () => {
    assert.equal(matchesMainSite("https://x.com/other", "https://x.com/home#top"), false);
});

test("query params are still compared (differ -> not the seed)", () => {
    assert.equal(matchesMainSite("https://x.com/?a=1", "https://x.com/?a=2#f"), false);
    assert.equal(matchesMainSite("https://x.com/?a=1", "https://x.com/?a=1#f"), true);
});
