import { describe, it, expect, vi, beforeEach } from "vitest"
import {
  parseAdminEmails,
  resolveClientCredentials,
  deriveClientEnvKeys,
  getAuthConfig,
  appOrigin,
  __resetClientCredentialsCache,
} from "./config"

describe("parseAdminEmails", () => {
  it("lowercases, trims, and drops empties", () => {
    const set = parseAdminEmails(" Alice@HP.fr , bob@hp.fr ,, ")
    expect(set.has("alice@hp.fr")).toBe(true)
    expect(set.has("bob@hp.fr")).toBe(true)
    expect(set.size).toBe(2)
  })
  it("returns empty set for undefined", () => {
    expect(parseAdminEmails(undefined).size).toBe(0)
  })
  it("returns empty set for empty string", () => {
    expect(parseAdminEmails("").size).toBe(0)
  })
})

describe("deriveClientEnvKeys", () => {
  it("slugifies SERVICE_NAME like the Go/Python clients", () => {
    expect(deriveClientEnvKeys("redis-client-frontend")).toEqual([
      "ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND",
      "ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND",
    ])
    expect(deriveClientEnvKeys("api-gateway")).toEqual([
      "ACCOUNT_CLIENT_ID_API_GATEWAY",
      "ACCOUNT_CLIENT_SECRET_API_GATEWAY",
    ])
  })
})

describe("resolveClientCredentials", () => {
  it("derives the key from SERVICE_NAME (reusable by any service)", async () => {
    const creds = await resolveClientCredentials({
      SERVICE_NAME: "api-gateway",
      ACCOUNT_CLIENT_ID_API_GATEWAY: "gw-id",
      ACCOUNT_CLIENT_SECRET_API_GATEWAY: "gw-sec",
    })
    expect(creds).toEqual({ clientId: "gw-id", clientSecret: "gw-sec" })
  })
  it("prefers the SERVICE_NAME-derived vars over plain", async () => {
    const creds = await resolveClientCredentials({
      SERVICE_NAME: "redis-client-frontend",
      ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND: "id-suffixed",
      ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND: "secret-suffixed",
      ACCOUNT_CLIENT_ID: "id-plain",
      ACCOUNT_CLIENT_SECRET: "secret-plain",
    })
    expect(creds).toEqual({ clientId: "id-suffixed", clientSecret: "secret-suffixed" })
  })
  it("falls back to plain vars when SERVICE_NAME-derived pair is unset", async () => {
    const creds = await resolveClientCredentials({
      SERVICE_NAME: "redis-client-frontend",
      ACCOUNT_CLIENT_ID: "id-plain",
      ACCOUNT_CLIENT_SECRET: "secret-plain",
    })
    expect(creds).toEqual({ clientId: "id-plain", clientSecret: "secret-plain" })
  })
  it("throws when neither is set", async () => {
    await expect(resolveClientCredentials({ SERVICE_NAME: "redis-client-frontend" })).rejects.toThrow(
      /Missing account-service credentials/,
    )
  })
})

describe("resolveClientCredentials internal-API fallback", () => {
  const base = {
    SERVICE_NAME: "redis-client-frontend",
    ACCOUNT_BASE_URL: "http://acct:8600/",
    ACCOUNT_INTERNAL_TOKEN: "adm",
  }
  beforeEach(() => {
    __resetClientCredentialsCache()
    vi.restoreAllMocks()
  })

  it("fetches from the internal endpoint when env creds are absent", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, status: 200, json: async () => ({ client_id: "fid", client_secret: "fsec" }) })
    vi.stubGlobal("fetch", fetchMock)
    const creds = await resolveClientCredentials(base)
    expect(creds).toEqual({ clientId: "fid", clientSecret: "fsec" })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe("http://acct:8600/internal/credentials/redis-client-frontend")
    expect(init.headers["X-Admin-Token"]).toBe("adm")
  })

  it("memoizes the fetched creds (no second fetch)", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, status: 200, json: async () => ({ client_id: "fid", client_secret: "fsec" }) })
    vi.stubGlobal("fetch", fetchMock)
    await resolveClientCredentials(base)
    await resolveClientCredentials(base)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it("throws on 404", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({}) }))
    await expect(resolveClientCredentials(base)).rejects.toThrow(/no active service/)
  })

  it("throws on a non-404 error status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}) }))
    await expect(resolveClientCredentials(base)).rejects.toThrow(/returned 500/)
  })

  it("throws when the response is missing client fields", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ client_id: "only-id" }) }))
    await expect(resolveClientCredentials(base)).rejects.toThrow(/missing fields/)
  })

  it("env creds still win over the fetch", async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
    const creds = await resolveClientCredentials({
      ...base,
      ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND: "eid",
      ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND: "esec",
    })
    expect(creds).toEqual({ clientId: "eid", clientSecret: "esec" })
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

const baseEnv = {
  ACCOUNT_PUBLIC_URL: "http://localhost:8601/",
  ACCOUNT_BASE_URL: "http://account-service-backend:8600/",
  ACCOUNT_REDIRECT_URI: "http://localhost:3551/auth/callback",
  ACCOUNT_CLIENT_ID: "cid",
  ACCOUNT_CLIENT_SECRET: "sec",
  JWT_SECRET: "jwt",
}

describe("getAuthConfig", () => {
  it("returns expected fields with defaults", async () => {
    const cfg = await getAuthConfig(baseEnv)
    expect(cfg.accountPublicUrl).toBe("http://localhost:8601")
    expect(cfg.accountBaseUrl).toBe("http://account-service-backend:8600")
    expect(cfg.sessionTtlSeconds).toBe(28800)
    expect(cfg.secureCookie).toBe(false)
    expect(cfg.centralLogout).toBe(false)
    expect(cfg.adminEmails).toBeInstanceOf(Set)
  })
  it("throws when SESSION_TTL is set to an invalid value", async () => {
    await expect(getAuthConfig({ ...baseEnv, SESSION_TTL: "abc" })).rejects.toThrow(/SESSION_TTL/)
  })
  it("uses a custom SESSION_TTL when valid", async () => {
    const cfg = await getAuthConfig({ ...baseEnv, SESSION_TTL: "3600" })
    expect(cfg.sessionTtlSeconds).toBe(3600)
  })
  it("throws when JWT_SECRET is missing", async () => {
    await expect(getAuthConfig({ ...baseEnv, JWT_SECRET: undefined })).rejects.toThrow(/JWT_SECRET/)
  })
})

describe("appOrigin", () => {
  it("derives the app origin from ACCOUNT_REDIRECT_URI (ignores path/port host details)", () => {
    expect(appOrigin({ ACCOUNT_REDIRECT_URI: "http://35.245.31.1:3551/auth/callback" })).toBe(
      "http://35.245.31.1:3551",
    )
  })
  it("throws when ACCOUNT_REDIRECT_URI is missing", () => {
    expect(() => appOrigin({})).toThrow(/ACCOUNT_REDIRECT_URI/)
  })
})
