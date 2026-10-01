import { describe, it, expect } from 'vitest';
import DefaultHead from '@/app/@head/default';

describe('DefaultHead', () => {
  it('returns null', () => {
    expect(DefaultHead()).toBeNull();
  });
});
