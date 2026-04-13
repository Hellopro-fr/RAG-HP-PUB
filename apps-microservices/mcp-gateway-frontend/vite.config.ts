import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8592',
        changeOrigin: true,
      },
      '/login': {
        target: 'http://localhost:8592',
        changeOrigin: true,
      },
      '/logout': {
        target: 'http://localhost:8592',
        changeOrigin: true,
      },
      '/token': {
        target: 'http://localhost:8592',
        changeOrigin: true,
      },
      '/register': {
        target: 'http://localhost:8592',
        changeOrigin: true,
      },
      '/.well-known': {
        target: 'http://localhost:8592',
        changeOrigin: true,
      },
      '/sse': {
        target: 'http://localhost:8592',
        changeOrigin: true,
        ws: true,
      },
      '/mcp': {
        target: 'http://localhost:8592',
        changeOrigin: true,
        ws: true,
      },
      '/message': {
        target: 'http://localhost:8592',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8592',
        changeOrigin: true,
      },
    },
  },
});
