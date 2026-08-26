'use client';

import dynamic from 'next/dynamic';

/**
 * Chargement PARESSEUX de `PhoneField` (react-international-phone + son CSS = la
 * lib la plus lourde du HUB). Elle ne sert qu'à l'étape COORDONNÉES, jamais au
 * chargement initial → on la sort du bundle initial (gain INP/TBT) : son chunk
 * n'est téléchargé qu'au moment où le champ s'affiche.
 *
 * `ssr:false` : le champ vit toujours dans un flux client (dialogs / étape
 * coordonnées), jamais rendu côté serveur. Le `loading` est une boîte de MÊME
 * hauteur (`h-12`) → aucun décalage (CLS) au remplacement.
 *
 * Les tests mockent CE module (`PhoneFieldLazy`) par un input simple, ce qui
 * évite d'embarquer la lib + son CSS dans jsdom.
 */
export const PhoneField = dynamic(() => import('./PhoneField').then((m) => m.PhoneField), {
  ssr: false,
  loading: () => (
    <div className="h-12 w-full rounded-xl border border-border bg-surface" aria-hidden />
  ),
});
