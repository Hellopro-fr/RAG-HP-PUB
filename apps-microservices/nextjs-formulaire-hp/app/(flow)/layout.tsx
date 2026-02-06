import type { ReactNode } from 'react';
import { CountriesPrefetcher } from '@/components/flow';

interface FlowLayoutProps {
  children: ReactNode;
}

export default function FlowLayout({ children }: FlowLayoutProps) {
  return (
    <div className="min-h-screen bg-background">
      {/* Préchargement des pays pour les formulaires de contact */}
      <CountriesPrefetcher />
      {/* Les composants flow ont leur propre header/navigation */}
      <main>
        {children}
      </main>
    </div>
  );
}
