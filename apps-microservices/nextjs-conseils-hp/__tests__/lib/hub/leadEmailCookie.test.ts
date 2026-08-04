import { describe, it, expect, afterEach } from 'vitest';
import { getRememberedEmail, rememberEmail } from '@/lib/hub/leadEmailCookie';

afterEach(() => {
  document.cookie = 'hub_lead_email=; path=/; max-age=0';
});

describe('leadEmailCookie', () => {
  it('mémorise puis relit un e-mail valide', () => {
    rememberEmail('jean@exemple.fr');
    expect(getRememberedEmail()).toBe('jean@exemple.fr');
  });

  it('ignore un e-mail invalide ou vide', () => {
    rememberEmail('pas-un-email');
    expect(getRememberedEmail()).toBe('');
    rememberEmail('');
    expect(getRememberedEmail()).toBe('');
  });

  it('renvoie une chaîne vide quand aucun e-mail n’est mémorisé', () => {
    expect(getRememberedEmail()).toBe('');
  });
});
