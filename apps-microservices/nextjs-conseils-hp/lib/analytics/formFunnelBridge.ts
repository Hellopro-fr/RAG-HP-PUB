'use client';

/**
 * Pont de mesure funnel entre le formulaire (iframe, hellopro.fr) et la page conseils (parent).
 *
 * Contexte : le formulaire legacy mesure son funnel via une URI par étape (`/3eme-question`,
 * `/email`…) + un event `quote_form_funnel`. En iframe (ctx=next), ce mécanisme agit sur la
 * fenêtre de l'iframe (cross-origin) → il ne touche ni l'URL du parent ni le bon page_location.
 *
 * Le form relaie donc, via postMessage `hellopro_form_step`, l'objet funnel + le pathname
 * calculé (segment d'étape). Ce helper, côté parent :
 *   1. applique le segment sur l'URL conseils (history.pushState sur `.../{slug}.html{segment}`),
 *   2. pousse le funnel dans le dataLayer parent avec `page_location_uri` = URL conseils,
 *   3. déduplique par `step_name` (l'étape 1 est déjà émise par le Hero).
 *
 * → Source unique de mesure = le parent. L'iframe reste muette côté GA4 (cf. bridge ctx=next
 * dans formulaire_demande_groupee.php / formulaire_demande_produit.php).
 */

interface FunnelData {
  event?: string;
  step_name?: string;
  [key: string]: unknown;
}

interface FormStepMessage {
  type?: string;
  funnel?: FunnelData;
  pathname?: string;
}

interface DataLayerWindow extends Window {
  dataLayer?: Array<Record<string, unknown>>;
}

/**
 * Traite un message `hellopro_form_step`. Retourne true si le message a été reconnu
 * (et traité), false sinon — l'appelant peut alors continuer son aiguillage.
 *
 * @param raw         données du MessageEvent
 * @param pushedSteps set de dédup (par step_name), à conserver le temps d'une ouverture de modale
 */
export function handleFormStepMessage(raw: unknown, pushedSteps: Set<string>): boolean {
  const data = raw as FormStepMessage;
  if (data?.type !== 'hellopro_form_step' || !data.funnel) return false;
  if (typeof window === 'undefined') return true;

  // Segment relayé par le form (pathname de l'iframe après url_add_parameter) :
  // "/3eme-question", "/email", "/coordonnees", ou "/" (1re question → pas de suffixe).
  const seg = typeof data.pathname === 'string' ? data.pathname : '/';
  const base = (window.location.pathname.match(/.*\.html/) ?? [window.location.pathname])[0];
  const newPath = !seg || seg === '/' ? base : base + seg;

  window.history.pushState(null, '', newPath);

  const stepName = typeof data.funnel.step_name === 'string' ? data.funnel.step_name : '';
  // Dédup : évite de recompter une étape déjà poussée (ex. étape 1 émise par le Hero).
  if (stepName && pushedSteps.has(stepName)) return true;
  if (stepName) pushedSteps.add(stepName);

  const w = window as DataLayerWindow;
  w.dataLayer = w.dataLayer || [];
  w.dataLayer.push({ ...data.funnel, page_location_uri: newPath });
  return true;
}
