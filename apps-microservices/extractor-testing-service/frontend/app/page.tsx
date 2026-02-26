"use client"

import { useState } from "react"
import InputSection from "@/components/input-section"
import OutputSection from "@/components/output-section"

export default function Page() {
  const [results, setResults] = useState<Record<string, any> | null>(null)
  const [boilerplateResults, setBoilerplateResults] = useState<any | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  // Track which view should be active based on what was last submitted
  const [activeView, setActiveView] = useState<"single" | "boilerplate">("single")

  const handleCompare = async (inputType: "raw_html" | "json_data", content: string, strategy: string, extractMetadata: boolean) => {
    setLoading(true)
    setError(null)
    setResults(null)
    setBoilerplateResults(null) // Reset boilerplate to ensure clean render
    setActiveView("single")

    try {
      const body = {
        ...(inputType === "raw_html" ? { raw_html: content } : { json_data: JSON.parse(content) }),
        strategy,
        extract_metadata: extractMetadata,
      }

      const response = await fetch("/api/test-extractors", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })

      if (!response.ok) {
        throw new Error(`API error: ${response.statusText}`)
      }

      const data = await response.json()
      setResults(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }

  const handleTestBoilerplate = async (mainHtml: string, ref1: string, ref2: string, gapWeights: any) => {
    setLoading(true)
    setError(null)
    setResults(null) // Reset general extractors to ensure clean render
    setBoilerplateResults(null)
    setActiveView("boilerplate")

    try {
      const body = {
        main_html: mainHtml,
        reference_htmls: [ref1, ref2],
        gap_weights: gapWeights
      }

      const response = await fetch("/api/test-boilerplate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })

      if (!response.ok) {
        throw new Error(`API error: ${response.statusText}`)
      }

      const data = await response.json()
      setBoilerplateResults(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="min-h-screen bg-background">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 p-6 max-w-7xl mx-auto">
        {/* Left Column: Input */}
        <div className="flex flex-col">
          <h1 className="text-3xl font-bold mb-6">Content Extraction Tester</h1>
          <InputSection 
            onCompare={handleCompare} 
            onTestBoilerplate={handleTestBoilerplate}
            disabled={loading} 
          />
        </div>

        {/* Right Column: Output */}
        <div className="flex flex-col">
          <h2 className="text-2xl font-bold mb-6">Results</h2>
          <OutputSection 
            activeView={activeView}
            results={results} 
            boilerplateResults={boilerplateResults}
            loading={loading} 
            error={error} 
          />
        </div>
      </div>
    </main>
  )
}