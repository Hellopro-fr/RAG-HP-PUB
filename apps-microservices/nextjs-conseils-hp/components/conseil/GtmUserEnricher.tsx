'use client';

import { useEffect } from 'react';
import { fetchAndPushUser } from '@/lib/analytics/gtmUser';

/**
 * Déclenche, après montage, l'enrichissement de l'objet `user` du dataLayer pour les
 * visiteurs identifiés (cf. lib/analytics/gtmUser). Ne rend rien.
 */
export function GtmUserEnricher() {
  useEffect(() => {
    void fetchAndPushUser();
  }, []);
  return null;
}
