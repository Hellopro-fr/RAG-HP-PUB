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
})
