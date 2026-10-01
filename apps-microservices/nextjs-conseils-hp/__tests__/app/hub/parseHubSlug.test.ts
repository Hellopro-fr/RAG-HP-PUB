import { describe, it, expect } from 'vitest';
import { parseHubSlug } from '@/app/hub/[hubSlug]/page';

/**
 * parseHubSlug est le point de bascule entre l'URL et les données.
 * Une régression ici ne lève AUCUNE exception : elle transforme silencieusement
 * une page valide en redirection 404. D'où ces tests.
 */
describe('parseHubSlug', () => {
  it('sépare le slug et l’id sur une entrée canonique', () => {
    expect(parseHubSlug('lancer-elevage-poules-pondeuses-1000')).toEqual({
      slug: 'lancer-elevage-poules-pondeuses',
      id: 1000,
    });
  });

  it('gère les 3 slugs HUB prévus', () => {
    expect(parseHubSlug('creer-food-truck-1001')).toEqual({
      slug: 'creer-food-truck',
      id: 1001,
    });
    expect(parseHubSlug('ouvrir-laverie-automatique-1002')).toEqual({
      slug: 'ouvrir-laverie-automatique',
      id: 1002,
    });
  });

  it('ne coupe que sur le DERNIER groupe de chiffres', () => {
    // Un slug peut légitimement contenir un nombre (ex. "top-10-...").
    expect(parseHubSlug('top-10-equipements-1000')).toEqual({
      slug: 'top-10-equipements',
      id: 1000,
    });
  });

  it('accepte un slug d’un seul segment', () => {
    expect(parseHubSlug('laverie-42')).toEqual({ slug: 'laverie', id: 42 });
  });

  it('rejette une entrée sans id', () => {
    expect(parseHubSlug('lancer-elevage-poules-pondeuses')).toBeNull();
  });

  it('rejette une entrée réduite à un id (slug vide)', () => {
    // `^(.+)-(\d+)$` exige au moins un caractère de slug avant le tiret.
    expect(parseHubSlug('1000')).toBeNull();
    expect(parseHubSlug('-1000')).toBeNull();
  });

  it('rejette une chaîne vide', () => {
    expect(parseHubSlug('')).toBeNull();
  });

  it('rejette un id non numérique', () => {
    expect(parseHubSlug('creer-food-truck-abc')).toBeNull();
  });

  it('rejette le suffixe -projet, qui doit avoir été retiré par le rewrite', () => {
    // Si cette entrée passait, c'est que le rewrite next.config.js ne fait pas
    // son travail et que l'URL publique atterrit brute sur le segment.
    expect(parseHubSlug('creer-food-truck-1001-projet')).toBeNull();
  });

  it('rejette une extension .html résiduelle', () => {
    expect(parseHubSlug('creer-food-truck-1001.html')).toBeNull();
  });
});
