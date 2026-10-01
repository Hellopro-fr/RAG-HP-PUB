import { test } from "node:test";
import assert from "node:assert";
import { shouldTripProxyWall, isDeadHost } from "./terminalFailure.js";

const cfg = { minSamples: 20, ratio: 0.9 };

test("proxy wall: trips when block ratio high over min sample", () => {
  assert.equal(shouldTripProxyWall(19, 20, cfg).trip, true);   // 0.95 >= 0.9
});
test("proxy wall: no trip below min sample", () => {
  assert.equal(shouldTripProxyWall(10, 10, cfg).trip, false);  // processed < minSamples
});
test("proxy wall: no trip when ratio low", () => {
  assert.equal(shouldTripProxyWall(10, 50, cfg).trip, false);  // 0.2 < 0.9
});
test("dead host: DNS permanent is dead", () => {
  assert.equal(isDeadHost("permanent", 0), true);
  assert.equal(isDeadHost("permanent", 5), true);
});
test("dead host: infra dead only if zero pages processed", () => {
  assert.equal(isDeadHost("infra", 0), true);
  assert.equal(isDeadHost("infra", 3), false);
});
test("dead host: transient/unknown never dead", () => {
  assert.equal(isDeadHost("transient", 0), false);
  assert.equal(isDeadHost("unknown", 0), false);
});
