/**
 * Contenu statique par catégorie — textes marketing, réassurances, CTA.
 * Clé = ID catégorie (number).
 * "xx" et "zz" sont des placeholders à remplacer dynamiquement par les vraies valeurs.
 */

export interface CategoryLandingContent {
  h1: string;
  reassuranceSousTitre: string;
  cta: string;
  blocDroiteReassurance: string;
}

export interface CategoryQuestionContent {
  header: string;
  reassurance: string;
}

export interface CategorySelectionContent {
  voirPlus: string;
  recommandeReassurance: string;
}

export interface CategoryStaticContent {
  landing: CategoryLandingContent;
  question: CategoryQuestionContent;
  selection: CategorySelectionContent;
}

const categoryStaticContent: Record<number, CategoryStaticContent> = {
  // Ponts élévateurs
  2007702: {
    landing: {
      h1: "Trouvez votre pont élévateur idéal en 1 minute",
      reassuranceSousTitre: "xx fournisseurs recensés · 1 400 options possibles",
      cta: "Trouver mon pont élévateur (1 min) →",
      blocDroiteReassurance: "xx fournisseurs de pont élévateurs sélectionnés et triés sur le volet",
    },
    question: {
      header: "1 minute pour trouver votre pont élévateur",
      reassurance: "xx modèles de ponts élévateurs comparés chez zz vendeurs de matériel de garage",
    },
    selection: {
      voirPlus: "Voir plus de pont élévateur",
      recommandeReassurance: "Basé sur 30+ ans d'expérience et parmi toute la base de données de HelloPro (xx références), les ponts élévateurs qui vous sont présentés sont ceux qui sont le plus proches de votre demande.",
    },
  },

  // Chambre froide
  2003445: {
    landing: {
      h1: "La chambre froide qu'il vous faut, au bon prix — devis en 1 minute",
      reassuranceSousTitre: "xx fabricants partenaires · Plus de 2 500 configurations disponibles",
      cta: "Recevoir mes devis chambre froide (1 min) →",
      blocDroiteReassurance: "xx spécialistes du froid professionnel vérifiés et référencés par HelloPro",
    },
    question: {
      header: "1 minute pour dimensionner votre chambre froide",
      reassurance: "xx modèles de chambres froides comparés auprès de zz spécialistes du froid commercial et industriel",
    },
    selection: {
      voirPlus: "Voir plus de chambres froides",
      recommandeReassurance: "Nos experts métier ont analysé plus de xx références de chambres froides dans la base HelloPro. Les solutions affichées ici sont celles qui correspondent le mieux à vos contraintes de volume, température et usage.",
    },
  },

  // Distributeur automatique de snacks
  2005786: {
    landing: {
      h1: "Offrez à vos équipes le distributeur de snacks qui change tout",
      reassuranceSousTitre: "xx fournisseurs qualifiés · Plus de 800 modèles référencés",
      cta: "Trouver mon distributeur de snacks (1 min) →",
      blocDroiteReassurance: "xx distributeurs automatiques sélectionnés parmi les marques leaders du marché",
    },
    question: {
      header: "En 1 minute, trouvez le distributeur de snacks adapté à vos locaux",
      reassurance: "xx modèles de distributeurs de snacks comparés chez zz spécialistes de la distribution automatique",
    },
    selection: {
      voirPlus: "Voir plus de distributeurs de snacks",
      recommandeReassurance: "Forts de 30+ ans d'expertise, nous avons passé au crible xx références de distributeurs automatiques. Les modèles proposés sont les mieux adaptés à votre fréquentation, vos espaces et vos attentes produits.",
    },
  },

  // Distributeur de boissons chaudes
  2012048: {
    landing: {
      h1: "Le bon distributeur de boissons chaudes pour vos locaux — en 1 minute",
      reassuranceSousTitre: "xx fournisseurs référencés · Plus de 600 machines comparées",
      cta: "Comparer les distributeurs de boissons chaudes (1 min) →",
      blocDroiteReassurance: "xx spécialistes de la machine à café et boissons chaudes triés sur le volet",
    },
    question: {
      header: "1 minute pour choisir la machine à boissons chaudes idéale",
      reassurance: "xx distributeurs de boissons chaudes comparés auprès de zz fournisseurs spécialisés en restauration automatique",
    },
    selection: {
      voirPlus: "Voir plus de distributeurs de boissons chaudes",
      recommandeReassurance: "Grâce à 30+ ans d'expérience terrain, nous avons sélectionné parmi xx références les distributeurs de boissons chaudes les plus pertinents pour votre volume de consommation et votre environnement.",
    },
  },

  // Épareuses et broyeurs forestiers
  2017713: {
    landing: {
      h1: "Épareuses & broyeurs forestiers : comparez les pros en 1 minute",
      reassuranceSousTitre: "xx constructeurs référencés · Plus de 1 000 modèles disponibles",
      cta: "Trouver mon épareuse ou broyeur forestier (1 min) →",
      blocDroiteReassurance: "xx fabricants d'épareuses et broyeurs forestiers analysés et sélectionnés par nos experts",
    },
    question: {
      header: "1 minute pour identifier l'épareuse ou le broyeur qu'il vous faut",
      reassurance: "xx modèles d'épareuses et broyeurs forestiers comparés chez zz spécialistes du matériel agricole et forestier",
    },
    selection: {
      voirPlus: "Voir plus d'épareuses et broyeurs forestiers",
      recommandeReassurance: "Notre équipe a passé au crible xx références d'épareuses et broyeurs dans la base HelloPro. Les machines proposées sont celles qui correspondent à votre puissance de tracteur, votre terrain et votre usage.",
    },
  },

  // Lave-linge professionnel
  2009397: {
    landing: {
      h1: "Trouvez le lave-linge pro qui tient la cadence — devis en 1 minute",
      reassuranceSousTitre: "xx fournisseurs vérifiés · Plus de 900 modèles professionnels comparés",
      cta: "Comparer les lave-linge professionnels (1 min) →",
      blocDroiteReassurance: "xx spécialistes de la blanchisserie professionnelle sélectionnés et évalués par HelloPro",
    },
    question: {
      header: "1 minute pour trouver le lave-linge professionnel adapté à votre activité",
      reassurance: "xx lave-linge professionnels comparés auprès de zz fournisseurs spécialisés en équipement de blanchisserie",
    },
    selection: {
      voirPlus: "Voir plus de lave-linge professionnels",
      recommandeReassurance: "Avec 30+ ans d'expertise, nous avons analysé xx références de lave-linge professionnels. Les modèles présentés sont ceux qui répondent le mieux à votre capacité de lavage, votre fréquence d'utilisation et vos normes d'hygiène.",
    },
  },

  // Machine à dupliquer les clés
  2008236: {
    landing: {
      h1: "La machine à clés qui booste votre service — trouvez-la en 1 minute",
      reassuranceSousTitre: "xx fournisseurs spécialisés · Plus de 400 modèles référencés",
      cta: "Trouver ma machine à clés (1 min) →",
      blocDroiteReassurance: "xx fabricants de machines à clés analysés et retenus par les experts HelloPro",
    },
    question: {
      header: "1 minute pour sélectionner la machine à clés adaptée à votre commerce",
      reassurance: "xx machines à clés comparées chez zz fournisseurs spécialisés en serrurerie et reproduction de clés",
    },
    selection: {
      voirPlus: "Voir plus de machines à clés",
      recommandeReassurance: "Forts de 30+ ans d'expérience, nous avons évalué xx références de machines à clés dans la base HelloPro. Celles qui vous sont présentées sont les plus adaptées à votre volume de reproduction et vos types de clés.",
    },
  },

  // Mini-pelles (moins de 10 tonnes)
  1001328: {
    landing: {
      h1: "Mini-pelles < 10 t : trouvez la machine qui creuse pour vous en 1 minute",
      reassuranceSousTitre: "xx concessionnaires et fabricants · Plus de 1 200 modèles comparés",
      cta: "Comparer les mini-pelles disponibles (1 min) →",
      blocDroiteReassurance: "xx spécialistes du TP et de la mini-pelle vérifiés et sélectionnés par HelloPro",
    },
    question: {
      header: "1 minute pour cibler la mini-pelle idéale pour vos chantiers",
      reassurance: "xx mini-pelles de moins de 10 tonnes comparées chez zz concessionnaires de matériel de chantier",
    },
    selection: {
      voirPlus: "Voir plus de mini-pelles",
      recommandeReassurance: "Nos experts ont analysé xx mini-pelles dans toute la base HelloPro. Les modèles affichés sont ceux qui collent le mieux à votre tonnage, votre profondeur de fouille et vos conditions de chantier.",
    },
  },

  // Monte-charge
  1002167: {
    landing: {
      h1: "Le monte-charge adapté à vos flux — devis gratuits en 1 minute",
      reassuranceSousTitre: "xx installateurs qualifiés · Plus de 700 solutions référencées",
      cta: "Recevoir mes devis monte-charge (1 min) →",
      blocDroiteReassurance: "xx spécialistes du levage et de la manutention verticale sélectionnés par HelloPro",
    },
    question: {
      header: "1 minute pour définir le monte-charge qu'il vous faut",
      reassurance: "xx monte-charges comparés auprès de zz installateurs spécialisés en équipements de levage",
    },
    selection: {
      voirPlus: "Voir plus de monte-charges",
      recommandeReassurance: "Avec 30+ ans d'expertise, nous avons passé en revue xx références de monte-charges. Les solutions présentées sont optimisées pour votre charge utile, votre hauteur de levée et votre configuration de bâtiment.",
    },
  },

  // Palette en bois
  1002265: {
    landing: {
      h1: "Palettes en bois au meilleur prix — comparez en 1 minute",
      reassuranceSousTitre: "xx fabricants et revendeurs · Des milliers de palettes disponibles sur stock",
      cta: "Obtenir mes devis palettes en bois (1 min) →",
      blocDroiteReassurance: "xx fournisseurs de palettes en bois certifiés et évalués par HelloPro",
    },
    question: {
      header: "1 minute pour sourcer vos palettes en bois au bon format et au bon prix",
      reassurance: "xx types de palettes en bois comparés chez zz fournisseurs spécialisés en emballage et logistique",
    },
    selection: {
      voirPlus: "Voir plus de palettes en bois",
      recommandeReassurance: "Notre équipe a analysé xx références de palettes en bois dans la base HelloPro. Les offres présentées correspondent au mieux à vos dimensions, votre charge et vos normes (EUR/EPAL, NIMP15, etc.).",
    },
  },

  // Tracteur agricole
  2001065: {
    landing: {
      h1: "Tracteurs agricoles : comparez les meilleures offres en 1 minute",
      reassuranceSousTitre: "xx concessionnaires et constructeurs · Plus de 2 000 modèles référencés",
      cta: "Trouver mon tracteur agricole (1 min) →",
      blocDroiteReassurance: "xx spécialistes du machinisme agricole rigoureusement sélectionnés par HelloPro",
    },
    question: {
      header: "1 minute pour trouver le tracteur taillé pour votre exploitation",
      reassurance: "xx tracteurs agricoles comparés auprès de zz concessionnaires et spécialistes du machinisme",
    },
    selection: {
      voirPlus: "Voir plus de tracteurs agricoles",
      recommandeReassurance: "Forts de 30+ ans de connaissance du marché, nous avons évalué xx références de tracteurs agricoles. Les modèles proposés sont les mieux adaptés à votre puissance cible, votre surface d'exploitation et vos travaux.",
    },
  },
};

/**
 * Récupère le contenu statique d'une catégorie par son ID.
 * Retourne undefined si la catégorie n'a pas de contenu statique.
 */
export function getCategoryContent(categoryId: number): CategoryStaticContent | undefined {
  return categoryStaticContent[categoryId];
}

/**
 * Récupère uniquement la section landing d'une catégorie.
 */
export function getCategoryLanding(categoryId: number): CategoryLandingContent | undefined {
  return getCategoryContent(categoryId)?.landing;
}

/**
 * Récupère uniquement la section question d'une catégorie.
 */
export function getCategoryQuestion(categoryId: number): CategoryQuestionContent | undefined {
  return getCategoryContent(categoryId)?.question;
}

/**
 * Récupère uniquement la section sélection d'une catégorie.
 */
export function getCategorySelection(categoryId: number): CategorySelectionContent | undefined {
  return getCategoryContent(categoryId)?.selection;
}

export default categoryStaticContent;
