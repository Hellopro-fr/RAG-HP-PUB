import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { H3Block } from '@/components/conseil/blocks/H3Block';

describe('H3Block', () => {
  it('renders the title', () => {
    render(<H3Block data={{ title: 'Sous-titre' }} />);
    expect(screen.getByText('Sous-titre')).toBeDefined();
  });

  it('renders as an h3 element', () => {
    const { container } = render(<H3Block data={{ title: 'Titre H3' }} />);
    expect(container.querySelector('h3')).toBeDefined();
  });
});
