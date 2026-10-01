import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import vueDevTools from 'vite-plugin-vue-devtools'

const BACKEND = process.env.ACCOUNT_BACKEND_URL || 'http://localhost:8600'

export default defineConfig({
  plugins: [vue(), vueJsx(), vueDevTools()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: false },
      '/authorize': { target: BACKEND, changeOrigin: false },
      '/token': { target: BACKEND, changeOrigin: false },
      '/introspect': { target: BACKEND, changeOrigin: false },
      '/register': { target: BACKEND, changeOrigin: false },
      '/.well-known': { target: BACKEND, changeOrigin: false },
    },
  },
})
