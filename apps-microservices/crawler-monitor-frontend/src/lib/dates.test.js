import { describe, it, expect } from 'vitest';
import { parseApiDate, parseApiDateMs, formatApiDate } from './dates';

describe('parseApiDate', () => {
  it('lit le format naif du backend Python comme de l\'UTC', () => {
    // « 2026-08-28 13:20:03.306901 » sans T ni Z : new Date() le lirait en heure
    // locale (decalage d'1 a 2 h) et Safari renverrait Invalid Date.
    const d = parseApiDate('2026-08-28 13:20:03.306901');
    expect(d).toBeInstanceOf(Date);
    expect(d.toISOString()).toBe('2026-08-28T13:20:03.306Z');
  });

  it('lit le RFC3339 renvoye apres le correctif backend', () => {
    expect(parseApiDate('2026-08-28T13:20:03Z').toISOString())
      .toBe('2026-08-28T13:20:03.000Z');
  });

  it('respecte un decalage explicite', () => {
    expect(parseApiDate('2026-08-28T15:20:03+02:00').toISOString())
      .toBe('2026-08-28T13:20:03.000Z');
  });

  it('accepte une date seule', () => {
    expect(parseApiDate('2026-08-28').toISOString()).toBe('2026-08-28T00:00:00.000Z');
  });

  it('retourne null au lieu d\'une Invalid Date', () => {
    expect(parseApiDate(null)).toBeNull();
    expect(parseApiDate('')).toBeNull();
    expect(parseApiDate('pas-une-date')).toBeNull();
    expect(parseApiDate({})).toBeNull();
  });

  it('parseApiDateMs retourne null sur une entree illisible', () => {
    expect(parseApiDateMs('pas-une-date')).toBeNull();
    expect(parseApiDateMs('2026-08-28T00:00:00Z')).toBe(Date.UTC(2026, 7, 28));
  });

  it('formatApiDate degrade sur un tiret plutot que « Invalid Date »', () => {
    expect(formatApiDate(null)).toBe('—');
    expect(formatApiDate('pas-une-date')).toBe('—');
    expect(formatApiDate('2026-08-28T13:20:03Z')).not.toMatch(/Invalid/);
  });
});
