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
    remotePatterns: [
      { protocol: 'https', hostname: 'www.hellopro.fr' },
      { protocol: 'https', hostname: 'cdn.hellopro.fr' },
      { protocol: 'https', hostname: 'api.hellopro.fr' },
      { protocol: 'https', hostname: '**.hellopro.fr' },
    ],
  },

  async rewrites() {
    return [
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

module.exports = nextConfig;
