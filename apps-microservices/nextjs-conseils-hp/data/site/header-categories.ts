/**
 * Rubrique du méga-menu « Tous les produits », au format attendu par `SiteHeader`.
 * L'`url` est celle des rubriques HelloPro (`…-<id>-fr-rubrique.html`).
 */
export interface HeaderCategory {
  id: number;
  nom: string;
  url: string;
}

/**
 * FILET DE SÉCURITÉ — pas la source de vérité.
 *
 * Les rubriques sont récupérées en direct depuis `mega-menu.php`, la même source
 * que www.hellopro.fr (voir `lib/site/headerCategories.ts`). Cet instantané ne
 * sert QUE si la récupération échoue ou renvoie un résultat manifestement
 * incomplet : un méga-menu vide signifierait zéro lien de rubrique crawlable
 * depuis les pages HUB, ce qui est pire qu'une liste légèrement datée.
 *
 * Relevé le 29/07/2026 — 24 rubriques de 1er niveau.
 *
 * ⚠️ Les slugs ne se déduisent PAS des libellés : « Engins et matériels de
 * chantier » → `travaux-publics-2006625`, « Industrie » →
 * `fabrication-et-processus-1000006`. Ne jamais reconstruire une URL à la main.
 */
export const HEADER_CATEGORIES_FALLBACK: HeaderCategory[] = [
  { id: 2006625, nom: 'Engins et matériels de chantier', url: 'https://www.hellopro.fr/travaux-publics-2006625-fr-rubrique.html' },
  { id: 2000517, nom: 'Espace extérieur - Aménagement urbain', url: 'https://www.hellopro.fr/amenagements-urbains-2000517-fr-rubrique.html' },
  { id: 2000543, nom: 'Matériaux de construction', url: 'https://www.hellopro.fr/maconnerie-structures-2000543-fr-rubrique.html' },
  { id: 2001029, nom: 'Agriculture - Elevage - Forestier', url: 'https://www.hellopro.fr/agriculture-elevage-peche-2001029-fr-rubrique.html' },
  { id: 2005622, nom: 'CHR - Café Hôtel Restaurant', url: 'https://www.hellopro.fr/restauration-collective-2005622-fr-rubrique.html' },
  { id: 1000013, nom: 'Logistique - Entrepôt', url: 'https://www.hellopro.fr/logistique-1000013-fr-rubrique.html' },
  { id: 2000230, nom: 'Emballage et conditionnement', url: 'https://www.hellopro.fr/emballage-et-conditionnement-2000230-fr-rubrique.html' },
  { id: 1000006, nom: 'Industrie', url: 'https://www.hellopro.fr/fabrication-et-processus-1000006-fr-rubrique.html' },
  { id: 2000139, nom: 'Industrie alimentaire', url: 'https://www.hellopro.fr/industrie-alimentaire-2000139-fr-rubrique.html' },
  { id: 2006376, nom: 'Equipement pour magasins / commerces', url: 'https://www.hellopro.fr/equipements-pour-la-distribution-2006376-fr-rubrique.html' },
  { id: 1000014, nom: 'Équipements et services aux entreprises', url: 'https://www.hellopro.fr/equipements-d-entreprises-1000014-fr-rubrique.html' },
  { id: 1000011, nom: 'Chauffage - Climatisation - Ventilation', url: 'https://www.hellopro.fr/genie-climatique-1000011-fr-rubrique.html' },
  { id: 9000312, nom: 'Outillage et fournitures industrielles', url: 'https://www.hellopro.fr/outillage-et-fournitures-industrielles-9000312-fr-rubrique.html' },
  { id: 1000012, nom: 'Sécurité', url: 'https://www.hellopro.fr/securite-1000012-fr-rubrique.html' },
  { id: 2006165, nom: 'Transport - Automobile', url: 'https://www.hellopro.fr/transports-2006165-fr-rubrique.html' },
  { id: 1000010, nom: 'Gestion des déchets - Environnement', url: 'https://www.hellopro.fr/environnement-1000010-fr-rubrique.html' },
  { id: 1000001, nom: 'Mesures, analyses et capteurs', url: 'https://www.hellopro.fr/mesures-analyses-et-capteurs-1000001-fr-rubrique.html' },
  { id: 1000003, nom: 'Électricité - Électronique - Énergie renouvelable', url: 'https://www.hellopro.fr/electricite-electronique-1000003-fr-rubrique.html' },
  { id: 1000005, nom: 'Pompe - Hydraulique - Pneumatique', url: 'https://www.hellopro.fr/hydraulique-pneumatique-1000005-fr-rubrique.html' },
  { id: 1000002, nom: 'Matériel informatique et réseau', url: 'https://www.hellopro.fr/reseaux-informatique-1000002-fr-rubrique.html' },
  { id: 1000015, nom: 'Communication - Événementiel', url: 'https://www.hellopro.fr/communication-evenementiel-1000015-fr-rubrique.html' },
  { id: 2000405, nom: 'Santé', url: 'https://www.hellopro.fr/sante-2000405-fr-rubrique.html' },
  { id: 1000009, nom: 'Laboratoire', url: 'https://www.hellopro.fr/laboratoires-1000009-fr-rubrique.html' },
  { id: 2004386, nom: "Matériel de nettoyage et d'entretien", url: 'https://www.hellopro.fr/nettoyage-entretien-2004386-fr-rubrique.html' },
];
