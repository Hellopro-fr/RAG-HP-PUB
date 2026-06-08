import { describe, it, expect } from 'vitest';
import type { ProduitsBlockData, ProductItem } from '@/types/blocks/produits';

describe('ProduitsBlockData', () => {
  it('accepts empty produits array', () => {
    const data: ProduitsBlockData = { productIds: [], produits: [] };
    expect(data.produits).toHaveLength(0);
  });

  it('accepts optional titre', () => {
    const data: ProduitsBlockData = {
      productIds: ['1'],
      titre: 'Les produits les plus populaires',
      produits: [],
    };
    expect(data.titre).toBe('Les produits les plus populaires');
  });

  it('ProductItem accepts null priceHt', () => {
    const item: ProductItem = {
      id: '42',
      name: 'Monte-charge hydraulique',
      image: 'https://cdn.hellopro.fr/vignette.jpg',
      priceHt: null,
      url: 'https://www.hellopro.fr/produit/42',
    };
    expect(item.priceHt).toBeNull();
  });

  it('ProductItem accepts numeric priceHt', () => {
    const item: ProductItem = {
      id: '1',
      name: 'Monte-charge de montage',
      image: 'https://cdn.hellopro.fr/img.jpg',
      priceHt: 1379,
      url: 'https://www.hellopro.fr/produit/1',
    };
    expect(item.priceHt).toBe(1379);
  });
});
