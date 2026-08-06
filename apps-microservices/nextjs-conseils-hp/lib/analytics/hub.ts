'use client';

import { getCategory5, getHpSessionId } from './gtm';

/**
 * Tracking des pages HUB « projet » — point d'entrée UNIQUE.
 *
 * Spécification complète : `docs/tracking-hub.md` (21 événements) et
 * `docs/tracking-hub-events.csv`.
 *
 * ⚠️ RÈGLE : aucun composant de `components/hub/` n'appelle `dataLayer.push` ni
 * `gtag()` en direct. Tout passe par `pushHubEvent`. Deux raisons :
 *  - les paramètres communs (§5.2 du plan) sont ajoutés en UN SEUL endroit ;
 *  - `grep pushHubEvent` donne l'inventaire exhaustif des points de mesure, ce
 *    qu'un `grep dataLayer` éparpillé dans 12 composants ne donnerait pas.
 * Un `gtag()` direct contournerait en plus le Consent Mode du conteneur.
 *
 * VOCABULAIRE DÉDIÉ `hub_*` — ne JAMAIS pousser `quote_form_funnel`,
 * `quote_funnel_validation`, `Popup_Appel_Offre` ni `eec.add` depuis le HUB. Les
 * tags GTM branchés sur ces noms alimentent les KPI devis, et l'analyse d'impact
 * du template conseils compte ses leads sur `quote_funnel_validation` : un lead
 * HUB dedans contaminerait cette mesure sans que personne ne s'en aperçoive.
 */

/* ------------------------------------------------------------------ types --- */

export type HubEventName =
  // Communs aux deux tunnels
  | 'hub_form_view'
  | 'hub_form_email_submit'
  | 'hub_email_check'
  | 'hub_form_coordinates_submit'
  | 'hub_form_submission'
  | 'hub_form_error'
  | 'hub_form_abandon'
  // Tunnel projet uniquement
  | 'hub_form_start'
  | 'hub_form_step'
  | 'hub_form_email_view'
  // Tunnel guide
  | 'hub_guide_popup_view'
  | 'hub_guide_download'
  | 'hub_guide_shortcut'
  // Engagement
  | 'hub_article_click';

export type HubGroup = 'projet' | 'guide' | 'engagement';

/** Emplacement d'où le parcours a été ouvert. Décisif pour le tunnel guide : 5 portes. */
export type HubEntryPoint =
  | 'hero'
  | 'banner_guide'
  | 'cta_final'
  | 'bloc_thematique'
  | 'popup_scroll'
  | 'sticky_mobile';

/**
 * Paramètres autorisés — LISTE FERMÉE, et c'est le point important.
 *
 * C'est la garde anti-PII du plan (§6) : avec un `Record<string, unknown>`,
 * `pushHubEvent('hub_form_submission', 'projet', { email })` compilerait. Ici,
 * c'est une erreur de typecheck. Aucune clé `email`, `telephone`, `nom`,
 * `prenom`, `code_postal` ni `civilite` n'existe et il ne faut pas en ajouter.
 *
 * `answer_label` est admis : les réponses au questionnaire sont des choix FERMÉS
 * définis dans `data/hub/`, pas de la saisie libre.
 */
export interface HubEventParams {
  form_id?: 'assistant' | 'guide';
  entry_point?: HubEntryPoint;
  /** Id de l'étape (`step.id` du fichier de données), jamais son libellé. */
  step_name?: string;
  step_index?: number;
  step_total?: number;
  /** Libellé du choix coché — choix fermé, donc pas une donnée personnelle. */
  answer_label?: string;
  /** Verdict de l'APPEL 1 : le serveur connaît-il ce contact ? */
  result?: 'known' | 'unknown';
  user_known_status?: 'Known' | 'Unknown';
  lead_path?: 'complet' | 'reconnu' | 'deja_converti';
  steps_answered?: number;
  last_step_name?: string;
  last_step_index?: number;
  error_stage?: 'email' | 'coordinates';
  http_status?: number;
  download_trigger?: 'auto' | 'manual';
  trigger_section_id?: string;
  article_url?: string;
  article_id?: number;
  source_block?: string;
  /** Id envoyé à l'API : id de page pour le projet, id + 1000 pour le guide. */
  id_page_hub?: number;
}

interface DataLayerWindow extends Window {
  dataLayer?: Array<Record<string, unknown>>;
}

/* --------------------------------------------------- contexte de la page --- */

/**
 * Contexte de page (`hub_page_id`, `hub_page_slug`), lu depuis le dataLayer et
 * non passé en props.
 *
 * Pourquoi : le faire descendre en props traverserait une dizaine de composants,
 * dont plusieurs Server Components qui n'en ont aucun autre usage. Et c'est déjà
 * le motif du legacy pour `product.category5` (cf. `getCategory5`).
 *
 * Le push est émis par un `<script>` rendu par le SERVEUR (`HubTrackingContext`),
 * donc exécuté au parsing du document : il est dans le dataLayer bien avant qu'un
 * composant client puisse être hydraté, et il n'y a aucune course possible.
 */
interface HubPageContext {
  hub_page_id: number;
  hub_page_slug: string;
}

function getHubPageContext(): Partial<HubPageContext> {
  if (typeof window === 'undefined') return {};
  const dl = (window as DataLayerWindow).dataLayer ?? [];
  // Parcours en sens inverse : sur une navigation client, le contexte le plus
  // récent est le bon.
  for (let i = dl.length - 1; i >= 0; i -= 1) {
    const entry = dl[i] as Partial<HubPageContext> | undefined;
    if (entry && typeof entry.hub_page_id === 'number') {
      return { hub_page_id: entry.hub_page_id, hub_page_slug: entry.hub_page_slug };
    }
  }
  return {};
}

/**
 * Sérialise le push de contexte pour le `<script>` serveur de `HubTrackingContext`.
 * Ici plutôt que dans le composant : la forme lue par `getHubPageContext` et la
 * forme écrite restent côte à côte, donc impossible de modifier l'une seule.
 */
export function hubPageContextScript(pageId: number, slug: string): string {
  const payload: HubPageContext = { hub_page_id: pageId, hub_page_slug: slug };
  // `JSON.stringify` n'échappe PAS `<` : un slug contenant `</script>` fermerait
  // la balise et le reste serait interprété comme du HTML. Le slug vient de nos
  // fichiers de données, donc le risque est théorique — mais un JSON inline
  // non échappé est le motif d'injection le plus banal du web, et le coût de
  // s'en protéger est d'un `replace`.
  const json = JSON.stringify(payload).replace(/</g, '\\u003c');
  return `window.dataLayer=window.dataLayer||[];dataLayer.push(${json});`;
}

/* -------------------------------------------------------------- le push --- */

/**
 * Pousse un événement `hub_*` avec les paramètres communs.
 *
 * `hub_group` est un argument EXPLICITE et non déduit du nom de l'événement :
 * `hub_form_submission` existe dans les deux tunnels, et se tromper de groupe est
 * une erreur silencieuse qui fausse tous les rapports segmentés.
 */
export function pushHubEvent(
  event: HubEventName,
  group: HubGroup,
  params: HubEventParams = {},
): void {
  if (typeof window === 'undefined') return;
  const w = window as DataLayerWindow;
  w.dataLayer = w.dataLayer || [];

  // Les clés `undefined` sont retirées : GA4 enregistrerait sinon une dimension
  // vide, indistinguable d'une valeur réellement absente à l'analyse.
  const cleaned = Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== undefined && value !== ''),
  );

  w.dataLayer.push({
    event,
    hub_group: group,
    ...getHubPageContext(),
    // Session partagée avec le formulaire legacy (fenêtre glissante de 30 min) :
    // permet de recoller un visiteur qui fait le questionnaire PUIS le guide.
    session_id: getHpSessionId(),
    'product.category5': getCategory5(),
    ...cleaned,
  });
}

/* ------------------------------------------------------ déduplication ------ */

/**
 * Clés déjà émises, portée CHARGEMENT DE PAGE.
 *
 * ⚠️ Ne convient qu'aux événements qui ne doivent partir qu'une fois par page :
 * l'impression du formulaire du hero, l'affichage de la pop-up. Un module ne se
 * réinitialise pas quand un parcours redémarre.
 *
 * Pour une dédup à la portée d'un PARCOURS (les étapes du questionnaire, qu'il
 * faut ré-émettre si le visiteur rouvre le dialog), utiliser un `useRef` dans le
 * composant — c'est lui qui sait quand le parcours est réinitialisé.
 */
const firedOnce = new Set<string>();

/** Variante à usage unique par chargement de page. Renvoie `true` si l'événement est parti. */
export function pushHubEventOnce(
  key: string,
  event: HubEventName,
  group: HubGroup,
  params: HubEventParams = {},
): boolean {
  if (firedOnce.has(key)) return false;
  firedOnce.add(key);
  pushHubEvent(event, group, params);
  return true;
}

/** Réinitialise la dédup « une fois par page ». Réservé aux tests. */
export function __resetHubEventDedup(): void {
  firedOnce.clear();
}

/* ------------------------------------------------------------- utilitaire --- */

/**
 * Extrait l'id numérique d'une URL de page conseil (`…-5297.html` → `5297`).
 * `undefined` si l'URL n'a pas cette forme — un lien hors conseils ne doit pas
 * produire un `article_id` inventé.
 */
export function articleIdFromUrl(url: string): number | undefined {
  const match = /-(\d+)\.html(?:[?#].*)?$/.exec(url);
  return match ? Number(match[1]) : undefined;
}
