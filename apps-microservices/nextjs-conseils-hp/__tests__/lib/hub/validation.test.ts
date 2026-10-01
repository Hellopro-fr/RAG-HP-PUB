import { describe, it, expect } from 'vitest';
import { isValidPhone } from '@/lib/hub/validation';

describe('isValidPhone', () => {
  it('accepte les numéros d’au moins 6 chiffres, séparateurs et indicatif libres', () => {
    expect(isValidPhone('06 12 34 56 78')).toBe(true);
    expect(isValidPhone('+33 6 12 34 56 78')).toBe(true);
    expect(isValidPhone('0033612345678')).toBe(true);
    expect(isValidPhone('0612345678')).toBe(true);
    expect(isValidPhone('01.23.45.67')).toBe(true);
    expect(isValidPhone('123456')).toBe(true); // pile 6 chiffres
  });

  it('rejette le vide, les lettres seules et les numéros trop courts', () => {
    expect(isValidPhone('')).toBe(false);
    expect(isValidPhone('   ')).toBe(false);
    expect(isValidPhone('abcdef')).toBe(false);
    expect(isValidPhone('12345')).toBe(false); // 5 chiffres
    expect(isValidPhone('06 12')).toBe(false);
  });
});
