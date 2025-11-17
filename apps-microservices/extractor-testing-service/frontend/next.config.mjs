/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  webpack: (config) => {
    // This prevents webpack's file watcher from watching the node_modules directory.
    // It's the standard solution for the "EMFILE: too many open files" error in Next.js.
    config.watchOptions = { ...config.watchOptions, ignored: /node_modules/ };
    return config;
  },
}

export default nextConfig