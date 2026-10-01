import { describe, it, expect } from 'vitest';
import { mockPageAutre } from '@/data/mocks/page-autre';

describe('mockPageAutre', () => {
  it('has required fields', () => {
    expect(mockPageAutre.slug).toBeTruthy();
    expect(mockPageAutre.pageType).toBe('autre');
    expect(mockPageAutre.hero.title).toBeTruthy();
  });

  it('has no mock author', () => {
    expect(mockPageAutre.author).toBeUndefined();
  });
});
