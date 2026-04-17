import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:3001',
        changeOrigin: true
      }
    }
  },
  build: {
    // Expose source maps for prod debugging without shipping them in the main bundle.
    // 'hidden' keeps the code map files available but no sourceMappingURL comment.
    sourcemap: 'hidden',
    rollupOptions: {
      output: {
        // Manual chunks so vendor libs cache independently of app code.
        // When we ship a patch of the app, users don't re-download 200 KB of Recharts.
        manualChunks: (id) => {
          if (!id.includes('node_modules')) return undefined;
          if (id.includes('recharts') || id.includes('d3-')) return 'vendor-charts';
          if (id.includes('react-router')) return 'vendor-router';
          if (id.includes('@tanstack/react-query')) return 'vendor-query';
          if (id.includes('lucide-react')) return 'vendor-icons';
          if (id.includes('prismjs') || id.includes('react-simple-code-editor')) return 'vendor-editor';
          if (id.includes('react-window')) return 'vendor-window';
          // react / react-dom / react-is bundled together (circular-safe)
          if (id.includes('/react/') || id.includes('/react-dom/') || id.includes('/react-is/')) return 'vendor-react';
          return 'vendor-misc';
        },
      },
    },
    // We split aggressively, so warn only on chunks > 800 KB (realistically none).
    chunkSizeWarningLimit: 800,
  },
});