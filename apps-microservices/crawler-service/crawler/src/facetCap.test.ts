import { test } from "node:test";
import assert from "node:assert/strict";
import { pathBaseKey, variantSignature } from "./urlBase.js";
import { recordVariant, isOverCap } from "./facetCap.js";

test("pathBaseKey drops query + fragment", () => {
    assert.equal(pathBaseKey("https://x.fr/cat/?a=1&b=2#z"), "https://x.fr/cat/");
    assert.equal(pathBaseKey("https://x.fr/cat/page/2/?a=1"), "https://x.fr/cat/page/2/");
});

test("variantSignature sorts and drops pagination", () => {
    assert.equal(variantSignature("https://x.fr/c/?b=2&a=1"), "a=1&b=2");
    assert.equal(variantSignature("https://x.fr/c/?page=3&min_price=1"), "min_price=1");
    assert.equal(variantSignature("https://x.fr/c/"), "");
});

test("cap trips once a base has >= K distinct signatures", () => {
    const m = new Map<string, Set<string>>();
    recordVariant(m, "https://x.fr/c/?min_price=1");
    recordVariant(m, "https://x.fr/c/?min_price=2");
    assert.equal(isOverCap(m, "https://x.fr/c/?min_price=3", 2), true);
    assert.equal(isOverCap(m, "https://x.fr/other/?z=1", 2), false);
    assert.equal(isOverCap(m, "https://x.fr/c/?min_price=1", 5), false);
});

test("recordVariant dedups identical signatures + ignores no-query urls", () => {
    const m = new Map<string, Set<string>>();
    recordVariant(m, "https://x.fr/c/?a=1");
    recordVariant(m, "https://x.fr/c/?a=1");
    assert.equal(m.get("https://x.fr/c/")!.size, 1);
    recordVariant(m, "https://x.fr/c/");
    assert.equal(m.get("https://x.fr/c/")!.size, 1);
});
