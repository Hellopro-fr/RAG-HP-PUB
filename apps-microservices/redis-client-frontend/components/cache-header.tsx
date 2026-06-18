// UI Component: Dashboard header with stats and actions
"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { RefreshCw, Trash2 } from "lucide-react"
import { refreshCacheData, clearAllCache } from "@/app/actions/cache-actions"
import { useToast } from "@/hooks/use-toast"
import { ConfirmDialog } from "./confirm-dialog"
import { formatBytes } from "@/lib/utils"

interface CacheHeaderProps {
  totalKeys: number
  totalSize: number
  lastRefreshed: Date
  onRefresh?: () => void
  userEmail?: string
}

export function CacheHeader({ totalKeys, totalSize, lastRefreshed, onRefresh, userEmail }: CacheHeaderProps) {
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isClearing, setIsClearing] = useState(false)
  const { toast } = useToast()

  const handleRefresh = async () => {
    setIsRefreshing(true)
    try {
      await refreshCacheData()
      onRefresh?.()
      toast({
        title: "Refreshed",
        description: "Cache data refreshed successfully",
      })
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to refresh cache",
        variant: "destructive",
      })
    } finally {
      setIsRefreshing(false)
    }
  }

  const handleClearAll = async () => {
    setIsClearing(true)
    try {
      const result = await clearAllCache()
      if (result.success) {
        toast({
          title: "Success",
          description: "Cache cleared successfully",
        })
        onRefresh?.()
      } else {
        toast({
          title: "Error",
          description: result.message,
          variant: "destructive",
        })
      }
    } finally {
      setIsClearing(false)
    }
  }

  const formatTime = (date: Date) => {
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(date)
  }

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

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-card border rounded-lg p-4">
          <p className="text-sm text-muted-foreground">Total Keys</p>
          <p className="text-2xl font-bold">{totalKeys}</p>
        </div>
        <div className="bg-card border rounded-lg p-4">
          <p className="text-sm text-muted-foreground">Total Size</p>
          <p className="text-2xl font-bold">{formatBytes(totalSize)}</p>
        </div>
        <div className="bg-card border rounded-lg p-4">
          <p className="text-sm text-muted-foreground">Last Refreshed</p>
          <p className="text-sm font-mono">{formatTime(lastRefreshed)}</p>
        </div>
      </div>

      <div className="flex gap-2">
        <Button onClick={handleRefresh} disabled={isRefreshing} variant="outline">
          <RefreshCw className={`w-4 h-4 mr-2 ${isRefreshing ? "animate-spin" : ""}`} />
          {isRefreshing ? "Refreshing..." : "Refresh"}
        </Button>

        {/* S7: ConfirmDialog now wraps the trigger button via AlertDialog.Trigger */}
        <ConfirmDialog
          title="Clear All Cache?"
          description="This will delete all entries in Redis. This action cannot be undone."
          onConfirm={handleClearAll}
          isLoading={isClearing}
        >
          <Button
            variant="destructive"
            disabled={totalKeys === 0 || isClearing}
          >
            <Trash2 className="w-4 h-4 mr-2" />
            Clear All
          </Button>
        </ConfirmDialog>
      </div>
    </div>
  )
}
