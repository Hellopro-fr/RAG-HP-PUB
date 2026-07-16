import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FaqBlock } from '@/components/conseil/blocks/FaqBlock';

const items = [
  { q: 'Combien coûte X ?', a: 'Entre 1 000 et 2 000 €.' },
  { q: 'Quels délais ?', a: 'Compter 3 à 6 mois.' },
];

describe('FaqBlock', () => {
  it('renders static fallback title when no title in data', () => {
    render(<FaqBlock data={{ items }} />);
    expect(screen.getByText('Vos questions les plus fréquentes')).toBeDefined();
  });

  it('renders custom title from data.title', () => {
    render(<FaqBlock data={{ items, title: 'Questions sur les bâtiments' }} />);
    expect(screen.getByText('Questions sur les bâtiments')).toBeDefined();
    expect(screen.queryByText('Vos questions les plus fréquentes')).toBeNull();
  });

  it('renders all FAQ items', () => {
    render(<FaqBlock data={{ items }} />);
    expect(screen.getByText('Combien coûte X ?')).toBeDefined();
    expect(screen.getByText('Quels délais ?')).toBeDefined();
  });

  it('opens first item by default', () => {
    render(<FaqBlock data={{ items }} />);
    expect(screen.getByText('Entre 1 000 et 2 000 €.')).toBeDefined();
  });

  it('toggles item on click', () => {
    render(<FaqBlock data={{ items }} />);
    const btn = screen.getByText('Quels délais ?').closest('button')!;
    fireEvent.click(btn);
    expect(screen.getByText('Compter 3 à 6 mois.')).toBeDefined();
  });

  it('closes open item when clicked again', () => {
    render(<FaqBlock data={{ items }} />);
    const btn = screen.getByText('Combien coûte X ?').closest('button')!;
    fireEvent.click(btn);
    expect(screen.queryByText('Entre 1 000 et 2 000 €.')).toBeNull();
  });

  it('compile les balises HTML dans les réponses FAQ', () => {
    const htmlItems = [{ q: 'Question HTML ?', a: '<p>Réponse avec <strong>mise en forme</strong>.</p>' }];
    render(<FaqBlock data={{ items: htmlItems }} />);
    const strong = document.querySelector('strong');
    expect(strong?.textContent).toBe('mise en forme');
  });
});
