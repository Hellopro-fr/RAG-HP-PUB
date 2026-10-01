import '@testing-library/jest-dom/vitest';

// jsdom n'expose pas ResizeObserver — react-window v2 le détecte par typeof
// mais d'autres libs (radix tooltip etc.) peuvent le réclamer. Polyfill no-op.
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// jsdom n'implémente pas window.matchMedia — polyfill no-op utilisé par useIsMobile.
// Toujours retourner matches=false (desktop par défaut) dans les tests.
if (typeof globalThis.window !== 'undefined' && typeof globalThis.window.matchMedia === 'undefined') {
  globalThis.window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

