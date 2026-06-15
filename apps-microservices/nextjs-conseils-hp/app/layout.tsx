import type { Metadata } from 'next';
import './globals.css';
import { CONSENT_MODE_INIT } from '@/lib/consent/consentMode';
import { CookieConsent } from '@/components/conseil/CookieConsent';
import { GtmUserEnricher } from '@/components/conseil/GtmUserEnricher';

const GTM_ID = 'GTM-PBBSTMC';

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
      <head>
        {/* Consent Mode v2 — DOIT être la 1re commande, avant GTM : push `consent default`
            (denied) + résolution depuis les cookies (.hellopro.fr) avec migration hp_consent.
            Remplace l'ancien anti-flicker Google Optimize (obsolète, service arrêté). Cf. ticket GTM. */}
        <script dangerouslySetInnerHTML={{ __html: CONSENT_MODE_INIT }} />
        {/* JSON-LD (schemaGuide + schemaBreadcrumb) rendu par @head/[slugWithId]/page.tsx */}
        {head}
      </head>
      <body className="min-h-screen bg-background font-sans antialiased">
        {/* Step 3 — GTM noscript fallback */}
        <noscript>
          <iframe
            src={`https://www.googletagmanager.com/ns.html?id=${GTM_ID}`}
            height="0"
            width="0"
            style={{ display: 'none', visibility: 'hidden' }}
          />
        </noscript>
        {children}
        {/* Enrichit le dataLayer `user` (type/pays/service/id) pour les visiteurs identifiés */}
        <GtmUserEnricher />
        {/* Bandeau de consentement RGPD (s'affiche si cookie hp_consent absent) */}
        <CookieConsent />
      </body>
    </html>
  );
}
