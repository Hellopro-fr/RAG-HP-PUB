// Login page — simple token-based authentication for the Redis admin UI
"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export default function LoginPage() {
  const [token, setToken] = useState("")
  const [error, setError] = useState("")
  const router = useRouter()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!token.trim()) {
      setError("Token is required")
      return
    }
    // Set the token as a cookie and redirect to the dashboard
    document.cookie = `admin_token=${encodeURIComponent(token)}; path=/; SameSite=Strict`
    router.push("/")
  }

  return (
    <main className="min-h-screen bg-background flex items-center justify-center">
      <div className="w-full max-w-sm space-y-6 p-8">
        <div className="text-center">
          <h1 className="text-2xl font-bold">Redis Cache Manager</h1>
          <p className="text-muted-foreground text-sm mt-1">Enter your admin token to continue</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            type="password"
            placeholder="Admin token"
            value={token}
            onChange={(e) => { setToken(e.target.value); setError("") }}
          />
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" className="w-full">Sign in</Button>
        </form>
      </div>
    </main>
  )
}
