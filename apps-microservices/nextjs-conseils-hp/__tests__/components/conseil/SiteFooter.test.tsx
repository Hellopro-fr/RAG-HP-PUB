import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SiteFooter } from '@/components/conseil/SiteFooter';

describe('SiteFooter', () => {
  it('renders the footer landmark', () => {
    render(<SiteFooter />);
    expect(screen.getByRole('contentinfo')).toBeDefined();
  });

  it('displays the HelloPro logo', () => {
    render(<SiteFooter />);
    expect(screen.getByAltText('HelloPro')).toBeDefined();
  });

  it('contains all 5 column headings', () => {
    render(<SiteFooter />);
    expect(screen.getByText(/pour les acheteurs/i)).toBeDefined();
    expect(screen.getByText(/pour les vendeurs/i)).toBeDefined();
    expect(screen.getByText(/à propos/i)).toBeDefined();
    expect(screen.getByText(/besoin d'aide/i)).toBeDefined();
    expect(screen.getByText(/informations légales/i)).toBeDefined();
  });

  it('has no placeholder # links', () => {
    render(<SiteFooter />);
    const links = screen.getAllByRole('link');
    const placeholders = links.filter((l) => l.getAttribute('href') === '#');
    expect(placeholders).toHaveLength(0);
  });
});
