import type { Metadata } from 'next';
import './globals.css';

const GTM_ID = 'GTM-PBBSTMC';

// Anti-flicker : cache la page le temps que GTM charge en footer (timeout 2000ms)
const ANTI_FLICKER = `(function(a,s,y,n,c,h,i,d,e){s.className+=' '+y;h.start=1*new Date;h.end=i=function(){s.className=s.className.replace(RegExp(' ?'+y),'')};(a[n]=a[n]||[]).hide=h;setTimeout(function(){i();h.end=null},c);h.timeout=c;})(window,document.documentElement,'async-hide','dataLayer',2000,{'${GTM_ID}':true});`;

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
        {/* Étape 1 — anti-flicker : cache la page + init dataLayer (avant tout) */}
        <style dangerouslySetInnerHTML={{ __html: '.async-hide{opacity:0!important}' }} />
        <script dangerouslySetInnerHTML={{ __html: ANTI_FLICKER }} />
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
      </body>
    </html>
  );
}
