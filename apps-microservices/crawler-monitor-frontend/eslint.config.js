import js from '@eslint/js'
import globals from 'globals'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs['recommended-latest'],
      reactRefresh.configs.vite,
    ],
    plugins: { react },
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    rules: {
      // Pas de `varsIgnorePattern` : il servait à taire les composants et
      // constantes en PascalCase/UPPER_SNAKE « utilisés seulement en JSX », rôle
      // désormais tenu par react/jsx-uses-vars ci-dessous. Le garder revenait à
      // amnistier toute constante réellement morte dont le nom commence par une
      // majuscule.
      'no-unused-vars': 'error',
      // Marque comme "utilisées" les variables consommées uniquement en JSX
      // (ex. `icon: Icon` déstructuré puis rendu via <Icon />), sinon
      // no-unused-vars remonte des faux positifs.
      'react/jsx-uses-vars': 'error',
    },
  },
  {
    // Fichiers de config exécutés par Node (CommonJS `require` de plugins).
    files: ['*.config.js'],
    languageOptions: { globals: globals.node },
  },
  {
    // Ces modules exportent volontairement un hook/contexte à côté de leur
    // composant — le coût est un Fast Refresh partiel, pas un bug.
    files: [
      'src/components/ui/**',
      'src/components/ToastProvider.jsx',
      'src/components/providers/ThemeProvider.jsx',
    ],
    rules: { 'react-refresh/only-export-components': 'off' },
  },
])
