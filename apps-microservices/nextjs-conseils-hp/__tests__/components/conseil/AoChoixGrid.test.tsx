import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AoChoixGrid } from '@/components/conseil/AoChoixGrid';
import type { AoFormQuestion } from '@/types/conseils';

const question: AoFormQuestion = {
  id: 1,
  question: 'Quel type de projet ?',
  avecImage: false,
  typeSelection: 1,
  obligatoire: 0,
  choix: [
    { id: 10, label: 'Construction neuve' },
    { id: 11, label: 'Rénovation' },
    { id: 12, label: 'Extension' },
  ],
};

describe('AoChoixGrid', () => {
  it('renders nothing when choix list is empty', () => {
    const { container } = render(
      <AoChoixGrid question={null} onChoixClick={vi.fn()} onAutreChange={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders all choice labels', () => {
    render(<AoChoixGrid question={question} onChoixClick={vi.fn()} onAutreChange={vi.fn()} />);
    expect(screen.getByText('Construction neuve')).toBeDefined();
    expect(screen.getByText('Rénovation')).toBeDefined();
    expect(screen.getByText('Extension')).toBeDefined();
  });

  it('calls onChoixClick when a choice is clicked', () => {
    const onChoixClick = vi.fn();
    render(<AoChoixGrid question={question} onChoixClick={onChoixClick} onAutreChange={vi.fn()} />);
    fireEvent.click(screen.getByText('Rénovation'));
    expect(onChoixClick).toHaveBeenCalledWith(question.choix[1]);
  });

  it('renders an image when choice has one', () => {
    const qWithImage: AoFormQuestion = {
      ...question,
      avecImage: true,
      choix: [{ id: 20, label: 'Avec image', image: 'https://cdn.hellopro.fr/img.jpg' }],
    };
    const { container } = render(
      <AoChoixGrid question={qWithImage} onChoixClick={vi.fn()} onAutreChange={vi.fn()} />
    );
    expect(container.querySelector('img')).toBeTruthy();
  });
});
