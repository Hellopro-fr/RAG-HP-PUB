import { describe, it, expect } from 'vitest';
import { QuoteFormBlockDataSchema } from '@/types/blocks/quote-form';

describe('QuoteFormBlockDataSchema', () => {
  it('accepts empty object (all fields optional)', () => {
    const result = QuoteFormBlockDataSchema.safeParse({});
    expect(result.success).toBe(true);
  });

  it('leaves ctaLabel undefined when not provided', () => {
    const result = QuoteFormBlockDataSchema.parse({});
    expect(result.ctaLabel).toBeUndefined();
  });

  it('accepts all optional fields', () => {
    const result = QuoteFormBlockDataSchema.parse({
      title: 'Passez à l\'action',
      subtitle: 'Obtenez vos devis',
      ctaLabel: 'Recevoir mes devis',
    });
    expect(result.title).toBe('Passez à l\'action');
  });
});
