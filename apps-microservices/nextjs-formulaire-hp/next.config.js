/** @type {import('next').NextConfig} */

// Version de build - MODIFIER À CHAQUE DÉPLOIEMENT pour forcer le cache busting
const BUILD_VERSION = '1.0.0';

const nextConfig = {
  reactStrictMode: true,

  // Build standalone pour Docker
  output: 'standalone',

  // Build ID unique basé sur la version + timestamp
  // Force le navigateur à recharger les fichiers JS/CSS
  generateBuildId: async () => {
    return `${BUILD_VERSION}-${Date.now()}`;
  },

  // Exposer la version au frontend
  env: {
    NEXT_PUBLIC_BUILD_VERSION: BUILD_VERSION,
  },

  // URL de base pour le proxy Apache
  basePath: '/formulaire',
  assetPrefix: '/formulaire',

  // Configuration des images
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: '**',
      },
    ],
  },

  // Redirection optionnelle de la racine vers le questionnaire
  async redirects() {
    return [
      // Décommenter si vous voulez rediriger / vers /questionnaire
      // {
      //   source: '/',
      //   destination: '/questionnaire',
      //   permanent: false,
      // },
    ];
  },

  // Headers de sécurité et cache
  async headers() {
    return [
      // Headers de sécurité globaux
      {
        source: '/:path*',
        headers: [
          {
            key: 'X-DNS-Prefetch-Control',
            value: 'on',
          },
          {
            key: 'X-Frame-Options',
            value: 'SAMEORIGIN',
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          // HSTS - Force HTTPS pendant 1 an
          {
            key: 'Strict-Transport-Security',
            value: 'max-age=31536000; includeSubDomains',
          },
          // CSP - Contrôle des sources autorisées
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-inline' 'unsafe-eval' www.googletagmanager.com www.google-analytics.com static.hotjar.com script.hotjar.com",
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data: https: *.hellopro.fr www.googletagmanager.com",
              "font-src 'self' data:",
              "connect-src 'self' www.google-analytics.com *.hotjar.com *.hellopro.fr",
              "frame-src 'self' vars.hotjar.com",
            ].join('; '),
          },
          // Referrer - Limite les infos envoyées aux sites tiers
          {
            key: 'Referrer-Policy',
            value: 'strict-origin-when-cross-origin',
          },
          // Permissions - Désactive les APIs sensibles non utilisées
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=()',
          },
        ],
      },
      // Cache long pour les assets statiques (fonts, images publiques)
      {
        source: '/fonts/:path*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=31536000, immutable',
          },
        ],
      },
      {
        source: '/images/:path*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=31536000, immutable',
          },
        ],
      },
      // Cache pour les données de référence (caractéristiques, géo)
      // Ces données changent rarement
      {
        source: '/api/caracteristiques',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=3600, stale-while-revalidate=86400',
          },
        ],
      },
      {
        source: '/api/geo',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=86400, stale-while-revalidate=604800',
          },
        ],
      },
      {
        source: '/api/info-categorie/:path*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=3600, stale-while-revalidate=86400',
          },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
