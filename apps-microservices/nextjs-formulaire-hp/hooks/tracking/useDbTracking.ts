"use client";

import { useCallback } from 'react';
import { getSessionId } from '@/lib/analytics/gtm';
import { basePath } from '@/lib/utils';

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
        sessionMeta = {
          user_agent: navigator.userAgent,
          referrer: document.referrer,
          entry_url: window.location.pathname,
          // token: ... (si disponible via URL ou store)
        };
        sessionStorage.setItem(metaKey, 'true');
      }

      // Construire le payload
      const payload: TrackingPayload = {
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
