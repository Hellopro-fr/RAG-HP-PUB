import type { HubEntryPoint } from '@/lib/analytics/hub';

/**
 * Canal d'ouverture du dialog guide — module VOLONTAIREMENT léger (aucune
 * dépendance UI).
 *
 * Les déclencheurs (`triggers.tsx`, rendus dès le chargement) n'ont besoin que de
 * `openGuideDialog`. S'ils l'importaient depuis `GuideDownloadDialog.tsx`, tout le
 * corps lourd du dialog (Radix + étapes) serait re-tiré dans le bundle initial et
 * annulerait son chargement paresseux (`HubOverlays`). En isolant l'événement +
 * l'opener ici, seul ce fichier minuscule est embarqué côté eager.
 *
 * ℹ️ Le seul import est un `import type` : effacé à la compilation, donc aucun
 * octet ajouté au bundle et aucune frontière client franchie.
 */
export const GUIDE_DIALOG_EVENT = 'hp:open-guide-dialog';

/**
 * Emplacement par défaut. Utilisé quand l'événement n'en transporte pas — ce qui
 * ne devrait pas arriver : `GuideButton` l'exige à l'appel.
 */
export const DEFAULT_GUIDE_ENTRY_POINT: HubEntryPoint = 'banner_guide';

/**
 * Ouvre le dialog guide depuis n'importe où (client uniquement).
 *
 * `entryPoint` voyage dans le `detail` de l'événement : quatre emplacements de la
 * page ouvrent ce même dialog, et c'est la seule façon de savoir lequel a
 * converti. Le fixer à la construction du dialog serait impossible — il n'en
 * existe qu'une instance.
 */
export function openGuideDialog(entryPoint: HubEntryPoint = DEFAULT_GUIDE_ENTRY_POINT) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(GUIDE_DIALOG_EVENT, { detail: { entryPoint } }));
}

/**
 * Lit l'emplacement porté par l'événement d'ouverture.
 *
 * Centralisé ici parce que DEUX écouteurs le lisent : celui de `HubOverlays` (qui
 * arme le montage paresseux) et celui du dialog lui-même. La forme du `detail`
 * doit rester décrite à un seul endroit, sinon l'un des deux dérive en silence et
 * la dimension `hub_entry_point` devient fausse sans que rien ne le signale.
 */
export function readGuideEntryPoint(event?: Event): HubEntryPoint {
  const detail = (event as CustomEvent<{ entryPoint?: HubEntryPoint }> | undefined)?.detail;
  return detail?.entryPoint ?? DEFAULT_GUIDE_ENTRY_POINT;
}
