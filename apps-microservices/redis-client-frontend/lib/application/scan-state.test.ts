import { describe, it, expect } from "vitest"
import { initialState, applyScanResult, toMatchGlob } from "@/lib/application/scan-state"
import type { KeyMeta } from "@/lib/domain/cache-entry"

const a: KeyMeta = { key: "a", type: "string", ttl: 10, size: 100 }
const b: KeyMeta = { key: "b", type: "hash", size: 50 }

describe("scan-state", () => {
  it("initialState is unscanned and empty", () => {
    expect(initialState).toEqual({ entries: [], nextCursor: 0, total: null, scanned: false })
  })

  it("reset=true replaces entries and adopts total", () => {
    const s = applyScanResult(initialState, { entries: [a], nextCursor: 5, total: 42 }, true)
    expect(s).toEqual({ entries: [a], nextCursor: 5, total: 42, scanned: true, error: undefined })
  })

  it("reset=false appends and keeps prior total", () => {
    const first = applyScanResult(initialState, { entries: [a], nextCursor: 5, total: 42 }, true)
    const second = applyScanResult(first, { entries: [b], nextCursor: 0, total: 0 }, false)
    expect(second.entries).toEqual([a, b])
    expect(second.total).toBe(42)
    expect(second.nextCursor).toBe(0)
  })

  it("error result sets error + scanned and preserves entries", () => {
    const first = applyScanResult(initialState, { entries: [a], nextCursor: 5, total: 42 }, true)
    const errored = applyScanResult(first, { entries: [], nextCursor: 0, total: 0, error: "boom" }, false)
    expect(errored.error).toBe("boom")
    expect(errored.scanned).toBe(true)
    expect(errored.entries).toEqual([a])
  })

  it("toMatchGlob wraps non-empty terms and trims", () => {
    expect(toMatchGlob("")).toBe("*")
    expect(toMatchGlob("   ")).toBe("*")
    expect(toMatchGlob(" foo ")).toBe("*foo*")
  })
})
