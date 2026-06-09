import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { GtmFooterScripts } from './GtmFooterScripts';

const BREADCRUMB = [
  { label: 'Accueil', href: 'https://conseils.hellopro.fr/' },
  { label: 'Bâtiment élevage', href: '/batiment-elevage' },
  { label: 'Bâtiment vaches laitières' },
];

describe('GtmFooterScripts', () => {
  it('rend 6 balises script (page_template + user+cats + GTM + GA4×2 + impressions)', () => {
    const { container } = render(<GtmFooterScripts breadcrumb={BREADCRUMB} />);
    expect(container.querySelectorAll('script')).toHaveLength(6);
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

  it('le quatrième script charge GA4 (src async)', () => {
    const { container } = render(<GtmFooterScripts breadcrumb={BREADCRUMB} />);
    const scripts = container.querySelectorAll('script');
    expect(scripts[3].getAttribute('src')).toContain('G-J3925VE86T');
  });

  it('le cinquième script configure GA4', () => {
    const { container } = render(<GtmFooterScripts breadcrumb={BREADCRUMB} />);
    const scripts = container.querySelectorAll('script');
    expect(scripts[4].innerHTML).toContain("gtag('config'");
    expect(scripts[4].innerHTML).toContain('G-J3925VE86T');
  });

  it('le sixième script pousse eec.impressionView et done', () => {
    const { container } = render(<GtmFooterScripts breadcrumb={BREADCRUMB} />);
    const scripts = container.querySelectorAll('script');
    expect(scripts[5].innerHTML).toContain('eec.impressionView');
    expect(scripts[5].innerHTML).toContain('"event":"done"');
    expect(scripts[5].innerHTML).toContain('"currencyCode":"EUR"');
  });

  it('construit category5 depuis le dernier élément du breadcrumb', () => {
    const { container } = render(<GtmFooterScripts breadcrumb={BREADCRUMB} />);
    const scripts = container.querySelectorAll('script');
    expect(scripts[1].innerHTML).toContain('Bâtiment-vaches-laitières');
  });
});
