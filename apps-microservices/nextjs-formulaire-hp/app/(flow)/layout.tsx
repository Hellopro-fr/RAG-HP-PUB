import type { ReactNode } from 'react';

interface FlowLayoutProps {
  children: ReactNode;
}

export default function FlowLayout({ children }: FlowLayoutProps) {
  return (
    <div className="min-h-screen bg-background">
      {/* Les composants flow ont leur propre header/navigation */}
      <main>
        {children}
      </main>
    </div>
  );
}
