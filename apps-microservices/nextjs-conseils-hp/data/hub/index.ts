import type { HubPage } from '@/types/hub';
import { lancerElevagePoulesPondeuses } from './lancer-elevage-poules-pondeuses';
import { ouvrirFoodTruck } from './ouvrir-food-truck';
import { ouvrirLaverieAutomatique } from './ouvrir-laverie-automatique';

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
  1001: ouvrirFoodTruck,
  1002: ouvrirLaverieAutomatique,
} satisfies Record<number, HubPage>;

/** Récupère une page par son id d'URL. `null` si l'id est inconnu → 404. */
export function getHubPage(id: number): HubPage | null {
  return (HUB_PAGES as Record<number, HubPage>)[id] ?? null;
}

/** Toutes les pages HUB — utilisé par `generateStaticParams` des deux routes. */
export function listHubPages(): HubPage[] {
  return Object.values(HUB_PAGES);
}

/**
 * ⚠️ `guideIdPageHub()` et `GUIDE_LEAD_ID_OFFSET` ont été SUPPRIMÉS le 2026-08-25.
 *
 * Le tunnel guide envoyait `id_page_hub = id de la page + 1000` (1001 → 2001)
 * pour que le back-office distingue ses leads de ceux du questionnaire. Deux
 * problèmes en production : le BO ne connaissait que les ids 1000-1002, donc les
 * leads guide arrivaient non rattachés ; et deux identifiants pour une même page
 * obligeaient chaque lecteur — GA4, BO, requête SQL — à connaître l'astuce.
 *
 * Désormais **`id_page_hub` est l'id de l'URL, pour les deux tunnels**.
 *
 * La distinction se lit à l'arrivée, sans champ supplémentaire : une demande
 * SANS ligne dans `hub_demande_reponse` vient du tunnel guide, une demande AVEC
 * réponses vient du questionnaire. L'API le prévoyait déjà (cf. le commentaire
 * « certains formulaires n'ont pas de questionnaire » dans `handle_hub_demande`).
 *
 * ⚠️ Cette règle repose sur un invariant : **le questionnaire produit toujours au
 * moins une réponse** — sa première question est obligatoire pour démarrer — et
 * **le tunnel guide n'en produit aucune**. Ajouter une question au tunnel guide,
 * ou rendre la première question du questionnaire facultative, casserait la
 * distinction EN SILENCE. Si l'un des deux devient nécessaire, il faudra alors
 * un champ explicite dans le payload.
 *
 * Côté analytics, rien ne repose sur cet invariant : `hub_group` distingue déjà
 * `projet` de `guide` sur chaque événement.
 */
