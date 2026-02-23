"use client"

import { useState } from "react"
import { Card } from "@/components/ui/card"
import { AlertCircle, ChevronDown, ChevronUp, Copy, Check } from "lucide-react"

interface LibraryResult {
  content: string
  char_count: number
  error: string | null
  metadata?: Record<string, any>
}

interface BoilerplateResult {
  header_content: string
  header_method: string
  footer_content: string
  footer_method: string
}

interface OutputSectionProps {
  activeView: "single" | "boilerplate"
  results: Record<string, LibraryResult> | null
  boilerplateResults?: BoilerplateResult | null
  loading: boolean
  error: string | null
}

export default function OutputSection({ activeView, results, boilerplateResults, loading, error }: OutputSectionProps) {
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

  // Render Boilerplate Results View
  if (activeView === "boilerplate") {
    if (!boilerplateResults) {
      return (
        <Card className="p-12 flex items-center justify-center flex-1 bg-muted/50">
          <p className="text-muted-foreground text-center">Boilerplate results will be displayed here</p>
        </Card>
      )
    }

    return (
      <div className="space-y-4 flex-1">
        <BoilerplateCard 
          title="Extracted Header" 
          content={boilerplateResults.header_content} 
          method={boilerplateResults.header_method} 
        />
        <BoilerplateCard 
          title="Extracted Footer" 
          content={boilerplateResults.footer_content} 
          method={boilerplateResults.footer_method} 
        />
      </div>
    )
  }

  // Render Single Extractor Results View
  if (activeView === "single") {
    if (!results) {
      return (
        <Card className="p-12 flex items-center justify-center flex-1 bg-muted/50">
          <p className="text-muted-foreground text-center">Extraction results will be displayed here</p>
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

  return null
}

interface BoilerplateCardProps {
  title: string
  content: string
  method: string
}

function BoilerplateCard({ title, content, method }: BoilerplateCardProps) {
  const [copied, setCopied] = useState(false)
  const isFallback = method.includes("Fallback")

  const handleCopy = async () => {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(content)
      } else {
        const textArea = document.createElement('textarea')
        textArea.value = content
        textArea.style.position = 'fixed'
        textArea.style.left = '-999999px'
        textArea.style.top = '-999999px'
        document.body.appendChild(textArea)
        textArea.focus()
        textArea.select()
        document.execCommand('copy')
        document.body.removeChild(textArea)
      }
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
      alert('Failed to copy to clipboard.')
    }
  }

  return (
    <Card className={`p-4 transition-colors ${isFallback ? "border-primary/50 bg-primary/5" : ""}`}>
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="font-semibold text-lg">{title}</h3>
          <p className="text-xs mt-1">
            Method Used: <span className={`font-semibold px-1.5 py-0.5 rounded ${isFallback ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}>{method}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleCopy}
            className="flex items-center gap-1 px-2 py-1 text-xs rounded border border-border hover:bg-muted transition-colors"
            title="Copy content"
          >
            {copied ? (
              <>
                <Check className="h-3 w-3" />
                <span>Copied!</span>
              </>
            ) : (
              <>
                <Copy className="h-3 w-3" />
                <span>Copy</span>
              </>
            )}
          </button>
        </div>
      </div>

      <p className="text-xs text-muted-foreground mb-3">
        Character count: <span className="font-semibold">{content.length}</span>
      </p>

      <pre className="p-3 bg-muted rounded border border-border text-xs overflow-auto max-h-96">
        <code>{content || "(No content detected)"}</code>
      </pre>
    </Card>
  )
}

interface LibraryCardProps {
  libraryName: string
  result: LibraryResult
}

function LibraryCard({ libraryName, result }: LibraryCardProps) {
  const hasError = result.error !== null
  const hasMetadata = result.metadata && Object.keys(result.metadata).length > 0
  const [showMetadata, setShowMetadata] = useState(true)
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      // Try modern Clipboard API first
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(result.content)
      } else {
        // Fallback for browsers without Clipboard API or non-HTTPS contexts
        const textArea = document.createElement('textarea')
        textArea.value = result.content
        textArea.style.position = 'fixed'
        textArea.style.left = '-999999px'
        textArea.style.top = '-999999px'
        document.body.appendChild(textArea)
        textArea.focus()
        textArea.select()

        const successful = document.execCommand('copy')
        document.body.removeChild(textArea)

        if (!successful) {
          throw new Error('Fallback copy failed')
        }
      }

      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
      // Show user-friendly error message
      alert('Failed to copy to clipboard. Please copy manually.')
    }
  }

  return (
    <Card className={`p-4 transition-colors ${hasError ? "bg-destructive/5 border-destructive/20" : ""}`}>
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <h3 className="font-semibold text-lg">{libraryName}</h3>
        <div className="flex items-center gap-2">
          {/* Copy button */}
          <button
            onClick={handleCopy}
            disabled={hasError}
            className="flex items-center gap-1 px-2 py-1 text-xs rounded border border-border hover:bg-muted transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title="Copy content"
          >
            {copied ? (
              <>
                <Check className="h-3 w-3" />
                <span>Copied!</span>
              </>
            ) : (
              <>
                <Copy className="h-3 w-3" />
                <span>Copy</span>
              </>
            )}
          </button>
          {/* Error badge */}
          {hasError && (
            <span className="text-xs font-semibold text-destructive bg-destructive/10 px-2 py-1 rounded">ERROR</span>
          )}
        </div>
      </div>

      {/* Metadata Section */}
      {!hasError && hasMetadata && (
        <div className="mb-3 border border-border rounded-md">
          <button
            onClick={() => setShowMetadata(!showMetadata)}
            className="w-full flex items-center justify-between p-2 hover:bg-muted/50 transition-colors"
          >
            <span className="text-sm font-semibold">Metadata</span>
            {showMetadata ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
          {showMetadata && (
            <div className="p-3 bg-muted/30 border-t border-border">
              <dl className="grid grid-cols-1 gap-2 text-xs">
                {Object.entries(result.metadata!).map(([key, value]) => (
                  <div key={key} className="flex gap-2">
                    <dt className="font-semibold min-w-[100px] capitalize">{key}:</dt>
                    <dd className="text-muted-foreground">
                      {Array.isArray(value) ? value.join(", ") : String(value)}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
        </div>
      )}

      {/* Content Metadata */}
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