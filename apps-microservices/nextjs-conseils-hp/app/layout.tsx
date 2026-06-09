import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: {
    default: 'Conseils HelloPro',
    template: '%s | HelloPro',
  },
  description: 'Guides, conseils et comparatifs pour vos achats professionnels.',
  // <meta name="author" content="Hellopro">
  authors: [{ name: 'Hellopro' }],
  // <meta name="robots" content="index, follow">
  robots: { index: true, follow: true },
  // <meta name="verify-v1" content="...">  (vérification de propriété du domaine)
  verification: {
    other: {
      'verify-v1': 'g7xyLD6Q4N922q7NXd0OIE5xnmKOHyIhF82OjU0ICeo=',
    },
  },
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
