/**
 * Centralized API client.
 *
 * Replaces the per-component authFetch helpers. Adds:
 *  - JSON content-type + parsing
 *  - 401 → triggers `onUnauthorized()` (logout)
 *  - Light retry with exponential backoff on network errors and 5xx
 *  - ApiError class for typed error handling
 */

import { API_URL } from './constants';

export class ApiError extends Error {
  constructor(message, { status = null, body = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

let _onUnauthorized = null;
/** Register a callback called when ANY API call returns 401. Use it to logout. */
export function setOnUnauthorized(fn) { _onUnauthorized = fn; }

const DEFAULT_RETRY = { attempts: 2, backoffMs: 300 }; // 1 retry => 2 attempts total

async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

/**
 * Low-level fetch wrapper.
 *
 * @param {string} path — like '/jobs' (will be prefixed with API_URL) OR an absolute URL
 * @param {object} [opts]
 * @param {string} [opts.token]      — JWT bearer token (required for /api/jobs/* etc.)
 * @param {string} [opts.method]     — default GET
 * @param {object} [opts.body]       — JSON body (auto-stringified)
 * @param {object} [opts.headers]    — extra headers
 * @param {object} [opts.query]      — query params object → URLSearchParams
 * @param {object} [opts.retry]      — { attempts, backoffMs } (default { 2, 300 })
 * @param {boolean} [opts.parseJson] — parse response as JSON (default true)
 * @param {AbortSignal} [opts.signal]
 *
 * @returns parsed JSON body (or raw Response if parseJson:false)
 * @throws ApiError on non-2xx (after retries) or network failure
 */
export async function apiFetch(path, opts = {}) {
  const {
    token,
    method = 'GET',
    body,
    headers = {},
    query,
    retry = DEFAULT_RETRY,
    parseJson = true,
    signal,
  } = opts;

  const url = path.startsWith('http')
    ? path
    : (query
        ? `${API_URL}${path}?${new URLSearchParams(query).toString()}`
        : `${API_URL}${path}`);

  const finalHeaders = { ...headers };
  if (token) finalHeaders['Authorization'] = `Bearer ${token}`;
  let bodyToSend;
  if (body !== undefined) {
    finalHeaders['Content-Type'] = finalHeaders['Content-Type'] || 'application/json';
    bodyToSend = typeof body === 'string' ? body : JSON.stringify(body);
  }

  const totalAttempts = Math.max(1, retry.attempts || 1);
  let lastErr;

  for (let attempt = 1; attempt <= totalAttempts; attempt++) {
    try {
      const res = await fetch(url, { method, headers: finalHeaders, body: bodyToSend, signal });

      if (res.status === 401) {
        if (_onUnauthorized) _onUnauthorized();
        throw new ApiError('Unauthorized', { status: 401 });
      }

      // Retry on 5xx (server transient)
      if (res.status >= 500 && attempt < totalAttempts) {
        await sleep(retry.backoffMs * Math.pow(2, attempt - 1));
        continue;
      }

      if (!res.ok) {
        let errBody = null;
        try { errBody = parseJson ? await res.json() : await res.text(); } catch { /* swallow */ }
        throw new ApiError(`HTTP ${res.status}`, { status: res.status, body: errBody });
      }

      if (!parseJson) return res;
      // Some endpoints return 204 (no content)
      if (res.status === 204) return null;
      return await res.json();
    } catch (err) {
      // Don't retry on aborts or ApiError 401
      if (err.name === 'AbortError') throw err;
      if (err instanceof ApiError) throw err;
      lastErr = err;
      if (attempt < totalAttempts) {
        await sleep(retry.backoffMs * Math.pow(2, attempt - 1));
        continue;
      }
      throw new ApiError(err.message || 'Network error', { status: null });
    }
  }
  throw lastErr;
}

/* Convenience helpers — all assume token is required (most of our API). */
export const api = {
  get:    (path, token, opts = {})    => apiFetch(path, { ...opts, token, method: 'GET'    }),
  post:   (path, token, body, opts = {}) => apiFetch(path, { ...opts, token, method: 'POST',   body }),
  delete: (path, token, opts = {})    => apiFetch(path, { ...opts, token, method: 'DELETE' }),
};