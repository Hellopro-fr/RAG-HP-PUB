import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { H2Block } from '@/components/conseil/blocks/H2Block';

describe('H2Block', () => {
  it('renders the title', () => {
    render(<H2Block data={{ id: 'sec-1', title: 'Mon titre' }} />);
    expect(screen.getByText('Mon titre')).toBeDefined();
  });

  it('renders intro when provided', () => {
    render(<H2Block data={{ id: 'sec-2', title: 'Titre', intro: 'Intro texte' }} />);
    expect(screen.getByText('Intro texte')).toBeDefined();
  });

  it('does not render intro when absent', () => {
    render(<H2Block data={{ id: 'sec-3', title: 'Titre' }} />);
    expect(screen.queryByText('Intro texte')).toBeNull();
  });

  it('sets the section id for anchor navigation', () => {
    const { container } = render(<H2Block data={{ id: 'mon-ancre', title: 'Titre' }} />);
    expect(container.querySelector('#mon-ancre')).toBeDefined();
  });
});
