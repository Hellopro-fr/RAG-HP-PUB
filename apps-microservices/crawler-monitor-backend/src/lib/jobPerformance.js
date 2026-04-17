/**
 * Per-job CPU/RAM performance history.
 *
 * Each heartbeat that carries a jobId is also stored in a per-job Redis
 * sorted set: job:perf:<jobId>. This allows viewing the full resource
 * usage curve for a specific crawl, even after the replica finishes it.
 *
 * Retention: 24h (configurable). Longer than replica:history (1h) because
 * users want to review perf for recently completed jobs.
 */

export const JOB_PERF_PREFIX = 'job:perf:';
// Extended to 7 days so the replay feature can scrub recently-completed jobs.
export const JOB_PERF_RETENTION_MS = 7 * 24 * 60 * 60 * 1000; // 7d

/**
 * Persist a heartbeat sample indexed by jobId (fire-and-forget from heartbeat handler).
 * Stores: { ts, cpu, ram, totalRam, replicaId }
 */
export async function persistJobPerf(client, hb) {
  if (!hb || !hb.jobId || !hb.replicaId) return;
  const ts = Number(hb.timestamp) || Date.now();
  const sample = JSON.stringify({
    ts,
    cpu: hb.cpu ?? 0,
    ram: hb.ram ?? 0,
    totalRam: hb.totalRam ?? 0,
    replicaId: hb.replicaId,
  });
  const key = JOB_PERF_PREFIX + hb.jobId;
  try {
    await client.zAdd(key, { score: ts, value: sample });
    // Prune old entries (sliding 24h window)
    await client.zRemRangeByScore(key, 0, ts - JOB_PERF_RETENTION_MS);
    // Set an expiry on the key itself so abandoned keys get cleaned up
    await client.expire(key, Math.ceil(JOB_PERF_RETENTION_MS / 1000));
  } catch (err) {
    console.error('[jobPerf] persist failed:', err.message);
  }
}

/**
 * Read performance points for a job.
 * Returns chronological array of { ts, cpu, ram, totalRam, replicaId }.
 * Also computes summary stats: peak CPU, peak RAM, avg CPU.
 */
export async function readJobPerf(client, jobId) {
  if (!jobId) return { points: [], summary: null };
  const key = JOB_PERF_PREFIX + jobId;
  const raw = await client.zRangeByScore(key, '-inf', '+inf');
  const points = [];
  for (const s of raw) {
    try { points.push(JSON.parse(s)); } catch { /* skip */ }
  }
  if (points.length === 0) return { points, summary: null };

  let peakCpu = 0, peakCpuTs = null;
  let peakRam = 0, peakRamTs = null;
  let cpuSum = 0;
  for (const p of points) {
    const cpu = p.cpu || 0;
    const ram = p.ram || 0;
    cpuSum += cpu;
    if (cpu > peakCpu) { peakCpu = cpu; peakCpuTs = p.ts; }
    if (ram > peakRam) { peakRam = ram; peakRamTs = p.ts; }
  }
  const summary = {
    count: points.length,
    duration_ms: points[points.length - 1].ts - points[0].ts,
    peak_cpu: peakCpu,
    peak_cpu_at: peakCpuTs,
    avg_cpu: cpuSum / points.length,
    peak_ram: peakRam,
    peak_ram_at: peakRamTs,
    total_ram: points[points.length - 1].totalRam || 0,
  };
  return { points, summary };
}