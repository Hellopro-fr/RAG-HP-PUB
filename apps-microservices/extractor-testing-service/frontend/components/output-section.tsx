"use client"

import { useState } from "react"
import { Card } from "@/components/ui/card"
import { AlertCircle, ChevronDown, ChevronUp, Copy, Check, Eye, FileCode } from "lucide-react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ScrollArea } from "@/components/ui/scroll-area"

interface LibraryResult {
  content: string
  char_count: number
  error: string | null
  metadata?: Record<string, any>
}

interface IntersectionDetail {
  signature: string
  text_main: string
  text_ref1: string
  text_ref2: string
}

interface BoilerplateResult {
  header_old: string
  footer_old: string
  
  header_class: string
  footer_class: string
  
  header_structural: string
  footer_structural: string
  
  intersections_class: IntersectionDetail[]
  intersections_structural: IntersectionDetail[]
  
  cleaned_html_main: string
  cleaned_html_ref1: string
  cleaned_html_ref2: string
  
  header_selected: string
  header_method_used: string
  footer_selected: string
  footer_method_used: string
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
      <div className="space-y-6 flex-1 w-full">
        <Tabs defaultValue="production" className="w-full">
          <TabsList className="grid w-full grid-cols-5 h-auto">
            <TabsTrigger value="production">Production</TabsTrigger>
            <TabsTrigger value="class">Strat: Class</TabsTrigger>
            <TabsTrigger value="structural">Strat: Struct</TabsTrigger>
            <TabsTrigger value="cleaned">Cleaned HTML</TabsTrigger>
            <TabsTrigger value="original">Original</TabsTrigger>
          </TabsList>
          
          <TabsContent value="production" className="space-y-4 pt-4">
            <h3 className="text-lg font-semibold">Final Automated Decision</h3>
            <BoilerplateCard 
              title="Selected Header" 
              content={boilerplateResults.header_selected} 
              method={boilerplateResults.header_method_used} 
            />
            <BoilerplateCard 
              title="Selected Footer" 
              content={boilerplateResults.footer_selected} 
              method={boilerplateResults.footer_method_used} 
            />
          </TabsContent>
          
          <TabsContent value="class" className="space-y-4 pt-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <BoilerplateCard 
                title="Class Strategy Header" 
                content={boilerplateResults.header_class} 
                method="Fallback (Class)" 
                />
                <BoilerplateCard 
                title="Class Strategy Footer" 
                content={boilerplateResults.footer_class} 
                method="Fallback (Class)" 
                />
            </div>
            <IntersectionTable 
                title="Detailed Intersection Analysis (Class Strategy)" 
                items={boilerplateResults.intersections_class} 
            />
          </TabsContent>

          <TabsContent value="structural" className="space-y-4 pt-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <BoilerplateCard 
                title="Structural Strategy Header" 
                content={boilerplateResults.header_structural} 
                method="Fallback (Structural)" 
                />
                <BoilerplateCard 
                title="Structural Strategy Footer" 
                content={boilerplateResults.footer_structural} 
                method="Fallback (Structural)" 
                />
            </div>
            <IntersectionTable 
                title="Detailed Intersection Analysis (Structural Strategy)" 
                items={boilerplateResults.intersections_structural} 
            />
          </TabsContent>

          <TabsContent value="cleaned" className="space-y-6 pt-4">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <FileCode className="h-5 w-5" /> Boilerpy3 Output (Marked HTML)
            </h3>
            <BoilerplateCard 
              title="Cleaned Main HTML" 
              content={boilerplateResults.cleaned_html_main} 
              method="boilerpy3.KeepEverythingExtractor" 
            />
            <BoilerplateCard 
              title="Cleaned Reference HTML 1" 
              content={boilerplateResults.cleaned_html_ref1} 
              method="boilerpy3.KeepEverythingExtractor" 
            />
            <BoilerplateCard 
              title="Cleaned Reference HTML 2" 
              content={boilerplateResults.cleaned_html_ref2} 
              method="boilerpy3.KeepEverythingExtractor" 
            />
          </TabsContent>

          <TabsContent value="original" className="space-y-4 pt-4">
            <BoilerplateCard 
              title="Original Header" 
              content={boilerplateResults.header_old} 
              method="Original Semantic/CSS" 
            />
            <BoilerplateCard 
              title="Original Footer" 
              content={boilerplateResults.footer_old} 
              method="Original Semantic/CSS" 
            />
          </TabsContent>
        </Tabs>
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

function IntersectionTable({ title, items }: { title: string, items: IntersectionDetail[] }) {
    if (!items || items.length === 0) {
        return (
            <Card className="p-4 border-dashed border-2">
                <h4 className="font-semibold text-sm text-muted-foreground">{title} - No intersections found.</h4>
            </Card>
        );
    }

    return (
        <Card className="p-4 border-dashed border-2">
            <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                <Eye className="h-4 w-4" />
                {title} ({items.length} matching blocks)
            </h4>
            <ScrollArea className="h-96 rounded-md border bg-muted/10">
                <div className="min-w-[800px]">
                    {/* Header */}
                    <div className="grid grid-cols-10 gap-2 p-3 bg-muted font-semibold text-xs border-b sticky top-0 z-10">
                        <div className="col-span-2">Signature</div>
                        <div className="col-span-3">Main Page Content</div>
                        <div className="col-span-5 grid grid-cols-2 gap-2">
                            <div>Ref 1 Content</div>
                            <div>Ref 2 Content</div>
                        </div>
                    </div>
                    {/* Rows */}
                    <div className="divide-y">
                        {items.map((item, idx) => (
                            <div key={idx} className="grid grid-cols-10 gap-2 p-3 text-xs hover:bg-muted/20">
                                <div className="col-span-2 font-mono text-[10px] break-all text-primary/80">
                                    {item.signature}
                                </div>
                                <div className="col-span-3 max-h-24 overflow-y-auto pr-1 text-muted-foreground">
                                    {item.text_main}
                                </div>
                                <div className="col-span-5 grid grid-cols-2 gap-2 text-muted-foreground/70">
                                    <div className="max-h-24 overflow-y-auto pr-1 border-r">{item.text_ref1}</div>
                                    <div className="max-h-24 overflow-y-auto pr-1">{item.text_ref2}</div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </ScrollArea>
        </Card>
    )
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
    <Card className={`p-4 transition-colors ${isFallback ? "border-primary/30 bg-primary/5" : ""}`}>
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="font-semibold text-lg">{title}</h3>
          <p className="text-xs mt-1">
            Method: <span className={`font-semibold px-1.5 py-0.5 rounded ${isFallback ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}>{method}</span>
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
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(result.content)
      } else {
        const textArea = document.createElement('textarea')
        textArea.value = result.content
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