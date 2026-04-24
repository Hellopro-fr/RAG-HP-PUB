import { describe, it, expect } from 'vitest';

describe('test infra smoke', () => {
  it('runs basic arithmetic', () => {
    expect(1 + 1).toBe(2);
  });

  it('has a functional jsdom environment', () => {
    const el = document.createElement('div');
    el.textContent = 'hello';
    expect(el.tagName).toBe('DIV');
    expect(el.textContent).toBe('hello');
  });
});
