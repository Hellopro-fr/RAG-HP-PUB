import Link from 'next/link';

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8 text-center">
      <h1 className="text-7xl font-bold">404</h1>
      <h2 className="mt-4 text-xl font-semibold">Page introuvable</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Cette page conseil n&apos;existe pas ou a été déplacée.
      </p>
      <Link
        href="/"
        className="mt-6 inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
      >
        Retour à l&apos;accueil
      </Link>
    </main>
  );
}
