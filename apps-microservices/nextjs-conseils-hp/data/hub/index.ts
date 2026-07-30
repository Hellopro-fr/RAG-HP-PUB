import type { HubPage } from '@/types/hub';
import { lancerElevagePoulesPondeuses } from './lancer-elevage-poules-pondeuses';

/**
 * Registry des pages HUB — source de vérité unique du contenu.
 *
 * La clé est l'**id numérique présent dans l'URL** (`/<slug>-<id>-projet.html`) :
 * c'est lui qui sert à récupérer les données, le slug n'étant que cosmétique (SEO)
 * et vérifié pour la redirection canonique.
 *
 * Contenu 100 % statique : les projets HUB n'existent pas en base SQL, il n'y a
 * donc ni fetch, ni transformer, ni token API pour le contenu. Les pages sont
 * prérendues au build via `generateStaticParams`, puis revalidées chaque jour —
 * la revalidation ne sert qu'aux rubriques du méga-menu, seule donnée distante
 * (cf. `app/hub/[hubSlug]/page.tsx`).
 *
 * Pour ajouter une page : créer `data/hub/<slug>.ts` puis l'enregistrer ici.
 * Aucun composant à modifier — si ce n'est pas le cas, c'est le modèle de données
 * qui est à revoir, pas le template.
 */
export const HUB_PAGES = {
  1000: lancerElevagePoulesPondeuses,
} satisfies Record<number, HubPage>;

/** Récupère une page par son id d'URL. `null` si l'id est inconnu → 404. */
export function getHubPage(id: number): HubPage | null {
  return (HUB_PAGES as Record<number, HubPage>)[id] ?? null;
}

/** Toutes les pages HUB — utilisé par `generateStaticParams` des deux routes. */
export function listHubPages(): HubPage[] {
  return Object.values(HUB_PAGES);
}
