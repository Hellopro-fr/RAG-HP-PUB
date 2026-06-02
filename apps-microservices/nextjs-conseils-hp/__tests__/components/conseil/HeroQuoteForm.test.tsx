import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { HeroQuoteForm } from '@/components/conseil/HeroQuoteForm';
import type { AoFormQuestion } from '@/types/conseils';

const mockQuestion: AoFormQuestion = {
  id: 42,
  question: 'Quel type de projet ?',
  avecImage: false,
  choix: [
    { id: 1, label: 'Construction neuve' },
    { id: 2, label: 'Rénovation' },
    { id: 3, label: 'Extension', image: 'https://www.hellopro.fr/img/extension.jpg' },
  ],
};

describe('HeroQuoteForm', () => {
  it('renders without question (fallback)', () => {
    render(<HeroQuoteForm />);
    expect(screen.getByText(/Quel est votre besoin/i)).toBeDefined();
    expect(screen.getByText(/3 devis gratuits/i)).toBeDefined();
  });

  it('displays the question from API', () => {
    render(<HeroQuoteForm question={mockQuestion} />);
    expect(screen.getByText('Quel type de projet ?')).toBeDefined();
  });

  it('renders all choices', () => {
    render(<HeroQuoteForm question={mockQuestion} />);
    expect(screen.getByText('Construction neuve')).toBeDefined();
    expect(screen.getByText('Rénovation')).toBeDefined();
    expect(screen.getByText('Extension')).toBeDefined();
  });

  it('renders image for choices that have one', () => {
    render(<HeroQuoteForm question={mockQuestion} />);
    const img = screen.getByAltText('Extension') as HTMLImageElement;
    expect(img.src).toContain('extension.jpg');
  });

  it('highlights selected choice on click', () => {
    render(<HeroQuoteForm question={mockQuestion} />);
    const btn = screen.getByText('Construction neuve').closest('button')!;
    fireEvent.click(btn);
    expect(btn.className).toContain('ring-2');
  });

  it('renders with null question (no choices shown)', () => {
    render(<HeroQuoteForm question={null} />);
    expect(screen.getByText(/Quel est votre besoin/i)).toBeDefined();
  });

  it('shows the CTA button', () => {
    render(<HeroQuoteForm question={mockQuestion} />);
    expect(screen.getByText(/demande groupée/i)).toBeDefined();
  });
});
