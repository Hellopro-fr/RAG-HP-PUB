import { describe, it, expect, beforeEach } from "vitest"
import { createSessionToken, readSession, SESSION_COOKIE } from "./session"

beforeEach(() => {
  process.env.SESSION_SECRET = "unit-test-session-secret"
})

describe("session", () => {
  it("exposes the cookie name", () => {
    expect(SESSION_COOKIE).toBe("rcf_session")
  })

  it("round-trips claims", async () => {
    const tok = await createSessionToken({ email: "alice@hp.fr", name: "Alice" }, 3600)
    const claims = await readSession(tok)
    expect(claims).toEqual({ email: "alice@hp.fr", name: "Alice" })
  })

  it("returns null for an expired token", async () => {
    const tok = await createSessionToken({ email: "alice@hp.fr" }, -1)
    expect(await readSession(tok)).toBeNull()
  })

  it("returns null for garbage", async () => {
    expect(await readSession("not-a-jwt")).toBeNull()
    expect(await readSession(undefined)).toBeNull()
  })

  it("rejects a token signed with a different secret", async () => {
    const tok = await createSessionToken({ email: "alice@hp.fr" }, 3600)
    process.env.SESSION_SECRET = "different-secret"
    expect(await readSession(tok)).toBeNull()
  })

  it("returns null for a token without sub", async () => {
    const { SignJWT } = await import("jose")
    const key = new TextEncoder().encode("unit-test-session-secret")
    const tok = await new SignJWT({})
      .setProtectedHeader({ alg: "HS256" })
      .setIssuedAt()
      .setExpirationTime("1h")
      .sign(key)
    expect(await readSession(tok)).toBeNull()
  })

  it("throws when SESSION_SECRET is missing", async () => {
    delete process.env.SESSION_SECRET
    await expect(readSession("any.jwt.token")).rejects.toThrow(/Missing SESSION_SECRET/)
  })
})
