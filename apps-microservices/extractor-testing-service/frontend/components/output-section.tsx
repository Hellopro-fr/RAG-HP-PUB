"use client"

import { Card } from "@/components/ui/card"
import { AlertCircle } from "lucide-react"

interface LibraryResult {
  content: string
  char_count: number
  error: string | null
}

interface OutputSectionProps {
  results: Record<string, LibraryResult> | null
  loading: boolean
  error: string | null
}

export default function OutputSection({ results, loading, error }: OutputSectionProps) {
  if (loading) {
    return (
      <Card className="p-12 flex items-center justify-center flex-1">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
          <p className="text-muted-foreground">Processing extractions...</p>
        </div>
      </Card>
    )
  }

  if (error) {
    return (
      <Card className="p-6 bg-destructive/10 border-destructive/20 flex-1 flex items-center gap-3">
        <AlertCircle className="h-5 w-5 text-destructive" />
        <div>
          <p className="font-semibold text-destructive">Error</p>
          <p className="text-sm text-destructive/80">{error}</p>
        </div>
      </Card>
    )
  }

  if (!results) {
    return (
      <Card className="p-12 flex items-center justify-center flex-1 bg-muted/50">
        <p className="text-muted-foreground text-center">Results will be displayed here</p>
      </Card>
    )
  }

  const libraries = Object.entries(results)

  return (
    <div className="space-y-4 flex-1">
      {libraries.length === 0 ? (
        <Card className="p-12 flex items-center justify-center bg-muted/50">
          <p className="text-muted-foreground text-center">No results returned from the API</p>
        </Card>
      ) : (
        libraries.map(([libraryName, result]) => (
          <LibraryCard key={libraryName} libraryName={libraryName} result={result} />
        ))
      )}
    </div>
  )
}

interface LibraryCardProps {
  libraryName: string
  result: LibraryResult
}

function LibraryCard({ libraryName, result }: LibraryCardProps) {
  const hasError = result.error !== null

  return (
    <Card className={`p-4 transition-colors ${hasError ? "bg-destructive/5 border-destructive/20" : ""}`}>
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <h3 className="font-semibold text-lg">{libraryName}</h3>
        {hasError && (
          <span className="text-xs font-semibold text-destructive bg-destructive/10 px-2 py-1 rounded">ERROR</span>
        )}
      </div>

      {/* Metadata */}
      {!hasError && (
        <p className="text-xs text-muted-foreground mb-3">
          Character count: <span className="font-semibold">{result.char_count}</span>
        </p>
      )}

      {/* Content or Error */}
      {hasError ? (
        <div className="p-3 bg-destructive/10 rounded border border-destructive/20">
          <p className="text-sm text-destructive">{result.error}</p>
        </div>
      ) : (
        <pre className="p-3 bg-muted rounded border border-border text-xs overflow-auto max-h-64">
          <code>{result.content || "(empty)"}</code>
        </pre>
      )}
    </Card>
  )
}
