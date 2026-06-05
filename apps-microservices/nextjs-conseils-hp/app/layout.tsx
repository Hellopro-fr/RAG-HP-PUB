import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: {
    default: 'Conseils HelloPro',
    template: '%s | HelloPro',
  },
  description: 'Guides, conseils et comparatifs pour vos achats professionnels.',
};

export default function RootLayout({
  children,
  head,
}: {
  children: React.ReactNode;
  head: React.ReactNode;
}) {
  return (
    <html lang="fr">
      <head>{head}</head>
      <body className="min-h-screen bg-background font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
