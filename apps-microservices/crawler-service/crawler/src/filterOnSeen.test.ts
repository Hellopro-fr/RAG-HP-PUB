import { test } from "node:test";
import assert from "node:assert/strict";
import { isFilterParam, filterParamCollapseTarget } from "./filterOnSeen.js";
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
test("pagination params never trigger (page 2 must not collapse onto seen page 1)", () => {
    const s = new Set<string>([ baseKeyAbsent("https://x.fr/c/") ]);
    assert.equal(isFilterParam("https://x.fr/c/?page=2", s), false);
    assert.equal(isFilterParam("https://x.fr/c/?paged=3", s), false);
});
test("filterParamCollapseTarget returns the seen base (baseKeyWithout the filter param)", () => {
    assert.equal(
        filterParamCollapseTarget("https://x.fr/c/?idRubrique=5&filtrage=1", seen),
        baseKeyAbsent("https://x.fr/c/?idRubrique=5"),
    );
});
test("filterParamCollapseTarget: single-param filtered view collapses onto the bare base", () => {
    const s = new Set<string>([ baseKeyAbsent("https://x.fr/c/") ]);
    assert.equal(filterParamCollapseTarget("https://x.fr/c/?f_place=47", s), baseKeyAbsent("https://x.fr/c/"));
});
test("filterParamCollapseTarget: null for pagination/meaningful params", () => {
    const s = new Set<string>([ baseKeyAbsent("https://x.fr/c/") ]);
    assert.equal(filterParamCollapseTarget("https://x.fr/c/?page=2", s), null);
    assert.equal(filterParamCollapseTarget("https://x.fr/c/?lang=en", s), null);
});
test("filterParamCollapseTarget: null when nothing matches", () => {
    assert.equal(filterParamCollapseTarget("https://x.fr/c/?filtrage=1", new Set()), null);
    assert.equal(filterParamCollapseTarget("https://x.fr/other?filtrage=1", seen), null);
});
test("isFilterParam agrees with filterParamCollapseTarget", () => {
    for (const u of ["https://x.fr/c/?idRubrique=5&filtrage=1", "https://x.fr/c/?idRubrique=5", "https://x.fr/c/?page=2"]) {
        assert.equal(isFilterParam(u, seen), filterParamCollapseTarget(u, seen) !== null);
    }
});
