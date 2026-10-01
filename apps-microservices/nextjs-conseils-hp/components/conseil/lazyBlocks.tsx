'use client';

import dynamic from 'next/dynamic';

/**
 * Versions lazy (code-split) des composants CLIENT sous la ligne de flottaison.
 * But : différer/découper l'hydratation initiale → meilleur INP mobile.
 *
 * - `ssr: false` (barres flottantes, aucun contenu SEO) → sortent totalement du
 *   rendu serveur ET du bundle initial ; montées côté client uniquement.
 * - `ssr: true` (contenu) → restent SSR-rendus (SEO/LCP intacts), mais leur JS
 *   client est chargé dans un chunk séparé → hydratation différée et découpée.
 *
 * Module `'use client'` pour autoriser `ssr: false` ; les composants restent
 * rendables depuis des Server Components (ConseilTemplate, BlockRenderer…).
 */

/* Barres flottantes — pas de contenu indexable */
export const StickyCtaBar = dynamic(
  () => import('./StickyCtaBar').then((m) => m.StickyCtaBar),
  { ssr: false },
);
export const ScrollToTopButton = dynamic(
  () => import('./ScrollToTopButton').then((m) => m.ScrollToTopButton),
  { ssr: false },
);

/* Contenu sous la flottaison — SSR gardé (SEO/LCP), hydratation différée */
export const Suppliers = dynamic(() => import('./Suppliers').then((m) => m.Suppliers));
export const CitedProductsCarousel = dynamic(
  () => import('./CitedProductsCarousel').then((m) => m.CitedProductsCarousel),
);
export const FaqBlock = dynamic(() => import('./blocks/FaqBlock').then((m) => m.FaqBlock));
export const ProduitsBlock = dynamic(() => import('./blocks/ProduitsBlock').then((m) => m.ProduitsBlock));
export const BrochureBlock = dynamic(() => import('./blocks/BrochureBlock').then((m) => m.BrochureBlock));
export const QuoteFormBlock = dynamic(() => import('./blocks/QuoteFormBlock').then((m) => m.QuoteFormBlock));
