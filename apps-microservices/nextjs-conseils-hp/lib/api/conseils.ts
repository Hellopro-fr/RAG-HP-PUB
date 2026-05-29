import type { ConseilPage } from '@/types/conseils';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'https://api.hellopro.fr/v1';
const API_TOKEN = process.env.CONSEILS_API_TOKEN ?? '';

/**
 * Récupère une page conseil depuis l'API HelloPro par son ID numérique.
 * Utilisé côté serveur uniquement (Server Component / generateMetadata).
 *
 * En dev local (Phase 6), si l'API est inaccessible, renvoie le mock correspondant.
 * Voir CLAUDE.md §9.
 */
export async function fetchConseilPage(id: number): Promise<ConseilPage | null> {
  // Utiliser les mocks si l'API n'est pas configurée (dev local ou Docker sans token)
  if (!API_TOKEN) {
    const { getMockPage } = await import('@/data/mocks/index');
    return getMockPage(id);
  }

  try {
    const res = await fetch(`${API_BASE}/conseils/${id}`, {
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      next: { revalidate: 3600 },
    });

    if (!res.ok) {
      if (res.status === 404) return null;
      console.error(`[fetchConseilPage] API error ${res.status} for id=${id}`);
      return null;
    }

    return (await res.json()) as ConseilPage;
  } catch (err) {
    console.error(`[fetchConseilPage] Fetch failed for id=${id}:`, err);
    return null;
  }
}
