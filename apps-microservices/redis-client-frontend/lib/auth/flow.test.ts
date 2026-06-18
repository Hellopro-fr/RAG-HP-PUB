import { describe, it, expect, vi, beforeEach } from "vitest"
import * as oauth from "./oauth"
import * as session from "./session"
import * as config from "./config"
import { startLogin, completeCallback } from "./flow"

const baseCfg: config.AuthConfig = {
  accountPublicUrl: "http://localhost:8601",
  accountBaseUrl: "http://acct:8600",
  clientId: "cid",
  clientSecret: "sec",
  redirectUri: "http://localhost:3551/auth/callback",
  jwtSecret: "jwt",
  adminEmails: new Set(["alice@hp.fr"]),
  secureCookie: false,
  sessionTtlSeconds: 3600,
  centralLogout: false,
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(config, "getAuthConfig").mockReturnValue(baseCfg)
})

describe("startLogin", () => {
  it("builds the authorize url with a fresh pkce + state", async () => {
    vi.spyOn(oauth, "generatePkce").mockResolvedValue({ verifier: "ver", challenge: "chal" })
    vi.spyOn(oauth, "randomState").mockReturnValue("st")
    const out = await startLogin()
    expect(out.verifier).toBe("ver")
    expect(out.state).toBe("st")
    expect(out.secureCookie).toBe(false)
    expect(out.authorizeUrl).toContain("http://localhost:8601/authorize?")
    expect(out.authorizeUrl).toContain("code_challenge=chal")
  })
})

describe("completeCallback", () => {
  it("errors on missing code/state", async () => {
    expect((await completeCallback({})).status).toBe("error")
  })
  it("errors on state mismatch", async () => {
    const r = await completeCallback({ code: "c", state: "a", stateCookie: "b", verifierCookie: "v" })
    expect(r).toEqual({ status: "error", reason: "state_mismatch" })
  })
  it("errors on missing verifier", async () => {
    const r = await completeCallback({ code: "c", state: "a", stateCookie: "a" })
    expect(r).toEqual({ status: "error", reason: "missing_verifier" })
  })
  it("denies a non-allow-listed email", async () => {
    vi.spyOn(oauth, "exchangeCode").mockResolvedValue({ access_token: "tok" })
    vi.spyOn(oauth, "verifyAndExtract").mockResolvedValue({ email: "mallory@hp.fr" })
    const r = await completeCallback({ code: "c", state: "a", stateCookie: "a", verifierCookie: "v" })
    expect(r).toEqual({ status: "denied", email: "mallory@hp.fr" })
  })
  it("returns ok + session token for an allowed email", async () => {
    vi.spyOn(oauth, "exchangeCode").mockResolvedValue({ access_token: "tok" })
    vi.spyOn(oauth, "verifyAndExtract").mockResolvedValue({ email: "Alice@hp.fr", name: "Alice" })
    vi.spyOn(session, "createSessionToken").mockResolvedValue("session-jwt")
    const r = await completeCallback({ code: "c", state: "a", stateCookie: "a", verifierCookie: "v" })
    expect(r).toEqual({ status: "ok", sessionToken: "session-jwt", ttlSeconds: 3600, secureCookie: false })
  })
  it("errors when token exchange throws", async () => {
    vi.spyOn(oauth, "exchangeCode").mockRejectedValue(new Error("boom"))
    const r = await completeCallback({ code: "c", state: "a", stateCookie: "a", verifierCookie: "v" })
    expect(r).toEqual({ status: "error", reason: "exchange_failed" })
  })
  it("errors when token verification throws", async () => {
    vi.spyOn(oauth, "exchangeCode").mockResolvedValue({ access_token: "tok" })
    vi.spyOn(oauth, "verifyAndExtract").mockRejectedValue(new Error("bad sig"))
    const r = await completeCallback({ code: "c", state: "a", stateCookie: "a", verifierCookie: "v" })
    expect(r).toEqual({ status: "error", reason: "token_invalid" })
  })
})
