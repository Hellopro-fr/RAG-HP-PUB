import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Hero } from '@/components/conseil/Hero';

vi.mock('next/image', () => ({
  default: ({ src, alt, ...props }: { src: string; alt: string; [key: string]: unknown }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} {...props} />
  ),
}));

const BASE_HERO = { title: 'Guide complet sur les conteneurs de stockage' };

describe('Hero', () => {
  it('affiche le titre de la page', () => {
    render(<Hero data={BASE_HERO} pageType="prix" />);
    expect(screen.getByRole('heading', { level: 1 })).toBeDefined();
    expect(screen.getByText(BASE_HERO.title)).toBeDefined();
  });

  it("n'affiche pas le bloc résumé quand resume est vide et pas de resumeHtml", () => {
    render(<Hero data={BASE_HERO} pageType="prix" resume={[]} />);
    expect(screen.queryByText(/essentiel à retenir/i)).toBeNull();
  });

  it('affiche KeyTakeaways quand des items resume sont fournis', () => {
    render(
      <Hero
        data={BASE_HERO}
        pageType="prix"
        resumeTitle="L'essentiel à retenir"
        resume={[
          { label: 'Coût', text: 'entre 200 et 500 €' },
          { label: 'Durée', text: '3 à 5 jours' },
        ]}
      />
    );
    expect(screen.getByText("L'essentiel à retenir")).toBeDefined();
    expect(screen.getByText(/Coût/)).toBeDefined();
  });

  it('affiche KeyTakeaways avec HTML brut quand resumeHtml est fourni', () => {
    render(
      <Hero
        data={BASE_HERO}
        pageType="prix"
        resumeTitle="L'essentiel à retenir"
        resumeHtml="<ul><li>Coût : entre 200 et 500 €</li><li>Durée : 3 jours</li></ul>"
      />
    );
    expect(screen.getByText("L'essentiel à retenir")).toBeDefined();
    expect(screen.getByText(/Coût : entre 200 et 500 €/i)).toBeDefined();
  });

  it('utilise resumeTitle comme titre du bloc résumé quand fourni', () => {
    render(
      <Hero
        data={BASE_HERO}
        pageType="prix"
        resumeTitle="Points clés à retenir"
        resumeHtml="<ul><li>Délai : 3 semaines</li></ul>"
      />
    );
    expect(screen.getByText('Points clés à retenir')).toBeDefined();
    expect(screen.queryByText(/essentiel à retenir/i)).toBeNull();
  });

  it("n'affiche pas de titre quand resumeTitle n'est pas fourni", () => {
    render(
      <Hero
        data={BASE_HERO}
        pageType="prix"
        resume={[{ label: 'Coût', text: '200 €' }]}
      />
    );
    expect(screen.queryByText(/essentiel à retenir/i)).toBeNull();
  });

  it('resumeHtml est prioritaire sur items vides', () => {
    render(
      <Hero
        data={BASE_HERO}
        pageType="prix"
        resume={[]}
        resumeHtml="<p>Résumé en HTML</p>"
      />
    );
    expect(screen.queryByText(/essentiel à retenir/i)).toBeNull();
    expect(screen.getByText('Résumé en HTML')).toBeDefined();
  });

  it('affiche le slot droit passé en prop', () => {
    render(
      <Hero
        data={BASE_HERO}
        pageType="prix"
        slot={<div data-testid="custom-slot">Formulaire devis</div>}
      />
    );
    expect(screen.getByTestId('custom-slot')).toBeDefined();
  });

  it('affiche le breadcrumb quand fourni', () => {
    render(
      <Hero
        data={BASE_HERO}
        pageType="prix"
        breadcrumb={[
          { label: 'Accueil', href: 'https://www.hellopro.fr' },
          { label: 'Conseils' },
        ]}
      />
    );
    expect(screen.getByRole('navigation', { name: /fil d.ariane/i })).toBeDefined();
    expect(screen.getByText('Accueil')).toBeDefined();
  });

  it('affiche "Voir plus" quand il y a plus de 2 items', () => {
    render(
      <Hero
        data={BASE_HERO}
        pageType="prix"
        resume={[
          { label: 'A', text: 'texte A' },
          { label: 'B', text: 'texte B' },
          { label: 'C', text: 'texte C' },
        ]}
      />
    );
    const btn = screen.getByText(/voir plus/i);
    expect(btn).toBeDefined();
    fireEvent.click(btn);
    expect(screen.getByText('texte C')).toBeDefined();
  });

  it("affiche l'estimation de prix quand pageType=prix et estimation présente", () => {
    render(
      <Hero
        data={{ ...BASE_HERO, estimation: { min: 200, max: 500, unit: '€' } }}
        pageType="prix"
      />
    );
    expect(screen.getByText(/estimation de prix/i)).toBeDefined();
    expect(screen.getByText(/200/)).toBeDefined();
    expect(screen.getByText(/500/)).toBeDefined();
  });
});
