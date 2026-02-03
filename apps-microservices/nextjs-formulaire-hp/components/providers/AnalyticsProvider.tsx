'use client';

import { usePathname, useSearchParams } from 'next/navigation';
import { useEffect, Suspense, type ReactNode, useState } from 'react';
import { trackPageView } from '@/lib/analytics/ga4';
import { hotjarStateChange } from '@/lib/analytics/hotjar';
import { trackDeviceInfo, trackTrafficSource } from '@/lib/analytics';

function AnalyticsTrackerInner() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [initialTracked, setInitialTracked] = useState(false);

  // Track device info and traffic source only once on initial load
  useEffect(() => {
    if (!initialTracked) {
      trackDeviceInfo();
      trackTrafficSource();
      setInitialTracked(true);
    }
  }, [initialTracked]);

  // Track page views on navigation
  useEffect(() => {
    const url = pathname + (searchParams?.toString() ? `?${searchParams.toString()}` : '');

    // Track page view in GA4
    trackPageView(url);

    // Notify Hotjar of SPA navigation
    hotjarStateChange(url);
  }, [pathname, searchParams]);

  return null;
}

interface AnalyticsProviderProps {
  children: ReactNode;
}

export function AnalyticsProvider({ children }: AnalyticsProviderProps) {
  return (
    <>
      <Suspense fallback={null}>
        <AnalyticsTrackerInner />
      </Suspense>
      {children}
    </>
  );
}
