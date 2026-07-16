import { CacheBrowser } from "@/components/cache-browser"
import { cookies } from "next/headers"
import { readSession, SESSION_COOKIE } from "@hellopro/auth"

export default async function Home() {
  const cookieStore = await cookies()
  const session = await readSession(cookieStore.get(SESSION_COOKIE)?.value)

  return (
    <main className="min-h-screen bg-background">
      <div className="max-w-7xl mx-auto px-4 py-8">
        <CacheBrowser userEmail={session?.email} />
      </div>
    </main>
  )
}
