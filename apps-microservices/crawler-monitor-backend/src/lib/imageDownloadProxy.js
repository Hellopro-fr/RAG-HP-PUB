/**
 * Proxy fin vers image-download-service.
 *
 * Usage:
 *   await proxyToImageDownload(req, res, { method: 'GET', path: '/domains/_summary' });
 *
 * - statusCode + body JSON forwardés tels quels.
 * - ECONNREFUSED/ENOTFOUND/EAI_AGAIN → 503.
 * - AbortError (timeout) → 504.
 *
 * Le helper n'inclut pas l'audit logging — celui-ci est géré dans `albums.js`.
 */

const DEFAULT_BASE = process.env.IMAGE_DOWNLOAD_SERVICE_URL || 'http://image-download-service:8505';
const DEFAULT_TIMEOUT_MS = parseInt(process.env.IMAGE_DOWNLOAD_TIMEOUT_MS || '60000', 10);

export async function proxyToImageDownload(req, res, opts) {
  const {
    method = 'GET',
    path,
    baseUrl = DEFAULT_BASE,
    fetchFn = fetch,
    timeoutMs = DEFAULT_TIMEOUT_MS,
  } = opts;

  const queryStr = (req.query && Object.keys(req.query).length)
    ? '?' + new URLSearchParams(req.query).toString() : '';
  const url = `${baseUrl}${path}${queryStr}`;

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);

  const headers = {};
  let body;
  if (['POST', 'PUT', 'PATCH'].includes(method) && req.body !== undefined && req.body !== null) {
    headers['content-type'] = 'application/json';
    body = JSON.stringify(req.body);
  }

  try {
    const upstream = await fetchFn(url, { method, headers, body, signal: ctrl.signal });
    clearTimeout(timer);

    const ct = upstream.headers.get ? upstream.headers.get('content-type')
                                    : upstream.headers.get?.('content-type');
    res.status(upstream.status);

    if (upstream.status === 204) {
      return res.send();
    }
    if (ct && ct.includes('application/json')) {
      const data = await upstream.json();
      return res.json(data);
    }
    const text = await upstream.text();
    return res.send(text);
  } catch (err) {
    clearTimeout(timer);
    if (err.name === 'AbortError') {
      return res.status(504).json({ error: 'upstream timeout', service: 'image-download-service' });
    }
    if (err.code === 'ECONNREFUSED' || err.code === 'ENOTFOUND' || err.code === 'EAI_AGAIN') {
      return res.status(503).json({ error: 'image-download-service unreachable', code: err.code });
    }
    console.error('[imageDownloadProxy] error:', err);
    return res.status(502).json({ error: 'upstream proxy error', message: err.message });
  }
}