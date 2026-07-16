import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Crossell } from '@/components/conseil/Crossell';
import type { ConseilAssocie } from '@/types/conseils';

vi.mock('@/components/conseil/CitedProductsCarousel', () => ({
  CitedProductsCarousel: () => <div data-testid="cited-products" />,
}));

const mockAssocies: ConseilAssocie[] = [
  { id: '1181', titre: 'Comment fonctionne un treuil ?', url: 'https://conseils.hellopro.fr/comment-fonctionne-un-treuil-1181.html', idTag: 0 },
  { id: '892', titre: 'Top fabricants portes industrielles', url: 'https://conseils.hellopro.fr/top-fabricants-portes-892.html', idTag: 2 },
  { id: '500', titre: 'Prix d\'une installation', url: 'https://conseils.hellopro.fr/prix-installation-500.html', idTag: 1 },
];

describe('Crossell', () => {
  it('renders nothing when no conseilsAssocies', () => {
    const { container } = render(<Crossell />);
    expect(screen.queryByText('Pour aller plus loin')).toBeNull();
    expect(container.querySelector('section')).toBeDefined();
  });

  it('renders "Pour aller plus loin" section with articles', () => {
    render(<Crossell conseilsAssocies={mockAssocies} />);
    expect(screen.getByText('Pour aller plus loin')).toBeDefined();
    expect(screen.getByText('Comment fonctionne un treuil ?')).toBeDefined();
    expect(screen.getByText('Top fabricants portes industrielles')).toBeDefined();
  });

  it('links each article to its URL', () => {
    render(<Crossell conseilsAssocies={mockAssocies} />);
    const link = screen.getByText('Comment fonctionne un treuil ?').closest('a')!;
    expect(link.getAttribute('href')).toBe('https://conseils.hellopro.fr/comment-fonctionne-un-treuil-1181.html');
  });

  it('displays correct tag label per idTag', () => {
    render(<Crossell conseilsAssocies={mockAssocies} />);
    expect(screen.getAllByText('Conseil').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Comparatif').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Guide').length).toBeGreaterThan(0);
  });

  it('falls back to Conseil tag for unknown idTag', () => {
    const unknown: ConseilAssocie[] = [
      { id: '9', titre: 'Article inconnu', url: '/article-inconnu-9.html', idTag: 99 },
    ];
    render(<Crossell conseilsAssocies={unknown} />);
    expect(screen.getByText('Conseil')).toBeDefined();
  });

  it('renders CitedProductsCarousel when liensIntexts provided', () => {
    const liens = [{ id: 1, type: 0 as const, photo: '', titre: 'Produit', description: '', url: '/p' }];
    render(<Crossell liensIntexts={liens} />);
    expect(screen.getByTestId('cited-products')).toBeDefined();
  });

  it('does not render CitedProductsCarousel when no liensIntexts', () => {
    render(<Crossell conseilsAssocies={mockAssocies} />);
    expect(screen.queryByTestId('cited-products')).toBeNull();
  });
});
