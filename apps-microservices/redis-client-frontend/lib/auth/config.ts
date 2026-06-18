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

export function resolveClientCredentials(env: Env = process.env): {
  clientId: string
  clientSecret: string
} {
  const clientId =
    env.ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND || env.ACCOUNT_CLIENT_ID
  const clientSecret =
    env.ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND || env.ACCOUNT_CLIENT_SECRET
  if (!clientId || !clientSecret) {
    throw new Error(
      "[redis-client] Missing ACCOUNT_CLIENT_ID(_REDIS_CLIENT_FRONTEND) / ACCOUNT_CLIENT_SECRET(_REDIS_CLIENT_FRONTEND)",
    )
  }
  return { clientId, clientSecret }
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
  return {
    accountPublicUrl: req("ACCOUNT_PUBLIC_URL", env).replace(/\/+$/, ""),
    accountBaseUrl: req("ACCOUNT_BASE_URL", env).replace(/\/+$/, ""),
    clientId,
    clientSecret,
    redirectUri: req("ACCOUNT_REDIRECT_URI", env),
    jwtSecret: req("JWT_SECRET", env),
    adminEmails: parseAdminEmails(env.ADMIN_EMAILS),
    secureCookie: (env.SECURE_COOKIE || "false").toLowerCase() === "true",
    sessionTtlSeconds: Number(env.SESSION_TTL || "28800"),
    centralLogout: (env.SSO_CENTRAL_LOGOUT || "false").toLowerCase() === "true",
  }
}
