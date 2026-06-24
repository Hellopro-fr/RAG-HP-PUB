'use client';

/**
 * Helpers GTM partagés — funnel de demande de devis (`quote_form_funnel`).
 *
 * Réplique le comportement legacy (cf. ticket GTM) :
 *  - `getHpSessionId()` : identifiant de session formulaire, MÊME format et MÊMES clés
 *    sessionStorage que le legacy (`hp_session_id` + `hp_session_last_activity`,
 *    fenêtre d'inactivité glissante de 30 min) → session partagée avec le formulaire iframe.
 *  - `pushQuoteFormFunnel()` : push de l'événement `quote_form_funnel` avec les mêmes champs
 *    que le legacy (dont `session_id` et `product.category5`).
 *
 * Utilisé par HeroQuoteForm et QuoteFormBlock (même formulaire groupée, contextes différents).
 */

const SESSION_KEY = 'hp_session_id';
const ACTIVITY_KEY = 'hp_session_last_activity';
const INACTIVITY_MAX_MS = 30 * 60 * 1000; // 30 min

interface DataLayerWindow extends Window {
  dataLayer?: Array<Record<string, unknown>>;
}

/**
 * Identifiant de session formulaire. Format identique au legacy :
 * `session_<timestamp_ms>_<9 car. base36>`. Réutilisé tant que l'inactivité < 30 min
 * (survit au reload), régénéré au-delà. Stocké dans sessionStorage (lisible par le legacy).
 */
export function getHpSessionId(): string {
  if (typeof window === 'undefined' || !window.sessionStorage) return 'unknown';

  const now = Date.now();
  let sessionId = sessionStorage.getItem(SESSION_KEY);
  const lastActivity = parseInt(sessionStorage.getItem(ACTIVITY_KEY) ?? '', 10);

  if (!sessionId || Number.isNaN(lastActivity) || now - lastActivity > INACTIVITY_MAX_MS) {
    sessionId = 'session_' + now + '_' + Math.random().toString(36).slice(2, 11);
    sessionStorage.setItem(SESSION_KEY, sessionId);
  }
  sessionStorage.setItem(ACTIVITY_KEY, String(now));
  return sessionId;
}

/** Lit `product.category5` depuis le dataLayer (poussé par GtmFooterScripts), comme le legacy. */
function getCategory5(): string {
  if (typeof window === 'undefined') return '';
  const dl = (window as DataLayerWindow).dataLayer ?? [];
  const entry = dl.find(
    (d) => (d as { product?: { category5?: string } }).product?.category5,
  ) as { product?: { category5?: string } } | undefined;
  return entry?.product?.category5 ?? '';
}

export interface QuoteFormFunnelParams {
  /** Contexte funnel : "header pages conseils" (Hero) ou "cta devis pages conseils" (bloc milieu). */
  funnelContext: string;
  stepNumber?: number;
  stepIndex?: number;
  stepName?: string;
  stepType?: string;
  funnelDevisplus?: string;
  userKnownStatus?: string;
}

/**
 * Pousse l'événement `quote_form_funnel` (vue de la 1re étape du formulaire), champs alignés
 * sur le legacy : ajoute `session_id` et `product.category5` (lu du dataLayer).
 */
export function pushQuoteFormFunnel(params: QuoteFormFunnelParams): void {
  if (typeof window === 'undefined') return;
  const w = window as DataLayerWindow;
  w.dataLayer = w.dataLayer || [];

  const {
    funnelContext,
    stepNumber,
    stepIndex = 0,
    stepName = '1ere-question',
    stepType = '1ere-question',
    funnelDevisplus = 'True',
    userKnownStatus = 'Unknown',
  } = params;

  w.dataLayer.push({
    event: 'quote_form_funnel',
    step_index: stepIndex,
    step_name: stepName,
    ...(stepNumber !== undefined ? { step_number: stepNumber } : {}),
    funnel_devisplus: funnelDevisplus,
    funnel_context: funnelContext,
    user_known_status: userKnownStatus,
    'product.category5': getCategory5(),
    step_type: stepType,
    page_location_uri: window.location.pathname + window.location.search,
    session_id: getHpSessionId(),
  });
}
