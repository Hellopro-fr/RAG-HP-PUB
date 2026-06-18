import { getCachedData } from "@/lib/application/get-cached-data"
import { CacheHeader } from "@/components/cache-header"
import { CacheTable } from "@/components/cache-table"
import { cookies } from "next/headers"
import { readSession, SESSION_COOKIE } from "@/lib/auth/session"

export default async function Home() {
  const { entries, metadata, error } = await getCachedData()
  const cookieStore = await cookies()
  const session = await readSession(cookieStore.get(SESSION_COOKIE)?.value)

  return (
    <main className="min-h-screen bg-background">
      <div className="max-w-7xl mx-auto px-4 py-8">
        {error && <div className="mb-6 p-4 bg-destructive/10 text-destructive rounded-lg">{error}</div>}

        <CacheHeader
          totalKeys={metadata.totalKeys}
          totalSize={metadata.totalSize}
          lastRefreshed={metadata.lastRefreshed}
          userEmail={session?.email}
        />

        <div className="mt-8">
          <CacheTable entries={entries} />
        </div>
      </div>
    </main>
  )
}
