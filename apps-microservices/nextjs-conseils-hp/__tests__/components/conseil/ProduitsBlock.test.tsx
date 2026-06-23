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
    // Titre rendu en <p> (balise simple, pas un heading) → on vérifie le texte de repli.
    expect(screen.getByText(/Les produits les plus populaires/i)).toBeDefined();
  });


  it('formats price as "X € HT"', () => {
    render(<ProduitsBlock data={{ productIds: [], titre: 'T', produits: PRODUITS }} />);
    expect(screen.getByText('1 379 € HT')).toBeDefined();
  });

  it('shows "Prix sur demande" when priceHt is null', () => {
    render(<ProduitsBlock data={{ productIds: [], titre: 'T', produits: PRODUITS }} />);
    expect(screen.getByText('Prix sur demande')).toBeDefined();
  });

  it('injecte le script prod_intern_gtm avec les données GTM', () => {
    const gtmProduits = [
      { id: '11454124', name: 'Produit A', image: '/img/a.jpg', priceHt: null, url: '/a',
        brand: 'Marque A', category: '1002121', variant: 'cert' },
    ];
    const { container } = render(
      <ProduitsBlock data={{ productIds: [], produits: gtmProduits }} />
    );
    const script = container.querySelector('script');
    expect(script?.innerHTML).toContain('prod_intern_gtm[1]');
    expect(script?.innerHTML).toContain('"id": "11454124"');
    expect(script?.innerHTML).toContain('"category": "1002121"');
    expect(script?.innerHTML).toContain('"variant": "cert"');
    expect(script?.innerHTML).toContain('"list": "lien interne"');
    expect(script?.innerHTML).toContain('"position": 1');
  });
});
