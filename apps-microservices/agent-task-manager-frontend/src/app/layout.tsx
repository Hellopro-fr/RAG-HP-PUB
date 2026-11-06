import type { Metadata } from 'next';
import Link from 'next/link';
import type { ReactNode } from 'react';

import { fr } from '@/lib/i18n/fr';

import './globals.css';
import { Providers } from './providers';

export const metadata: Metadata = {
  title: fr.app,
  description: 'Tableau de tâches en temps réel pour agents et humains',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="fr">
      <body>
        <header className="border-b border-slate-200 bg-white">
          <nav className="mx-auto flex max-w-[1600px] items-center gap-6 px-4 py-3 text-sm">
            <Link href="/projects" className="font-semibold">
              {fr.app}
            </Link>
            <Link href="/projects">{fr.nav.projects}</Link>
            <Link href="/questions">{fr.nav.questions}</Link>
            <Link href="/agents">{fr.nav.agents}</Link>
            <form action="/api/auth/logout" method="post" className="ml-auto">
              <button type="submit" className="text-slate-500 hover:text-slate-900">
                {fr.nav.logout}
              </button>
            </form>
          </nav>
        </header>
        <main className="mx-auto max-w-[1600px] px-4 py-6">
          <Providers>{children}</Providers>
        </main>
      </body>
    </html>
  );
}
