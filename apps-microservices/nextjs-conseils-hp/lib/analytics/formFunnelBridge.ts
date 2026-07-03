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
 * Dédup GLOBALE (niveau module), partagée entre TOUTES les modales et écouteurs `message` de la
 * page. Indispensable : plusieurs IframeFormModal / IframeProduitModal peuvent être montés et
 * OUVERTS simultanément (Hero mobile + desktop, blocs CTA/QuoteForm/TexteImage…). Le même relais
 * `hellopro_form_step` est alors reçu par chaque écouteur → sans dédup partagée, chaque étape
 * (dont page-remerciement = validation) serait poussée autant de fois qu'il y a d'écouteurs.
 * Réinitialisée à la fermeture de la modale (resetFormStepUri).
 */
const globalPushedSteps = new Set<string>();

/**
 * Traite un message `hellopro_form_step`. Retourne true si le message a été reconnu
 * (et traité), false sinon — l'appelant peut alors continuer son aiguillage.
 *
 * @param raw         données du MessageEvent
 * @param pushedSteps set de dédup par instance (conservé pour compat ; la dédup effective est
 *                    GLOBALE via globalPushedSteps pour couvrir le cas multi-écouteurs)
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
  // Cas particulier page-remerciement (= validation de la soumission) : une seule fois par
  // soumission, quelle que soit la variante (page-remerciement, -0, -1…) et le nombre de relais
  // reçus. On normalise donc toutes ces variantes sur une clé de dédup unique.
  const dedupKey = stepName.indexOf('page-remerciement') === 0 ? 'page-remerciement' : stepName;
  // Dédup sur le set GLOBAL (partagé entre tous les écouteurs) → chaque étape poussée UNE fois,
  // quel que soit le nombre de modales/écouteurs montés simultanément. (pushedSteps reste
  // alimenté pour compat/inspection, mais n'est plus la source de vérité de la dédup.)
  if (dedupKey && globalPushedSteps.has(dedupKey)) return true;
  if (dedupKey) { globalPushedSteps.add(dedupKey); pushedSteps.add(dedupKey); }

  const w = window as DataLayerWindow;
  w.dataLayer = w.dataLayer || [];
  w.dataLayer.push({ ...data.funnel, page_location_uri: newPath });
  return true;
}

/**
 * Réinitialise l'URL conseils à sa base (`.../{slug}.html`), en retirant le segment d'étape
 * (`/2eme-question`, `/email`…) ajouté pendant le parcours du formulaire. À appeler à la
 * fermeture de la modale pour que l'URL ne conserve pas l'étape du formulaire.
 */
export function resetFormStepUri(): void {
  if (typeof window === 'undefined') return;
  globalPushedSteps.clear(); // ré-arme la dédup funnel pour une éventuelle réouverture du formulaire
  const base = (window.location.pathname.match(/.*\.html/) ?? [window.location.pathname])[0];
  if (window.location.pathname !== base) {
    window.history.pushState(null, '', base + window.location.search + window.location.hash);
  }
}
