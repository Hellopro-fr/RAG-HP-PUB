import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CTABlock } from './CTABlock';

describe('CTABlock', () => {
  it('affiche le titre et le label du bouton', () => {
    render(<CTABlock data={{ title: 'Estimez votre projet', ctaLabel: 'Estimer maintenant' }} />);
    expect(screen.getByText('Estimez votre projet')).toBeDefined();
    expect(screen.getByText('Estimer maintenant')).toBeDefined();
  });

  it('affiche le subtitle quand présent', () => {
    render(<CTABlock data={{ title: 'Titre', subtitle: 'Sous-titre', ctaLabel: 'Action' }} />);
    expect(screen.getByText('Sous-titre')).toBeDefined();
  });

  it('rend un <a> quand ctaUrl est fourni', () => {
    const { container } = render(
      <CTABlock data={{ title: 'Titre', ctaLabel: 'Cliquer', ctaUrl: 'https://hellopro.fr' }} />
    );
    const link = container.querySelector('a[href="https://hellopro.fr"]');
    expect(link).toBeTruthy();
  });

  it('rend un <button> quand ctaUrl est absent', () => {
    const { container } = render(
      <CTABlock data={{ title: 'Titre', ctaLabel: 'Cliquer' }} />
    );
    expect(container.querySelector('button')).toBeTruthy();
    expect(container.querySelector('a')).toBeNull();
  });
});
