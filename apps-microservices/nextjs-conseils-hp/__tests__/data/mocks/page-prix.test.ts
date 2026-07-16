import { describe, it, expect } from 'vitest';
import { mockPagePrix } from '@/data/mocks/page-prix';

describe('mockPagePrix', () => {
  it('has required top-level fields', () => {
    expect(mockPagePrix.slug).toBeTruthy();
    expect(mockPagePrix.pageType).toBe('prix');
    expect(mockPagePrix.meta.title).toBeTruthy();
    expect(mockPagePrix.hero.title).toBeTruthy();
  });

  it('has at least one block', () => {
    expect(mockPagePrix.blocks.length).toBeGreaterThan(0);
  });

  it('all blocks have id, type and order', () => {
    for (const block of mockPagePrix.blocks) {
      expect(block.id).toBeTruthy();
      expect(block.type).toBeTruthy();
      expect(typeof block.order).toBe('number');
    }
  });

  it('image URLs use accessible hostnames', () => {
    const urlsToCheck = [
      mockPagePrix.meta.ogImage,
      mockPagePrix.hero.image,
      ...mockPagePrix.blocks
        .filter((b) => b.data && typeof (b.data as Record<string, unknown>).imageUrl === 'string')
        .map((b) => (b.data as Record<string, unknown>).imageUrl as string),
    ].filter(Boolean) as string[];

    for (const url of urlsToCheck) {
      expect(url).not.toContain('cdn.hellopro.fr');
    }
  });
});
