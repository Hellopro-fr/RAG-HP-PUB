import { describe, it, expect } from 'vitest';
import type { FaqBlockData, FaqItem } from '@/types/blocks/faq';

describe('FaqBlockData', () => {
  it('accepts items without optional title', () => {
    const data: FaqBlockData = { items: [{ q: 'Q ?', a: 'R.' }] };
    expect(data.items).toHaveLength(1);
    expect(data.title).toBeUndefined();
  });

  it('accepts optional title', () => {
    const data: FaqBlockData = { items: [], title: 'Questions fréquentes' };
    expect(data.title).toBe('Questions fréquentes');
  });

  it('FaqItem has q and a fields', () => {
    const item: FaqItem = { q: 'Combien ?', a: 'Environ 1000 €.' };
    expect(item.q).toBe('Combien ?');
    expect(item.a).toBe('Environ 1000 €.');
  });
});
