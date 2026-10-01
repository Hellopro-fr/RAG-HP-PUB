// Client "brain": owns scan state and orchestrates header + table.
// page.tsx stays a Server Component (session only); all Redis contact is user-initiated here.
"use client"

import { useState, useCallback } from "react"
import { CacheHeader } from "@/components/cache-header"
import { CacheTable } from "@/components/cache-table"
import { listCacheKeys } from "@/app/actions/cache-actions"
import { initialState, applyScanResult, toMatchGlob, type BrowserState } from "@/lib/application/scan-state"
import { useToast } from "@/hooks/use-toast"

interface CacheBrowserProps {
  userEmail?: string
}

export function CacheBrowser({ userEmail }: CacheBrowserProps) {
  const [state, setState] = useState<BrowserState>(initialState)
  const [match, setMatch] = useState("*")
  const [loading, setLoading] = useState(false)
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null)
  const { toast } = useToast()

  const runScan = useCallback(
    async (cursor: number, glob: string, reset: boolean) => {
      setLoading(true)
      try {
        const result = await listCacheKeys({ cursor, match: glob })
        setState((prev) => applyScanResult(prev, result, reset))
        if (result.error) {
          toast({ title: "Error", description: result.error, variant: "destructive" })
        } else if (reset) {
          setLastRefreshed(new Date())
        }
      } catch {
        // listCacheKeys normally returns an error object rather than throwing; guard the
        // transport (network/RSC) case so the UI always surfaces a failure.
        toast({ title: "Error", description: "Scan request failed", variant: "destructive" })
      } finally {
        setLoading(false)
      }
    },
    [toast],
  )

  const handleScan = useCallback(() => {
    setMatch("*")
    void runScan(0, "*", true)
  }, [runScan])

  const handleRefresh = useCallback(() => {
    void runScan(0, match, true)
  }, [runScan, match])

  const handleLoadMore = useCallback(() => {
    void runScan(state.nextCursor, match, false)
  }, [runScan, state.nextCursor, match])

  const handleSearch = useCallback(
    (term: string) => {
      const glob = toMatchGlob(term)
      setMatch(glob)
      void runScan(0, glob, true)
    },
    [runScan],
  )

  const handleChanged = useCallback(() => {
    void runScan(0, match, true)
  }, [runScan, match])

  return (
    <div className="space-y-8">
      <CacheHeader
        totalKeys={state.total}
        lastRefreshed={lastRefreshed}
        loading={loading}
        scanned={state.scanned}
        onRefresh={handleRefresh}
        onCleared={handleChanged}
        userEmail={userEmail}
      />
      <CacheTable
        entries={state.entries}
        nextCursor={state.nextCursor}
        scanned={state.scanned}
        loading={loading}
        onScan={handleScan}
        onLoadMore={handleLoadMore}
        onSearch={handleSearch}
        onDeleted={handleChanged}
      />
    </div>
  )
}
