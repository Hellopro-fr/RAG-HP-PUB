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

  // Headers de sécurité
  async headers() {
    return [
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
        ],
      },
    ];
  },
};

module.exports = nextConfig;
