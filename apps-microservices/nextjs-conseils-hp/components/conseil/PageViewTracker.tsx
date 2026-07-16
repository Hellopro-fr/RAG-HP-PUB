'use client';

import { useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import { sendPageView } from '@/lib/analytics/sessionTracking';

/**
 * Émet une « page vue » (cf. lib/analytics/sessionTracking) à CHAQUE page conseil affichée.
 *
 * Next est une SPA : un simple onload ne couvre que la 1re page. On branche donc sur le
 * routeur App Router via `usePathname` — l'effet se rejoue à chaque changement d'URL.
 * Le `useRef` garantit « une fois par page affichée » (évite le double-envoi du double
 * montage d'effet en mode strict React 18). Ne rend rien.
 */
export function PageViewTracker() {
  const pathname = usePathname();
  const lastTracked = useRef<string | null>(null);

  useEffect(() => {
    if (lastTracked.current === pathname) return;
    lastTracked.current = pathname;
    sendPageView();
  }, [pathname]);

  return null;
}
