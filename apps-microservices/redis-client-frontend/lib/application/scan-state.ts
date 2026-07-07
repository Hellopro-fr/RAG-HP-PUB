// Pure, framework-free scan-state transitions for the cache browser.
// Kept out of the React component so the append/replace + total-sticky logic is unit-testable.
import type { KeyMeta } from "@/lib/domain/cache-entry"

export interface ScanResult {
  entries: KeyMeta[]
  nextCursor: number
  total: number
  error?: string
}

export interface BrowserState {
  entries: KeyMeta[]
  nextCursor: number
  total: number | null // null until the first successful page-1 scan
  scanned: boolean
  error?: string
}

export const initialState: BrowserState = {
  entries: [],
  nextCursor: 0,
  total: null,
  scanned: false,
}

// reset=true  → page 1: replace entries, adopt result.total.
// reset=false → append (Load more): keep entries + prior total.
export function applyScanResult(state: BrowserState, result: ScanResult, reset: boolean): BrowserState {
  if (result.error) {
    return { ...state, scanned: true, error: result.error }
  }
  return {
    entries: reset ? result.entries : [...state.entries, ...result.entries],
    nextCursor: result.nextCursor,
    total: reset ? result.total : state.total,
    scanned: true,
    error: undefined,
  }
}

// Search term → Redis glob. Empty → "*" (all keys). Wraps in * for substring match.
// NOTE: this is a Redis glob, not a regex; * ? [ in the term are glob metacharacters.
export function toMatchGlob(term: string): string {
  const t = term.trim()
  return t === "" ? "*" : `*${t}*`
}
