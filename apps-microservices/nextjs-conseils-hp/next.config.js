/** @type {import('next').NextConfig} */

const BUILD_VERSION = '0.1.0';

const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',

  // Next.js 15 — optimisations
  experimental: {
    optimizePackageImports: ['lucide-react', '@radix-ui/react-icons'],
  },

  generateBuildId: async () => `${BUILD_VERSION}-${Date.now()}`,

  env: {
    NEXT_PUBLIC_BUILD_VERSION: BUILD_VERSION,
  },

  // Pas de basePath — service monté sur sous-domaine conseils.hellopro.fr
  // Voir CLAUDE.md §6 et §20 (décision 2026-05-22)

  images: {
    // WebP uniquement (défaut Next). ⚠️ NE PAS ajouter 'image/avif' : les images
    // HUB incluent des PNG transparents (livres `_removebg.png`), et l'AVIF à canal
    // alpha est mal rendu sur iOS Safari 15.4–16 (versions du browserslist) → image
    // transparente invisible en mobile. WebP gère l'alpha partout. En prime, éviter
    // l'AVIF supprime son encodage coûteux sous `cpus: 0.5` (affichages lents).
    formats: ['image/webp'],
    // Les images HUB sont des assets STATIQUES immuables (chemins figés dans
    // data/hub/). Le TTL par défaut du cache optimiseur est de 60 s : passé ce
    // délai, l'image est ré-encodée à la requête suivante — coûteux en AVIF sous
    // `cpus: 0.5`, d'où des affichages lents par intermittence. On fixe 1 an :
    // chaque variante n'est encodée qu'UNE fois, plus de ré-encodage périodique.
    minimumCacheTTL: 31536000,
    remotePatterns: [
      { protocol: 'https', hostname: 'www.hellopro.fr' },
      { protocol: 'https', hostname: 'cdn.hellopro.fr' },
      { protocol: 'https', hostname: 'api.hellopro.fr' },
      { protocol: 'https', hostname: '**.hellopro.fr' },
    ],
  },

  async rewrites() {
    return [
      // ⚠️ ORDRE SIGNIFICATIF : le premier match gagne. La règle HUB doit rester
      // AVANT la règle conseils, sinon /…-projet.html tomberait sur [slugWithId]
      // qui exige un suffixe -<digits> et redirigerait vers la 404 HelloPro.
      //
      // HUB : /<slug>-<id>-projet.html → /hub/<slug>-<id>
      // Namespace `-projet.html` neuf (aucune page HelloPro existante) → pas de
      // collision possible avec les slugs conseils. L'URL publique reste inchangée
      // (rewrite interne, pas de redirect). L'id est la clé de lecture des données
      // dans data/hub/, parsé côté TS par parseHubSlug().
      { source: '/:hubSlug([^/]+)-projet\\.html', destination: '/hub/:hubSlug' },

      // /slug-123.html → /slug-123 : route les URLs .html vers le segment
      // dynamique [slugWithId] SANS middleware. Préserve l'ISR / le full route
      // cache, contrairement à NextResponse.rewrite() en middleware qui force
      // le rendu dynamique. L'URL .html reste visible (rewrite interne, pas de redirect).
      { source: '/:slug([^/]+)\\.html', destination: '/:slug' },
    ];
  },

  async headers() {
    return [
      // Les en-têtes de sécurité (X-Frame-Options, X-Content-Type-Options,
      // X-XSS-Protection, Referrer-Policy, X-DNS-Prefetch-Control) sont posés par
      // le reverse proxy nginx (nginx.conf), unique point d'entrée public en prod
      // (le conteneur Next est `expose` only). On évite ici de les dupliquer.
      // Seuls les Cache-Control par route restent gérés côté Next.
      {
        source: '/fonts/:path*',
        headers: [
          { key: 'Cache-Control', value: 'public, max-age=31536000, immutable' },
        ],
      },
      {
        source: '/images/:path*',
        headers: [
          { key: 'Cache-Control', value: 'public, max-age=31536000, immutable' },
        ],
      },
      {
        source: '/api/conseils/:path*',
        headers: [
          { key: 'Cache-Control', value: 'public, max-age=3600, stale-while-revalidate=86400' },
        ],
      },
      {
        source: '/api/produits',
        headers: [
          { key: 'Cache-Control', value: 'public, max-age=600, stale-while-revalidate=3600' },
        ],
      },
    ];
  },
};

// Bundle analyzer — activé UNIQUEMENT en passant ANALYZE=true. Le `require` est
// fait DANS le `if` : un build/`npm ci` normal ne le charge jamais, donc le paquet
// n'a PAS besoin d'être dans package.json (le mettre y casserait `npm ci`, dont le
// lockfile ne le connaît pas). Pour analyser en local, l'installer ad hoc puis
// lancer le build, sans toucher au lockfile :
//   npm i --no-save @next/bundle-analyzer && ANALYZE=true npm run build
let exportedConfig = nextConfig;
if (process.env.ANALYZE === 'true') {
  const withBundleAnalyzer = require('@next/bundle-analyzer')({ enabled: true });
  exportedConfig = withBundleAnalyzer(nextConfig);
}

module.exports = exportedConfig;
