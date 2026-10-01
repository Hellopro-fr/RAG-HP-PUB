import { test } from "node:test";
import assert from "node:assert/strict";
import { processUrl } from "./functions.js";

test("processUrl per-class OFF: legacy skipDiez behavior unchanged", () => {
    delete process.env.DIEZ_PERCLASS_ENABLED;
    assert.equal(processUrl("https://x.fr/p#section", false, true), "https://x.fr/p");
    assert.equal(processUrl("https://x.fr/p#section", false, false), "https://x.fr/p#section");
});

test("processUrl per-class ON: anchor stripped, spa kept, skipDiez ignored", () => {
    process.env.DIEZ_PERCLASS_ENABLED = "true";
    try {
        assert.equal(processUrl("https://x.fr/p#section", false, false), "https://x.fr/p");
        assert.equal(processUrl("https://x.fr/p#", false, false), "https://x.fr/p");
        assert.equal(processUrl("https://x.fr/p?a=1#section", false, false), "https://x.fr/p?a=1");
        assert.equal(processUrl("https://x.fr/p#/produit/1", false, false), "https://x.fr/p#/produit/1");
        assert.equal(processUrl("https://x.fr/p#/produit/1", false, true), "https://x.fr/p#/produit/1");
    } finally {
        delete process.env.DIEZ_PERCLASS_ENABLED;
    }
});
