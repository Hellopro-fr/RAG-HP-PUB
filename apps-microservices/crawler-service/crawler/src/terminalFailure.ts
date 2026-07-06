// terminalFailure.ts — pure, dependency-free predicates for terminal crawl-failure detection.
// Intentionally free of crawlee/main.ts imports so it is unit-testable in isolation.

export interface ProxyWallConfig { minSamples: number; ratio: number; }

export function terminalFailureDetectEnabled(): boolean {
  return process.env.TERMINAL_FAILURE_DETECT_ENABLED === "true";
}

export function proxyWallConfig(): ProxyWallConfig {
  const minSamples = Number(process.env.PROXY_WALL_MIN_SAMPLES ?? "20");
  const ratio = Number(process.env.PROXY_WALL_RATIO ?? "0.9");
  return {
    minSamples: Number.isFinite(minSamples) && minSamples > 0 ? minSamples : 20,
    ratio: Number.isFinite(ratio) && ratio > 0 && ratio <= 1 ? ratio : 0.9,
  };
}

/** Trip the proxy-wall breaker only after a meaningful sample and a high block ratio. */
export function shouldTripProxyWall(
  blocked: number, processed: number, cfg: ProxyWallConfig,
): { trip: boolean; reason: string } {
  if (processed < cfg.minSamples) return { trip: false, reason: "sample-too-small" };
  const r = processed > 0 ? blocked / processed : 0;
  if (r >= cfg.ratio) return { trip: true, reason: `proxy_blocked ${blocked}/${processed}` };
  return { trip: false, reason: "ratio-below-threshold" };
}

/** DNS-gone (permanent) is dead; conn-refused/timeout (infra) is dead only if nothing was crawled. */
export function isDeadHost(rootFailureClass: string, processedCount: number): boolean {
  if (rootFailureClass === "permanent") return true;
  if (rootFailureClass === "infra" && processedCount === 0) return true;
  return false;
}
