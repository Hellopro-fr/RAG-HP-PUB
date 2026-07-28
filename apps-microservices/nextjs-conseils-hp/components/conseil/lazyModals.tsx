'use client';

import dynamic from 'next/dynamic';

/**
 * Versions lazy-loadées (code-split) des modales lourdes, chargées hors du bundle
 * initial pour alléger l'hydratation mobile (INP). Chaque modale rend `null`
 * quand fermée et s'affiche en overlay `position: fixed` → `ssr: false` sans impact
 * (rien à rendre côté serveur), et sa position DOM n'a aucune importance.
 *
 * Usage : remplacer l'import direct par cet import (même nom) — l'API des composants
 * est identique, seul le moment de chargement change.
 */

export const IframeFormModal = dynamic(
  () => import('./IframeFormModal').then((m) => m.IframeFormModal),
  { ssr: false },
);

export const IframeProduitModal = dynamic(
  () => import('./IframeProduitModal').then((m) => m.IframeProduitModal),
  { ssr: false },
);

export const SearchModal = dynamic(
  () => import('./SearchModal').then((m) => m.SearchModal),
  { ssr: false },
);
