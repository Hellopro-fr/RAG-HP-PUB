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

  it('rend le titre de section', () => {
    render(<HowItWorks data={data} />);
    expect(screen.getByRole('heading', { level: 2 }).textContent).toBe(data.title);
  });

  /**
   * RÉGRESSION : le numéro avait été sorti du titre pour devenir un gros chiffre
   * décoratif à côté de l'icône. L'ordre doit être porté par le texte du titre,
   * lisible tel quel — y compris à la navigation par titres.
   */
  it('préfixe chaque titre par son numéro d’étape', () => {
    render(<HowItWorks data={data} />);
    data.steps.forEach((step, index) => {
      expect(
        screen.getByRole('heading', { level: 3, name: `${index + 1}. ${step.title}` })
      ).toBeDefined();
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
