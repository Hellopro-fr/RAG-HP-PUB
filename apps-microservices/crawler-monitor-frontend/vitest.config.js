import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.js'],
    globals: true,
    include: [
      'src/**/*.{test,spec}.{js,jsx}',
      'tests/**/*.{test,spec}.{js,jsx}',
    ],
    // Fuseau figé : la CI tourne en UTC, où « pas de fuseau → UTC » et « pas de
    // fuseau → heure locale » donnent le MÊME résultat. dates.test.js ne
    // prouvait donc plus rien là où le bug se produit (poste dev en Europe/Paris).
    env: { TZ: 'Europe/Paris' },
  },
});
