import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { CitedProductsCarousel } from './CitedProductsCarousel';
import type { LienInterne } from '@/types/conseils';

const ITEMS: LienInterne[] = [
  { id: '1', url: 'https://example.com/1', titre: 'Produit A', description: 'Desc A', photo: null, prix: '1 200 € HT' },
  { id: '2', url: 'https://example.com/2', titre: 'Produit B', description: 'Desc B', photo: null, prix: null },
];

describe('CitedProductsCarousel', () => {
  it('rend les cartes produits', () => {
    const { getAllByRole } = render(<CitedProductsCarousel items={ITEMS} />);
    expect(getAllByRole('link')).toHaveLength(2);
  });

  it('affiche le prix quand disponible', () => {
    const { getByText } = render(<CitedProductsCarousel items={ITEMS} />);
    expect(getByText('1 200 € HT')).toBeTruthy();
  });

  it('affiche "Sur devis" quand le prix est absent', () => {
    const { getByText } = render(<CitedProductsCarousel items={ITEMS} />);
    expect(getByText('Sur devis')).toBeTruthy();
  });

  it('le span prix/devis a la classe mt-auto', () => {
    const { container } = render(<CitedProductsCarousel items={ITEMS} />);
    const spans = container.querySelectorAll('.mt-auto');
    expect(spans.length).toBeGreaterThan(0);
  });
});
