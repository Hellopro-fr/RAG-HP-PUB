export class ApiError extends Error {
  status: number
  code: string
  constructor(message: string, status: number, code: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

let unauthorizedHandler: (() => void) | null = null

export function onUnauthorized(handler: () => void) {
  unauthorizedHandler = handler
}

export interface ApiOpts {
  method?: string
  body?: unknown
  query?: Record<string, string | number | undefined>
  signal?: AbortSignal
}

function buildUrl(path: string, query?: ApiOpts['query']): string {
  if (!query) return path
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null) params.set(k, String(v))
  }
  const qs = params.toString()
  return qs ? `${path}?${qs}` : path
}

export async function api<T>(path: string, opts: ApiOpts = {}): Promise<T> {
  const init: RequestInit = {
    method: opts.method ?? 'GET',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    signal: opts.signal,
  }
  if (opts.body !== undefined) init.body = JSON.stringify(opts.body)

  const res = await fetch(buildUrl(path, opts.query), init)
  if (res.status === 401) {
    if (unauthorizedHandler) unauthorizedHandler()
    throw new ApiError('Unauthorized', 401, 'unauthorized')
  }
  if (!res.ok) {
    let body: { error?: string; error_description?: string } = {}
    try { body = await res.json() } catch { /* ignore */ }
    throw new ApiError(body.error_description || body.error || res.statusText, res.status, body.error || 'http_error')
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}
