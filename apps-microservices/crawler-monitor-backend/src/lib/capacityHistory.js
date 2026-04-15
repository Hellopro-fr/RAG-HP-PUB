/**
 * Capacity history helpers.
 * Snapshots `running_jobs / max_global_jobs` into a Redis sorted set
 * (score = unix timestamp ms) every 60 seconds, capped at 24h.
 */

export const CAPACITY_HISTORY_KEY = 'capacity:history:zset';
export const SNAPSHOT_INTERVAL_MS = 60 * 1000;          // 60s
export const RETENTION_MS = 24 * 60 * 60 * 1000;        // 24h

/**
 * Parse a window string like '1h', '6h', '24h' to milliseconds.
 * Throws on invalid input.
 */
export function parseWindow(input) {
  const allowed = { '1h': 3600000, '6h': 21600000, '24h': 86400000 };
  if (typeof input !== 'string' || !(input in allowed)) {
    throw new Error("Invalid window. Use '1h', '6h' or '24h'.");
  }
  return allowed[input];
}

/**
 * Take a single capacity snapshot and ZADD it. Also prunes entries older than
 * `retentionMs` from now.
 */
export async function snapshotCapacity(client, runningKey, maxKey) {
  const [runningStr, maxStr] = await Promise.all([
    client.get(runningKey),
    client.get(maxKey),
  ]);
  const running = parseInt(runningStr, 10) || 0;
  const max = parseInt(maxStr, 10) || 0;
  const point = {
    ts: Date.now(),
    running,
    max,
    full: max > 0 && running >= max,
  };
  await client.zAdd(CAPACITY_HISTORY_KEY, { score: point.ts, value: JSON.stringify(point) });
  // Trim old entries
  await client.zRemRangeByScore(CAPACITY_HISTORY_KEY, 0, point.ts - RETENTION_MS);
  return point;
}

/**
 * Read history points within [now - windowMs, now]. Returns chronological array.
 */
export async function readCapacityHistory(client, windowMs) {
  const now = Date.now();
  const min = now - windowMs;
  const raw = await client.zRangeByScore(CAPACITY_HISTORY_KEY, min, '+inf');
  const points = [];
  for (const s of raw) {
    try { points.push(JSON.parse(s)); }
    catch { /* skip corrupt */ }
  }
  return points;
}