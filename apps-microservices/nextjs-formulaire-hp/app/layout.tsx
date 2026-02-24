import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import { GoogleAnalytics } from '@next/third-parties/google';
import { GoogleTagManager, GoogleTagManagerNoScript } from '@/components/analytics';
import { Hotjar } from '@/components/analytics';
import { QueryProvider, AnalyticsProvider, ThemeProvider } from '@/components/providers';
import { Toaster } from '@/components/ui/toaster';
import { Toaster as Sonner } from '@/components/ui/sonner';
import { Suspense } from 'react';
import FlowStorageReset from '@/components/flow/FlowStorageReset';
import './globals.css';

const inter = Inter({
  subsets: ['latin'],
  display: 'swap', // Évite le blocage du rendu pendant le chargement de la font
});

export const metadata: Metadata = {
  title: 'Trouvez votre fournisseur - Demande de devis | HelloPro',
  description:
    'Recevez gratuitement des devis de fournisseurs qualifiés. HelloPro vous met en relation avec les meilleurs professionnels pour votre projet.',
  authors: [{ name: 'HelloPro' }],
  robots: {
    index: false,
    follow: false,
  },
  openGraph: {
    title: 'Trouvez votre fournisseur - Demande de devis | HelloPro',
    description:
      'Recevez gratuitement des devis de fournisseurs qualifiés. HelloPro vous met en relation avec les meilleurs professionnels.',
    type: 'website',
    siteName: 'HelloPro',
    locale: 'fr_FR',
  },
  twitter: {
    card: 'summary',
    title: 'Demande de devis | HelloPro',
    description: 'Recevez gratuitement des devis de fournisseurs qualifiés.',
  },
  other: {
    'format-detection': 'telephone=no',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const gtmId = process.env.NEXT_PUBLIC_GTM_ID;
  const gaId = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;
  const hotjarId = process.env.NEXT_PUBLIC_HOTJAR_ID;
  const hotjarSv = process.env.NEXT_PUBLIC_HOTJAR_SV || '6';

  // Vérifier si les services analytics sont activés
  const isGtmEnabled = gtmId && gtmId !== 'GTM-XXXXXXX';
  const isGaEnabled = gaId && gaId !== 'G-XXXXXXXXXX';

  return (
    <html lang="fr" suppressHydrationWarning>
      <head>
        {/* Preconnect conditionnel - uniquement si les services analytics sont activés */}
        {isGtmEnabled && (
          <link rel="preconnect" href="https://www.googletagmanager.com" crossOrigin="anonymous" />
        )}
        {(isGtmEnabled || isGaEnabled) && (
          <link rel="preconnect" href="https://www.google-analytics.com" crossOrigin="anonymous" />
        )}

        {isGtmEnabled && <GoogleTagManager gtmId={gtmId} />}
      </head>
      <body className={inter.className}>
        {isGtmEnabled && <GoogleTagManagerNoScript gtmId={gtmId} />}

        <ThemeProvider
          attribute="class"
          defaultTheme="light"
          enableSystem
          disableTransitionOnChange
        >
          <QueryProvider>
            <AnalyticsProvider>
              <Suspense fallback={null}>
                <FlowStorageReset />
              </Suspense>
              {children}
              <Toaster />
              <Sonner />
            </AnalyticsProvider>
          </QueryProvider>
        </ThemeProvider>

        {/* Google Analytics 4 */}
        {isGaEnabled && <GoogleAnalytics gaId={gaId} />}

        {/* Hotjar - Si non renseigné, peut être chargé via GTM */}
        {hotjarId && hotjarId !== '1234567' && hotjarId !== '' && (
          <Hotjar hjid={hotjarId} hjsv={hotjarSv} />
        )}
      </body>
    </html>
  );
}
