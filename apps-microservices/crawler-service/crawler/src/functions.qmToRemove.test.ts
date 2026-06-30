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
