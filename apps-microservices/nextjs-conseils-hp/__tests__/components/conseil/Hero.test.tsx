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

  /**
   * TITRE DU BLOC RÉSUMÉ — arbitré le 2026-09-07.
   *
   * Ces trois tests attendaient un titre rendu depuis la prop `resumeTitle`.
   * `KeyTakeaways` ne rend AUCUN titre : celui-ci fait partie du HTML éditorial
   * envoyé par le BO (le texte qui précède le `<ul>`). Le rendre aussi depuis une
   * prop l'afficherait deux fois.
   *
   * La prop `resumeTitle` est donc morte de bout en bout et part dans un commit
   * de nettoyage distinct. Les tests ci-dessous décrivent le comportement réel.
   */
  it('affiche les items du résumé, sans titre ajouté', () => {
    render(
      <Hero
        data={BASE_HERO}
        pageType="prix"
        resume={[
          { label: 'Coût', text: 'entre 200 et 500 €' },
          { label: 'Durée', text: '3 à 5 jours' },
        ]}
      />
    );
    expect(screen.getByText(/Coût/)).toBeDefined();
    expect(screen.getByText(/entre 200 et 500 €/)).toBeDefined();
  });

  it('rend le titre porté par le HTML du BO', () => {
    render(
      <Hero
        data={BASE_HERO}
        pageType="prix"
        resumeHtml="<p>L'essentiel à retenir</p><ul><li>Coût : entre 200 et 500 €</li><li>Durée : 3 jours</li></ul>"
      />
    );
    expect(screen.getByText("L'essentiel à retenir")).toBeDefined();
    expect(screen.getByText(/Coût : entre 200 et 500 €/i)).toBeDefined();
  });

  /**
   * Le corollaire, et la raison d'être du nettoyage à venir : fournir un titre
   * par la prop n'affiche rien. Si quelqu'un rebranche `resumeTitle` un jour, ce
   * test tombera et l'obligera à vérifier qu'il ne crée pas un titre en double
   * avec celui du HTML.
   */
  it('ignore la prop resumeTitle', () => {
    render(
      <Hero
        data={BASE_HERO}
        pageType="prix"
        resumeTitle="Points clés à retenir"
        resumeHtml="<ul><li>Délai : 3 semaines</li></ul>"
      />
    );
    expect(screen.getByText(/Délai : 3 semaines/)).toBeDefined();
    expect(screen.queryByText('Points clés à retenir')).toBeNull();
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

  /**
   * La prop unique `slot` a été scindée en `slotMobile` / `slotDesktop` : le
   * formulaire devis est rendu DEUX fois, la copie mobile portant le vrai `h2` et
   * la copie desktop un simple `p`, pour n'avoir qu'un seul `h2` dans le DOM. Ce
   * test suivait encore l'ancienne signature et faisait échouer `tsc` — donc
   * aussi tout `tsc && vitest`.
   *
   * Il vérifie maintenant les deux emplacements, puisque c'est précisément ce que
   * la scission a introduit : oublier d'en rendre un ne se verrait qu'à une
   * largeur d'écran donnée.
   */
  it('affiche les deux copies du slot formulaire', () => {
    render(
      <Hero
        data={BASE_HERO}
        pageType="prix"
        slotMobile={<div data-testid="slot-mobile">Formulaire devis</div>}
        slotDesktop={<div data-testid="slot-desktop">Formulaire devis</div>}
      />
    );
    expect(screen.getByTestId('slot-mobile')).toBeDefined();
    expect(screen.getByTestId('slot-desktop')).toBeDefined();
  });

  /** Chaque copie reste indépendante : n'en passer qu'une ne rend que celle-là. */
  it('n’invente pas la copie manquante', () => {
    render(
      <Hero
        data={BASE_HERO}
        pageType="prix"
        slotMobile={<div data-testid="slot-mobile">Formulaire devis</div>}
      />
    );
    expect(screen.getByTestId('slot-mobile')).toBeDefined();
    expect(screen.queryByTestId('slot-desktop')).toBeNull();
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
    /**
     * Le premier maillon est rendu en ICÔNE (maison) et non en texte : « Accueil »
     * n'existe plus que comme nom accessible. On l'interroge donc par le rôle, ce
     * qui vérifie au passage ce qui compte vraiment ici — qu'un lecteur d'écran
     * annonce toujours le maillon, malgré l'absence de libellé visible.
     */
    expect(screen.getByRole('link', { name: 'Accueil' })).toBeDefined();
    expect(screen.getByText('Conseils')).toBeDefined();
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
