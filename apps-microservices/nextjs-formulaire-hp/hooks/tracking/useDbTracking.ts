"use client";

import { useCallback } from 'react';
import { getSessionId } from '@/lib/analytics/gtm';
import { basePath } from '@/lib/utils';
import { useFlowStore, FLOW_ORIGINAL_TOKEN_KEY } from '@/lib/stores/flow-store';

const getApiBasePath = () => {
  return basePath || '';
};

// Use Next.js API proxy to avoid CORS issues
// Route renommée pour éviter blocage WAF Imperva (mot "tracking" détecté)
const TRACKING_API_URL = '/api/tck';

type EventType = 'questionnaire' | 'profile' | 'selection' | 'contact' | 'conversion' | 'matching' | 'pricing';

interface TrackingEvent {
  event_type: string;
  event_name: string;
  event_data?: Record<string, any>;
  page?: string;
  step_index?: number;
  client_timestamp?: string;
}

interface TrackingPayload {
  etape: string;
  data: {
    session_id: string;
    category_id?: number | null;
    event: TrackingEvent;
    session_meta?: {
      user_agent: string;
      referrer: string;
      entry_url: string;
      token?: string;
      abtest_ux_lead_version: number;
    };
  };
}

export function useDbTracking() {
  const trackDbEvent = useCallback((
    eventType: EventType,
    eventName: string,
    eventData: Record<string, any> = {},
    categoryId?: number | null,
    stepIndex?: number
  ) => {
    if (typeof window === 'undefined' || window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') return;

    try {
      const sessionId = getSessionId();
      const metaKey = `hp_db_tracking_meta_sent_${sessionId}`;
      const hasSentMeta = sessionStorage.getItem(metaKey);

      // Préparer les méta-données de session (seulement si pas encore envoyées)
      let sessionMeta = undefined;
      if (!hasSentMeta) {
        // Récupérer le token original si présent
        let token = undefined;
        if (typeof window !== 'undefined') {
          token = sessionStorage.getItem(FLOW_ORIGINAL_TOKEN_KEY) || undefined;
        }

        // Version A/B injectée dans le token URL (abtest_UX_lead_version).
        // Normalisée à 0 par défaut pour faciliter les filtres SQL côté analytics.
        const abtestVersion = useFlowStore.getState().abtestUxLeadVersion ?? 0;

        sessionMeta = {
          user_agent: navigator.userAgent,
          referrer: document.referrer || '', // 'direct' si vide (ex: accès direct ou favori)
          entry_url: window.location.pathname,
          token: token,
          abtest_ux_lead_version: abtestVersion,
        };
        sessionStorage.setItem(metaKey, 'true');
      }
      // type_flow et type_dmd_categ (On ne les initialise plus à 0 par défaut pour éviter d'écraser la base)
      let typeFlow: number | null = null;
      let typeDmdCateg: number | null = null;

      if (eventType === "matching") {
        if ( eventName === "success" || eventName === "initial") {
          typeFlow = 2;
        } else {
          typeFlow = 1;
        } 
        typeDmdCateg = 0;     
      } else if (eventName === "insufficient_results") { 
        typeFlow = 1;
        typeDmdCateg = 1;
      } else if (eventName === "form_submit_custom_need") { 
        typeFlow = 1;
        typeDmdCateg = 2;
      } else if (eventName === "form_submit") { 
        typeFlow = 2;
        typeDmdCateg = 0;
      }

      // Construire le payload
      const payload: any = {
        etape: 'tracking_action',
        data: {
          session_id: sessionId,
          category_id: categoryId,
          event: {
            event_type: eventType,
            event_name: eventName,
            event_data: eventData,
            page: window.location.pathname,
            step_index: stepIndex ?? 0,
            client_timestamp: new Date().toISOString(),
          },
          session_meta: sessionMeta,
        },
      };

      // N'ajouter les champs de qualification que s'ils ont été définis ci-dessus
      if (typeFlow !== null) {
        payload.data.type_flow = typeFlow;
        payload.data.type_dmd_categ = typeDmdCateg;
      }

      const apiBase = getApiBasePath();
      // Envoyer avec fetch (sendBeacon ne supporte pas bien les proxies Next.js)
      fetch(`${apiBase}${TRACKING_API_URL}`, {
        method: 'POST',
        body: JSON.stringify(payload),
        headers: { 'Content-Type': 'application/json'},
        keepalive: true, // Permet l'envoi même si la page se décharge
      }).catch(err => console.error('Tracking error:', err));

    } catch (error) {
      console.error('DB Tracking error:', error);
    }
  }, []);

  return { trackDbEvent };
}
