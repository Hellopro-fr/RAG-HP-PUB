"use client"

import * as React from "react"
import { useState, useEffect } from "react"

interface ClientDateProps {
  timestamp: string
  className?: string
}

export function ClientDate({ timestamp, className }: ClientDateProps) {
  const [formattedDate, setFormattedDate] = useState<string>("")

  useEffect(() => {
    if (!timestamp) {
        setFormattedDate("N/A")
        return
    }
    try {
      setFormattedDate(new Date(timestamp).toLocaleString())
    } catch (e) {
      setFormattedDate(timestamp)
    }
  }, [timestamp])

  if (!formattedDate) {
    // Render a placeholder or the raw timestamp to avoid layout shift, 
    // but keep it consistent with server render if possible, or empty.
    // Using a non-breaking space to keep height.
    return <span className={className}>&nbsp;</span>
  }

  return <span className={className}>{formattedDate}</span>
}
