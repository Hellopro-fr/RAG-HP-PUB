import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { ProduitsBlock } from './ProduitsBlock';
import type { ProduitsBlockData } from '@/types/blocks/produits';

const DATA: ProduitsBlockData = {
  titre: 'Produits test',
  productIds: ['1', '2'],
  produits: [
    { id: '1', name: 'Produit A', url: '/a', image: '/a.jpg', brand: 'A', category: 'cat', variant: 'std', priceHt: 100 },
    { id: '2', name: 'Produit B', url: '/b', image: '/b.jpg', brand: 'B', category: 'cat', variant: 'cert', priceHt: null },
  ],
};

describe('ProduitsBlock', () => {
  it('rend les cartes produits', () => {
    const { getAllByRole } = render(<ProduitsBlock data={DATA} />);
    expect(getAllByRole('link').length).toBeGreaterThanOrEqual(2);
  });

  it('retourne null si aucun produit', () => {
    const { container } = render(<ProduitsBlock data={{ titre: '', productIds: [], produits: [] }} />);
    expect(container.firstChild).toBeNull();
  });
});
