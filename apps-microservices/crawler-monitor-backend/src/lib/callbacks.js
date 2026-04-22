/**
 * Failed-callbacks helpers.
 *
 * The crawler-service stores failed webhooks as a Redis LIST
 * (key: `crawl_jobs:failed_callbacks`, see `crawler-service/app/core/crawler_manager.py`).
 * Each entry is JSON: { webhook_type, url, params, crawl_id, error, timestamp, manual_retry_attempts? }
 *
 * Webhooks are HTTP GET (NOT POST) — the producer uses `httpx.get(url, params=...)`
 * with exponential backoff, then stores here on exhaustion.
 */

/**
 * Build the final URL by appending callback params as query string.
 * Preserves any existing query string in the base URL.
 */
export function buildCallbackUrl(baseUrl, params = {}) {
  const url = new URL(baseUrl);
  if (params && typeof params === 'object') {
    for (const [k, v] of Object.entries(params)) {
      if (v === null || v === undefined) continue;
      url.searchParams.append(k, String(v));
    }
  }
  return url.toString();
}

/**
 * Replays a single callback HTTP GET with a 30s timeout.
 * Returns { ok, status, error }.
 *
 * `fetchImpl` is injectable for tests; defaults to global fetch.
 */
export async function replayCallback(entry, { fetchImpl = fetch, timeoutMs = 30000 } = {}) {
  if (!entry || !entry.url) return { ok: false, status: null, error: 'invalid_entry' };
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const finalUrl = buildCallbackUrl(entry.url, entry.params || {});
    const res = await fetchImpl(finalUrl, { method: 'GET', signal: ctrl.signal });
    return { ok: res.ok, status: res.status, error: res.ok ? null : `HTTP ${res.status}` };
  } catch (err) {
    return { ok: false, status: null, error: err.name === 'AbortError' ? 'timeout' : err.message };
  } finally {
    clearTimeout(timer);
  }
}