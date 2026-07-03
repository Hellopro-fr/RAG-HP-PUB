import { test } from "node:test";
import assert from "node:assert/strict";
import { facetParamsForCms } from "./cmsFacetLists.js";

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
