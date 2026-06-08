import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ProduitsBlock } from '@/components/conseil/blocks/ProduitsBlock';

const PRODUITS = [
  { id: '1', name: 'Monte-charge hydraulique compact', image: '/img/1.jpg', priceHt: 1379, url: 'https://www.hellopro.fr/1' },
  { id: '2', name: 'Monte-chariot et monte-fût - Transport', image: '/img/2.jpg', priceHt: null, url: 'https://www.hellopro.fr/2' },
  { id: '3', name: 'Monte-charge hydraulique compact', image: '/img/3.jpg', priceHt: 2500, url: 'https://www.hellopro.fr/3' }, // doublon
];

describe('ProduitsBlock', () => {
  it('renders nothing when no products', () => {
    const { container } = render(
      <ProduitsBlock data={{ productIds: [], produits: [] }} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders the titre', () => {
    render(
      <ProduitsBlock data={{ productIds: [], titre: 'Les produits populaires', produits: PRODUITS }} />
    );
    expect(screen.getByText('Les produits populaires')).toBeDefined();
  });

  it('uses fallback title when titre is absent', () => {
    render(<ProduitsBlock data={{ productIds: [], produits: PRODUITS }} />);
    expect(screen.getByRole('heading')).toBeDefined();
  });

  it('deduplicates products with identical name', () => {
    render(
      <ProduitsBlock data={{ productIds: [], titre: 'T', produits: PRODUITS }} />
    );
    // "Monte-charge hydraulique compact" dupliqué → 1 seule occurrence
    const cards = screen.getAllByText('Monte-charge hydraulique compact');
    expect(cards).toHaveLength(1);
  });

  it('formats price as "X € HT"', () => {
    render(<ProduitsBlock data={{ productIds: [], titre: 'T', produits: PRODUITS }} />);
    expect(screen.getByText('1 379 € HT')).toBeDefined();
  });

  it('shows "Prix sur demande" when priceHt is null', () => {
    render(<ProduitsBlock data={{ productIds: [], titre: 'T', produits: PRODUITS }} />);
    expect(screen.getByText('Prix sur demande')).toBeDefined();
  });
});
