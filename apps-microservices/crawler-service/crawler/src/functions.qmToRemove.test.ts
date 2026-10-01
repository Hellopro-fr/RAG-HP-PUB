import { test } from "node:test";
import assert from "node:assert/strict";
import { processUrl } from "./functions.js";

test("processUrl strips toRemove param with skipQuestionMark=false (mechanism Part A relies on)", () => {
    assert.equal(
        processUrl("https://x.fr/c?q=batterie&z=2", false, false, { toRemove: ["q"] }),
        "https://x.fr/c?z=2",
    );
    // empty toRemove → unchanged
    assert.equal(
        processUrl("https://x.fr/c?q=batterie", false, false, { toRemove: [] }),
        "https://x.fr/c?q=batterie",
    );
});

test("processUrl empty toKeep falls back to defaultKeep (bug: [] stripped page/id/lang)", () => {
    // The bug case: toKeep [] (config default when no --tokeep) must NOT mean "keep nothing"
    assert.equal(
        processUrl("https://x.fr/cat?page=2", true, false, { toKeep: [] }),
        "https://x.fr/cat?page=2",
    );
    // undefined toKeep / no parameters → defaultKeep (already worked)
    assert.equal(
        processUrl("https://x.fr/cat?page=2", true, false, { toKeep: undefined }),
        "https://x.fr/cat?page=2",
    );
    assert.equal(
        processUrl("https://x.fr/cat?page=2", true, false, {}),
        "https://x.fr/cat?page=2",
    );
    // empty toKeep still strips non-default params
    assert.equal(
        processUrl("https://x.fr/cat?page=2&utm_source=abc", true, false, { toKeep: [] }),
        "https://x.fr/cat?page=2",
    );
});

test("processUrl explicit toKeep list stays exclusive", () => {
    assert.equal(
        processUrl("https://x.fr/cat?page=2&couleur=rouge", true, false, { toKeep: ["couleur"] }),
        "https://x.fr/cat?couleur=rouge",
    );
});

test("processUrl toRemove wins over defaultKeep with empty toKeep", () => {
    assert.equal(
        processUrl("https://x.fr/cat?page=2", true, false, { toKeep: [], toRemove: ["page"] }),
        "https://x.fr/cat",
    );
});
