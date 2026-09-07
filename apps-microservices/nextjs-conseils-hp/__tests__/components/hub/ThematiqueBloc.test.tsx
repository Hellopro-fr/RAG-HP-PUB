import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThematiqueBloc } from '@/components/hub/ThematiqueBloc';
import type { HubThematique } from '@/types/hub';

vi.mock('next/image', () => ({
  default: ({ src, alt, ...props }: { src: string; alt: string; [key: string]: unknown }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} {...props} />
  ),
}));

const IMAGE = { src: '/images/hub/x/a.jpg', alt: 'Visuel A' };

function base(overrides: Partial<HubThematique> = {}): HubThematique {
  return {
    id: 'bloc-test',
    tag: 'Rubrique test',
    layout: 'grid',
    cards: [{ title: 'Carte 1' }, { title: 'Carte 2' }],
    ...overrides,
  };
}

describe('ThematiqueBloc', () => {
  it('porte son id comme ancre de section', () => {
    const { container } = render(<ThematiqueBloc data={base()} />);
    expect(container.querySelector('section#bloc-test')).not.toBeNull();
  });

  it('affiche le tag et l’intro', () => {
    render(<ThematiqueBloc data={base({ intro: 'Une introduction.' })} />);
    expect(screen.getByText('Rubrique test')).toBeDefined();
    expect(screen.getByText('Une introduction.')).toBeDefined();
  });

  it('rend toutes les cartes en layout grid', () => {
    render(<ThematiqueBloc data={base()} />);
    expect(screen.getByText('Carte 1')).toBeDefined();
    expect(screen.getByText('Carte 2')).toBeDefined();
  });

  /**
   * Invariant SEO : le carrousel est en scroll-snap CSS, sans JavaScript. Les
   * cartes hors écran doivent donc TOUTES être dans le HTML initial — c'est la
   * raison d'avoir écarté embla-carousel.
   */
  it('rend toutes les cartes du carrousel dans le DOM', () => {
    const cards = Array.from({ length: 7 }, (_, i) => ({ title: `Article ${i + 1}` }));
    render(<ThematiqueBloc data={base({ layout: 'carousel', cards })} />);
    for (const card of cards) {
      expect(screen.getByText(card.title)).toBeDefined();
    }
  });

  /**
   * Les chiffres clés sont mis en gras au milieu des puces et de l'intro : ces
   * champs acceptent donc du HTML restreint, toujours assaini.
   */
  it('rend le gras des puces et de l’intro de l’overlay', () => {
    render(
      <ThematiqueBloc
        data={base({
          layout: 'overlay-left',
          overlay: {
            title: 'T',
            intro: 'Calculée selon le <strong>nombre de poules</strong>.',
            bullets: ['Au moins <strong>4 m²</strong> par poule'],
          },
        })}
      />
    );
    expect(screen.getByText('nombre de poules').tagName).toBe('STRONG');
    expect(screen.getByText('4 m²').tagName).toBe('STRONG');
  });

  it('assainit le HTML des puces et de l’intro de l’overlay', () => {
    const { container } = render(
      <ThematiqueBloc
        data={base({
          layout: 'overlay-left',
          overlay: {
            title: 'T',
            intro: 'ok<script>alert(1)</script>',
            bullets: ['<a href="//evil">lien</a>'],
          },
        })}
      />
    );
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('a[href="//evil"]')).toBeNull();
  });

  it('rend l’overlay et ses puces en layout overlay-left', () => {
    render(
      <ThematiqueBloc
        data={base({
          layout: 'overlay-left',
          overlay: { title: 'Titre overlay', image: IMAGE, bullets: ['Puce A', 'Puce B'] },
        })}
      />
    );
    expect(screen.getByText('Titre overlay')).toBeDefined();
    expect(screen.getByText('Puce A')).toBeDefined();
    expect(screen.getByAltText('Visuel A')).toBeDefined();
  });

  it('rend l’overlay sans image sans casser (visuel non livré)', () => {
    render(
      <ThematiqueBloc
        data={base({
          layout: 'overlay-right',
          overlay: { title: 'Sans visuel', bullets: ['Puce'] },
        })}
      />
    );
    expect(screen.getByText('Sans visuel')).toBeDefined();
    expect(screen.queryByRole('img')).toBeNull();
  });

  it('affiche le bouton guide quand il est déclaré', () => {
    render(
      <ThematiqueBloc
        data={base({
          layout: 'overlay-left',
          overlay: { title: 'T', bullets: [] },
          guideButtonLabel: 'Télécharger le guide',
        })}
      />
    );
    expect(screen.getByText('Télécharger le guide')).toBeDefined();
  });

  it('n’affiche pas de bouton guide quand il n’est pas déclaré', () => {
    render(
      <ThematiqueBloc
        data={base({ layout: 'overlay-left', overlay: { title: 'T', bullets: [] } })}
      />
    );
    expect(screen.queryByText('Télécharger le guide')).toBeNull();
  });

  /**
   * RÉGRESSION : le CTA de la carte overlay et la ligne « Lire l'article » des
   * cartes info avaient été oubliés au portage. Deux éléments visibles et
   * cliquables absents du rendu.
   */
  it('rend le CTA de la carte overlay quand ctaLabel est déclaré', () => {
    render(
      <ThematiqueBloc
        data={base({
          layout: 'overlay-left',
          overlay: { title: 'T', bullets: ['b'], ctaLabel: 'Lire la suite' },
        })}
      />
    );
    expect(screen.getByRole('button', { name: /Lire la suite/i })).toBeDefined();
  });

  it('n’affiche pas de CTA overlay sans ctaLabel', () => {
    render(
      <ThematiqueBloc
        data={base({ layout: 'overlay-left', overlay: { title: 'T', bullets: ['b'] } })}
      />
    );
    expect(screen.queryByRole('button', { name: /Lire la suite/i })).toBeNull();
  });

  it('rend la ligne de lien des cartes info quand linkLabel est déclaré', () => {
    render(
      <ThematiqueBloc
        data={base({
          layout: 'overlay-left',
          overlay: { title: 'T', bullets: [] },
          cards: [
            { title: 'Carte A', linkLabel: "Lire l'article" },
            { title: 'Carte B', linkLabel: "Lire l'article" },
          ],
        })}
      />
    );
    expect(screen.getAllByRole('button', { name: /Lire l’article|Lire l'article/i })).toHaveLength(2);
  });

  it('n’affiche pas de ligne de lien sans linkLabel', () => {
    render(<ThematiqueBloc data={base({ cards: [{ title: 'Sans lien' }] })} />);
    expect(screen.queryByRole('button', { name: /Lire l’article|Lire l'article/i })).toBeNull();
  });

  /**
   * ⚠️ Layout `overlay-*` OBLIGATOIRE ici, et pas le `grid` de `base()` : seules
   * les cartes latérales des layouts overlay (`InfoCard`) rendent une
   * description. Les cartes de `grid`/`carousel` (`ArticleCard`) n'affichent que
   * le visuel, le titre et le lien — c'est l'invariant que `registry.test.ts`
   * fait respecter côté données. Ces deux tests visaient donc une combinaison
   * qui n'existe pas, et échouaient sur « Unable to find an element with the
   * text ».
   */
  it('rend descriptionHtml en HTML et description en texte', () => {
    render(
      <ThematiqueBloc
        data={base({
          layout: 'overlay-left',
          overlay: { title: 'T', bullets: [] },
          cards: [
            { title: 'HTML', descriptionHtml: 'Apport de <strong>20 %</strong>.' },
            { title: 'Texte', description: 'Description simple.' },
          ],
        })}
      />
    );
    expect(screen.getByText('20 %').tagName).toBe('STRONG');
    expect(screen.getByText('Description simple.')).toBeDefined();
  });

  /**
   * Carte entièrement cliquable (2026-09-03) — « lien étiré ».
   *
   * L'overlay est un pseudo-élément du `<a>`, invisible pour jsdom : on ne peut
   * pas simuler le clic dans un coin de la carte. Ce test verrouille donc les
   * DEUX conditions dont dépend le procédé, et c'est justement là qu'une
   * régression se glisserait sans bruit :
   *
   * 1. le lien porte `after:absolute after:inset-0` ;
   * 2. la carte porteuse est `relative`.
   *
   * Perdre (2) ne casse RIEN visiblement : l'overlay remonte simplement jusqu'au
   * premier ancêtre positionné et rend cliquable une zone bien plus large que la
   * carte. Aucune erreur, aucun test rouge — d'où celui-ci.
   */
  it.each([
    ['overlay-left' as const, 'Lire la suite'],
    ['grid' as const, 'Lire l’article'],
    ['carousel' as const, 'Lire l’article'],
  ])('rend la carte %s entièrement cliquable', (layout, label) => {
    const href = 'https://conseils.hellopro.fr/article-1-conseil.html';
    render(
      <ThematiqueBloc
        data={base({
          layout,
          overlay: { title: 'T', bullets: ['b'], ctaLabel: label, href },
          cards: [{ title: 'Carte A', href }],
        })}
      />
    );

    const link = screen.getByRole('link', { name: new RegExp(label, 'i') });
    expect(link.className).toContain('after:absolute');
    expect(link.className).toContain('after:inset-0');
    expect(link.closest('article')?.className).toContain('relative');
  });

  /** Même invariant pour les cartes latérales des layouts overlay (`InfoCard`). */
  it('rend la carte info latérale entièrement cliquable', () => {
    render(
      <ThematiqueBloc
        data={base({
          layout: 'overlay-left',
          overlay: { title: 'T', bullets: [] },
          cards: [
            {
              title: 'Carte A',
              linkLabel: 'Lire l’article',
              href: 'https://conseils.hellopro.fr/a-1-conseil.html',
            },
          ],
        })}
      />
    );
    const link = screen.getByRole('link', { name: /Lire l’article/i });
    expect(link.className).toContain('after:inset-0');
    expect(link.closest('article')?.className).toContain('relative');
  });

  /**
   * Corollaire du lien étiré : UN SEUL lien par carte. En ajouter un second
   * (ou un bouton) le placerait sous l'overlay, donc hors d'atteinte au clic.
   */
  it('ne rend qu’un seul lien par carte article', () => {
    const { container } = render(
      <ThematiqueBloc
        data={base({
          cards: [
            { title: 'A', href: 'https://conseils.hellopro.fr/a-1-conseil.html' },
            { title: 'B', href: 'https://conseils.hellopro.fr/b-2-conseil.html' },
          ],
        })}
      />
    );
    for (const article of container.querySelectorAll('article')) {
      expect(article.querySelectorAll('a, button')).toHaveLength(1);
    }
  });

  /** Le contenu vient de nos fichiers, mais la règle de sécurité est sans exception. */
  it('retire les balises dangereuses de descriptionHtml', () => {
    const { container } = render(
      <ThematiqueBloc
        data={base({
          // Layout overlay pour la même raison que le test précédent.
          layout: 'overlay-left',
          overlay: { title: 'T', bullets: [] },
          cards: [
            {
              title: 'XSS',
              descriptionHtml: 'Sûr <strong>ok</strong><script>alert(1)</script><a href="/x">lien</a>',
            },
          ],
        })}
      />
    );
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('a[href="/x"]')).toBeNull();
    expect(screen.getByText('ok').tagName).toBe('STRONG');
  });
});
