import { describe, it, expect, afterEach } from 'vitest';
import { isLeadKnown, markLeadKnown } from '@/lib/hub/leadEmailCookie';

// Ids de PAGE — ceux de l'URL. Un seul identifiant par page depuis le 2026-08-25.
const ELEVAGE = 1000;
const LAVERIE = 1002;

afterEach(() => {
  document.cookie = 'hub_lead=; path=/; max-age=0';
});

describe('leadEmailCookie', () => {
  it('marque puis détecte un lead connu pour ce projet', () => {
    expect(isLeadKnown(ELEVAGE)).toBe(false);
    markLeadKnown(ELEVAGE);
    expect(isLeadKnown(ELEVAGE)).toBe(true);
  });

  /**
   * LE test de ce module (2026-08-24). Chaque page HUB est un projet distinct et
   * les leads sont rappelés selon le projet consulté : un visiteur converti sur
   * l'élevage doit quand même laisser son e-mail pour le guide laverie, sinon
   * aucun lead laverie n'est créé et personne ne le rappellera là-dessus.
   *
   * Le drapeau valait `1` sans notion de page jusqu'à cette date — c'était
   * exactement le défaut.
   */
  it('ne reconnaît PAS un visiteur converti sur un autre projet', () => {
    markLeadKnown(ELEVAGE);
    expect(isLeadKnown(LAVERIE)).toBe(false);
  });

  it('cumule les projets sans perdre les précédents', () => {
    markLeadKnown(ELEVAGE);
    markLeadKnown(LAVERIE);
    expect(isLeadKnown(ELEVAGE)).toBe(true);
    expect(isLeadKnown(LAVERIE)).toBe(true);
  });

  it('ne duplique pas un projet déjà marqué', () => {
    markLeadKnown(ELEVAGE);
    markLeadKnown(ELEVAGE);
    const value = /hub_lead=([^;]*)/.exec(document.cookie)?.[1] ?? '';
    expect(value.split('.').filter((id) => id === String(ELEVAGE))).toHaveLength(1);
  });

  it('ne stocke JAMAIS d’e-mail, uniquement des identifiants numériques', () => {
    markLeadKnown(ELEVAGE);
    markLeadKnown(LAVERIE);
    const value = /hub_lead=([^;]*)/.exec(document.cookie)?.[1] ?? '';
    expect(value).toMatch(/^\d+(?:\.\d+)*$/);
    expect(document.cookie).not.toMatch(/@/);
  });

  it('renvoie false quand aucun cookie n’est présent', () => {
    expect(isLeadKnown(ELEVAGE)).toBe(false);
  });

  /**
   * Les cookies posés avant le passage à la portée par projet valent `1`. Aucun
   * projet ne porte cet id : ils sont donc lus comme « rien de converti », et le
   * visiteur se voit redemander son e-mail une fois. C'est la dégradation
   * voulue — redemander une adresse coûte un champ, ne pas créer le lead coûte
   * le contact.
   */
  it('traite un cookie de l’ancien format comme aucun projet converti', () => {
    document.cookie = 'hub_lead=1; path=/';
    expect(isLeadKnown(ELEVAGE)).toBe(false);
    expect(isLeadKnown(LAVERIE)).toBe(false);
  });
});
