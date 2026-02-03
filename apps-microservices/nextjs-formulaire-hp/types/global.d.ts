// Global type declarations for analytics libraries

export {};

declare global {
  interface Window {
    // Google Tag Manager dataLayer
    dataLayer: Record<string, unknown>[];
    // Google Analytics gtag
    gtag: (...args: unknown[]) => void;
    // Hotjar
    hj: (...args: unknown[]) => void;
  }
}
