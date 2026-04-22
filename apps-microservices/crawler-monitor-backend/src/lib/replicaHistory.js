/**
 * Per-replica CPU/RAM history.
 *
 * The crawler-service publishes a heartbeat every 2s to channel `crawler:heartbeat`.
 * We persist a compact sample per heartbeat into a Redis sorted set per replica:
 *
 *   key:   replica:history:<replicaId>      (sorted set, score=ts ms)
 *   value: { ts, cpu, ram, totalRam, jobId }
 *
 * Auto-trimmed to a 1h sliding window (heartbeats are 2s -> 1800 points/h max).
 * The known-replica set tracks active replicas to expose them via a batch
 * endpoint without having to KEYS-scan.
 */

export const REPLICA_HISTORY_PREFIX = 'replica:history:';
export const KNOWN_REPLICAS_KEY = 'replica:known';
export const REPLICA_HISTORY_RETENTION_MS = 60 * 60 * 1000; // 1h

const WINDOW_MAP = {
  '15m': 15 * 60 * 1000,
  '1h':  60 * 60 * 1000,
};

export function parseReplicaWindow(input) {
  if (typeof input !== 'string' || !(input in WINDOW_MAP)) {
    throw new Error("Invalid window. Use '15m' or '1h'.");
  }
  return WINDOW_MAP[input];
}

/**
 * Persist a single heartbeat sample. Tolerant: never throws.
 *
 * @param {object} client - connected Redis client
 * @param {object} hb - heartbeat payload from crawler-service
 *   { type: 'heartbeat', replicaId, jobId, domain, cpu, ram, totalRam, topProcesses, timestamp }
 */
export async function persistHeartbeat(client, hb) {
  if (!hb || !hb.replicaId) return;
  const ts = Number(hb.timestamp) || Date.now();
  const sample = JSON.stringify({
    ts,
    cpu: hb.cpu ?? 0,
    ram: hb.ram ?? 0,
    totalRam: hb.totalRam ?? 0,
    jobId: hb.jobId ?? null,
  });
  const key = REPLICA_HISTORY_PREFIX + hb.replicaId;
  try {
    await client.zAdd(key, { score: ts, value: sample });
    await client.zRemRangeByScore(key, 0, ts - REPLICA_HISTORY_RETENTION_MS);
    await client.sAdd(KNOWN_REPLICAS_KEY, hb.replicaId);
  } catch (err) {
    console.error('[replicaHistory] persist failed:', err.message);
  }
}

/**
 * Read history points for a single replica within [now-windowMs, now].
 */
export async function readReplicaHistory(client, replicaId, windowMs) {
  if (!replicaId) return [];
  const min = Date.now() - windowMs;
  const raw = await client.zRangeByScore(REPLICA_HISTORY_PREFIX + replicaId, min, '+inf');
  const out = [];
  for (const s of raw) {
    try { out.push(JSON.parse(s)); } catch { /* skip */ }
  }
  return out;
}

/**
 * Batch: return history for ALL known replicas in one call.
 * Also opportunistically prunes orphan replicas (no points in retention window).
 */
export async function readAllReplicasHistory(client, windowMs) {
  const ids = await client.sMembers(KNOWN_REPLICAS_KEY);
  if (!ids || ids.length === 0) return {};
  const result = {};
  for (const id of ids) {
    const points = await readReplicaHistory(client, id, windowMs);
    if (points.length === 0) {
      // No data in the window -> drop from known-set (keeps it bounded)
      try { await client.sRem(KNOWN_REPLICAS_KEY, id); } catch { /* swallow */ }
      continue;
    }
    result[id] = points;
  }
  return result;
}