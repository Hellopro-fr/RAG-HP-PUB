import { test } from "node:test";
import assert from "node:assert/strict";
import { facetParamsForCms } from "./cmsFacetLists.js";
import { LANGUAGE_PARAMS } from "./urlBase.js";

test("WordPress list carries WooCommerce facets, excludes identity", () => {
    const l = facetParamsForCms("WordPress");
    assert.ok(l.includes("min_price") && l.includes("stock_status") && l.includes("orderby"));
    assert.ok(!l.includes("product_cat") && !l.includes("p"));
});
test("case-insensitive label match", () => {
    assert.deepEqual(facetParamsForCms("prestashop"), facetParamsForCms("PrestaShop"));
});
test("empty / unknown cms -> no list", () => {
    assert.deepEqual(facetParamsForCms(""), []);
    assert.deepEqual(facetParamsForCms("Drupal"), []);
    assert.deepEqual(facetParamsForCms(undefined as any), []);
});

// A CMS facet list is merged straight into `toRemove` at startup (main.ts, queue-purge
// denylist Layer A), which is a THIRD write path into `toRemove` — separate from tier-2
// sampling and from the persisted-decision rehydration, and ungated by QM_TIER2_ENABLED.
// A language param landing in one of these curated lists would strip `?lang=fr` from every
// enqueued URL and undo the propagation fix. Here the class is closed by a list's CONTENT,
// not by construction, so it needs a test: nothing else would catch a future edit adding
// `lang` to a CMS list.
test("no CMS facet list may contain a language param", () => {
    const lang = new Set(LANGUAGE_PARAMS.map((s) => s.toLowerCase()));
    for (const cms of ["WordPress", "PrestaShop", "Shopify", "Magento", "Wix", "Joomla"]) {
        for (const p of facetParamsForCms(cms)) {
            assert.ok(
                !lang.has(p.toLowerCase()),
                `CMS '${cms}' facet list contains language param '${p}' — merging it into ` +
                `toRemove would strip the propagated ?lang=fr from every enqueued URL`,
            );
        }
    }
});
