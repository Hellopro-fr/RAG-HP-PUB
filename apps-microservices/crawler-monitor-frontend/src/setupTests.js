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

