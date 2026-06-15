import { describe, it, expect } from 'vitest';
import { mockPageTop } from '@/data/mocks/page-top';

describe('mockPageTop', () => {
  it('has required fields', () => {
    expect(mockPageTop.slug).toBeTruthy();
    expect(mockPageTop.pageType).toBe('top');
    expect(mockPageTop.hero.title).toBeTruthy();
  });

  it('has no mock author', () => {
    expect(mockPageTop.author).toBeUndefined();
  });
});
