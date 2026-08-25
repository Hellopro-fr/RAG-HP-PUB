import type { HubPage } from '@/types/hub';
import { HUB_SECTION_IDS } from '@/lib/hub/anchors';
import { ACCOMPAGNEMENT, FAQ, HOW_IT_WORKS } from './_shared';

/**
 * Page HUB 1001 — « Ouvrir un food truck ».
 * URL : /ouvrir-food-truck-1001-projet.html
 *
 * Contenu issu du cahier des charges Notion « Ouvrir un food-truck » et du
 * tableur de maillage (21 articles conseils, ids 5419 à 5440). Même gabarit que
 * la page 1000 : 4 blocs thématiques, sommaire à 8 entrées, blocs communs
 * mutualisés dans `_shared.ts`.
 *
 * IMAGES — 26 emplacements sur 26, tous pourvus depuis le 2026-08-07.
 *
 * Règle du modèle : un emplacement sans visuel livré n'a PAS de champ `image`,
 * jamais de chemin inventé. Les composants dégradent proprement (aplat, icône).
 * `registry.test.ts` vérifie les deux sens : toute image déclarée existe sur le
 * disque, et aucun fichier du dossier n'est laissé sans référence.
 *
 * Les fichiers livrés portaient des noms avec espaces, accents et `&`
 * (« Réglementation & démarches.jpg ») : renommés en kebab-case ASCII pour rester
 * cohérents avec le reste du dépôt et éviter les chemins encodés.
 *
 * ⚠️ Les cartes LATÉRALES des layouts `overlay-*` n'ont pas d'emplacement image
 * (seule l'icône y est rendue). Les visuels des articles 5420, 5421, 5423, 5424
 * et 5425 ont donc été sortis de `/public` : les laisser aurait fait échouer le
 * contrôle des fichiers orphelins.
 */
const SLUG = 'ouvrir-food-truck';
const IMG = `/images/hub/${SLUG}`;
const CONSEILS = 'https://conseils.hellopro.fr';

/**
 * Vignette d'article, nommée par l'id de la page conseil.
 *
 * Les fichiers source portent le H1 en nom : espaces, apostrophes typographiques
 * et accents, inexploitables dans une URL. On les renomme par id à la copie dans
 * `/public` — court, stable, insensible à une retouche de titre.
 */
const articleImage = (id: number, alt: string) => ({
  src: `${IMG}/articles/${id}.jpg`,
  alt,
});

/**
 * Couverture du guide — le MÊME visuel est affiché à cinq endroits (bandeau
 * guide, CTA final, pop-up, écran de téléchargement du dialog, remerciement du
 * questionnaire). Constante plutôt que cinq littéraux : un changement de fichier
 * ou d'`alt` ne peut plus n'être appliqué qu'à quatre d'entre eux.
 *
 * ⚠️ PNG DÉTOURÉ, et c'est nécessaire : sur l'aplat bleu nuit du CTA final et
 * dans la pop-up, un JPG à fond opaque dessinerait un rectangle blanc autour du
 * livre. Ne pas revenir à un JPG.
 */
const GUIDE_COVER = {
  src: `${IMG}/livre-food-truck.png`,
  alt: 'Guide complet — Ouvrir votre food truck',
};

/** URL publique d'un article conseil. */
const conseilUrl = (slug: string, id: number) => `${CONSEILS}/${slug}-${id}.html`;

export const ouvrirFoodTruck: HubPage = {
  id: 1001,
  slug: SLUG,

  // Métadonnées validées le 2026-08-06 (cf. docs/hub-pages-meta.md).
  // `title` part VERBATIM : le suffixe « | Hellopro » fait partie de la chaîne.
  meta: {
    title: 'Ouvrir un food truck : guide complet étape par étape | Hellopro',
    description:
      'Lancez votre food truck sans rien oublier : démarches, matériel, emplacement, budget. Guide gratuit à télécharger, accompagnement sans engagement.',
  },

  // 1er = Accueil, dernier = titre de page. Les items intermédiaires alimentent
  // `product.category1` et `category5` dans GA4 (cf. GtmFooterScripts) :
  // ici `CHR-Café-Hôtel-Restaurant` et `Cuisson-mobile`.
  breadcrumb: [
    { label: 'Accueil', href: 'https://www.hellopro.fr/' },
    { label: 'CHR - Café Hôtel Restaurant' },
    { label: 'Cuisson mobile' },
    { label: 'Ouvrir un food truck' },
  ],

  hero: {
    badge: "Préparez l'ouverture de votre food-truck",
    titleParts: [
      { text: 'Ouvrir un ' },
      { text: 'food truck', accent: true },
      { text: ' rentable étape par étape' },
    ],
    // « Promesse : RAS » et « Social proof : RAS » au cahier des charges → repris
    // de la page 1000, ces formulations ne portent aucun vocabulaire métier.
    subtitle:
      'Recevez en moins de 2 minutes une estimation de budget, les équipements nécessaires et les étapes clés de votre projet.',
    background: { src: `${IMG}/hero-food-truck.jpg`, alt: 'Food truck en service sur un festival' },
    features: [
      { icon: 'users', title: 'Besoin qualifié', desc: 'Compréhension précise de votre projet' },
      {
        icon: 'phone',
        title: 'Appel avec un conseiller',
        desc: 'Conseils personnalisés et recommandations',
      },
      {
        icon: 'route',
        title: 'Mise en relation progressive',
        desc: 'Fournisseurs adaptés à chaque étape',
      },
    ],
    trust: {
      rating: '4.3/5 de satisfaction',
      suppliers: '+15 000 fournisseurs certifiés',
    },
  },

  // ⚠️ Ne plus renommer ces id une fois la page en ligne : ce sont les ancres
  // publiques du sommaire, elles se retrouvent dans les liens partagés.
  nav: [
    { id: HUB_SECTION_IDS.valueProps, label: 'Découvrir', icon: 'search' },
    { id: 'budget-financement', label: 'Budget & financement', icon: 'wallet' },
    { id: 'cadrage-projet', label: 'Cadrage du projet', icon: 'compass' },
    { id: 'reglementation-demarches', label: 'Réglementation', icon: 'file-text' },
    { id: 'equipements', label: 'Équipements', icon: 'wrench' },
    { id: HUB_SECTION_IDS.guideCta, label: 'Guide gratuit', icon: 'download' },
    { id: HUB_SECTION_IDS.faq, label: 'FAQ', icon: 'help' },
    { id: HUB_SECTION_IDS.finalCta, label: 'Être accompagné', icon: 'mail' },
  ],

  // « Ce que vous gagnez : RAS » au cahier des charges → repris tel quel de la
  // page 1000. Ces quatre arguments portent sur le parcours HelloPro, pas sur le
  // métier : ils valent pour les trois verticales.
  valueProps: {
    title: 'Ce que vous gagnez pour votre projet',
    subtitle: 'Un accompagnement complet, 100% gratuit et sans engagement.',
    closing: 'Faites-vous accompagner à chaque étape de votre projet',
    items: [
      {
        tag: 'Accompagnement 360°',
        title: 'Un projet mieux cadré',
        desc: 'Une vision claire des priorités, des étapes et des choix structurants pour avancer avec méthode.',
        icon: 'compass',
        accent: 'primary',
      },
      {
        tag: 'Devis gratuit',
        title: 'Un premier budget estimatif',
        desc: "Une première enveloppe réaliste pour cadrer votre besoin, vos postes d'investissement et vos arbitrages.",
        icon: 'wallet',
        accent: 'cta',
      },
      {
        tag: 'Conseils personnalisés',
        title: 'Un conseiller qui vous guide',
        desc: 'Des recommandations concrètes pour éviter les erreurs de dimensionnement et sécuriser les prochaines étapes.',
        icon: 'user-check',
        accent: 'primary',
      },
      {
        tag: 'Mise en relation ciblée',
        title: 'Les bonnes solutions au bon moment',
        desc: "Des interlocuteurs et solutions adaptés à votre niveau d'avancement, sans perte de temps ni mauvais aiguillage.",
        icon: 'handshake',
        accent: 'cta',
      },
    ],
  },

  thematiques: [
    {
      id: 'budget-financement',
      tag: 'Budget & financement',
      tagIcon: 'piggy-bank',
      layout: 'overlay-left',
      overlay: {
        title: 'Quel budget pour ouvrir un food truck ?',
        image: articleImage(5419, 'Quel budget pour ouvrir un food truck ?'),
        // Paliers alignés sur l'edito budget (`quel-budget-prevoir`) : les deux
        // sont visibles sur la même page, toute divergence se verrait.
        intro:
          'Le budget pour ouvrir un food truck se situe entre <strong>40 000 et 120 000 €</strong> selon le prix du véhicule, son aménagement, les équipements de cuisine et le concept de restauration.',
        bullets: [
          '<strong>40 000 à 120 000 €</strong> de budget indicatif',
          "Environ <strong>30 % d'apport personnel</strong> pour faciliter l'obtention du financement",
          '<strong>5 000 à 10 000 €</strong> de réserve pour le stock de départ, la trésorerie et les imprévus',
        ],
        ctaLabel: 'Lire la suite',
        href: conseilUrl('quel-budget-pour-ouvrir-un-food-truck', 5419),
      },
      cards: [
        {
          icon: 'hand-coins',
          title: 'Quelles aides et subventions pour ouvrir un food truck ?',
          descriptionHtml:
            "Selon le profil, l'<strong>ARCE</strong> peut verser <strong>60 % des droits ARE</strong> restants en capital et le <strong>prêt d'honneur</strong> peut apporter <strong>1 000 à 80 000 €</strong> à taux zéro.",
          linkLabel: "Lire l'article",
          href: conseilUrl('quelles-aides-et-subventions-pour-ouvrir-un-food-truck', 5420),
        },
        {
          icon: 'truck',
          title: "Food truck neuf, d'occasion ou sur mesure : lequel choisir selon son budget ?",
          descriptionHtml:
            "Un food truck d'occasion coûte entre <strong>15 000 et 70 000 €</strong>, contre <strong>60 000 à 150 000 €</strong> pour un modèle neuf sur mesure : comparez la meilleure option.",
          linkLabel: "Lire l'article",
          href: conseilUrl(
            'food-truck-neuf-d-occasion-ou-sur-mesure-lequel-choisir-selon-son-budget',
            5421
          ),
        },
      ],
      guideButtonLabel: 'Télécharger le guide complet',
    },
    {
      id: 'cadrage-projet',
      tag: 'Cadrage du projet',
      tagIcon: 'compass',
      layout: 'overlay-right',
      overlay: {
        title: "Comment aménager l'intérieur d'un food truck professionnel ?",
        image: articleImage(5422, "Comment aménager l'intérieur d'un food truck professionnel ?"),
        intro:
          "Organisez l'espace autour de la préparation, de la cuisson, du lavage et du stockage pour limiter les déplacements et risques de contamination dans le food-truck.",
        bullets: [
          '<strong>Plans de travail et revêtements lavables</strong>, résistants et non toxiques',
          '<strong>Eau potable chaude et froide</strong> pour le lavage des mains, des ustensiles et des aliments',
          '<strong>Froid, extraction et rangements</strong> dimensionnés selon le menu et le rythme de service',
        ],
        ctaLabel: 'Lire la suite',
        href: conseilUrl(
          'comment-amenager-l-interieur-d-un-food-truck-professionnel-conforme-et-fonctionnel',
          5422
        ),
      },
      cards: [
        {
          icon: 'route',
          title: 'Ouvrir un food truck : les 8 étapes de A à Z',
          descriptionHtml:
            'Concept, marché, business plan, financement, véhicule, création, normes et emplacements : suivez ces <strong>8 étapes</strong> avant le lancement.',
          linkLabel: "Lire l'article",
          href: conseilUrl('ouvrir-un-food-truck-les-8-etapes-de-a-a-z', 5425),
        },
        {
          icon: 'utensils',
          title: 'Food truck burger, pizza, crêpe ou tacos : quel concept est le plus rentable ?',
          descriptionHtml:
            "Aucun <strong>concept de food-truck</strong> ne domine partout : comparez coût matière, ticket moyen, vitesse de service et demande locale.",
          linkLabel: "Lire l'article",
          href: conseilUrl(
            'food-truck-burger-pizza-crepe-ou-tacos-quel-concept-est-le-plus-rentable',
            5424
          ),
        },
        {
          icon: 'truck',
          title: 'Camion ou remorque food truck : quelle solution choisir pour démarrer ?',
          descriptionHtml:
            "Choisissez le <strong>camion</strong> pour changer souvent d'emplacement ; la <strong>remorque</strong> convient à une implantation plus stable avec véhicule tracteur.",
          linkLabel: "Lire l'article",
          href: conseilUrl(
            'camion-ou-remorque-food-truck-quelle-solution-choisir-pour-demarrer',
            5423
          ),
        },
      ],
      guideButtonLabel: 'Télécharger le guide complet',
    },
    {
      id: 'reglementation-demarches',
      tag: 'Réglementation & démarches',
      tagIcon: 'scale',
      // `carousel` et non `grid` (2026-08-07) : en grille, 4 cartes se répartissent
      // en 3 + 1, et la dernière ligne à moitié vide déséquilibre le bloc. Le
      // carrousel garde une piste pleine quel que soit le nombre de cartes.
      // Uniformisé sur toutes les pages HUB — voir la page 1000.
      layout: 'carousel',
      intro:
        'Anticipez les obligations administratives pour sécuriser votre projet et éviter les erreurs dès le départ.',
      cards: [
        {
          title: 'Quelles autorisations pour ouvrir un food-truck ?',
          image: articleImage(5437, 'Quelles autorisations pour ouvrir un food-truck ?'),
          href: conseilUrl('quelles-autorisations-pour-ouvrir-un-food-truck', 5437),
        },
        {
          title: "Comment mettre un food-truck aux normes et obtenir l'homologation VASP ?",
          image: articleImage(
            5439,
            "Comment mettre un food-truck aux normes et obtenir l'homologation VASP ?"
          ),
          href: conseilUrl(
            'comment-mettre-un-food-truck-aux-normes-et-obtenir-l-homologation-vasp',
            5439
          ),
        },
        {
          title: 'Carte de commerçant ambulant : est-elle obligatoire pour un food-truck ?',
          image: articleImage(
            5438,
            'Carte de commerçant ambulant : est-elle obligatoire pour un food-truck ?'
          ),
          href: conseilUrl(
            'carte-de-commercant-ambulant-est-elle-obligatoire-pour-un-food-truck',
            5438
          ),
        },
        {
          title: 'Quel permis pour conduire un food-truck ?',
          image: articleImage(5440, 'Quel permis pour conduire un food-truck ?'),
          href: conseilUrl('quel-permis-pour-conduire-un-food-truck', 5440),
        },
      ],
    },
    {
      id: 'equipements',
      tag: 'Équipements',
      tagIcon: 'wrench',
      layout: 'carousel',
      intro:
        "Comparez les équipements indispensables grâce à notre catalogue de plus d'1 million de produits pour vous aider à structurer votre projet.",
      cards: [
        {
          title: 'Liste des 32 équipements indispensables pour lancer un food truck',
          image: articleImage(5426, 'Liste des 32 équipements indispensables pour lancer un food truck'),
          href: conseilUrl('liste-des-32-equipements-indispensables-pour-lancer-un-food-truck', 5426),
        },
        {
          title: 'Froid professionnel pour food truck : quelle capacité prévoir ?',
          image: articleImage(5431, 'Froid professionnel pour food truck : quelle capacité prévoir ?'),
          href: conseilUrl('froid-professionnel-pour-food-truck-quelle-capacite-prevoir', 5431),
        },
        {
          title: 'Matériel de cuisson food truck : plancha, friteuse, four ou crêpière ?',
          image: articleImage(
            5427,
            'Matériel de cuisson food truck : plancha, friteuse, four ou crêpière ?'
          ),
          href: conseilUrl(
            'materiel-de-cuisson-food-truck-plancha-friteuse-four-ou-crepiere',
            5427
          ),
        },
        {
          title: 'Hotte, ventilation et extraction : que prévoir dans un food truck ?',
          image: articleImage(
            5428,
            'Hotte, ventilation et extraction : que prévoir dans un food truck ?'
          ),
          href: conseilUrl(
            'hotte-ventilation-et-extraction-que-prevoir-dans-un-food-truck',
            5428
          ),
        },
        {
          title: 'Gaz ou électrique dans un food truck : quelle énergie choisir ?',
          image: articleImage(5429, 'Gaz ou électrique dans un food truck : quelle énergie choisir ?'),
          href: conseilUrl('gaz-ou-electrique-dans-un-food-truck-quelle-energie-choisir', 5429),
        },
        {
          title: 'Groupe électrogène pour food truck : quelle puissance choisir ?',
          image: articleImage(5430, 'Groupe électrogène pour food truck : quelle puissance choisir ?'),
          href: conseilUrl('groupe-electrogene-pour-food-truck-quelle-puissance-choisir', 5430),
        },
        {
          title: 'Caisse, TPE et prise de commande : comment encaisser vite en food truck ?',
          image: articleImage(
            5432,
            'Caisse, TPE et prise de commande : comment encaisser vite en food truck ?'
          ),
          href: conseilUrl(
            'caisse-tpe-et-prise-de-commande-comment-encaisser-vite-en-food-truck',
            5432
          ),
        },
      ],
    },
  ],

  accompagnementBanner: {
    tag: 'Accompagnement gratuit',
    title: 'Faites-vous accompagner pour ouvrir votre food-truck',
    // « Sous-titre : RAS » → repris de la page 1000, sans vocabulaire métier.
    text: "Bénéficiez d'un échange qualifié pour cadrer votre besoin, valider vos priorités et avancer avec les bons interlocuteurs.",
    ctaLabel: 'Être accompagné gratuitement',
    // Position au cahier des charges : le CTA suit le bloc « Cadrage du projet ».
    afterThematiqueId: 'cadrage-projet',
    image: {
      src: `${IMG}/cta-accompagnement-gratuit.jpg`,
      alt: 'Échange avec un conseiller Hellopro',
    },
  },

  // « CTA Guide gratuit : RAS » → repris de la page 1000.
  guideCta: {
    tag: 'Guide gratuit',
    title: 'Téléchargez votre guide de démarrage',
    text: 'Tous les repères essentiels pour cadrer votre budget, choisir vos équipements, comprendre la réglementation et avancer sereinement.',
    ctaLabel: 'Télécharger mon guide',
    image: GUIDE_COVER,
  },

  ressources: {
    title: 'Nos ressources pour ouvrir votre food-truck',
    subtitle:
      'Guides, conseils pratiques et ressources expertes pour vous aider à structurer votre projet.',
    items: [
      {
        tag: 'Exploitation',
        title:
          "Festivals et marchés : comment obtenir les meilleurs emplacements pour son food truck ?",
        image: articleImage(
          5436,
          "Festivals et marchés : comment obtenir les meilleurs emplacements pour son food truck ?"
        ),
        href: conseilUrl(
          'festivals-et-marches-comment-obtenir-les-meilleurs-emplacements-pour-son-food-truck',
          5436
        ),
      },
      {
        tag: 'Exploitation',
        title:
          'Marchés, événements, emplacements privés : comment équiper un food truck pour vendre partout ?',
        image: articleImage(
          5433,
          'Marchés, événements, emplacements privés : comment équiper un food truck pour vendre partout ?'
        ),
        href: conseilUrl(
          'marches-evenements-emplacements-prives-comment-equiper-un-food-truck-pour-vendre-partout',
          5433
        ),
      },
      {
        tag: 'Exploitation',
        title: 'Food truck événementiel : comment se positionner sur les mariages ?',
        image: articleImage(
          5434,
          'Food truck événementiel : comment se positionner sur les mariages ?'
        ),
        href: conseilUrl(
          'food-truck-evenementiel-comment-se-positionner-sur-les-mariages',
          5434
        ),
      },
    ],
  },

  grandesEtapes: {
    title: "Explorez les grandes étapes pour l'ouverture de votre food-truck",
    items: [
      {
        label: 'Budget & financement',
        href: '#budget-financement',
        image: { src: `${IMG}/etapes/budget-financement.jpg`, alt: 'Budget & financement' },
      },
      {
        label: 'Cadrage du projet',
        href: '#cadrage-projet',
        image: { src: `${IMG}/etapes/cadrage-projet.jpg`, alt: 'Cadrage du projet' },
      },
      {
        label: 'Équipements',
        href: '#equipements',
        image: { src: `${IMG}/etapes/equipements.jpg`, alt: 'Équipements' },
      },
      {
        // Aucun bloc thématique « Exploitation » : la tuile renvoie vers le bloc
        // ressources, dont les 3 articles portent justement ce tag.
        label: 'Exploitation',
        href: `#${HUB_SECTION_IDS.ressources}`,
        image: { src: `${IMG}/etapes/exploitation.jpg`, alt: 'Exploitation' },
      },
      {
        label: 'Réglementation & démarches',
        href: '#reglementation-demarches',
        image: { src: `${IMG}/etapes/reglementation.jpg`, alt: 'Réglementation & démarches' },
      },
    ],
  },

  editos: [
    {
      // Ancres dérivées du titre : elles portent les mots-clés et restent
      // lisibles dans un lien partagé.
      id: 'quel-budget-prevoir',
      title: 'Quel budget prévoir pour ouvrir un food-truck ?',
      intro:
        "Le budget nécessaire pour ouvrir un food-truck se situe généralement entre <strong>30 000 et 100 000 €</strong>. Il peut dépasser <strong>150 000 €</strong> pour un camion neuf aménagé sur mesure, avec un habillage complet et un équipement de cuisson haut de gamme :",
      // L'intro se termine par un deux-points : la liste doit la suivre
      // immédiatement. Sans ce réglage, les deux paragraphes de `bodyHtml`
      // s'intercalaient entre l'annonce et la liste (constaté le 2026-08-24).
      itemsPosition: 'after-intro',
      items: [
        "<strong>Remorque food-truck d'occasion</strong> avec équipement à reprendre : 10 000 à 20 000 €",
        '<strong>Remorque food-truck neuve de moins de 3 mètres :</strong> 9 000 à 15 000 €',
        '<strong>Remorque food-truck neuve de 3 à 4 mètres :</strong> 15 000 à 25 000 €',
        '<strong>Remorque food-truck neuve de plus de 4 mètres :</strong> 25 000 à 50 000 €',
        "<strong>Camion aménagé d'occasion :</strong> 30 000 à 50 000 €",
        '<strong>Camion neuf aménagé sur mesure :</strong> 80 000 à 150 000 €',
      ],
      bodyHtml:
        "<p>À ce poste principal s'ajoutent l'équipement de cuisson et de froid, à prévoir entre <strong>10 000 et 15 000 €</strong> lorsque le véhicule est livré nu, l'installation électrique et gaz, le groupe électrogène, la hotte d'extraction, l'habillage extérieur et l'identité visuelle, la caisse et le terminal de paiement, ainsi que le stock de départ et la trésorerie des premiers mois.</p>" +
        "<p>Les charges récurrentes doivent être intégrées dès le prévisionnel : l'assurance d'un food-truck représente <strong>100 à 300 € par mois</strong>, les emplacements varient de quelques dizaines d'euros pour un droit de place sur un marché communal à <strong>plus de 1 000 € par jour</strong> pour un événement à forte fréquentation, auxquels s'ajoutent le carburant, le gaz, l'entretien du véhicule et la maintenance des équipements.</p>",
    },
    {
      id: 'camion-ou-remorque',
      title: 'Camion ou remorque food-truck : quel véhicule choisir ?',
      intro:
        "Le choix du véhicule food-truck détermine l'investissement de départ, le permis nécessaire et la souplesse d'exploitation.",
      // ⚠️ Seul bloc éditorial des 3 pages HUB à comporter des SOUS-TITRES. Les
      // `h3` sont autorisés dans le corps depuis le 2026-08-07 (cf. sanitize.ts) :
      // le titre du bloc étant un `h2`, ils s'y emboîtent correctement.
      bodyHtml:
        '<h3>La remorque food-truck</h3>' +
        "<p>Une remorque food-truck est un module de restauration tracté par un véhicule léger. C'est le format au ticket d'entrée le plus bas, entre <strong>9 000 et 50 000 €</strong> en neuf selon la longueur et les équipements. Elle se déplace sans immobiliser le véhicule tracteur, qui reste disponible pour les approvisionnements, et permet de laisser le point de vente sur un emplacement sécurisé entre deux services. Le <strong>permis B</strong> suffit lorsque le PTAC de la remorque ne dépasse pas 750 kg ou lorsque le PTAC de l'ensemble reste sous 3 500 kg. Au-delà, une <strong>formation B96</strong> est requise jusqu'à 4 250 kg, puis le <strong>permis BE</strong> jusqu'à 7 tonnes.</p>" +
        '<h3>Le camion aménagé</h3>' +
        "<p>Un camion aménagé intègre la cuisine dans le véhicule lui-même. Il compte de <strong>30 000 à 50 000 €</strong> en occasion et de <strong>80 000 à 150 000 €</strong> en neuf sur mesure. Il offre une meilleure autonomie, une installation plus rapide sur site et une image de marque plus forte, mais il immobilise le véhicule pendant le service et son entretien mécanique reste à la charge de l'exploitant. Un camion dont le PTAC dépasse 3 500 kg impose le <strong>permis C</strong>.</p>",
    },
    {
      id: 'demarches-obligatoires',
      title: 'Quelles démarches sont obligatoires pour ouvrir un food-truck ?',
      intro:
        "L'ouverture d'un food-truck suppose plusieurs formalités, indépendantes de l'achat du véhicule et à engager plusieurs semaines avant le lancement.",
      items: [
        "<strong>Immatriculation de l'entreprise :</strong> micro-entreprise, EURL ou SASU selon le chiffre d'affaires visé, le régime social souhaité et la présence d'associés",
        "<strong>Carte permettant l'exercice d'une activité commerciale ambulante :</strong> obligatoire pour exercer en dehors de la commune de domiciliation, délivrée par la chambre de métiers et de l'artisanat ou la chambre de commerce pour 30 € et valable 4 ans, avec une attestation provisoire remise immédiatement et une carte définitive sous 15 à 30 jours",
        "<strong>Formation à l'hygiène alimentaire :</strong> 14 heures auprès d'un organisme agréé, obligatoire pour au moins une personne de l'établissement, sauf diplôme du secteur ou trois années d'expérience comme gestionnaire en entreprise alimentaire",
        "<strong>Déclaration d'activité auprès de la direction départementale de la protection des populations</strong>, à effectuer avant l'ouverture",
        "<strong>Autorisation d'occupation du domaine public</strong> délivrée par la mairie pour chaque emplacement, ou droit de place pour un marché, ou convention avec le propriétaire sur un terrain privé",
        "<strong>Licence de vente de boissons alcoolisées et permis d'exploitation</strong>, uniquement si l'offre comprend de l'alcool",
        '<strong>Assurances :</strong> responsabilité civile professionnelle, assurance du véhicule et garantie du matériel embarqué',
      ],
    },
  ],

  // Blocs communs — cf. `_shared.ts`. « Comment ça marche » est inséré APRÈS le
  // dernier édito, conformément à l'ordre du cahier des charges.
  howItWorks: { ...HOW_IT_WORKS, afterEditoId: 'demarches-obligatoires' },

  accompagnement: {
    ...ACCOMPAGNEMENT,
    image: { src: `${IMG}/accompagnement-expert.jpg`, alt: 'Échange avec un conseiller Hellopro' },
  },

  finalCta: {
    badge: '🎁 100% Gratuit & sans engagement',
    titleParts: [
      { text: 'Recevez gratuitement votre ' },
      { text: 'guide et plan projet', accent: true },
      { text: ' pour ouvrir votre food-truck' },
    ],
    text: 'Un plan projet personnalisé et des conseils pratiques pour structurer votre food-truck, étape par étape, et maximiser vos chances de réussite.',
    items: [
      { icon: 'clipboard', label: 'Plan projet personnalisé' },
      { icon: 'users-group', label: 'Conseils et retours terrain' },
      { icon: 'shield', label: 'Contenu fiable et à jour' },
    ],
    ctaLabel: 'Recevoir mon guide gratuit',
    reassurance: 'Vos informations sont sécurisées et ne seront jamais partagées.',
    image: GUIDE_COVER,
  },

  faq: FAQ,

  stickyCtaLabel: 'Être accompagné gratuitement',

  assistant: {
    cardTitle: 'Parlez de votre projet à un conseiller',
    ctaLabel: "Démarrer l'étude du projet",
    reassurance: 'Un guide de démarrage vous sera envoyé immédiatement après validation.',
    steps: [
      {
        id: 'projet',
        label: 'Quel projet de food truck souhaitez-vous concrétiser ?',
        multi: false,
        options: [
          'Lancer mon premier food truck',
          'Reprendre un food truck en activité',
          'Renouveler mon camion ou mes équipements',
          'Étudier la faisabilité de mon idée',
        ],
        illustrations: ['lightbulb', 'handshake', 'wrench', 'compass'],
      },
      {
        id: 'specialite',
        // ⚠️ SEULE étape à choix MULTIPLE des 3 pages HUB (case à cocher au cahier
        // des charges). Conséquence : pas d'auto-avance — le dialog affiche un
        // bouton « Continuer », actif dès qu'une option est cochée. Cette étape
        // doit donc rester en position 2 ou plus : en position 1 elle serait
        // rendue dans le hero, dont le bouton s'active sur une valeur non vide et
        // laisserait passer une sélection vide.
        label: 'Quelle spécialité envisagez-vous pour votre food-truck ?',
        multi: true,
        options: [
          'Burgers, sandwichs, tacos ou hot-dogs',
          'Pizzeria',
          'Cuisine du monde ou régionale',
          'Rôtisserie, grillades ou barbecue',
          'Crêperie, gaufrerie, glacerie ou desserts',
          'Café et boissons',
          'Autre',
          'Je ne sais pas encore',
        ],
      },
      {
        id: 'vehicule',
        label: 'Où en êtes-vous dans le choix du véhicule food-truck ?',
        multi: false,
        options: [
          'Le véhicule est acheté ou commandé',
          'Je compare des véhicules / des devis',
          "Je sais ce que je veux, je n'ai pas encore consulté",
          "Je n'ai pas encore commencé mes recherches",
          'Je souhaite être conseillé(e)',
        ],
      },
      {
        id: 'budget',
        label: 'Quel budget prévoyez-vous pour lancer votre food truck ?',
        multi: false,
        options: [
          'Moins de 50 000 €',
          'De 50 000 à 100 000 €',
          'De 100 000 à 150 000 €',
          'Plus de 150 000 €',
          'Mon budget reste à définir',
        ],
      },
    ],
    contact: {
      badge: 'Presque terminé',
      label: 'À quelle adresse e-mail souhaitez-vous être contacté(e) ?',
      emailPlaceholder: 'votre.email@entreprise.fr',
      submitLabel: 'Continuer',
    },
    coordinates: {
      badge: 'Dernière étape',
      label: 'Pour terminer, qui fait cette demande ?',
      helper: 'Vos informations sont utilisées uniquement pour vous répondre.',
      civilityLabel: 'Civilité',
      civilityOptions: ['Monsieur', 'Madame'],
      fields: {
        name: 'Nom',
        prenom: 'Prénom',
        phone: 'Numéro de téléphone',
        postalCode: 'Code postal',
      },
      submitLabel: 'Continuer',
    },
    success: {
      title: 'Merci ! Votre projet est bien enregistré',
      subtitle:
        'Pour vous aider à avancer, nous vous offrons gratuitement un guide de démarrage. Vous pouvez aussi le récupérer à nouveau à tout moment.',
      image: GUIDE_COVER,
      downloadLabel: 'Télécharger à nouveau le guide',
      // PDF de test, comme la page 1000. À remplacer par le guide food truck.
      fileUrl: '/seo_masterclass_detailed.pdf',
    },
  },

  guideDialog: {
    badge: 'Télécharger le guide complet',
    titleParts: [
      { text: 'Recevez le ' },
      { text: 'guide complet', accent: true },
      { text: ' pour ouvrir votre ' },
      { text: 'food-truck', accent: true },
    ],
    fields: {
      name: 'Nom',
      prenom: 'Prénom',
      email: 'Adresse e-mail',
      phone: 'Numéro de téléphone',
      postalCode: 'Code postal',
    },
    emailPlaceholder: 'votre.email@entreprise.fr',
    emailSubmitLabel: 'Continuer',
    coordinatesBadge: 'Dernière étape',
    coordinatesTitle: 'Votre guide est presque prêt',
    coordinatesSubtitle: 'Renseignez vos coordonnées pour télécharger votre guide',
    civilityLabel: 'Civilité',
    civilityOptions: ['Monsieur', 'Madame'],
    coordinatesSubmitLabel: 'Recevoir mon guide complet',
    trust: ['Un guide pratique et détaillé', '100% gratuit et sans engagement'],
    download: {
      title: 'Merci ! Votre guide est prêt',
      subtitle: 'Le téléchargement démarre automatiquement.',
      note: 'Vous pouvez aussi le récupérer à nouveau à tout moment.',
      image: GUIDE_COVER,
      buttonLabel: 'Télécharger à nouveau le guide',
      fileUrl: '/seo_masterclass_detailed.pdf',
    },
  },

  leadPopup: {
    badge: '🎁 Guide 100% gratuit + contenus exclusifs',
    title: 'Lancez votre food-truck sur de bonnes bases',
    scriptLine: 'avec un guide complet',
    // « Autre : RAS » → repris de la page 1000, adapté à la verticale.
    text: "Un guide complet pour structurer votre projet de A à Z : étapes clés, équipements indispensables, budget estimatif et points de vigilance pour ouvrir votre food-truck.",
    emailPlaceholder: 'Votre adresse e-mail',
    submitLabel: 'Continuer',
    reassurance: '100% gratuit, sans engagement',
    circleBadgeLines: ['100%', 'Gratuit'],
    image: GUIDE_COVER,
    bannerImage: { src: `${IMG}/pop-up-food-truck.jpg`, alt: 'Food truck en service' },
    // Même position que la page 1000 : la pop-up se déclenche une fois le bloc
    // réglementation dépassé, signe d'une lecture significative.
    triggerSectionId: 'reglementation-demarches',
  },
};
