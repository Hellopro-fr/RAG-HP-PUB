export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <h1 className="text-4xl font-bold tracking-tight">Conseils HelloPro</h1>
      <p className="mt-4 text-muted-foreground">
        Le service tourne. Les pages conseils seront accessibles sur{' '}
        <code className="rounded bg-muted px-1 py-0.5">/conseils/[slug]</code>.
      </p>
      <p className="mt-2 text-xs text-muted-foreground">
        Stack : Next.js 15 · React 19 · Tailwind 4 · Node 22
      </p>
    </main>
  );
}
