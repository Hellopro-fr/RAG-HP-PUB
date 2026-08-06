import { describe, it, expect, afterEach } from 'vitest';
import { isLeadKnown, markLeadKnown } from '@/lib/hub/leadEmailCookie';

afterEach(() => {
  document.cookie = 'hub_lead=; path=/; max-age=0';
});

describe('leadEmailCookie', () => {
  it('marque puis détecte un lead connu', () => {
    expect(isLeadKnown()).toBe(false);
    markLeadKnown();
    expect(isLeadKnown()).toBe(true);
  });

  it('ne stocke JAMAIS d’e-mail, uniquement le drapeau `1`', () => {
    markLeadKnown();
    expect(document.cookie).toContain('hub_lead=1');
    expect(document.cookie).not.toMatch(/@/);
  });

  it('renvoie false quand aucun cookie n’est présent', () => {
    expect(isLeadKnown()).toBe(false);
  });
});
