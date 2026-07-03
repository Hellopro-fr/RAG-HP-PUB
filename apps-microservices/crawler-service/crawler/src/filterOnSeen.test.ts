import { test } from "node:test";
import assert from "node:assert/strict";
import { isFilterParam } from "./filterOnSeen.js";
import { baseKeyAbsent } from "./urlBase.js";

const seen = new Set<string>([ baseKeyAbsent("https://x.fr/c/?idRubrique=5") ]);

test("filtered view of a seen base is detected", () => {
    assert.equal(isFilterParam("https://x.fr/c/?idRubrique=5&filtrage=1", seen), true);
});
test("the seen base itself is not a filtered view", () => {
    assert.equal(isFilterParam("https://x.fr/c/?idRubrique=5", seen), false);
});
test("R1 allowlist params never trigger", () => {
    const s = new Set<string>([ baseKeyAbsent("https://x.fr/c/") ]);
    assert.equal(isFilterParam("https://x.fr/c/?lang=en", s), false);
});
test("no seen base -> not a filter", () => {
    assert.equal(isFilterParam("https://x.fr/c/?filtrage=1", new Set()), false);
});
