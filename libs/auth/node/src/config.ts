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

// Resolve (clientId, clientSecret) by SERVICE_NAME-derived keys, falling back to
// plain ACCOUNT_CLIENT_ID / ACCOUNT_CLIENT_SECRET. Same contract as the Go/Python clients.
export function resolveClientCredentials(env: Env = process.env): {
  clientId: string
  clientSecret: string
} {
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
  throw new Error(
    "[account-auth] Missing account-service credentials: set " +
      "ACCOUNT_CLIENT_ID_<SERVICE_NAME> + ACCOUNT_CLIENT_SECRET_<SERVICE_NAME>, " +
      "or plain ACCOUNT_CLIENT_ID + ACCOUNT_CLIENT_SECRET",
  )
}

function req(name: string, env: Env): string {
  const v = env[name]
  if (!v) throw new Error(`[redis-client] Missing required env var: ${name}`)
  return v
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

export function getAuthConfig(env: Env = process.env): AuthConfig {
  const { clientId, clientSecret } = resolveClientCredentials(env)
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
