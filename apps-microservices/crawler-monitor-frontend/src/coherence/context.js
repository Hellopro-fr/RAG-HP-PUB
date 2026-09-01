import { createContext } from 'react';

/**
 * Contexte du framework de coherence.
 *
 * Isole dans son propre module : un fichier qui exporte un composant ne doit
 * exporter que des composants, sinon le Fast Refresh de Vite recharge la page
 * entiere a chaque edition (regle react-refresh/only-export-components).
 */
export const CoherenceContext = createContext(null);
