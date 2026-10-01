'use client';

import { useEffect } from 'react';

/**
 * Déclenche AUTOMATIQUEMENT le téléchargement du guide dès l'affichage de l'écran
 * de remerciement (montage du composant). Le bouton « Télécharger à nouveau »
 * reste disponible pour relancer manuellement.
 *
 * No-op tant que l'URL n'est pas un vrai fichier (`undefined` ou `'#'`, design-only).
 *
 * ⚠️ Le forçage du téléchargement via l'attribut `download` ne fonctionne que pour
 * une URL MÊME ORIGINE. Pour un PDF servi cross-origin (CDN / api.hellopro.fr), le
 * serveur devra renvoyer `Content-Disposition: attachment` — sinon le navigateur
 * ouvrira le fichier au lieu de le télécharger.
 */
export function useAutoDownload(fileUrl?: string) {
  useEffect(() => {
    if (!fileUrl || fileUrl === '#') return;
    const link = document.createElement('a');
    link.href = fileUrl;
    link.download = '';
    link.rel = 'noopener';
    document.body.appendChild(link);
    link.click();
    link.remove();
  }, [fileUrl]);
}
