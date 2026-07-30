import { describe, it, expect } from 'vitest';
import { HEADER_CATEGORIES_FALLBACK as HUB_HEADER_CATEGORIES } from '@/data/site/header-categories';

/**
 * Filet de sécurité, utilisé uniquement si `fetchHeaderCategories` échoue. Ces
 * tests attrapent les erreurs de recopie sur 24 URLs saisies à la main — le
 * risque réel de ce fichier. La fraîcheur, elle, est assurée par le parsing en
 * direct (`lib/site/headerCategories.ts`).
 */
describe('HEADER_CATEGORIES_FALLBACK', () => {
  it('contient les 24 rubriques de 1er niveau', () => {
    expect(HUB_HEADER_CATEGORIES).toHaveLength(24);
  });

  it('n’a ni id ni libellé dupliqué', () => {
    const ids = HUB_HEADER_CATEGORIES.map((c) => c.id);
    const noms = HUB_HEADER_CATEGORIES.map((c) => c.nom);
    expect(new Set(ids).size).toBe(ids.length);
    expect(new Set(noms).size).toBe(noms.length);
  });

  it('a des libellés non vides', () => {
    for (const category of HUB_HEADER_CATEGORIES) {
      expect(category.nom.trim(), `id ${category.id}`).not.toBe('');
    }
  });

  /**
   * Le format `…-<id>-fr-rubrique.html` est ce qui rend le lien crawlable et
   * cohérent avec le reste du site. Une URL mal recopiée casse silencieusement
   * un lien du méga-menu.
   */
  it('respecte le format d’URL de rubrique HelloPro', () => {
    for (const category of HUB_HEADER_CATEGORIES) {
      expect(category.url, category.nom).toMatch(
        /^https:\/\/www\.hellopro\.fr\/[a-z0-9-]+-\d+-fr-rubrique\.html$/
      );
    }
  });

  /** L'id doit être celui présent dans l'URL, sinon l'un des deux est faux. */
  it('a un id cohérent avec celui de son URL', () => {
    for (const category of HUB_HEADER_CATEGORIES) {
      const match = category.url.match(/-(\d+)-fr-rubrique\.html$/);
      expect(match, category.nom).not.toBeNull();
      expect(Number(match?.[1]), `${category.nom} (${category.url})`).toBe(category.id);
    }
  });
});
