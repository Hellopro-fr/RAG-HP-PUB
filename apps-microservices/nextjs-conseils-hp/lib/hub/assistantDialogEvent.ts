import type { HubEntryPoint } from '@/lib/analytics/hub';

/**
 * Canal d'ouverture du questionnaire projet — module VOLONTAIREMENT léger
 * (aucune dépendance UI), jumeau de `guideDialogEvent.ts`.
 *
 * Les déclencheurs (`triggers.tsx`, `StickyCta.tsx`) n'ont besoin que de
 * `openAssistantDialog`. L'importer depuis `AssistantForm.tsx` tirerait tout le
 * corps du questionnaire — Radix, les étapes, `react-international-phone` — dans
 * chaque module qui pose un simple bouton.
 *
 * ℹ️ Le seul import est un `import type` : effacé à la compilation, donc aucun
 * octet ajouté au bundle et aucune frontière client franchie.
 *
 * ⚠️ Créé le 2026-08-25 pour corriger une asymétrie entre les deux tunnels. Le
 * tunnel guide savait depuis le début quel CTA l'avait ouvert ; le questionnaire,
 * lui, émettait `hub_entry_point: 'hero'` en dur à l'impression du bloc inline et
 * RIEN sur sa conversion. Six emplacements ouvrent pourtant ce même dialog :
 * impossible de répondre à « quel CTA amène des projets ? », alors que la
 * question était résolue côté guide.
 */
export const ASSISTANT_DIALOG_EVENT = 'hp:open-assistant-dialog';

/**
 * Emplacement par défaut.
 *
 * `hero` et non une valeur neutre : le questionnaire commence toujours par son
 * bloc inline du hero, et c'est de là que part un visiteur qui n'a cliqué sur
 * aucun CTA. Un appel sans argument décrit donc bien la réalité.
 */
export const DEFAULT_ASSISTANT_ENTRY_POINT: HubEntryPoint = 'hero';

/**
 * Ouvre le questionnaire depuis n'importe où (client uniquement).
 *
 * `entryPoint` voyage dans le `detail` de l'événement : c'est la seule façon de
 * savoir quel emplacement a converti, le dialog n'existant qu'en un exemplaire.
 */
export function openAssistantDialog(
  entryPoint: HubEntryPoint = DEFAULT_ASSISTANT_ENTRY_POINT
) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(ASSISTANT_DIALOG_EVENT, { detail: { entryPoint } }));
}

/**
 * Lit l'emplacement porté par l'événement d'ouverture.
 *
 * Centralisé ici pour que la forme du `detail` soit décrite à un seul endroit :
 * un écouteur qui dérive rend la dimension `hub_entry_point` fausse sans que
 * rien ne le signale — ni erreur, ni valeur vide, juste une mauvaise attribution.
 */
export function readAssistantEntryPoint(event?: Event): HubEntryPoint {
  const detail = (event as CustomEvent<{ entryPoint?: HubEntryPoint }> | undefined)?.detail;
  return detail?.entryPoint ?? DEFAULT_ASSISTANT_ENTRY_POINT;
}
