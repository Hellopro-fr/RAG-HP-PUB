import { test } from "node:test";
import assert from "node:assert/strict";
import { fragmentAwareUniqueKey } from "./diezKeepFragment.js";

test("uniqueKey keeps the fragment so base and base#x differ", () => {
	assert.equal(fragmentAwareUniqueKey("https://x.fr/p"), "https://x.fr/p");
	assert.equal(fragmentAwareUniqueKey("https://x.fr/p#a"), "https://x.fr/p#a");
	assert.notEqual(
		fragmentAwareUniqueKey("https://x.fr/p#a"),
		fragmentAwareUniqueKey("https://x.fr/p#b"),
	);
});
