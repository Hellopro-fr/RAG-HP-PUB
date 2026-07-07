import { getAuthConfig } from "./config"
import { generatePkce, randomState, buildAuthorizeUrl, exchangeCode, verifyAndExtract } from "./oauth"
import { createSessionToken } from "./session"

export interface LoginStart {
  authorizeUrl: string
  verifier: string
  state: string
  secureCookie: boolean
}

export async function startLogin(): Promise<LoginStart> {
  const cfg = getAuthConfig()
  const { verifier, challenge } = await generatePkce()
  const state = randomState()
  const authorizeUrl = buildAuthorizeUrl({
    publicUrl: cfg.accountPublicUrl,
    clientId: cfg.clientId,
    redirectUri: cfg.redirectUri,
    challenge,
    state,
  })
  return { authorizeUrl, verifier, state, secureCookie: cfg.secureCookie }
}

export type CallbackResult =
  | { status: "ok"; sessionToken: string; ttlSeconds: number; secureCookie: boolean }
  | { status: "denied"; email: string }
  | { status: "error"; reason: string }

export async function completeCallback(input: {
  code?: string | null
  state?: string | null
  stateCookie?: string
  verifierCookie?: string
}): Promise<CallbackResult> {
  const cfg = getAuthConfig()

  if (!input.code || !input.state) return { status: "error", reason: "missing_code_or_state" }
  if (!input.stateCookie || input.stateCookie !== input.state) {
    return { status: "error", reason: "state_mismatch" }
  }
  if (!input.verifierCookie) return { status: "error", reason: "missing_verifier" }

  let tokens
  try {
    tokens = await exchangeCode({
      baseUrl: cfg.accountBaseUrl,
      clientId: cfg.clientId,
      clientSecret: cfg.clientSecret,
      code: input.code,
      redirectUri: cfg.redirectUri,
      verifier: input.verifierCookie,
    })
  } catch {
    return { status: "error", reason: "exchange_failed" }
  }

  let identity
  try {
    identity = await verifyAndExtract(tokens.access_token, cfg.jwtSecret)
  } catch {
    return { status: "error", reason: "token_invalid" }
  }

  if (!cfg.adminEmails.has(identity.email.toLowerCase())) {
    return { status: "denied", email: identity.email }
  }

  const sessionToken = await createSessionToken(
    { email: identity.email, name: identity.name },
    cfg.sessionTtlSeconds,
  )
  return { status: "ok", sessionToken, ttlSeconds: cfg.sessionTtlSeconds, secureCookie: cfg.secureCookie }
}
