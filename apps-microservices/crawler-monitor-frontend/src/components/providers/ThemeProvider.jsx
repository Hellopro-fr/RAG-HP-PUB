import { createContext, useContext, useEffect, useState } from 'react';

/**
 * Theme system — light | dark | system (follows OS preference).
 * Persisted in localStorage under `theme` key. Applies .dark class on <html>.
 */

const ThemeContext = createContext({
  theme: 'system',
  setTheme: () => null,
  resolvedTheme: 'dark', // actual applied theme (light/dark) after resolving 'system'
});

const STORAGE_KEY = 'theme';

export function ThemeProvider({ children, defaultTheme = 'system' }) {
  const [theme, setThemeState] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === 'light' || stored === 'dark' || stored === 'system') return stored;
    } catch { /* swallow */ }
    return defaultTheme;
  });

  const [resolvedTheme, setResolvedTheme] = useState('dark');

  useEffect(() => {
    const root = document.documentElement;
    const apply = () => {
      const wantsDark =
        theme === 'dark' ||
        (theme === 'system' &&
          typeof window !== 'undefined' &&
          window.matchMedia('(prefers-color-scheme: dark)').matches);
      root.classList.toggle('dark', wantsDark);
      setResolvedTheme(wantsDark ? 'dark' : 'light');
    };
    apply();
    // If user picked 'system', respond to OS changes live.
    if (theme === 'system' && typeof window !== 'undefined') {
      const media = window.matchMedia('(prefers-color-scheme: dark)');
      media.addEventListener('change', apply);
      return () => media.removeEventListener('change', apply);
    }
    return undefined;
  }, [theme]);

  const setTheme = (next) => {
    try { localStorage.setItem(STORAGE_KEY, next); } catch { /* swallow */ }
    setThemeState(next);
  };

  return (
    <ThemeContext.Provider value={{ theme, setTheme, resolvedTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export const useTheme = () => useContext(ThemeContext);
