export const dynamic = "force-dynamic"

export default async function DeniedPage({
  searchParams,
}: {
  searchParams: Promise<{ email?: string }>
}) {
  const { email } = await searchParams
  return (
    <main className="min-h-screen bg-background flex items-center justify-center">
      <div className="w-full max-w-md space-y-4 p-8 text-center">
        <h1 className="text-2xl font-bold">Access denied</h1>
        <p className="text-muted-foreground">
          {email ? `The account ${email} is not authorized` : "Your account is not authorized"} to use the
          Redis Cache Manager.
        </p>
        <p className="text-sm text-muted-foreground">Contact an administrator to request access.</p>
        <a href="/auth/logout" className="text-sm underline">
          Sign out
        </a>
      </div>
    </main>
  )
}
