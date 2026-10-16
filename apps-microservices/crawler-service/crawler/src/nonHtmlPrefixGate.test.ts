import { test } from "node:test";
import assert from "node:assert/strict";
import { NonHtmlPrefixGate } from "./nonHtmlPrefixGate.js";
import type { GatePoint } from "./nonHtmlPrefixGate.js";
import { createNonHtmlPrefixState, NONHTML_PREFIX_DEFAULTS } from "./nonHtmlPrefix.js";
import { loadSidecarInto, parseNonHtmlPrefixSidecar } from "./nonHtmlPrefixSidecar.js";

const NOW = "2026-10-16T00:00:00.000Z";
const KEY = "h.fr/image";
const U1 = "https://h.fr/image/a1";
const U2 = "https://h.fr/image/a2";
const U3 = "https://h.fr/image/a3";
const ISOLATED = "https://h.fr/telechargement?id=12";

function makeGate(mode: "shadow" | "on", minNonHtml = 2) {
    const logs: string[] = [];
    const persisted: string[] = [];
    const state = createNonHtmlPrefixState({ ...NONHTML_PREFIX_DEFAULTS, minNonHtml });
    const gate = new NonHtmlPrefixGate({
        mode,
        state,
        log: (m) => logs.push(m),
        persist: (t) => persisted.push(t),
        now: () => NOW,
    });
    return { gate, state, logs, persisted };
}

// Learns KEY (K=2: two non-HTML answers) then clears the recorded logs/persists.
function learned(mode: "shadow" | "on") {
    const g = makeGate(mode);
    g.gate.onNonHtml(U1);
    g.gate.onNonHtml(U2);
    g.logs.length = 0;
    g.persisted.length = 0;
    return g;
}

// Loaded-from-previous-crawl entry: over K but still in probation (no probe admitted yet).
function withProbation(mode: "shadow" | "on") {
    const g = makeGate(mode);
    g.state.prefixes.set(KEY, {
        nonHtml: 5,
        sawHtml: false,
        confirmed: false,
        confirmedAt: null,
        probation: { admitted: 0, probeUrl: null, resolved: false },
    });
    return g;
}

function expectBlockDecision(mode: "shadow" | "on", point: GatePoint) {
    const g = learned(mode);
    const passed = g.gate.check(U3, point);
    return { passed, logs: g.logs, persisted: g.persisted };
}

test("enqueue + shadow: passes and logs would block", () => {
    const r = expectBlockDecision("shadow", "enqueue");
    assert.equal(r.passed, true);
    assert.deepEqual(r.logs, [`[nonhtml-prefix] would block (enqueue): ${U3} [${KEY}]`]);
    assert.equal(r.persisted.length, 0);
});

test("enqueue + on: refuses and logs blocked", () => {
    const r = expectBlockDecision("on", "enqueue");
    assert.equal(r.passed, false);
    assert.deepEqual(r.logs, [`[nonhtml-prefix] blocked (enqueue): ${U3} [${KEY}]`]);
});

test("prenav + shadow: passes and logs would block", () => {
    const r = expectBlockDecision("shadow", "prenav");
    assert.equal(r.passed, true);
    assert.deepEqual(r.logs, [`[nonhtml-prefix] would block (prenav): ${U3} [${KEY}]`]);
});

test("prenav + on: refuses and logs blocked", () => {
    const r = expectBlockDecision("on", "prenav");
    assert.equal(r.passed, false);
    assert.deepEqual(r.logs, [`[nonhtml-prefix] blocked (prenav): ${U3} [${KEY}]`]);
});

test("seed + shadow: passes and logs would block", () => {
    const r = expectBlockDecision("shadow", "seed");
    assert.equal(r.passed, true);
    assert.deepEqual(r.logs, [`[nonhtml-prefix] would block (seed): ${U3} [${KEY}]`]);
});

test("seed + on: refuses and logs blocked", () => {
    const r = expectBlockDecision("on", "seed");
    assert.equal(r.passed, false);
    assert.deepEqual(r.logs, [`[nonhtml-prefix] blocked (seed): ${U3} [${KEY}]`]);
});

test("probe: passes in both modes and logs probe", () => {
    for (const mode of ["shadow", "on"] as const) {
        const g = withProbation(mode);
        assert.equal(g.gate.check(U1, "enqueue"), true);
        assert.deepEqual(g.logs, [`[nonhtml-prefix] probe (enqueue): ${U1} [${KEY}]`]);
    }
});

test("allow: unknown prefix passes without any log", () => {
    const g = learned("on");
    assert.equal(g.gate.check("https://h.fr/produits/p1", "enqueue"), true);
    assert.equal(g.gate.check("https://h.fr/", "prenav"), true);
    assert.deepEqual(g.logs, []);
});

test("exemption without trailing slash protects both forms", () => {
    const g = learned("on");
    g.gate.addExempt(U3);
    assert.equal(g.gate.check(U3, "prenav"), true);
    assert.equal(g.gate.check(`${U3}/`, "prenav"), true);
    assert.deepEqual(g.logs, []);
    // control: a non-exempt sibling is still blocked
    assert.equal(g.gate.check("https://h.fr/image/a4", "prenav"), false);
    assert.equal(g.logs.length, 1);
});

test("exemption with trailing slash protects both forms", () => {
    const g = learned("on");
    g.gate.addExempt(`${U3}/`);
    assert.equal(g.gate.check(U3, "seed"), true);
    assert.equal(g.gate.check(`${U3}/`, "seed"), true);
    assert.deepEqual(g.logs, []);
});

test("exemptCount counts distinct normalized URLs", () => {
    const g = makeGate("on");
    assert.equal(g.gate.exemptCount(), 0);
    g.gate.addExempt(U3);
    g.gate.addExempt(`${U3}/`);
    g.gate.addExempt(U1);
    assert.equal(g.gate.exemptCount(), 2);
});

test("onNonHtml learned: logs the learned prefix and persists", () => {
    const g = makeGate("shadow");
    g.gate.onNonHtml(U1); // below K: isolated, persists without log
    assert.deepEqual(g.logs, []);
    g.gate.onNonHtml(U2); // K reached: learned
    assert.deepEqual(g.logs, [`Non-HTML prefix learned: ${KEY} (n=2)`]);
    assert.equal(g.persisted.length, 2);
});

test("onNonHtml counted: neither logs nor persists", () => {
    const g = learned("on");
    g.gate.onNonHtml(U3); // already blocking: counted
    assert.deepEqual(g.logs, []);
    assert.equal(g.persisted.length, 0);
});

test("onNonHtml confirmed (probation): logs and persists", () => {
    const g = withProbation("on");
    g.gate.onNonHtml(U1);
    assert.deepEqual(g.logs, [`Non-HTML prefix confirmed by probe: ${KEY} (n=6)`]);
    assert.equal(g.persisted.length, 1);
});

test("onNonHtml isolated (no folder key): persists without log", () => {
    const g = makeGate("on");
    g.gate.onNonHtml(ISOLATED);
    assert.deepEqual(g.logs, []);
    assert.equal(g.persisted.length, 1);
    assert.ok(g.persisted[0].includes(ISOLATED));
});

test("onHtml released: logs the release and persists", () => {
    const g = learned("shadow");
    g.gate.onHtml(U3);
    assert.deepEqual(g.logs, [`Non-HTML prefix released: ${KEY} (n=2)`]);
    assert.equal(g.persisted.length, 1);
    // the veto holds: the prefix no longer blocks
    assert.equal(g.gate.check(U1, "enqueue"), true);
});

test("onProbeFailure: logs without persisting; unrelated URL is silent", () => {
    const g = withProbation("on");
    assert.equal(g.gate.check(U1, "enqueue"), true); // admits U1 as the probe
    g.logs.length = 0;
    g.gate.onProbeFailure(U1);
    assert.deepEqual(g.logs, [`[nonhtml-prefix] probe failed: ${U1} [${KEY}]`]);
    assert.equal(g.persisted.length, 0);
    g.gate.onProbeFailure(U2); // not the admitted probe
    assert.equal(g.logs.length, 1);
});

test("flush: persists a key confirmed by probe exhaustion (no event write before)", () => {
    const g = withProbation("on");
    for (const u of [U1, U2, U3]) {
        assert.equal(g.gate.check(u, "enqueue"), true); // admits u as the in-flight probe
        g.gate.onProbeFailure(u);
    }
    assert.equal(g.persisted.length, 0); // exhaustion alone never writes
    g.gate.flush();
    assert.equal(g.persisted.length, 1);
    const fresh = createNonHtmlPrefixState({ ...NONHTML_PREFIX_DEFAULTS, minNonHtml: 2 });
    assert.equal(loadSidecarInto(fresh, parseNonHtmlPrefixSidecar(g.persisted[0]), "current"), 1);
    const reloaded = new NonHtmlPrefixGate({ mode: "on", state: fresh, log: () => {}, persist: () => {} });
    assert.equal(reloaded.check("https://h.fr/image/a9", "enqueue"), false);
});

test("flush: empty state persists once a parseable payload", () => {
    const g = makeGate("on");
    g.gate.flush();
    assert.equal(g.persisted.length, 1);
    const data = parseNonHtmlPrefixSidecar(g.persisted[0]);
    assert.equal(data.prefixes.size, 0);
    assert.deepEqual(data.urls, []);
});

test("injected now() stamps confirmedAt in the persisted sidecar", () => {
    const g = makeGate("on");
    g.gate.onNonHtml(U1);
    g.gate.onNonHtml(U2);
    const last = g.persisted[g.persisted.length - 1];
    assert.ok(last.includes(`"confirmedAt":"${NOW}"`));
});

test("default now() yields an ISO timestamp", () => {
    const logs: string[] = [];
    const persisted: string[] = [];
    const state = createNonHtmlPrefixState({ ...NONHTML_PREFIX_DEFAULTS, minNonHtml: 1 });
    const gate = new NonHtmlPrefixGate({
        mode: "on",
        state,
        log: (m) => logs.push(m),
        persist: (t) => persisted.push(t),
    });
    gate.onNonHtml(U1);
    assert.match(persisted[persisted.length - 1], /"confirmedAt":"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
});

// ------------------------------------------- R23 I-2: one probe per loaded isolated URL

// An isolated URL loaded from the previous crawl's sidecar, in probation.
function withIsolatedProbation(mode: "shadow" | "on", url: string = ISOLATED) {
    const g = makeGate(mode);
    loadSidecarInto(g.state, parseNonHtmlPrefixSidecar(JSON.stringify({ version: 1, prefixes: {}, urls: [url] })), "previous");
    return g;
}

test("I-2 check: an isolated URL in probation passes in shadow and in on, logged as a probe", () => {
    for (const mode of ["shadow", "on"] as const) {
        const g = withIsolatedProbation(mode);
        assert.equal(g.gate.check(ISOLATED, "enqueue"), true);
        assert.equal(g.gate.check(ISOLATED, "prenav"), true, "the retry/prenav pass is probed again");
        assert.equal(g.logs.length, 2);
        assert.ok(g.logs[0].startsWith(`[nonhtml-prefix] probe (enqueue): ${ISOLATED}`));
        assert.equal(g.persisted.length, 0);
    }
});

test("I-2 onNonHtml: kept is logged, then the URL is blocked in on and only would-blocked in shadow", () => {
    const on = withIsolatedProbation("on");
    on.gate.onNonHtml(ISOLATED);
    assert.equal(on.logs[0], `[nonhtml-prefix] isolated kept by probe: ${ISOLATED}`);
    assert.equal(on.gate.check(ISOLATED, "enqueue"), false);
    const shadow = withIsolatedProbation("shadow");
    shadow.gate.onNonHtml(ISOLATED);
    shadow.logs.length = 0;
    assert.equal(shadow.gate.check(ISOLATED, "enqueue"), true, "shadow lets it through");
    assert.ok(shadow.logs[0].startsWith(`[nonhtml-prefix] would block (enqueue): ${ISOLATED}`));
});

test("I-2 onHtml: released is logged and persisted; the URL leaves the sidecar and passes silently", () => {
    const g = withIsolatedProbation("on");
    g.gate.onHtml(ISOLATED);
    assert.deepEqual(g.logs, [`Non-HTML isolated URL released: ${ISOLATED}`]);
    assert.equal(g.persisted.length, 1);
    assert.deepEqual(JSON.parse(g.persisted[0]).urls, []);
    assert.equal(g.gate.check(ISOLATED, "enqueue"), true);
    assert.equal(g.logs.length, 1, "allow logs nothing");
});

test("I-2 onProbeFailure: kept is logged (no persist), then the URL is blocked in on", () => {
    const g = withIsolatedProbation("on");
    g.gate.onProbeFailure(ISOLATED);
    assert.deepEqual(g.logs, [`[nonhtml-prefix] isolated probe failed: ${ISOLATED}`]);
    assert.equal(g.persisted.length, 0);
    assert.equal(g.gate.check(ISOLATED, "enqueue"), false);
});

test("I-2: an isolated non-HTML URL under a key in probation also confirms the key (key behaviour intact)", () => {
    const g = withProbation("on");
    g.state.isolatedProbation.add(U1);
    assert.equal(g.gate.check(U1, "enqueue"), true);
    assert.deepEqual(g.state.prefixes.get(KEY)?.probation, { admitted: 0, probeUrl: null, resolved: false },
        "the isolated probe takes no key admission");
    g.logs.length = 0;
    g.gate.onNonHtml(U1);
    assert.deepEqual(g.logs, [
        `[nonhtml-prefix] isolated kept by probe: ${U1}`,
        `Non-HTML prefix confirmed by probe: ${KEY} (n=6)`,
    ]);
    assert.equal(g.state.prefixes.get(KEY)?.confirmed, true);
});

test("I-2: a URL not in isolated probation logs nothing new in the three handlers", () => {
    const g = makeGate("on");
    g.gate.onHtml(ISOLATED);
    g.gate.onProbeFailure(ISOLATED);
    assert.deepEqual(g.logs, []);
    assert.equal(g.persisted.length, 0);
});
