import '@testing-library/jest-dom/vitest';

/**
 * Bouchons des API navigateur que jsdom n'implémente pas.
 *
 * Sans eux, tout composant qui observe le défilement plante au montage sur
 * `ReferenceError: IntersectionObserver is not defined` — le test ne teste alors
 * plus rien, il échoue avant le premier `expect`. Neuf composants du service sont
 * concernés (`HubSectionNav`, `StickyCta`, `CardCarousel`, `HubCardCarousel`,
 * `AssistantForm`, `HubTemplate`, plus `StickyCtaBar`, `HeroQuoteForm`,
 * `QuoteFormBlock` et `VideoEmbed` côté conseils).
 *
 * Quatre tests conseils bouchonnaient déjà l'API chacun de leur côté ; leurs
 * définitions locales continuent de primer, elles s'appliquent après ce fichier.
 *
 * ⚠️ Ces bouchons N'OBSERVENT RIEN : le callback n'est jamais appelé. Ils
 * permettent au composant de se monter, pas de simuler une entrée dans le
 * viewport. Un test qui a besoin de déclencher l'observateur doit garder son
 * propre espion — c'est ce que fait `StickyCtaBar.test.tsx`.
 */
class NoopObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords(): [] {
    return [];
  }
  readonly root = null;
  readonly rootMargin = '';
  readonly thresholds: readonly number[] = [];
}

const g = globalThis as unknown as Record<string, unknown>;

if (!g.IntersectionObserver) g.IntersectionObserver = NoopObserver;
if (!g.ResizeObserver) g.ResizeObserver = NoopObserver;

/**
 * `matchMedia` manque aussi à jsdom. Réponse fixe « ne correspond pas » : les
 * composants retombent sur leur rendu par défaut, celui du mobile-first.
 */
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

/**
 * jsdom n'implémente pas le défilement et journalise une erreur à chaque appel.
 * Les carrousels et le sommaire ancré en font un usage normal.
 */
if (!window.scrollTo) {
  window.scrollTo = (() => {}) as typeof window.scrollTo;
}
Element.prototype.scrollIntoView ??= function scrollIntoView() {};
