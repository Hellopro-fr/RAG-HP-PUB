// Auth configuration: read + validate environment at call time (not import time,
// so tests can vary process.env per case).

type Env = Record<string, string | undefined>

export function parseAdminEmails(raw: string | undefined): Set<string> {
  if (!raw) return new Set()
  return new Set(
    raw
      .split(",")
      .map((e) => e.trim().toLowerCase())
      .filter((e) => e.length > 0),
  )
}

// Derive the per-service credential env keys from SERVICE_NAME. Mirrors
// libs/account-client-go DeriveEnvKeys and libs/common-utils/sso, so this module
// is a drop-in for any Node service: "redis-client-frontend" ->
// ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND / ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND.
export function deriveClientEnvKeys(serviceName: string): [string, string] {
  const slug = serviceName
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
  return [`ACCOUNT_CLIENT_ID_${slug}`, `ACCOUNT_CLIENT_SECRET_${slug}`]
}

// Module-level memo of creds fetched from the internal API (keyed by service name).
const _fetchedCredsCache = new Map<string, { clientId: string; clientSecret: string }>()

// Test-only: clear the fetched-credentials memo so cases are isolated.
export function __resetClientCredentialsCache(): void {
  _fetchedCredsCache.clear()
}

// Fetch (clientId, clientSecret) from account-service's admin-gated internal endpoint.
// Mirrors libs/account-client-go credentials_api.go GetCredentialsFromAPI.
async function fetchClientCredentialsFromApi(
  baseUrl: string,
  serviceName: string,
  adminToken: string,
): Promise<{ clientId: string; clientSecret: string }> {
  const cached = _fetchedCredsCache.get(serviceName)
  if (cached) return cached
  const url = `${baseUrl.replace(/\/+$/, "")}/internal/credentials/${encodeURIComponent(serviceName)}`
  const r = await fetch(url, { headers: { "X-Admin-Token": adminToken } })
  if (r.status === 404) {
    throw new Error(`[account-auth] no active service named "${serviceName}" in account-service`)
  }
  if (!r.ok) {
    throw new Error(`[account-auth] internal credentials endpoint returned ${r.status}`)
  }
  let body: { client_id?: string; client_secret?: string }
  try {
    body = (await r.json()) as { client_id?: string; client_secret?: string }
  } catch {
    throw new Error("[account-auth] internal credentials response was not valid JSON")
  }
  if (!body.client_id || !body.client_secret) {
    throw new Error("[account-auth] internal credentials response missing fields")
  }
  const creds = { clientId: body.client_id, clientSecret: body.client_secret }
  _fetchedCredsCache.set(serviceName, creds)
  return creds
}

// Resolve (clientId, clientSecret): SERVICE_NAME-derived env keys, then plain env,
// then (if ACCOUNT_INTERNAL_TOKEN set) the account-service internal API. Env wins.
export async function resolveClientCredentials(
  env: Env = process.env,
): Promise<{ clientId: string; clientSecret: string }> {
  const serviceName = (env.SERVICE_NAME || "").trim()
  if (serviceName) {
    const [idKey, secretKey] = deriveClientEnvKeys(serviceName)
    if (env[idKey] && env[secretKey]) {
      return { clientId: env[idKey]!, clientSecret: env[secretKey]! }
    }
  }
  if (env.ACCOUNT_CLIENT_ID && env.ACCOUNT_CLIENT_SECRET) {
    return { clientId: env.ACCOUNT_CLIENT_ID, clientSecret: env.ACCOUNT_CLIENT_SECRET }
  }
  if (serviceName && env.ACCOUNT_INTERNAL_TOKEN && env.ACCOUNT_BASE_URL) {
    return fetchClientCredentialsFromApi(env.ACCOUNT_BASE_URL, serviceName, env.ACCOUNT_INTERNAL_TOKEN)
  }
  throw new Error(
    "[account-auth] Missing account-service credentials: set " +
      "ACCOUNT_CLIENT_ID_<SERVICE_NAME> + ACCOUNT_CLIENT_SECRET_<SERVICE_NAME>, " +
      "plain ACCOUNT_CLIENT_ID + ACCOUNT_CLIENT_SECRET, " +
      "or SERVICE_NAME + ACCOUNT_INTERNAL_TOKEN (+ ACCOUNT_BASE_URL) for the internal API",
  )
}

function req(name: string, env: Env): string {
  const v = env[name]
  if (!v) throw new Error(`[redis-client] Missing required env var: ${name}`)
  return v
}

// Trusted public origin of THIS app, derived from its registered callback
// (ACCOUNT_REDIRECT_URI). Use this for app-internal redirects instead of `request.url`,
// which is unreliable behind a reverse proxy / container port-map (it reports the
// internal container host, e.g. http://<container-id>:3000).
export function appOrigin(env: Env = process.env): string {
  const uri = env.ACCOUNT_REDIRECT_URI
  if (!uri) {
    throw new Error("[account-auth] Missing required env var: ACCOUNT_REDIRECT_URI")
  }
  return new URL(uri).origin
}

export interface AuthConfig {
  accountPublicUrl: string
  accountBaseUrl: string
  clientId: string
  clientSecret: string
  redirectUri: string
  jwtSecret: string
  adminEmails: Set<string>
  secureCookie: boolean
  sessionTtlSeconds: number
  centralLogout: boolean
}

export async function getAuthConfig(env: Env = process.env): Promise<AuthConfig> {
  const { clientId, clientSecret } = await resolveClientCredentials(env)
  const ttl = Number(env.SESSION_TTL || "28800")
  if (!Number.isFinite(ttl) || ttl <= 0) {
    throw new Error(`[redis-client] SESSION_TTL must be a positive integer, got: ${env.SESSION_TTL}`)
  }
  return {
    accountPublicUrl: req("ACCOUNT_PUBLIC_URL", env).replace(/\/+$/, ""),
    accountBaseUrl: req("ACCOUNT_BASE_URL", env).replace(/\/+$/, ""),
    clientId,
    clientSecret,
    redirectUri: req("ACCOUNT_REDIRECT_URI", env),
    jwtSecret: req("JWT_SECRET", env),
    adminEmails: parseAdminEmails(env.ADMIN_EMAILS),
    secureCookie: (env.SECURE_COOKIE || "false").toLowerCase() === "true",
    sessionTtlSeconds: ttl,
    centralLogout: (env.SSO_CENTRAL_LOGOUT || "false").toLowerCase() === "true",
  }
}
