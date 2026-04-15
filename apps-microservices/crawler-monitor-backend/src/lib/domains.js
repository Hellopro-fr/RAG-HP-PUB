/**
 * Domain aggregation helpers.
 *
 * Each crawler job carries a `domain` field; we aggregate jobs by domain to
 * power the /domains list and the per-domain detail page (run chain).
 *
 * Window default: 7 days. Reuses the same loadJobs pattern as systemStats.
 */

const WINDOW_MAP = {
  '24h': 24 * 60 * 60 * 1000,
  '7d':  7 * 24 * 60 * 60 * 1000,
  '30d': 30 * 24 * 60 * 60 * 1000,
};

export function parseDomainWindow(input) {
  if (typeof input !== 'string' || !(input in WINDOW_MAP)) {
    throw new Error("Invalid window. Use '24h', '7d' or '30d'.");
  }
  return WINDOW_MAP[input];
}

const TERMINAL_OK = new Set(['finished', 'archived']);
const TERMINAL_KO = new Set(['failed']);

/**
 * Aggregate the list of jobs by domain.
 * Returns an array sorted by `last_run_at` desc.
 *
 * Each entry: {
 *   domain,
 *   total_jobs,
 *   success, failure, running,
 *   success_rate (0..1 or null if no terminal jobs),
 *   oom_total,
 *   update_share (0..1),
 *   last_run_at (ISO string or null),
 *   last_status,
 * }
 */
export function aggregateDomains(jobs, nowMs, windowMs) {
  const cutoff = nowMs - windowMs;
  const inWindow = jobs.filter(j => {
    const t = Date.parse(j.start_time);
    return Number.isFinite(t) && t >= cutoff && j.domain;
  });

  const byDomain = new Map();
  for (const j of inWindow) {
    const d = j.domain;
    let agg = byDomain.get(d);
    if (!agg) {
      agg = {
        domain: d,
        total_jobs: 0,
        success: 0, failure: 0, running: 0, other: 0,
        oom_total: 0,
        update_count: 0,
        last_run_at: null,
        last_run_ts: 0,
        last_status: null,
      };
      byDomain.set(d, agg);
    }
    agg.total_jobs++;
    const status = (j.status || '').toLowerCase();
    if (TERMINAL_OK.has(status)) agg.success++;
    else if (TERMINAL_KO.has(status)) agg.failure++;
    else if (status === 'running' || status === 'stopping' || status === 'restarting_oom') agg.running++;
    else agg.other++;
    agg.oom_total += j.oom_restart_count || 0;
    if (j.crawl_mode === 'update') agg.update_count++;
    const ts = Date.parse(j.start_time);
    if (Number.isFinite(ts) && ts > agg.last_run_ts) {
      agg.last_run_ts = ts;
      agg.last_run_at = j.start_time;
      agg.last_status = j.status || null;
    }
  }

  const out = [];
  for (const agg of byDomain.values()) {
    const completed = agg.success + agg.failure;
    out.push({
      domain: agg.domain,
      total_jobs: agg.total_jobs,
      success: agg.success,
      failure: agg.failure,
      running: agg.running,
      other: agg.other,
      success_rate: completed > 0 ? agg.success / completed : null,
      oom_total: agg.oom_total,
      update_share: agg.total_jobs > 0 ? agg.update_count / agg.total_jobs : 0,
      last_run_at: agg.last_run_at,
      last_status: agg.last_status,
    });
  }
  // Sort by latest activity desc
  out.sort((a, b) => Date.parse(b.last_run_at || 0) - Date.parse(a.last_run_at || 0));
  return out;
}

/**
 * Filter jobs for a single domain, sorted by start_time desc, with a built
 * "run chain" (links via previous_crawl_id) for the most recent root.
 */
export function jobsForDomain(jobs, domain, windowMs, nowMs = Date.now()) {
  const cutoff = nowMs - windowMs;
  const filtered = jobs
    .filter(j => j.domain === domain)
    .filter(j => {
      const t = Date.parse(j.start_time);
      return Number.isFinite(t) && t >= cutoff;
    })
    .sort((a, b) => Date.parse(b.start_time) - Date.parse(a.start_time));

  // Build a chain starting from the most recent job, walking back via previous_crawl_id.
  const byId = new Map(filtered.map(j => [j.id, j]));
  const chain = [];
  if (filtered.length > 0) {
    let cur = filtered[0];
    const seen = new Set();
    while (cur && !seen.has(cur.id)) {
      seen.add(cur.id);
      chain.push({
        id: cur.id,
        status: cur.status,
        start_time: cur.start_time,
        crawl_mode: cur.crawl_mode || null,
        oom_restart_count: cur.oom_restart_count || 0,
      });
      const prevId = cur.previous_crawl_id;
      cur = prevId ? byId.get(prevId) : null;
    }
  }

  return { jobs: filtered, chain };
}