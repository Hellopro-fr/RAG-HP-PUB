import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TextBlock } from './TextBlock';

describe('TextBlock', () => {
  it('affiche le contenu HTML', () => {
    render(<TextBlock data={{ html: '<p>Contenu texte</p>' }} />);
    expect(screen.getByText('Contenu texte')).toBeDefined();
  });

  it('préserve les balises ul et li dans le rendu', () => {
    const { container } = render(
      <TextBlock data={{ html: '<ul><li>Item 1</li><li>Item 2</li></ul>' }} />
    );
    expect(container.querySelectorAll('li')).toHaveLength(2);
    expect(container.querySelector('ul')).toBeTruthy();
  });

  it('affiche le badge estimation quand présent', () => {
    render(
      <TextBlock data={{ html: '<p>texte</p>', estimation: { value: '200 à 500 €', label: 'Estimation' } }} />
    );
    expect(screen.getByText('200 à 500 €')).toBeDefined();
  });

  it('ne rend pas le badge estimation quand absent', () => {
    const { container } = render(<TextBlock data={{ html: '<p>texte</p>' }} />);
    expect(container.querySelector('.bg-primary-soft')).toBeNull();
  });
});
