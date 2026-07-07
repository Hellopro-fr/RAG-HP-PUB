import { describe, it, expect, vi, beforeEach } from "vitest"

const fake = {
  isOpen: true,
  connect: vi.fn().mockResolvedValue(undefined),
  on: vi.fn(),
  scan: vi.fn(),
  type: vi.fn(),
  ttl: vi.fn(),
  memoryUsage: vi.fn(),
  get: vi.fn(),
  dbSize: vi.fn(),
}

vi.mock("redis", () => ({ createClient: () => fake }))

// Import AFTER the mock is registered.
const { RedisCacheRepository } = await import("@/lib/infrastructure/redis-cache-repository")
const repo = new RedisCacheRepository()

beforeEach(() => {
  process.env.REDIS_HOST = "h"
  process.env.REDIS_PORT = "1"
  process.env.REDIS_SECRET = "s"
  vi.clearAllMocks()
  fake.isOpen = true
})

describe("RedisCacheRepository", () => {
  it("scanKeys returns {keys,nextCursor} and passes MATCH/COUNT", async () => {
    fake.scan.mockResolvedValue({ cursor: 12, keys: ["a", "b"] })
    const r = await repo.scanKeys(0, "foo*", 50)
    expect(r).toEqual({ keys: ["a", "b"], nextCursor: 12 })
    expect(fake.scan).toHaveBeenCalledWith(0, { MATCH: "foo*", COUNT: 50 })
  })

  it("scanKeys defaults empty match to * and COUNT 100", async () => {
    fake.scan.mockResolvedValue({ cursor: 0, keys: [] })
    await repo.scanKeys(0, "")
    expect(fake.scan).toHaveBeenCalledWith(0, { MATCH: "*", COUNT: 100 })
  })

  it("getKeyMeta composes type/ttl/size without GET", async () => {
    fake.type.mockResolvedValue("hash")
    fake.ttl.mockResolvedValue(300)
    fake.memoryUsage.mockResolvedValue(2048)
    const m = await repo.getKeyMeta("k")
    expect(m).toEqual({ key: "k", type: "hash", ttl: 300, size: 2048 })
    expect(fake.get).not.toHaveBeenCalled()
  })

  it("getKeyMeta maps ttl<=0 to undefined and null memory to 0", async () => {
    fake.type.mockResolvedValue("string")
    fake.ttl.mockResolvedValue(-1)
    fake.memoryUsage.mockResolvedValue(null)
    const m = await repo.getKeyMeta("k")
    expect(m.ttl).toBeUndefined()
    expect(m.size).toBe(0)
  })

  it("getKeyMeta degrades on per-command failure", async () => {
    fake.type.mockRejectedValue(new Error("x"))
    fake.ttl.mockRejectedValue(new Error("x"))
    fake.memoryUsage.mockRejectedValue(new Error("x"))
    const m = await repo.getKeyMeta("k")
    expect(m).toEqual({ key: "k", type: "unknown", ttl: undefined, size: 0 })
  })

  it("dbSize returns the count", async () => {
    fake.dbSize.mockResolvedValue(42)
    expect(await repo.dbSize()).toBe(42)
  })
})
