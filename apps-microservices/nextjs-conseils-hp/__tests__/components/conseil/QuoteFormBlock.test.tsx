import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QuoteFormBlock } from '@/components/conseil/blocks/QuoteFormBlock';
import type { AoFormQuestion } from '@/types/conseils';

const mockQuestion: AoFormQuestion = {
  id: 1,
  question: 'Quel type de projet ?',
  avecImage: true,
  typeSelection: 1,
  choix: [
    { id: 10, label: 'Construction neuve', image: 'https://cdn.hellopro.fr/construction.jpg' },
    { id: 11, label: 'Rénovation' },
    { id: 12, label: 'Extension' },
  ],
};

describe('QuoteFormBlock', () => {
  it('renders static fallback text when no question in data', () => {
    render(<QuoteFormBlock data={{}} />);
    expect(screen.getByText(/passez à l'action/i)).toBeDefined();
  });

  it('renders question label from data.question', () => {
    render(<QuoteFormBlock data={{ question: mockQuestion }} />);
    expect(screen.getByText('Quel type de projet ?')).toBeDefined();
  });

  it('renders all choices from data.question.choix', () => {
    render(<QuoteFormBlock data={{ question: mockQuestion }} />);
    expect(screen.getByText('Construction neuve')).toBeDefined();
    expect(screen.getByText('Rénovation')).toBeDefined();
    expect(screen.getByText('Extension')).toBeDefined();
  });

  it('renders image when choice has image', () => {
    render(<QuoteFormBlock data={{ question: mockQuestion }} />);
    const img = screen.getByAltText('Construction neuve') as HTMLImageElement;
    expect(img.src).toContain('construction.jpg');
  });

  it('highlights selected choice on click', () => {
    render(<QuoteFormBlock data={{ question: mockQuestion }} />);
    const btn = screen.getByText('Construction neuve').closest('button')!;
    fireEvent.click(btn);
    expect(btn.className).toContain('ring-2');
  });

  it('renders custom ctaLabel', () => {
    render(<QuoteFormBlock data={{ ctaLabel: 'Obtenir mes devis' }} />);
    expect(screen.getByText(/obtenir mes devis/i)).toBeDefined();
  });
});
