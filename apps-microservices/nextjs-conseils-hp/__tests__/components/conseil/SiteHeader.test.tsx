import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SiteHeader } from '@/components/conseil/SiteHeader';

describe('SiteHeader', () => {
  it('renders the header landmark', () => {
    render(<SiteHeader />);
    expect(screen.getByRole('banner')).toBeDefined();
  });

  it('displays the HelloPro logo', () => {
    render(<SiteHeader />);
    expect(screen.getByAltText('HelloPro')).toBeDefined();
  });

  it('has correct "Devenir vendeur" link', () => {
    render(<SiteHeader />);
    const link = screen.getByText('Devenir vendeur').closest('a');
    expect(link?.getAttribute('href')).toBe(
      'https://www.hellopro.fr/online/page_fournisseur.php?utm_source=www.hellopro.fr'
    );
  });

  it('has correct "Mes demandes" link', () => {
    render(<SiteHeader />);
    const link = screen.getByText('Mes demandes').closest('a');
    expect(link?.getAttribute('href')).toBe('https://www.hellopro.fr/mhp/buyer/login?utm=mca');
  });
});
