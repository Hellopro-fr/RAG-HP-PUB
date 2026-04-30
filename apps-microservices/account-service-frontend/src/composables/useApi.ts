const BASE = ''  // same origin (Nginx proxies /authorize, /token, etc. to backend)

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const text = await r.text()
  let json: unknown
  try { json = text ? JSON.parse(text) : {} } catch { json = {} }
  if (!r.ok) {
    const detail = (json as { error?: string })?.error || `HTTP ${r.status}`
    throw new Error(detail)
  }
  return json as T
}
