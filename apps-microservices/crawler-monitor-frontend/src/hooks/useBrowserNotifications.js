import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * useBrowserNotifications — small wrapper around the Web Notifications API.
 *
 * Behavior:
 * - Reads the user preference from localStorage (key: 'notifications.enabled')
 * - Tracks the current Notification.permission
 * - When enabled + permission='granted': notify() actually shows the OS toast
 * - When enabled + permission='default': notify() requests permission first
 * - When tab is visible: notify() is a no-op (user is already looking)
 *
 * Returns:
 *   { enabled, permission, supported, toggle(), notify(title, opts) }
 */

const STORAGE_KEY = 'notifications.enabled';

const getInitialEnabled = () => {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === null) return true; // opt-in by default
    return v === 'true';
  } catch { return true; }
};

const SUPPORTED = typeof window !== 'undefined' && 'Notification' in window;

export function useBrowserNotifications() {
  const [enabled, setEnabled] = useState(getInitialEnabled);
  const [permission, setPermission] = useState(SUPPORTED ? Notification.permission : 'denied');
  const visibleRef = useRef(typeof document !== 'undefined' ? !document.hidden : true);

  // Track tab visibility — notifications skipped when tab is visible
  useEffect(() => {
    if (typeof document === 'undefined') return undefined;
    const onVisibility = () => { visibleRef.current = !document.hidden; };
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, []);

  // Persist preference
  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, String(enabled)); } catch { /* swallow */ }
  }, [enabled]);

  const requestPermission = useCallback(async () => {
    if (!SUPPORTED) return 'denied';
    if (Notification.permission !== 'default') {
      setPermission(Notification.permission);
      return Notification.permission;
    }
    try {
      const p = await Notification.requestPermission();
      setPermission(p);
      return p;
    } catch {
      return 'denied';
    }
  }, []);

  const toggle = useCallback(async () => {
    const next = !enabled;
    setEnabled(next);
    if (next && SUPPORTED && Notification.permission === 'default') {
      await requestPermission();
    }
  }, [enabled, requestPermission]);

  const notify = useCallback((title, opts = {}) => {
    if (!enabled || !SUPPORTED) return;
    if (visibleRef.current) return; // user is already on the dashboard
    if (Notification.permission !== 'granted') {
      // Best-effort: try to request once, if user pressed allow we'll have it next time.
      if (Notification.permission === 'default') requestPermission();
      return;
    }
    try {
      new Notification(title, {
        icon: '/vite.svg',
        badge: '/vite.svg',
        ...opts,
      });
    } catch (err) {
      console.warn('[notif] failed:', err.message);
    }
  }, [enabled, requestPermission]);

  return { enabled, permission, supported: SUPPORTED, toggle, notify };
}