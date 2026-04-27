import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:3001',
        changeOrigin: true
      },
      '/cdn-images': {
        target: 'http://localhost:8580',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/cdn-images/, '/images')
      }
    }
  },
  build: {
    // Expose source maps for prod debugging without shipping them in the main bundle.
    // 'hidden' keeps the code map files available but no sourceMappingURL comment.
    sourcemap: 'hidden',
    // No manualChunks: Vite auto-splits via dynamic imports (React.lazy).
    // An earlier aggressive split caused runtime "Cannot set properties of
    // undefined (setting 'Activity')" because React ecosystem packages had
    // circular refs with vendor-misc (prop-types / tslib / etc). Rollup
    // reorders loads silently in that case and breaks React 19 init.
    // Page-level code-splitting via lazy() already gives us most of the caching
    // benefit without the ordering risk.
    chunkSizeWarningLimit: 900,
  },
});