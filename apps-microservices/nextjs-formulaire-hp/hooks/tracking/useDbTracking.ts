"use client";

import { useCallback } from 'react';
import { getSessionId } from '@/lib/analytics/gtm';
import { basePath } from '@/lib/utils';
import { useFlowStore, FLOW_ORIGINAL_TOKEN_KEY } from '@/lib/stores/flow-store';

const getApiBasePath = () => {
  return basePath || '';
};

// Use Next.js API proxy to avoid CORS issues
const TRACKING_API_URL = '/api/tracking';

type EventType = 'questionnaire' | 'profile' | 'selection' | 'contact' | 'conversion' | 'matching';

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
    if (typeof window === 'undefined') return;

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

        sessionMeta = {
          user_agent: navigator.userAgent,
          referrer: document.referrer || '', // 'direct' si vide (ex: accès direct ou favori)
          entry_url: window.location.pathname,
          token: token,
        };
        sessionStorage.setItem(metaKey, 'true');
      }

      // Récupérer le flowType depuis le store pour le tracking session
      const storeFlowType = useFlowStore.getState().flowType;
      
      // type_flow (0: default | 1: flow demande categ | 2: flow produit)
      let typeFlow = 2;
      if (storeFlowType === 'principal') {
        typeFlow = 2;
      } else if (storeFlowType) {
        typeFlow = 1;
      }
      
      // Déterminer type_dmd_categ (0: par défaut, 1: produit insuffisant, 2: intentionnelle)
      let typeDmdCateg = 0;
      if (storeFlowType === 'pas_assez_produits') {
        typeDmdCateg = 1;
      } else if (storeFlowType === 'pas_trouve_recherchez') {
        typeDmdCateg = 2;
      }

      // Construire le payload
      const payload: any = {
        etape: 'tracking_action',
        data: {
          session_id: sessionId,
          category_id: categoryId,
          type_flow: typeFlow,
          type_dmd_categ: typeDmdCateg,
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
