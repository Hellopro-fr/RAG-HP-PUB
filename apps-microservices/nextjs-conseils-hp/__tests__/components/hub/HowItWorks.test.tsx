import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HowItWorks } from '@/components/hub/HowItWorks';
import { listHubPages } from '@/data/hub';

const data = listHubPages()[0].howItWorks;

describe('HowItWorks', () => {
  it('porte l’ancre du sommaire', () => {
    const { container } = render(<HowItWorks data={data} />);
    expect(container.querySelector('section#comment-ca-marche')).not.toBeNull();
  });

  /**
   * Section de SERVICE : hors du plan de titres depuis l'arbitrage SEO du
   * 2026-08-07. Le libellé reste affiché avec la même apparence, mais aucun
   * élément de ce composant ne doit être un heading — sans quoi il réapparaîtrait
   * dans l'outline de la page.
   */
  it('rend le titre de section sans en faire un heading', () => {
    render(<HowItWorks data={data} />);
    expect(screen.getByText(data.title)).toBeDefined();
    expect(screen.queryAllByRole('heading')).toHaveLength(0);
  });

  /**
   * RÉGRESSION : le numéro avait été sorti du titre pour devenir un gros chiffre
   * décoratif à côté de l'icône. L'ordre doit rester porté par le texte lui-même,
   * lisible tel quel.
   */
  it('préfixe chaque étape par son numéro', () => {
    render(<HowItWorks data={data} />);
    data.steps.forEach((step, index) => {
      expect(screen.getByText(`${index + 1}. ${step.title}`)).toBeDefined();
    });
  });

  it('rend une liste ordonnée d’autant d’éléments que d’étapes', () => {
    const { container } = render(<HowItWorks data={data} />);
    expect(container.querySelector('ol')).not.toBeNull();
    expect(container.querySelectorAll('ol > li')).toHaveLength(data.steps.length);
  });

  it('rend la description de chaque étape', () => {
    render(<HowItWorks data={data} />);
    for (const step of data.steps) {
      expect(screen.getByText(step.desc)).toBeDefined();
    }
  });

  /** n étapes → n-1 séparateurs, et ils ne doivent pas être annoncés. */
  it('intercale un chevron décoratif entre les étapes, jamais après la dernière', () => {
    const { container } = render(<HowItWorks data={data} />);
    const separators = container.querySelectorAll('li > [aria-hidden="true"]');
    expect(separators).toHaveLength(data.steps.length - 1);
  });

  it('n’intercale aucun chevron avec une seule étape', () => {
    const { container } = render(
      <HowItWorks data={{ ...data, steps: [data.steps[0]] }} />
    );
    expect(container.querySelectorAll('li > [aria-hidden="true"]')).toHaveLength(0);
  });
});
