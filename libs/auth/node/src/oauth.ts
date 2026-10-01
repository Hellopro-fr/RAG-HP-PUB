import { jwtVerify } from "jose"

function b64url(buf: ArrayBuffer | Uint8Array): string {
  const bytes = buf instanceof Uint8Array ? buf : new Uint8Array(buf)
  return Buffer.from(bytes)
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "")
}

export interface Pkce {
  verifier: string
  challenge: string
}

export async function generatePkce(): Promise<Pkce> {
  const verifier = b64url(crypto.getRandomValues(new Uint8Array(32)))
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier))
  return { verifier, challenge: b64url(digest) }
}

export function randomState(): string {
  return b64url(crypto.getRandomValues(new Uint8Array(16)))
}

export function buildAuthorizeUrl(opts: {
  publicUrl: string
  clientId: string
  redirectUri: string
  challenge: string
  state: string
}): string {
  const params = new URLSearchParams({
    response_type: "code",
    client_id: opts.clientId,
    redirect_uri: opts.redirectUri,
    code_challenge: opts.challenge,
    code_challenge_method: "S256",
    state: opts.state,
  })
  return `${opts.publicUrl}/authorize?${params.toString()}`
}

export interface TokenResponse {
  access_token: string
  refresh_token?: string
  token_type?: string
  expires_in?: number
}

export async function exchangeCode(opts: {
  baseUrl: string
  clientId: string
  clientSecret: string
  code: string
  redirectUri: string
  verifier: string
}): Promise<TokenResponse> {
  const basic = Buffer.from(`${opts.clientId}:${opts.clientSecret}`).toString("base64")
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code: opts.code,
    redirect_uri: opts.redirectUri,
    code_verifier: opts.verifier,
  })
  const r = await fetch(`${opts.baseUrl}/token`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Authorization: `Basic ${basic}`,
    },
    body: body.toString(),
  })
  if (!r.ok) {
    throw new Error(`[redis-client] token exchange failed: ${r.status}`)
  }
  return (await r.json()) as TokenResponse
}

export interface Identity {
  email: string
  name?: string
}

export async function verifyAndExtract(accessToken: string, jwtSecret: string): Promise<Identity> {
  const key = new TextEncoder().encode(jwtSecret)
  // aud is intentionally NOT verified (account-service sets aud=client_id).
  const { payload } = await jwtVerify(accessToken, key, { algorithms: ["HS256"] })
  const email = (payload.sub as string | undefined) ?? (payload.email as string | undefined)
  if (!email) throw new Error("[redis-client] token missing sub/email claim")
  return { email, name: payload.name as string | undefined }
}
