import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ProsConsBlock } from '@/components/conseil/blocks/ProsConsBlock';

const data = {
  labelPros: 'Avantages',
  labelCons: 'Inconvénients',
  pros: ['Facile à installer', 'Économique', 'Durable'],
  cons: ['Nécessite un entretien', 'Sensible aux chocs'],
};

describe('ProsConsBlock', () => {
  it('renders pros and cons headings', () => {
    render(<ProsConsBlock data={data} />);
    expect(screen.getByText('Avantages')).toBeDefined();
    expect(screen.getByText('Inconvénients')).toBeDefined();
  });

  it('renders all pros items', () => {
    render(<ProsConsBlock data={data} />);
    data.pros.forEach((p) => expect(screen.getByText(p)).toBeDefined());
  });

  it('renders all cons items', () => {
    render(<ProsConsBlock data={data} />);
    data.cons.forEach((c) => expect(screen.getByText(c)).toBeDefined());
  });

  it('falls back to default labels when labelPros/labelCons are absent', () => {
    render(<ProsConsBlock data={{ pros: ['A'], cons: ['B'] }} />);
    expect(screen.getByText('Avantages')).toBeDefined();
    expect(screen.getByText('Inconvénients')).toBeDefined();
  });

  it('renders two columns', () => {
    const { container } = render(<ProsConsBlock data={data} />);
    const columns = container.querySelectorAll('.rounded-xl');
    expect(columns.length).toBe(2);
  });
});
