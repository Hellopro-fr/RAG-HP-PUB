import type { Metadata } from 'next';
import Link from 'next/link';
import type { ReactNode } from 'react';

import { Badge } from '@/components/ui';
import { currentUser } from '@/lib/api/server';
import { fr } from '@/lib/i18n/fr';

import './globals.css';
import { Providers } from './providers';

export const metadata: Metadata = {
  title: fr.app,
  description: 'Tableau de tâches en temps réel pour agents et humains',
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  const me = await currentUser();
  const can = (p: string) => !!me?.permissions.includes(p);
  return (
    <html lang="fr">
      <body>
        <header className="border-b border-slate-200 bg-white">
          <nav className="mx-auto flex max-w-[1600px] items-center gap-6 px-4 py-3 text-sm">
            <Link href="/projects" className="font-semibold">
              {fr.app}
            </Link>
            {me && (
              <>
                <Link href="/projects">{fr.nav.projects}</Link>
                <Link href="/questions">{fr.nav.questions}</Link>
                {can('agents.view') && <Link href="/agents">{fr.nav.agents}</Link>}
                {can('access.manage') && <Link href="/access">{fr.nav.access}</Link>}
                <span className="ml-auto flex items-center gap-2 text-slate-600" data-testid="current-user">
                  {me.name}
                  {me.level && <Badge tone={me.level === 'admin' ? 'info' : 'neutral'}>{fr.level[me.level]}</Badge>}
                </span>
                <form action="/api/auth/logout" method="post">
                  <button type="submit" className="text-slate-500 hover:text-slate-900">
                    {fr.nav.logout}
                  </button>
                </form>
              </>
            )}
          </nav>
        </header>
        <main className="mx-auto max-w-[1600px] px-4 py-6">
          <Providers>{children}</Providers>
        </main>
      </body>
    </html>
  );
}
