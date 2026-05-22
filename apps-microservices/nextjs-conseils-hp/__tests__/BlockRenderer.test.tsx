import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { BlockRenderer } from '@/components/conseil/BlockRenderer';
import type { ConseilBlock } from '@/types/conseils';

describe('BlockRenderer', () => {
  it('rend un placeholder pour un bloc h2 (Phase 4 — à implémenter)', () => {
    const block: ConseilBlock = {
      id: 'block-1',
      type: 'h2',
      order: 1,
      data: { text: 'Mon titre' },
    };
    render(<BlockRenderer block={block} />);
    expect(screen.getByText(/à implémenter/i)).toBeInTheDocument();
  });
});
