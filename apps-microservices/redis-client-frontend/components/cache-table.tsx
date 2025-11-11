// UI Component: Data table displaying cache entries
"use client"

import { useState, useMemo } from "react"
import type { CacheEntry } from "@/lib/domain/cache-entry"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Trash2, Copy, ChevronDown, ChevronUp } from "lucide-react"
import { invalidateCacheEntry } from "@/app/actions/cache-actions"
import { useToast } from "@/hooks/use-toast"

type SortField = "key" | "size" | "ttl"
type SortOrder = "asc" | "desc"

interface CacheTableProps {
  entries: CacheEntry[]
  onDelete?: () => void
}

export function CacheTable({ entries, onDelete }: CacheTableProps) {
  const [searchTerm, setSearchTerm] = useState("")
  const [sortField, setSortField] = useState<SortField>("key")
  const [sortOrder, setSortOrder] = useState<SortOrder>("asc")
  const [deletingKey, setDeletingKey] = useState<string | null>(null)
  const { toast } = useToast()

  const filteredAndSortedEntries = useMemo(() => {
    const filtered = entries.filter((entry) => entry.key.toLowerCase().includes(searchTerm.toLowerCase()))

    filtered.sort((a, b) => {
      const aVal: any = a[sortField]
      const bVal: any = b[sortField]

      if (sortField === "key") {
        return sortOrder === "asc" ? a.key.localeCompare(b.key) : b.key.localeCompare(a.key)
      }

      if (aVal === undefined || aVal === null) return 1
      if (bVal === undefined || bVal === null) return -1

      if (typeof aVal === "number") {
        return sortOrder === "asc" ? aVal - bVal : bVal - aVal
      }

      return 0
    })

    return filtered
  }, [entries, searchTerm, sortField, sortOrder])

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc")
    } else {
      setSortField(field)
      setSortOrder("asc")
    }
  }

  const handleDelete = async (key: string) => {
    setDeletingKey(key)
    try {
      const result = await invalidateCacheEntry(key)
      if (result.success) {
        toast({
          title: "Success",
          description: `Cache entry "${key}" deleted`,
        })
        onDelete?.()
      } else {
        toast({
          title: "Error",
          description: result.message,
          variant: "destructive",
        })
      }
    } finally {
      setDeletingKey(null)
    }
  }

  const handleCopy = (key: string) => {
    navigator.clipboard.writeText(key)
    toast({
      title: "Copied",
      description: `Key copied to clipboard`,
    })
  }

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return "0 B"
    const k = 1024
    const sizes = ["B", "KB", "MB", "GB"]
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i]
  }

  const formatTTL = (ttl?: number) => {
    if (!ttl) return "No expiry"
    if (ttl < 60) return `${ttl}s`
    if (ttl < 3600) return `${Math.floor(ttl / 60)}m`
    if (ttl < 86400) return `${Math.floor(ttl / 3600)}h`
    return `${Math.floor(ttl / 86400)}d`
  }

  if (filteredAndSortedEntries.length === 0 && searchTerm === "") {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <div className="text-muted-foreground">
          <p className="text-lg font-medium">No cached data</p>
          <p className="text-sm">Redis cache is empty</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Input
          placeholder="Search cache keys..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="flex-1"
        />
        <span className="text-sm text-muted-foreground whitespace-nowrap">
          {filteredAndSortedEntries.length} entries
        </span>
      </div>

      {filteredAndSortedEntries.length === 0 ? (
        <div className="py-8 text-center text-muted-foreground">No results matching "{searchTerm}"</div>
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>
                  <button onClick={() => handleSort("key")} className="flex items-center gap-1 hover:text-foreground">
                    Key
                    {sortField === "key" &&
                      (sortOrder === "asc" ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />)}
                  </button>
                </TableHead>
                <TableHead>
                  <button onClick={() => handleSort("size")} className="flex items-center gap-1 hover:text-foreground">
                    Size
                    {sortField === "size" &&
                      (sortOrder === "asc" ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />)}
                  </button>
                </TableHead>
                <TableHead>
                  <button onClick={() => handleSort("ttl")} className="flex items-center gap-1 hover:text-foreground">
                    Expires
                    {sortField === "ttl" &&
                      (sortOrder === "asc" ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />)}
                  </button>
                </TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredAndSortedEntries.map((entry) => (
                <TableRow key={entry.key}>
                  <TableCell className="font-mono text-sm max-w-xs truncate">{entry.key}</TableCell>
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
    </div>
  )
}
