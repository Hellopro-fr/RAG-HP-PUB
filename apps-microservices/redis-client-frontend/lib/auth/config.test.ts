import { describe, it, expect } from "vitest"
import { parseAdminEmails, resolveClientCredentials, deriveClientEnvKeys, getAuthConfig } from "./config"

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
  it("derives the key from SERVICE_NAME (reusable by any service)", () => {
    const creds = resolveClientCredentials({
      SERVICE_NAME: "api-gateway",
      ACCOUNT_CLIENT_ID_API_GATEWAY: "gw-id",
      ACCOUNT_CLIENT_SECRET_API_GATEWAY: "gw-sec",
    })
    expect(creds).toEqual({ clientId: "gw-id", clientSecret: "gw-sec" })
  })
  it("prefers the SERVICE_NAME-derived vars over plain", () => {
    const creds = resolveClientCredentials({
      SERVICE_NAME: "redis-client-frontend",
      ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND: "id-suffixed",
      ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND: "secret-suffixed",
      ACCOUNT_CLIENT_ID: "id-plain",
      ACCOUNT_CLIENT_SECRET: "secret-plain",
    })
    expect(creds).toEqual({ clientId: "id-suffixed", clientSecret: "secret-suffixed" })
  })
  it("falls back to plain vars when SERVICE_NAME-derived pair is unset", () => {
    const creds = resolveClientCredentials({
      SERVICE_NAME: "redis-client-frontend",
      ACCOUNT_CLIENT_ID: "id-plain",
      ACCOUNT_CLIENT_SECRET: "secret-plain",
    })
    expect(creds).toEqual({ clientId: "id-plain", clientSecret: "secret-plain" })
  })
  it("throws when neither is set", () => {
    expect(() => resolveClientCredentials({ SERVICE_NAME: "redis-client-frontend" })).toThrow(
      /Missing account-service credentials/,
    )
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
  it("returns expected fields with defaults", () => {
    const cfg = getAuthConfig(baseEnv)
    expect(cfg.accountPublicUrl).toBe("http://localhost:8601")
    expect(cfg.accountBaseUrl).toBe("http://account-service-backend:8600")
    expect(cfg.sessionTtlSeconds).toBe(28800)
    expect(cfg.secureCookie).toBe(false)
    expect(cfg.centralLogout).toBe(false)
    expect(cfg.adminEmails).toBeInstanceOf(Set)
  })
  it("throws when SESSION_TTL is set to an invalid value", () => {
    expect(() => getAuthConfig({ ...baseEnv, SESSION_TTL: "abc" })).toThrow(/SESSION_TTL/)
  })
  it("uses a custom SESSION_TTL when valid", () => {
    const cfg = getAuthConfig({ ...baseEnv, SESSION_TTL: "3600" })
    expect(cfg.sessionTtlSeconds).toBe(3600)
  })
  it("throws when JWT_SECRET is missing", () => {
    expect(() => getAuthConfig({ ...baseEnv, JWT_SECRET: undefined })).toThrow(/JWT_SECRET/)
  })
})
