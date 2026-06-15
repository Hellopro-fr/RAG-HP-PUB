import { describe, it, expect, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/react';
import { GtmFooterScripts } from './GtmFooterScripts';

afterEach(() => {
  cleanup();
  // remove scripts hoisted to <head> by React 18
  document.querySelectorAll('head script[src]').forEach((s) => s.remove());
});

const BREADCRUMB = [
  { label: 'Accueil', href: 'https://conseils.hellopro.fr/' },
  { label: 'Bâtiment élevage', href: '/batiment-elevage' },
  { label: 'Bâtiment vaches laitières' },
];

describe('GtmFooterScripts', () => {
  // React 18 hoists <script async src="..."> to <head> — it's outside container
  it('rend 5 scripts inline + 1 script GA4 src hissé dans <head>', () => {
    const { container } = render(<GtmFooterScripts breadcrumb={BREADCRUMB} />);
    expect(container.querySelectorAll('script')).toHaveLength(5);
    expect(document.querySelector('script[src*="G-J3925VE86T"]')).toBeTruthy();
  });

  it('le premier script pousse page_template conseils', () => {
    const { container } = render(<GtmFooterScripts breadcrumb={BREADCRUMB} />);
    const scripts = container.querySelectorAll('script');
    expect(scripts[0].innerHTML).toContain('"page_template":"conseils"');
  });

  it('le deuxième script pousse user + catégories', () => {
    const { container } = render(<GtmFooterScripts breadcrumb={BREADCRUMB} />);
    const scripts = container.querySelectorAll('script');
    expect(scripts[1].innerHTML).toContain('visitorLoginState');
    expect(scripts[1].innerHTML).toContain('category5');
  });

  it('le troisième script charge GTM', () => {
    const { container } = render(<GtmFooterScripts breadcrumb={BREADCRUMB} />);
    const scripts = container.querySelectorAll('script');
    expect(scripts[2].innerHTML).toContain('GTM-PBBSTMC');
  });

  it('le quatrième script configure GA4', () => {
    const { container } = render(<GtmFooterScripts breadcrumb={BREADCRUMB} />);
    const scripts = container.querySelectorAll('script');
    expect(scripts[3].innerHTML).toContain("gtag('config'");
    expect(scripts[3].innerHTML).toContain('G-J3925VE86T');
  });

  it('le cinquième script pousse eec.impressionView et done', () => {
    const { container } = render(<GtmFooterScripts breadcrumb={BREADCRUMB} />);
    const scripts = container.querySelectorAll('script');
    expect(scripts[4].innerHTML).toContain('eec.impressionView');
    expect(scripts[4].innerHTML).toContain('"event":"done"');
    expect(scripts[4].innerHTML).toContain('"currencyCode":"EUR"');
  });

  it('construit category5 depuis le dernier élément du breadcrumb', () => {
    const { container } = render(<GtmFooterScripts breadcrumb={BREADCRUMB} />);
    const scripts = container.querySelectorAll('script');
    expect(scripts[1].innerHTML).toContain('Bâtiment-vaches-laitières');
  });
});
