import { describe, it, expect } from 'vitest';
import type { CTABlockData } from '@/types/blocks/cta';

describe('CTABlockData', () => {
  it('accepte un CTA minimal', () => {
    const data: CTABlockData = { title: 'Estimez votre projet', ctaLabel: 'Estimer' };
    expect(data.title).toBe('Estimez votre projet');
    expect(data.ctaUrl).toBeUndefined();
  });

  it('accepte un CTA avec URL', () => {
    const data: CTABlockData = {
      title: 'Estimez votre projet',
      subtitle: 'Recevez 3 devis',
      ctaLabel: 'Estimer',
      ctaUrl: 'https://www.hellopro.fr/devis',
    };
    expect(data.ctaUrl).toBe('https://www.hellopro.fr/devis');
  });
});
