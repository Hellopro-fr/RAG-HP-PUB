/**
 * Canal d'ouverture du dialog guide — module VOLONTAIREMENT léger (aucune
 * dépendance UI).
 *
 * Les déclencheurs (`triggers.tsx`, rendus dès le chargement) n'ont besoin que de
 * `openGuideDialog`. S'ils l'importaient depuis `GuideDownloadDialog.tsx`, tout le
 * corps lourd du dialog (Radix + étapes) serait re-tiré dans le bundle initial et
 * annulerait son chargement paresseux (`HubOverlays`). En isolant l'événement +
 * l'opener ici, seul ce fichier minuscule est embarqué côté eager.
 */
export const GUIDE_DIALOG_EVENT = 'hp:open-guide-dialog';

/** Ouvre le dialog guide depuis n'importe où (client uniquement). */
export function openGuideDialog() {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(GUIDE_DIALOG_EVENT));
}
