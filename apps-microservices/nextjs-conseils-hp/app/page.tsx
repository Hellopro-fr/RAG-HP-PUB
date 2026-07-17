export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <h1 className="text-4xl font-bold tracking-tight">Conseils HelloPro</h1>
      <p className="mt-4 text-muted-foreground">
        Le service tourne. Les pages conseils sont accessibles à la racine du
        sous-domaine sous la forme{' '}
        <code className="rounded bg-muted px-1 py-0.5">/&lt;slug&gt;-&lt;id&gt;.html</code>.
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        Ex :{' '}
        <code className="rounded bg-muted px-1 py-0.5">
          /comment-choisir-un-malaxeur-a-beton-1001.html
        </code>
      </p>
      <p className="mt-2 text-xs text-muted-foreground">
        Stack : Next.js 15 · React 19 · Tailwind 4 · Node 22
      </p>
    </main>
  );
}
