// Flat config for ESLint v9 — Vue 3 + TS + Prettier integration.
// Run: `npm run lint` (or `npm run lint:fix`).
// Format with: `npm run format`.
import vue from 'eslint-plugin-vue';
import vueTsConfig from '@vue/eslint-config-typescript';
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting';

export default [
  {
    ignores: ['dist/**', 'node_modules/**', 'public/**', '**/*.d.ts'],
  },
  ...vue.configs['flat/recommended'],
  ...vueTsConfig(),
  skipFormatting,
  {
    rules: {
      // Project-specific tweaks
      'vue/multi-word-component-names': 'off',
      'vue/component-api-style': ['error', ['script-setup']],
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    },
  },
];
