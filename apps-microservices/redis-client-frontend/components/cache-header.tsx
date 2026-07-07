// UI Component: dashboard header with stats and actions.
"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { RefreshCw, Trash2 } from "lucide-react"
import { clearAllCache } from "@/app/actions/cache-actions"
import { useToast } from "@/hooks/use-toast"
import { ConfirmDialog } from "./confirm-dialog"

interface CacheHeaderProps {
  totalKeys: number | null
  lastRefreshed: Date | null
  loading: boolean
  scanned: boolean
  onRefresh: () => void
  onCleared: () => void
  userEmail?: string
}

export function CacheHeader({
  totalKeys,
  lastRefreshed,
  loading,
  scanned,
  onRefresh,
  onCleared,
  userEmail,
}: CacheHeaderProps) {
  const [isClearing, setIsClearing] = useState(false)
  const { toast } = useToast()

  const handleClearAll = async () => {
    setIsClearing(true)
    try {
      const result = await clearAllCache()
      if (result.success) {
        toast({ title: "Success", description: "Cache cleared successfully" })
        onCleared()
      } else {
        toast({ title: "Error", description: result.message, variant: "destructive" })
      }
    } finally {
      setIsClearing(false)
    }
  }

  const formatTime = (date: Date) =>
    new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(date)

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold">Redis Cache Manager</h1>
          <p className="text-muted-foreground">Monitor and manage your cached data</p>
        </div>
        {userEmail && (
          <div className="text-right text-sm">
            <p className="text-muted-foreground">{userEmail}</p>
            <a href="/auth/logout" className="underline">
              Sign out
            </a>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-card border rounded-lg p-4">
          <p className="text-sm text-muted-foreground">Total Keys</p>
          <p className="text-2xl font-bold">{totalKeys ?? "—"}</p>
        </div>
        <div className="bg-card border rounded-lg p-4">
          <p className="text-sm text-muted-foreground">Last Refreshed</p>
          <p className="text-sm font-mono">{lastRefreshed ? formatTime(lastRefreshed) : "—"}</p>
        </div>
      </div>

      <div className="flex gap-2">
        {/* Refresh re-scans page 1; behind a consent dialog because it re-queries the shared Redis. */}
        <ConfirmDialog
          title="Scan the shared Redis?"
          description="Refresh re-queries the shared production Redis (paginated SCAN + per-key metadata). This may add latency for other services on the same instance. Continue?"
          onConfirm={onRefresh}
          isLoading={loading}
        >
          <Button variant="outline" disabled={!scanned || loading}>
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
            {loading ? "Scanning..." : "Refresh"}
          </Button>
        </ConfirmDialog>

        <ConfirmDialog
          title="Clear All Cache?"
          description="This will delete all entries in Redis. This action cannot be undone."
          onConfirm={handleClearAll}
          isLoading={isClearing}
        >
          <Button variant="destructive" disabled={!totalKeys || isClearing}>
            <Trash2 className="w-4 h-4 mr-2" />
            Clear All
          </Button>
        </ConfirmDialog>
      </div>
    </div>
  )
}
