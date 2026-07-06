import { describe, it, expect, vi, afterEach } from "vitest"
import { SignJWT } from "jose"
import {
  generatePkce,
  randomState,
  buildAuthorizeUrl,
  exchangeCode,
  verifyAndExtract,
} from "./oauth"

const b64url = (buf: ArrayBuffer) =>
  Buffer.from(new Uint8Array(buf)).toString("base64")
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")

afterEach(() => vi.restoreAllMocks())

describe("generatePkce", () => {
  it("produces challenge = b64url(sha256(verifier))", async () => {
    const { verifier, challenge } = await generatePkce()
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier))
    expect(challenge).toBe(b64url(digest))
    expect(verifier).not.toContain("=")
  })
})

describe("randomState", () => {
  it("is url-safe and non-empty", () => {
    expect(randomState()).toMatch(/^[A-Za-z0-9_-]+$/)
  })
})

describe("buildAuthorizeUrl", () => {
  it("encodes params and sets S256", () => {
    const url = buildAuthorizeUrl({
      publicUrl: "http://localhost:8601",
      clientId: "cid",
      redirectUri: "http://localhost:3551/auth/callback",
      challenge: "chal",
      state: "st",
    })
    const u = new URL(url)
    expect(u.origin + u.pathname).toBe("http://localhost:8601/authorize")
    expect(u.searchParams.get("response_type")).toBe("code")
    expect(u.searchParams.get("redirect_uri")).toBe("http://localhost:3551/auth/callback")
    expect(u.searchParams.get("code_challenge_method")).toBe("S256")
    expect(url).toContain("redirect_uri=http%3A%2F%2Flocalhost%3A3551%2Fauth%2Fcallback")
  })
})

describe("exchangeCode", () => {
  it("posts Basic auth + form body", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ access_token: "tok" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    const res = await exchangeCode({
      baseUrl: "http://acct:8600",
      clientId: "cid",
      clientSecret: "sec",
      code: "code123",
      redirectUri: "http://localhost:3551/auth/callback",
      verifier: "ver",
    })
    expect(res.access_token).toBe("tok")
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe("http://acct:8600/token")
    expect(init.headers.Authorization).toBe("Basic " + Buffer.from("cid:sec").toString("base64"))
    expect(init.body).toContain("grant_type=authorization_code")
    expect(init.body).toContain("code_verifier=ver")
  })
  it("throws on non-200", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401 }))
    await expect(
      exchangeCode({ baseUrl: "b", clientId: "c", clientSecret: "s", code: "x", redirectUri: "r", verifier: "v" }),
    ).rejects.toThrow(/401/)
  })
})

describe("verifyAndExtract", () => {
  const secret = "test-secret"
  const key = new TextEncoder().encode(secret)

  it("extracts email from sub on a valid token", async () => {
    const token = await new SignJWT({})
      .setProtectedHeader({ alg: "HS256" })
      .setSubject("alice@hp.fr")
      .setExpirationTime("5m")
      .sign(key)
    const id = await verifyAndExtract(token, secret)
    expect(id.email).toBe("alice@hp.fr")
  })

  it("rejects a token signed with the wrong secret", async () => {
    const token = await new SignJWT({})
      .setProtectedHeader({ alg: "HS256" })
      .setSubject("alice@hp.fr")
      .setExpirationTime("5m")
      .sign(new TextEncoder().encode("wrong-secret"))
    await expect(verifyAndExtract(token, secret)).rejects.toThrow()
  })
})
