import type { ConseilPage } from '@/types/conseils';
import { mockPagePrix } from './page-prix';
import { mockPageAutre } from './page-autre';
import { mockPageTop } from './page-top';

/**
 * Registre des mocks par ID fictif.
 * Utilisé uniquement en dev local quand CONSEILS_API_TOKEN n'est pas défini.
 * Voir lib/api/conseils.ts et CLAUDE.md §9.
 */
const MOCK_REGISTRY: Record<number, ConseilPage> = {
  1001: mockPagePrix,
  1002: mockPageAutre,
  1003: mockPageTop,
};

export function getMockPage(id: number): ConseilPage | null {
  return MOCK_REGISTRY[id] ?? mockPagePrix; // fallback sur prix pour tout ID inconnu en dev
}

export { mockPagePrix, mockPageAutre, mockPageTop };
