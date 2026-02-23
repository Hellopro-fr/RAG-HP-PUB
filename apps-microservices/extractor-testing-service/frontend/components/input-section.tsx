"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

interface InputSectionProps {
  onCompare: (inputType: "raw_html" | "json_data", content: string, strategy: string, extractMetadata: boolean) => void
  onTestBoilerplate: (mainHtml: string, ref1: string, ref2: string) => void
  disabled: boolean
}

export default function InputSection({ onCompare, onTestBoilerplate, disabled }: InputSectionProps) {
  // Single Extractor State
  const [inputType, setInputType] = useState<"raw_html" | "json_data">("raw_html")
  const [content, setContent] = useState("")
  const [strategy, setStrategy] = useState<string>("balanced")
  const [extractMetadata, setExtractMetadata] = useState<boolean>(false)

  // Boilerplate Intersection State
  const [mainHtml, setMainHtml] = useState("")
  const [ref1Html, setRef1Html] = useState("")
  const [ref2Html, setRef2Html] = useState("")

  const handleSubmitExtractor = () => {
    if (!content.trim()) {
      alert("Please enter content to extract")
      return
    }
    onCompare(inputType, content, strategy, extractMetadata)
  }

  const handleSubmitBoilerplate = () => {
    if (!mainHtml.trim() || !ref1Html.trim() || !ref2Html.trim()) {
      alert("Please provide the Main HTML and both Reference HTMLs to run the intersection.")
      return
    }
    onTestBoilerplate(mainHtml, ref1Html, ref2Html)
  }

  return (
    <Tabs defaultValue="single" className="flex flex-col flex-1">
      <TabsList className="grid w-full grid-cols-2 mb-4">
        <TabsTrigger value="single" disabled={disabled}>Single Page Extractor</TabsTrigger>
        <TabsTrigger value="boilerplate" disabled={disabled}>Boilerplate Fallback</TabsTrigger>
      </TabsList>

      {/* SINGLE PAGE EXTRACTOR TAB */}
      <TabsContent value="single" className="flex-1 flex flex-col mt-0 outline-none">
        <Card className="p-6 flex-1 flex flex-col">
          {/* Format Selection */}
          <div className="mb-6">
            <label className="block text-sm font-semibold mb-3">Input Format</label>
            <div className="flex gap-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="format"
                  value="raw_html"
                  checked={inputType === "raw_html"}
                  onChange={(e) => setInputType(e.target.value as "raw_html" | "json_data")}
                  disabled={disabled}
                />
                <span className="text-sm">Raw HTML</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="format"
                  value="json_data"
                  checked={inputType === "json_data"}
                  onChange={(e) => setInputType(e.target.value as "raw_html" | "json_data")}
                  disabled={disabled}
                />
                <span className="text-sm">Full JSON Data</span>
              </label>
            </div>
          </div>

          {/* Extraction Strategy Selection */}
          <div className="mb-6">
            <Label htmlFor="strategy" className="block text-sm font-semibold mb-2">
              Extraction Strategy
            </Label>
            <select
              id="strategy"
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              disabled={disabled}
              className="w-full p-2 border border-input rounded-md bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="balanced">Balanced (Default)</option>
              <option value="precision">Precision (Less noise, higher quality)</option>
              <option value="recall">Recall (More content, may include noise)</option>
            </select>
            <p className="text-xs text-muted-foreground mt-1">
              Controls how Trafilatura variants extract content
            </p>
          </div>

          {/* Metadata Extraction Checkbox */}
          <div className="mb-6 flex items-center gap-2">
            <Checkbox
              id="metadata"
              checked={extractMetadata}
              onCheckedChange={(checked) => setExtractMetadata(checked === true)}
              disabled={disabled}
            />
            <Label
              htmlFor="metadata"
              className="text-sm font-medium cursor-pointer"
            >
              Extract metadata (author, date, title, etc.)
            </Label>
          </div>

          {/* Textarea */}
          <div className="mb-6 flex-1 flex flex-col">
            <label className="block text-sm font-semibold mb-2">
              {inputType === "raw_html" ? "HTML Content" : "JSON Data"}
            </label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={inputType === "raw_html" ? "Paste your HTML here..." : "Paste your JSON data here..."}
              disabled={disabled}
              className="flex-1 p-3 border border-input rounded-md font-mono text-sm bg-background resize-none focus:outline-none focus:ring-2 focus:ring-ring min-h-[200px]"
            />
          </div>

          {/* Submit Button */}
          <Button onClick={handleSubmitExtractor} disabled={disabled} className="w-full" size="lg">
            {disabled ? "Comparing..." : "Compare Extractions"}
          </Button>
        </Card>
      </TabsContent>

      {/* BOILERPLATE FALLBACK TAB */}
      <TabsContent value="boilerplate" className="flex-1 flex flex-col mt-0 outline-none">
        <Card className="p-6 flex-1 flex flex-col gap-4">
          <div className="flex-1 flex flex-col">
            <label className="block text-sm font-semibold mb-2 text-primary">Main HTML (Target)</label>
            <textarea
              value={mainHtml}
              onChange={(e) => setMainHtml(e.target.value)}
              placeholder="Paste the target product/article HTML here..."
              disabled={disabled}
              className="flex-1 p-3 border border-primary/50 rounded-md font-mono text-sm bg-background resize-none focus:outline-none focus:ring-2 focus:ring-ring min-h-[120px]"
            />
          </div>

          <div className="flex-1 flex flex-col">
            <label className="block text-sm font-semibold mb-2">Reference HTML 1 (e.g., Homepage)</label>
            <textarea
              value={ref1Html}
              onChange={(e) => setRef1Html(e.target.value)}
              placeholder="Paste the first reference HTML here..."
              disabled={disabled}
              className="flex-1 p-3 border border-input rounded-md font-mono text-sm bg-background resize-none focus:outline-none focus:ring-2 focus:ring-ring min-h-[120px]"
            />
          </div>

          <div className="flex-1 flex flex-col">
            <label className="block text-sm font-semibold mb-2">Reference HTML 2 (e.g., Category Page)</label>
            <textarea
              value={ref2Html}
              onChange={(e) => setRef2Html(e.target.value)}
              placeholder="Paste the second reference HTML here..."
              disabled={disabled}
              className="flex-1 p-3 border border-input rounded-md font-mono text-sm bg-background resize-none focus:outline-none focus:ring-2 focus:ring-ring min-h-[120px]"
            />
          </div>

          {/* Submit Button */}
          <Button onClick={handleSubmitBoilerplate} disabled={disabled} className="w-full mt-2" size="lg">
            {disabled ? "Processing Intersection..." : "Test Boilerplate Fallback"}
          </Button>
        </Card>
      </TabsContent>

    </Tabs>
  )
}