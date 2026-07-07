import { test } from "node:test";
import assert from "node:assert/strict";
import { hasIgnoredExtensionForSeed } from "./seedExtensionFilter.js";

test("hasIgnoredExtensionForSeed: true for known binary/image/doc extensions", () => {
    assert.equal(hasIgnoredExtensionForSeed("https://x.fr/wp-content/uploads/photo.jpg"), true);
    assert.equal(hasIgnoredExtensionForSeed("https://x.fr/img/IMG.PNG"), true, "case-insensitive");
    assert.equal(hasIgnoredExtensionForSeed("https://x.fr/img/x.jpeg?width=200"), true, "tolerates ?query");
    assert.equal(hasIgnoredExtensionForSeed("https://x.fr/doc.pdf#page=2"), true, "tolerates #fragment");
    assert.equal(hasIgnoredExtensionForSeed("https://x.fr/archive.zip"), true);
});

test("hasIgnoredExtensionForSeed: false for HTML/no-extension/query-only/malformed URLs", () => {
    assert.equal(hasIgnoredExtensionForSeed("https://x.fr/page.html"), false);
    assert.equal(hasIgnoredExtensionForSeed("https://x.fr/produit/toa3"), false, "no extension");
    assert.equal(hasIgnoredExtensionForSeed("https://x.fr/page?param=.jpg"), false, "extension in query, not path");
    assert.equal(hasIgnoredExtensionForSeed("not a url"), false, "malformed → false, never throws");
});
