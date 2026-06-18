import { SignJWT, jwtVerify } from "jose"

export const SESSION_COOKIE = "rcf_session"

function sessionKey(): Uint8Array {
  const secret = process.env.SESSION_SECRET
  if (!secret) throw new Error("[redis-client] Missing SESSION_SECRET")
  return new TextEncoder().encode(secret)
}

export interface SessionClaims {
  email: string
  name?: string
}

export async function createSessionToken(claims: SessionClaims, ttlSeconds: number): Promise<string> {
  return new SignJWT({ name: claims.name })
    .setProtectedHeader({ alg: "HS256" })
    .setSubject(claims.email)
    .setIssuedAt()
    .setExpirationTime(Math.floor(Date.now() / 1000) + ttlSeconds)
    .sign(sessionKey())
}

export async function readSession(token: string | undefined): Promise<SessionClaims | null> {
  if (!token) return null
  try {
    const { payload } = await jwtVerify(token, sessionKey(), { algorithms: ["HS256"] })
    const email = payload.sub
    if (!email) return null
    return { email, name: payload.name as string | undefined }
  } catch {
    return null
  }
}
