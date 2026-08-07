import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AccompagnementSplit } from '@/components/hub/AccompagnementSplit';
import { listHubPages } from '@/data/hub';

vi.mock('next/image', () => ({
  default: ({ src, alt, ...props }: { src: string; alt: string; [key: string]: unknown }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} {...props} />
  ),
}));

const data = listHubPages()[0].accompagnement;

describe('AccompagnementSplit', () => {
  it('rend le titre et les points', () => {
    render(<AccompagnementSplit data={data} />);
    // Section de réassurance : hors du plan de titres depuis l'arbitrage SEO du
    // 2026-08-07. Le libellé s'affiche, mais ce n'est plus un heading.
    expect(screen.getByText(data.title)).toBeDefined();
    expect(screen.queryAllByRole('heading')).toHaveLength(0);
    for (const point of data.points) {
      expect(screen.getByText(point)).toBeDefined();
    }
  });

  /** Le texte de référence compte deux paragraphes : `text` accepte du HTML. */
  it('rend les deux paragraphes du texte', () => {
    const { container } = render(<AccompagnementSplit data={data} />);
    const paragraphs = container.querySelectorAll('div[class*="space-y-3"] p');
    expect(paragraphs.length).toBe(2);
  });

  it('assainit le texte', () => {
    const { container } = render(
      <AccompagnementSplit
        data={{ ...data, text: '<p>ok</p><script>alert(1)</script><a href="//evil">x</a>' }}
      />
    );
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('a')).toBeNull();
  });

  it('rend le visuel quand il est fourni', () => {
    render(<AccompagnementSplit data={data} />);
    expect(screen.getByAltText(data.image!.alt)).toBeDefined();
  });

  /** Sans visuel, la colonne texte doit s'élargir au lieu de laisser un vide. */
  it('élargit la colonne texte quand aucun visuel n’est fourni', () => {
    const { container } = render(<AccompagnementSplit data={{ ...data, image: undefined }} />);
    expect(container.querySelector('img')).toBeNull();
    expect(container.innerHTML).toContain('lg:col-span-8');
  });
});
