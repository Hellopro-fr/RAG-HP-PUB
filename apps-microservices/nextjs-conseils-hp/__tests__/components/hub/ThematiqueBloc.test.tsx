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

  it('rend descriptionHtml en HTML et description en texte', () => {
    render(
      <ThematiqueBloc
        data={base({
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

  /** Le contenu vient de nos fichiers, mais la règle de sécurité est sans exception. */
  it('retire les balises dangereuses de descriptionHtml', () => {
    const { container } = render(
      <ThematiqueBloc
        data={base({
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
