import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RessourcesGrid } from '@/components/hub/RessourcesGrid';
import type { HubRessources } from '@/types/hub';

vi.mock('next/image', () => ({
  default: ({ src, alt, ...props }: { src: string; alt: string; [key: string]: unknown }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} {...props} />
  ),
}));

const HREF = 'https://conseils.hellopro.fr/vente-oeufs-5301.html';

function base(overrides: Partial<HubRessources> = {}): HubRessources {
  return {
    title: 'Nos ressources',
    subtitle: 'Guides et conseils pratiques.',
    items: [{ title: 'Ressource A', tag: 'Exploitation', href: HREF }],
    ...overrides,
  };
}

describe('RessourcesGrid', () => {
  it('rend le titre, le chapeau et les items', () => {
    render(<RessourcesGrid data={base()} />);
    expect(screen.getByText('Nos ressources')).toBeDefined();
    expect(screen.getByText('Guides et conseils pratiques.')).toBeDefined();
    expect(screen.getByText('Ressource A')).toBeDefined();
  });

  /**
   * Carte entièrement cliquable (2026-09-03) — mêmes invariants que les cartes de
   * `ThematiqueBloc`, et pour les mêmes raisons. Le détail du procédé et de ses
   * pièges est dans `components/hub/stretchedLink.ts`.
   *
   * L'overlay est un pseudo-élément, invisible pour jsdom : on ne peut pas
   * simuler un clic dans un coin de la carte. On verrouille donc les deux
   * conditions dont il dépend — dont `relative`, dont l'absence ne casse rien de
   * visible mais étire la zone cliquable bien au-delà de la carte.
   */
  it('rend la carte ressource entièrement cliquable', () => {
    render(<RessourcesGrid data={base()} />);
    const link = screen.getByRole('link', { name: /En savoir plus/i });
    expect(link.className).toContain('after:absolute');
    expect(link.className).toContain('after:inset-0');
    expect(link.closest('article')?.className).toContain('relative');
  });

  /** Corollaire : un second élément interactif passerait sous l'overlay. */
  it('ne rend qu’un seul élément interactif par carte', () => {
    const { container } = render(
      <RessourcesGrid
        data={base({
          items: [
            { title: 'A', tag: 'Exploitation', href: HREF },
            { title: 'B', tag: 'Équipements', href: HREF },
          ],
        })}
      />
    );
    for (const article of container.querySelectorAll('article')) {
      expect(article.querySelectorAll('a, button')).toHaveLength(1);
    }
  });

  /**
   * ⚠️ Sans `href`, le repli est un `AssistantButton` qui OUVRE UN DIALOG. Il ne
   * doit jamais être étiré : un survol distrait deviendrait une ouverture de
   * questionnaire. Ce test est la garde de cette limite — c'est la seule chose
   * qui distingue le cas « navigue » du cas « déclenche ».
   */
  it('n’étire jamais le repli qui ouvre le questionnaire', () => {
    const { container } = render(
      <RessourcesGrid data={base({ items: [{ title: 'Sans lien', tag: 'Exploitation' }] })} />
    );
    expect(screen.queryByRole('link')).toBeNull();
    // Scopé à l'`<article>` : `HubCardCarousel` rend ses propres boutons de
    // navigation, qui arrivent avant dans le DOM.
    const trigger = container.querySelector('article button');
    expect(trigger).not.toBeNull();
    expect(trigger!.className).not.toContain('after:inset-0');
  });
});
