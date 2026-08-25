'use client';

import { getCategory5, getHpSessionId } from './gtm';
// ⚠️ Le TYPE seulement. `hubPageContextScript` NE DOIT PAS être réexporté d'ici :
// ce module porte `'use client'`, et tout ce qui en sort est marqué client — un
// Server Component ne pourrait plus l'appeler. Il s'importe depuis
// `./hubPageContext`, qui est neutre.
import type { HubPageContext } from './hubPageContext';

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
 *
 * ⚠️ CONVENTION DE NOMMAGE (arbitrée le 2026-08-24, avec l'équipe analytics).
 * Le préfixe n'est pas cosmétique, il dit à quel seau GA4 la valeur appartient :
 *
 *  - **préfixe `hub_`** → paramètre PROPRE au HUB. Sa dimension GA4 lui est
 *    dédiée (`hub_group`, `hub_entry_point`, `hub_lead_path`).
 *  - **sans préfixe** → paramètre DÉLIBÉRÉMENT partagé avec le funnel devis
 *    historique, dont la dimension GA4 existe depuis 2022 : `step_name`,
 *    `step_index`, `user_known_status`. Les valeurs se mélangent dans la même
 *    dimension, et c'est voulu — un seul rapport couvre les deux périmètres.
 *
 * Ne pas préfixer un paramètre partagé (il cesserait d'alimenter sa dimension),
 * ne pas dé-préfixer un paramètre HUB (il polluerait un rapport existant).
 * GA4 fait une correspondance STRICTE sur le nom : une divergence ne produit
 * aucune erreur, seulement une dimension éternellement vide.
 */
export interface HubEventParams {
  form_id?: 'assistant' | 'guide';
  /** Dimension GA4 dédiée `hub_entry_point` — cf. convention ci-dessus. */
  hub_entry_point?: HubEntryPoint;
  /**
   * Position de l'étape en libellé GÉNÉRIQUE : `1ere-question`, `2eme-question`…
   * (plus `email` et `coordinates`). Voir `questionStepName`.
   */
  step_name?: string;
  /**
   * Id métier de l'étape (`budget`, `volume`…), propre à chaque page.
   * Complète `step_name` sans le remplacer : l'un sert à comparer les pages entre
   * elles, l'autre à savoir QUELLE question fait décrocher sur une page donnée.
   */
  step_id?: string;
  step_index?: number;
  step_total?: number;
  /** Libellé du choix coché — choix fermé, donc pas une donnée personnelle. */
  answer_label?: string;
  /**
   * Verdict de l'APPEL 1 : le serveur connaît-il ce contact ?
   *
   * Nommé `email_check_result` et non `result` : une dimension GA4 appelée
   * « result » dans une propriété partagée entre plusieurs périmètres est
   * ambiguë, et un nom de dimension est figé dès son enregistrement.
   */
  email_check_result?: 'known' | 'unknown';
  /** Sans préfixe : dimension PARTAGÉE avec le funnel devis (créée en 2022). */
  user_known_status?: 'Known' | 'Unknown';
  /** Dimension GA4 dédiée `hub_lead_path` — cf. convention ci-dessus. */
  hub_lead_path?: 'complet' | 'reconnu' | 'deja_converti';
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

/**
 * Toutes les clés de `HubEventParams`, énumérées à l'exécution.
 *
 * ⚠️ Une clé ajoutée à l'interface DOIT l'être ici aussi, sinon elle ne sera
 * jamais nettoyée entre deux événements. Le type `Record<keyof HubEventParams, …>`
 * en fait une erreur de compilation si on en oublie une — c'est volontaire, un
 * simple tableau de chaînes laisserait passer l'oubli.
 */
const HUB_PARAM_KEYS = Object.keys({
  form_id: 0,
  hub_entry_point: 0,
  step_name: 0,
  step_id: 0,
  step_index: 0,
  step_total: 0,
  answer_label: 0,
  email_check_result: 0,
  user_known_status: 0,
  hub_lead_path: 0,
  steps_answered: 0,
  last_step_name: 0,
  last_step_index: 0,
  error_stage: 0,
  http_status: 0,
  download_trigger: 0,
  trigger_section_id: 0,
  article_url: 0,
  article_id: 0,
  source_block: 0,
  id_page_hub: 0,
} satisfies Record<keyof HubEventParams, 0>) as Array<keyof HubEventParams>;

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
 * Le push est émis par un `<script>` rendu par le SERVEUR (`HubTrackingContext`,
 * qui appelle `hubPageContextScript` depuis `./hubPageContext`), donc exécuté au
 * parsing du document : il est dans le dataLayer bien avant qu'un composant
 * client puisse être hydraté, et il n'y a aucune course possible.
 */
function getHubPageContext(): Partial<HubPageContext> {
  if (typeof window === 'undefined') return {};
  const dl = (window as DataLayerWindow).dataLayer ?? [];
  // Parcours en sens inverse : sur une navigation client, le contexte le plus
  // récent est le bon.
  for (let i = dl.length - 1; i >= 0; i -= 1) {
    const entry = dl[i] as Partial<HubPageContext> | undefined;
    if (entry && typeof entry.hub_page_id === 'number') {
      return { hub_page_id: entry.hub_page_id, hub_page_uri: entry.hub_page_uri };
    }
  }
  return {};
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

  // ⚠️ TOUTES les clés connues sont poussées, y compris celles que cet événement
  // ne renseigne pas — avec la valeur `undefined`.
  //
  // GTM FUSIONNE les pushes successifs dans un modèle de données UNIQUE : une clé
  // absente d'un push conserve la valeur du push précédent. Omettre les
  // paramètres non pertinents laissait donc fuiter les valeurs d'un événement sur
  // le suivant — constaté en recette : un `hub_form_submission` du tunnel guide
  // portait encore `step_name: "delai"`, `answer_label` et `steps_answered: 4` du
  // questionnaire projet rempli juste avant. Silencieux, et faux dans GA4.
  //
  // Une clé présente à `undefined` écrase la précédente, et le tag GA4 n'émet pas
  // les paramètres `undefined` : la dimension est nettoyée sans être envoyée vide.
  const cleaned = Object.fromEntries(
    HUB_PARAM_KEYS.map((key) => {
      const value = params[key];
      return [key, value === '' ? undefined : value];
    }),
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
 * Libellé générique d'une étape de questionnaire, à partir de son index 0-based :
 * `1ere-question`, `2eme-question`, `3eme-question`…
 *
 * POURQUOI GÉNÉRIQUE plutôt que l'id métier (`budget`, `volume`) : les trois pages
 * HUB n'ont pas les mêmes questions. Avec des ids métier, un entonnoir GA4 ne peut
 * pas superposer les verticales — chaque page aurait ses propres noms d'étapes et
 * il faudrait trois rapports au lieu d'un. La position, elle, est comparable.
 *
 * L'id métier n'est pas perdu pour autant : il part dans `step_id`.
 *
 * Reprend la convention du funnel devis legacy (`pushQuoteFormFunnel` utilise
 * déjà `1ere-question`), ce qui évite deux vocabulaires dans le même conteneur.
 */
export function questionStepName(index: number): string {
  return index === 0 ? '1ere-question' : `${index + 1}eme-question`;
}

/**
 * Extrait l'id numérique d'une URL de page conseil (`…-5297.html` → `5297`).
 * `undefined` si l'URL n'a pas cette forme — un lien hors conseils ne doit pas
 * produire un `article_id` inventé.
 */
export function articleIdFromUrl(url: string): number | undefined {
  const match = /-(\d+)\.html(?:[?#].*)?$/.exec(url);
  return match ? Number(match[1]) : undefined;
}
