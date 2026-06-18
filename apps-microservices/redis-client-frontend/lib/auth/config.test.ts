import { describe, it, expect } from "vitest"
import { parseAdminEmails, resolveClientCredentials } from "./config"

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
})

describe("resolveClientCredentials", () => {
  it("prefers the suffixed vars over plain", () => {
    const creds = resolveClientCredentials({
      ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND: "id-suffixed",
      ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND: "secret-suffixed",
      ACCOUNT_CLIENT_ID: "id-plain",
      ACCOUNT_CLIENT_SECRET: "secret-plain",
    })
    expect(creds).toEqual({ clientId: "id-suffixed", clientSecret: "secret-suffixed" })
  })
  it("falls back to plain vars", () => {
    const creds = resolveClientCredentials({
      ACCOUNT_CLIENT_ID: "id-plain",
      ACCOUNT_CLIENT_SECRET: "secret-plain",
    })
    expect(creds).toEqual({ clientId: "id-plain", clientSecret: "secret-plain" })
  })
  it("throws when neither is set", () => {
    expect(() => resolveClientCredentials({})).toThrow(/Missing ACCOUNT_CLIENT_ID/)
  })
})
