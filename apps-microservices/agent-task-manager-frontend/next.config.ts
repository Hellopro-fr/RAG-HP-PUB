import path from 'node:path';
import { fileURLToPath } from 'node:url';

import type { NextConfig } from 'next';

// This service is self-contained inside the monorepo: trace and bundle from its own directory.
const root = path.dirname(fileURLToPath(import.meta.url));

// In production one origin serves everything: the ingress (Caddy) routes /api/* and /mcp to the
// Rust server. `next dev` has no ingress, so /api is rewritten to the backend; the SSE stream is
// opened directly on NEXT_PUBLIC_STREAM_ORIGIN in dev because the dev proxy may buffer it (§10).
const backend = process.env.BACKEND_INTERNAL_URL ?? 'http://localhost:8621';

const nextConfig: NextConfig = {
  output: 'standalone',
  outputFileTracingRoot: root,
  turbopack: { root },
  poweredByHeader: false,
  async rewrites() {
    if (process.env.NODE_ENV !== 'development') return [];
    return [{ source: '/api/:path*', destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
