// UI Component: paginated, consent-gated key browser.
"use client"

import { useState, useEffect, useRef } from "react"
import type { KeyMeta } from "@/lib/domain/cache-entry"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Trash2, Copy, Search } from "lucide-react"
import { invalidateCacheEntry } from "@/app/actions/cache-actions"
import { useToast } from "@/hooks/use-toast"
import { ConfirmDialog } from "./confirm-dialog"
import { formatBytes } from "@/lib/utils"

interface CacheTableProps {
  entries: KeyMeta[]
  nextCursor: number
  scanned: boolean
  loading: boolean
  onScan: () => void
  onLoadMore: () => void
  onSearch: (term: string) => void
  onDeleted: () => void
}

export function CacheTable({
  entries,
  nextCursor,
  scanned,
  loading,
  onScan,
  onLoadMore,
  onSearch,
  onDeleted,
}: CacheTableProps) {
  const [searchTerm, setSearchTerm] = useState("")
  const [deletingKey, setDeletingKey] = useState<string | null>(null)
  const { toast } = useToast()
  const firstRender = useRef(true)

  // Debounce search → server-side MATCH. Skip the mount pass so opening the page never scans.
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    const id = setTimeout(() => onSearch(searchTerm), 300)
    return () => clearTimeout(id)
  }, [searchTerm, onSearch])

  const handleDelete = async (key: string) => {
    setDeletingKey(key)
    try {
      const result = await invalidateCacheEntry(key)
      if (result.success) {
        toast({ title: "Success", description: `Cache entry "${key}" deleted` })
        onDeleted()
      } else {
        toast({ title: "Error", description: result.message, variant: "destructive" })
      }
    } finally {
      setDeletingKey(null)
    }
  }

  const handleCopy = (key: string) => {
    navigator.clipboard.writeText(key)
    toast({ title: "Copied", description: "Key copied to clipboard" })
  }

  const formatTTL = (ttl?: number) => {
    if (!ttl) return "No expiry"
    if (ttl < 60) return `${ttl}s`
    if (ttl < 3600) return `${Math.floor(ttl / 60)}m`
    if (ttl < 86400) return `${Math.floor(ttl / 3600)}h`
    return `${Math.floor(ttl / 86400)}d`
  }

  // Pre-scan gate — page open makes zero Redis contact until the user consents.
  if (!scanned) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center gap-4">
        <div className="text-muted-foreground">
          <p className="text-lg font-medium">Cache not scanned</p>
          <p className="text-sm max-w-md">
            Scanning queries the shared production Redis (paginated SCAN plus per-key TTL/type/size — no
            key values are read), which may still add latency for other services on the same instance.
          </p>
        </div>
        <ConfirmDialog
          title="Scan the shared Redis?"
          description="This queries the shared production Redis (paginated SCAN + per-key TTL/type/size). It may add latency for other services using the same instance. Continue?"
          onConfirm={onScan}
          isLoading={loading}
        >
          <Button>
            <Search className="w-4 h-4 mr-2" />
            Scan keys
          </Button>
        </ConfirmDialog>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Input
          placeholder="Filter keys (server-side glob, matches *term*)..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="flex-1"
        />
        <span className="text-sm text-muted-foreground whitespace-nowrap">{entries.length} loaded</span>
      </div>

      {entries.length === 0 ? (
        <div className="py-8 text-center text-muted-foreground">No keys match this filter</div>
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Key</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Size</TableHead>
                <TableHead>Expires</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((entry) => (
                <TableRow key={entry.key}>
                  <TableCell className="font-mono text-sm max-w-xs truncate">{entry.key}</TableCell>
                  <TableCell className="text-sm">{entry.type}</TableCell>
                  <TableCell>{formatBytes(entry.size)}</TableCell>
                  <TableCell>{formatTTL(entry.ttl)}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button variant="ghost" size="sm" onClick={() => handleCopy(entry.key)} title="Copy key">
                        <Copy className="w-4 h-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(entry.key)}
                        disabled={deletingKey === entry.key}
                        className="text-destructive hover:text-destructive"
                        title="Delete entry"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {nextCursor !== 0 && (
        <div className="flex justify-center">
          <Button variant="outline" onClick={onLoadMore} disabled={loading}>
            {loading ? "Loading..." : "Load more"}
          </Button>
        </div>
      )}
    </div>
  )
}
