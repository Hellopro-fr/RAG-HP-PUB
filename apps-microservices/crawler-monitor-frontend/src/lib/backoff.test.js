import { describe, it, expect } from 'vitest';
import { wsBackoffDelay, WS_BACKOFF_BASE_MS, WS_BACKOFF_MAX_MS } from './backoff';

describe('wsBackoffDelay', () => {
  it('attempt 0 → 1s', () => {
    expect(wsBackoffDelay(0)).toBe(1000);
  });

  it('attempt 1 → 2s', () => {
    expect(wsBackoffDelay(1)).toBe(2000);
  });

  it('attempt 2 → 4s', () => {
    expect(wsBackoffDelay(2)).toBe(4000);
  });

  it('attempt 4 → 16s', () => {
    expect(wsBackoffDelay(4)).toBe(16000);
  });

  it('attempt 5 → plafonné à 30s', () => {
    expect(wsBackoffDelay(5)).toBe(30000);
  });

  it('attempt 10 → toujours plafonné à 30s', () => {
    expect(wsBackoffDelay(10)).toBe(30000);
  });

  it('attempt négatif → délai de base (1s)', () => {
    expect(wsBackoffDelay(-3)).toBe(1000);
  });

  it('attempt undefined → délai de base (1s)', () => {
    expect(wsBackoffDelay(undefined)).toBe(1000);
  });

  it('expose les constantes base/max', () => {
    expect(WS_BACKOFF_BASE_MS).toBe(1000);
    expect(WS_BACKOFF_MAX_MS).toBe(30000);
  });
});
