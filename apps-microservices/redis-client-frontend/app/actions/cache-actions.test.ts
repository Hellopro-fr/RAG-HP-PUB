import { describe, it, expect, vi, beforeEach } from "vitest"

vi.mock("@/lib/infrastructure/redis-cache-repository", () => ({
  cacheRepository: {
    scanKeys: vi.fn(),
    getKeyMeta: vi.fn(),
    dbSize: vi.fn(),
    deleteEntry: vi.fn(),
    clearAll: vi.fn(),
  },
}))

// Static imports — vitest hoists vi.mock above imports (avoids TS1378 under target ES6).
import { listCacheKeys, invalidateCacheEntry } from "@/app/actions/cache-actions"
import { cacheRepository } from "@/lib/infrastructure/redis-cache-repository"

beforeEach(() => vi.clearAllMocks())

describe("listCacheKeys", () => {
  it("page 1 fetches meta + dbSize", async () => {
    vi.mocked(cacheRepository.scanKeys).mockResolvedValue({ keys: ["a"], nextCursor: 5 })
    vi.mocked(cacheRepository.getKeyMeta).mockResolvedValue({ key: "a", type: "string", size: 10 })
    vi.mocked(cacheRepository.dbSize).mockResolvedValue(10)
    const r = await listCacheKeys({ cursor: 0, match: "x*" })
    expect(r).toEqual({ entries: [{ key: "a", type: "string", size: 10 }], nextCursor: 5, total: 10 })
    expect(cacheRepository.scanKeys).toHaveBeenCalledWith(0, "x*")
    expect(cacheRepository.dbSize).toHaveBeenCalledOnce()
  })

  it("later pages skip dbSize (total 0)", async () => {
    vi.mocked(cacheRepository.scanKeys).mockResolvedValue({ keys: [], nextCursor: 0 })
    const r = await listCacheKeys({ cursor: 5, match: "" })
    expect(r.total).toBe(0)
    expect(cacheRepository.dbSize).not.toHaveBeenCalled()
  })

  it("coerces a negative/NaN cursor to 0", async () => {
    vi.mocked(cacheRepository.scanKeys).mockResolvedValue({ keys: [], nextCursor: 0 })
    vi.mocked(cacheRepository.dbSize).mockResolvedValue(0)
    await listCacheKeys({ cursor: -3 })
    expect(cacheRepository.scanKeys).toHaveBeenCalledWith(0, "*")
    expect(cacheRepository.dbSize).toHaveBeenCalledOnce()
  })

  it("returns error shape when the repo throws", async () => {
    vi.mocked(cacheRepository.scanKeys).mockRejectedValue(new Error("down"))
    const r = await listCacheKeys({ cursor: 0 })
    expect(r).toEqual({ entries: [], nextCursor: 0, total: 0, error: "Failed to list cache keys" })
  })
})

describe("invalidateCacheEntry", () => {
  it("rejects an invalid key without touching Redis", async () => {
    const r = await invalidateCacheEntry("")
    expect(r.success).toBe(false)
    expect(cacheRepository.deleteEntry).not.toHaveBeenCalled()
  })
})
