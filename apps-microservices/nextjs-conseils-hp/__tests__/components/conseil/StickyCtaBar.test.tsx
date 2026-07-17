import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { StickyCtaBar } from '@/components/conseil/StickyCtaBar';
import type { CtaSticky } from '@/types/conseils';

const baseProps: CtaSticky = {
  wording: 'Obtenez vos devis gratuits',
  label_bouton: 'Faire une demande groupée (1 min)',
  eligible_ao: true,
};

/* IntersectionObserver mock */
let intersectionCallback: IntersectionObserverCallback;
const observeMock = vi.fn();
const disconnectMock = vi.fn();

beforeEach(() => {
  observeMock.mockClear();
  disconnectMock.mockClear();

  /* Crée l'élément trigger que le composant observe */
  const hero = document.createElement('section');
  hero.id = 'hero-trigger';
  document.body.appendChild(hero);

  class FakeIO {
    constructor(cb: IntersectionObserverCallback) { intersectionCallback = cb; }
    observe = observeMock;
    disconnect = disconnectMock;
  }
  vi.stubGlobal('IntersectionObserver', FakeIO);

  return () => hero.remove();
});

function triggerIntersection(isIntersecting: boolean) {
  act(() => {
    intersectionCallback([{ isIntersecting } as IntersectionObserverEntry], {} as IntersectionObserver);
  });
}

describe('StickyCtaBar', () => {
  it('est caché initialement puis visible après scroll hors hero', () => {
    render(<StickyCtaBar ctaSticky={baseProps} />);
    expect(screen.getByRole('region').className).toContain('translate-y-full');
    triggerIntersection(false);
    expect(screen.getByRole('region').className).not.toContain('translate-y-full');
  });

  it('redevient caché quand le hero redevient visible', () => {
    render(<StickyCtaBar ctaSticky={baseProps} />);
    triggerIntersection(false);
    triggerIntersection(true);
    expect(screen.getByRole('region').className).toContain('translate-y-full');
  });

  it('affiche le wording et le bouton CTA', () => {
    render(<StickyCtaBar ctaSticky={baseProps} />);
    expect(screen.getByText('Obtenez vos devis gratuits')).toBeDefined();
    expect(screen.getByRole('button')).toBeDefined();
  });

  it('dispatche hellopro:open-ao-form quand eligible_ao est vrai', () => {
    const listener = vi.fn();
    window.addEventListener('hellopro:open-ao-form', listener);
    render(<StickyCtaBar ctaSticky={baseProps} />);
    fireEvent.click(screen.getByRole('button'));
    expect(listener).toHaveBeenCalled();
    window.removeEventListener('hellopro:open-ao-form', listener);
  });

  it('redirige vers lien_redirection quand eligible_ao est faux', () => {
    const assignMock = vi.fn();
    vi.stubGlobal('location', { assign: assignMock });
    const props: CtaSticky = { ...baseProps, eligible_ao: false, lien_redirection: 'https://example.com' };
    render(<StickyCtaBar ctaSticky={props} />);
    fireEvent.click(screen.getByRole('button'));
    expect(assignMock).toHaveBeenCalledWith('https://example.com');
  });

  it('affiche le sous_titre si présent', () => {
    const props = { ...baseProps, sous_titre: 'Sans engagement · 100% gratuit' };
    render(<StickyCtaBar ctaSticky={props} />);
    expect(screen.getByText('Sans engagement · 100% gratuit')).toBeDefined();
  });
});
