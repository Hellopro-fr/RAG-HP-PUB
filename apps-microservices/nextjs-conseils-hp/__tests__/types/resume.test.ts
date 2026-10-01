import { describe, it, expect } from 'vitest';
import type { ResumeItem, ResumeBlockData } from '@/types/blocks/resume';

describe('ResumeBlockData', () => {
  it('accepte un bloc avec items uniquement', () => {
    const data: ResumeBlockData = {
      items: [
        { label: 'Coût', text: 'entre 200 et 500 €' },
        { label: 'Durée', text: '3 à 5 jours' },
      ],
    };
    expect(data.items).toHaveLength(2);
    expect(data.html).toBeUndefined();
  });

  it('accepte un bloc avec html brut uniquement', () => {
    const data: ResumeBlockData = {
      items: [],
      html: '<ul><li><strong>Coût :</strong> 200 à 500 €</li></ul>',
    };
    expect(data.html).toContain('<ul>');
    expect(data.items).toHaveLength(0);
  });

  it('accepte un bloc avec items ET html (html prioritaire)', () => {
    const data: ResumeBlockData = {
      items: [{ label: 'Coût', text: '200 €' }],
      html: '<p>Coût : 200 €</p>',
    };
    expect(data.items).toHaveLength(1);
    expect(data.html).toBe('<p>Coût : 200 €</p>');
  });

  it('ResumeItem a les champs requis label et text', () => {
    const item: ResumeItem = { label: 'Délai', text: '2 semaines' };
    expect(item.label).toBe('Délai');
    expect(item.text).toBe('2 semaines');
  });
});
