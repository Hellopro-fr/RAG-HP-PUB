import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AuthorBlock } from '@/components/conseil/AuthorBlock';

const mockAuthor = {
  name: 'Sophie Martin',
  role: 'Experte achats',
  bio: 'Spécialiste des marchés B2B avec 10 ans d\'expérience dans le secteur industriel.',
  linkedinUrl: 'https://linkedin.com/in/sophie-martin',
  contactEmail: 'sophie@hellopro.fr',
};

describe('AuthorBlock', () => {
  it('renders author name and role', () => {
    render(<AuthorBlock author={mockAuthor} />);
    expect(screen.getByText(/Sophie Martin/)).toBeDefined();
    expect(screen.getByText(/Experte achats/)).toBeDefined();
  });

  it('renders bio text', () => {
    render(<AuthorBlock author={mockAuthor} />);
    expect(screen.getByText(/Spécialiste des marchés B2B/)).toBeDefined();
  });

  it('renders LinkedIn link when provided', () => {
    render(<AuthorBlock author={mockAuthor} />);
    expect(screen.getByText('LinkedIn')).toBeDefined();
  });

  it('renders contact link when email provided', () => {
    render(<AuthorBlock author={mockAuthor} />);
    expect(screen.getByText(/Contacter Sophie/)).toBeDefined();
  });

  it('renders avatar placeholder when no photo', () => {
    render(<AuthorBlock author={mockAuthor} />);
    expect(screen.getByText('S')).toBeDefined();
  });
});
