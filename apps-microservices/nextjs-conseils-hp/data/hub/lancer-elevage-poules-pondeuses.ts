import type { HubPage } from '@/types/hub';
import { HUB_SECTION_IDS } from '@/lib/hub/anchors';
import { ACCOMPAGNEMENT, FAQ, HOW_IT_WORKS } from './_shared';

/**
 * Page HUB 1000 — « Lancer un élevage de poules pondeuses ».
 * URL : /lancer-elevage-poules-pondeuses-1000-projet.html
 *
 * Contenu repris du prototype Lovable (`Project Navigator/src/routes/index.tsx`),
 * verbatim, en ne conservant QUE les sections réellement montées par `ProjectHub`.
 * Les ~22 composants morts du prototype ne sont pas portés.
 *
 * IMAGES — les 25 emplacements sont pourvus.
 *
 * Règle : un emplacement sans visuel livré n'a **pas** de champ `image` — pas de
 * chemin inventé, pas d'image approximative. Les composants dégradent proprement.
 * `registry.test.ts` vérifie les deux sens : toute image déclarée existe sur le
 * disque, et aucun fichier du dossier n'est laissé sans référence.
 */
const SLUG = 'lancer-elevage-poules-pondeuses';
const IMG = `/images/hub/${SLUG}`;
const CONSEILS = 'https://conseils.hellopro.fr';

/**
 * Vignette d'article, nommée par l'id de la page conseil.
 *
 * Les fichiers source (`Projet HUB/images compressées`) portent le H1 en nom :
 * espaces, virgules, apostrophes typographiques et accents. Inexploitable dans
 * une URL. On les renomme donc par id au moment de la copie dans `/public` —
 * court, stable, et insensible à une retouche de titre.
 */
const articleImage = (id: number, alt: string) => ({
  src: `${IMG}/articles/${id}.jpg`,
  alt,
});

/** URL publique d'un article conseil. */
const conseilUrl = (slug: string, id: number) => `${CONSEILS}/${slug}-${id}.html`;

export const lancerElevagePoulesPondeuses: HubPage = {
  id: 1000,
  slug: SLUG,

  meta: {
    title: 'Lancer son élevage de poules pondeuses — Hellopro',
    description:
      "Hellopro accompagne les porteurs de projets agricoles de l'idée à la mise en production : budget, bâtiment, équipements, conformité et fournisseurs.",
    // Vignette de partage social. Sans elle, `openGraph.images` sortait vide.
    ogImage: `${IMG}/hero-poules.jpg`,
  },

  // 1er = Accueil, dernier = titre de page (convention GtmFooterScripts :
  // les items intermédiaires alimentent category1..5).
  // ⚠️ Les 2 items de catégorie n'ont volontairement PAS de href : les URLs de
  // rubrique cibles ne sont pas encore arrêtées. Ils servent au tracking GTM
  // (category1 / category5) ; le JSON-LD BreadcrumbList n'inclut que les items
  // réellement adressables (cf. app/@head/hub/[hubSlug]/page.tsx).
  breadcrumb: [
    { label: 'Accueil', href: 'https://www.hellopro.fr/' },
    { label: 'Agriculture' },
    { label: 'Élevage avicole' },
    { label: 'Lancer son élevage de poules pondeuses' },
  ],

  hero: {
    badge: 'Accompagnement gratuit',
    titleParts: [
      { text: 'Lancez votre élevage de ' },
      { text: 'poules pondeuses', accent: true },
      { text: ' en toute sérénité' },
    ],
    subtitle:
      'Recevez en moins de 2 minutes une estimation de budget, les équipements nécessaires et les étapes clés de votre projet.',
    background: { src: `${IMG}/hero-poules.jpg`, alt: 'Élevage de poules pondeuses' },
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

  // Les 8 entrées du sommaire sticky. Les id viennent soit de `HUB_SECTION_IDS`
  // (sections fixes), soit des `thematiques[].id` ci-dessous.
  // ⚠️ Ne plus les renommer une fois la page en ligne : ça casserait les liens
  // profonds déjà partagés.
  nav: [
    { id: HUB_SECTION_IDS.valueProps, label: 'Découvrir', icon: 'search' },
    { id: 'budget-financement', label: 'Budget & financement', icon: 'wallet' },
    { id: 'dimensionnement-projet', label: 'Dimensionnement', icon: 'ruler' },
    { id: 'reglementation-demarches', label: 'Réglementation', icon: 'file-text' },
    { id: 'equipements', label: 'Équipements', icon: 'wrench' },
    { id: HUB_SECTION_IDS.guideCta, label: 'Guide gratuit', icon: 'download' },
    { id: HUB_SECTION_IDS.faq, label: 'FAQ', icon: 'help' },
    { id: HUB_SECTION_IDS.finalCta, label: 'Être accompagné', icon: 'mail' },
  ],

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
        title: 'Quel budget prévoir pour créer un élevage de poules pondeuses professionnel ?',
        image: articleImage(
          5297,
          'Quel budget prévoir pour créer un élevage de poules pondeuses professionnel ?'
        ),
        // Paliers alignés sur l'edito budget (`quel-budget-prevoir`), qui fait référence.
        // Les deux sont visibles sur la même page : toute divergence se voit.
        intro:
          "Le budget pour créer un élevage de poules pondeuses varie de 30 000 € à 1,5 million d'euros selon la taille du troupeau.",
        bullets: [
          '500 à 1 500 pondeuses : 30 000 à 100 000 €',
          '3 000 à 10 000 pondeuses : 150 000 à 550 000 €',
          '20 000 à 25 000 pondeuses : 1 000 000 à 1 500 000 €',
        ],
        ctaLabel: 'Lire la suite',
        href: conseilUrl(
          'quel-budget-prevoir-pour-creer-un-elevage-de-poules-pondeuses-professionnel',
          5297
        ),
      },
      cards: [
        {
          icon: 'home',
          title: 'Comment financer un bâtiment avicole pour poules pondeuses ?',
          descriptionHtml:
            'Le financement combine <strong>apport personnel</strong>, <strong>prêt bancaire agricole</strong> et aides régionales <strong>FEADER/PCAE</strong>, pouvant couvrir <strong>30 à 40 % des dépenses</strong>.',
          linkLabel: "Lire l'article",
          href: conseilUrl('comment-financer-un-batiment-avicole-pour-poules-pondeuses', 5270),
        },
        {
          icon: 'hand-coins',
          title: 'Quelles aides et subventions pour créer un élevage de poules pondeuses ?',
          descriptionHtml:
            "Le projet peut bénéficier de la <strong>DJA</strong>, des subventions régionales <strong>FEADER/PCAE</strong>, de l'aide <strong>PAC aux jeunes agriculteurs</strong> pendant 5 ans.",
          linkLabel: "Lire l'article",
          href: conseilUrl(
            'quelles-aides-et-subventions-pour-creer-un-elevage-de-poules-pondeuses',
            5291
          ),
        },
      ],
      guideButtonLabel: 'Télécharger le guide complet',
    },
    {
      id: 'dimensionnement-projet',
      tag: 'Dimensionnement du projet',
      tagIcon: 'ruler',
      layout: 'overlay-right',
      overlay: {
        title: 'Quelle surface prévoir pour un élevage de poules pondeuses professionnel ?',
        image: articleImage(
          5287,
          'Quelle surface prévoir pour un élevage de poules pondeuses professionnel ?'
        ),
        intro:
          "La surface d'un élevage de poules pondeuses est calculée selon le <strong>nombre de poules</strong>, le <strong>mode d'élevage</strong> et le parcours extérieur.",
        bullets: [
          "Jusqu'à <strong>9 poules par m² de surface utilisable</strong> pour un élevage en plein air",
          "Jusqu'à <strong>6 poules par m² en bâtiment</strong> en agriculture biologique",
          'Au moins <strong>4 m² de parcours extérieur par poule</strong>',
        ],
        ctaLabel: "Lire l'article",
        href: conseilUrl(
          'quelle-surface-prevoir-pour-un-elevage-de-poules-pondeuses-professionnel',
          5287
        ),
      },
      cards: [
        {
          icon: 'home',
          title:
            'Bâtiment fixe ou poulailler mobile : quelle solution choisir pour des poules pondeuses ?',
          description:
            "Identifiez la solution la plus adaptée à votre élevage de poules pondeuses selon le budget, la mobilité et les contraintes d'exploitation.",
          linkLabel: "Lire l'article",
          href: conseilUrl(
            'batiment-fixe-ou-poulailler-mobile-quelle-solution-choisir-pour-des-poules-pondeuses',
            5309
          ),
        },
        {
          icon: 'calculator',
          title:
            'Bâtiment avicole neuf, rénovation ou poulailler mobile : quel investissement choisir ?',
          description:
            "Comparez les coûts, les contraintes et le niveau d'équipement de chaque solution pour votre élevage de poules pondeuses.",
          linkLabel: "Lire l'article",
          href: conseilUrl(
            'batiment-avicole-neuf-renovation-ou-poulailler-mobile-quel-investissement-choisir',
            5285
          ),
        },
        {
          icon: 'file-text',
          title: 'Lancer son élevage de poules pondeuses : guide complet',
          description:
            'Découvrez les étapes, le budget, les équipements et les démarches à prévoir pour créer un élevage de poules pondeuses viable et conforme.',
          linkLabel: "Lire l'article",
          href: conseilUrl('lancer-son-elevage-de-poules-pondeuses-guide-complet', 5137),
        },
      ],
      guideButtonLabel: 'Télécharger le guide complet',
    },
    {
      id: 'reglementation-demarches',
      tag: 'Réglementation & démarches',
      tagIcon: 'scale',
      layout: 'grid',
      intro:
        'Anticipez les obligations administratives pour sécuriser votre projet et éviter les erreurs dès le départ.',
      cards: [
        {
          title:
            'Réglementation poules pondeuses : les équipements à prévoir pour être conforme',
          image: articleImage(
            5298,
            'Réglementation poules pondeuses : les équipements à prévoir pour être conforme'
          ),
          href: conseilUrl(
            'reglementation-poules-pondeuses-les-equipements-a-prevoir-pour-etre-conforme',
            5298
          ),
        },
        {
          title:
            'Permis, déclaration préalable ou rénovation : quelles autorisations pour un bâtiment avicole ?',
          image: articleImage(
            5271,
            'Permis, déclaration préalable ou rénovation : quelles autorisations pour un bâtiment avicole ?'
          ),
          href: conseilUrl(
            'permis-declaration-prealable-ou-renovation-quelles-autorisations-pour-un-batiment-avicole',
            5271
          ),
        },
        {
          title: 'Quelles démarches administratives pour créer un élevage de poules pondeuses ?',
          image: articleImage(
            5286,
            'Quelles démarches administratives pour créer un élevage de poules pondeuses ?'
          ),
          href: conseilUrl(
            'quelles-demarches-administratives-pour-creer-un-elevage-de-poules-pondeuses',
            5286
          ),
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
          title:
            'Liste des 24 équipements à prévoir pour lancer un atelier de poules pondeuses',
          image: articleImage(
            5289,
            'Liste des 24 équipements à prévoir pour lancer un atelier de poules pondeuses'
          ),
          href: conseilUrl(
            'liste-des-24-equipements-a-prevoir-pour-lancer-un-atelier-de-poules-pondeuses',
            5289
          ),
        },
        {
          title:
            "Abreuvoirs, lignes pipettes, traitement de l'eau : que prévoir pour un élevage pondeuses ?",
          image: articleImage(
            5312,
            "Abreuvoirs, lignes pipettes, traitement de l'eau : que prévoir pour un élevage pondeuses ?"
          ),
          href: conseilUrl(
            'abreuvoirs-lignes-pipettes-traitement-de-l-eau-que-prevoir-pour-un-elevage-pondeuses',
            5312
          ),
        },
        {
          title: 'Clôtures et protection du parcours : comment sécuriser un élevage plein air ?',
          image: articleImage(
            5311,
            'Clôtures et protection du parcours : comment sécuriser un élevage plein air ?'
          ),
          href: conseilUrl(
            'clotures-et-protection-du-parcours-comment-securiser-un-elevage-plein-air',
            5311
          ),
        },
        {
          title:
            "Silo, mangeoires, distribution automatique : comment organiser l'alimentation des pondeuses ?",
          image: articleImage(
            5310,
            "Silo, mangeoires, distribution automatique : comment organiser l'alimentation des pondeuses ?"
          ),
          href: conseilUrl(
            'silo-mangeoires-distribution-automatique-comment-organiser-l-alimentation-des-pondeuses',
            5310
          ),
        },
        {
          title: 'Ventilation et éclairage en bâtiment pondeuses : quels équipements choisir ?',
          image: articleImage(
            5308,
            'Ventilation et éclairage en bâtiment pondeuses : quels équipements choisir ?'
          ),
          href: conseilUrl(
            'ventilation-et-eclairage-en-batiment-pondeuses-quels-equipements-choisir',
            5308
          ),
        },
        {
          title: 'Sas sanitaire et biosécurité : comment équiper un élevage de poules pondeuses ?',
          image: articleImage(
            5295,
            'Sas sanitaire et biosécurité : comment équiper un élevage de poules pondeuses ?'
          ),
          href: conseilUrl(
            'sas-sanitaire-et-biosecurite-comment-equiper-un-elevage-de-poules-pondeuses',
            5295
          ),
        },
        {
          title: 'Comment dimensionner les pondoirs pour un élevage de poules pondeuses ?',
          image: articleImage(
            5272,
            'Comment dimensionner les pondoirs pour un élevage de poules pondeuses ?'
          ),
          href: conseilUrl(
            'comment-dimensionner-les-pondoirs-pour-un-elevage-de-poules-pondeuses',
            5272
          ),
        },
      ],
    },
  ],

  accompagnementBanner: {
    tag: 'Accompagnement gratuit',
    title: 'Faites-vous accompagner pour lancer votre élevage de poules pondeuses',
    text: "Bénéficiez d'un échange qualifié pour cadrer votre besoin, valider vos priorités et avancer avec les bons interlocuteurs.",
    ctaLabel: 'Être accompagné gratuitement',
    // Position d'origine du prototype : entre dimensionnement et réglementation.
    afterThematiqueId: 'dimensionnement-projet',
    image: {
      src: `${IMG}/cta-accompagnement-gratuit.jpg`,
      alt: 'Accompagnement gratuit par un expert avicole',
    },
  },

  guideCta: {
    tag: 'Guide gratuit',
    title: 'Téléchargez votre guide de démarrage',
    text: 'Tous les repères essentiels pour cadrer votre budget, choisir vos équipements, comprendre la réglementation et avancer sereinement.',
    ctaLabel: 'Télécharger mon guide',
    image: {
      src: `${IMG}/Livre_poules_pondeuses_removebg.png`,
      alt: 'Guide complet — Lancer votre élevage de poules pondeuses',
    },
  },

  // Le prototype déclarait 20 items puis n'en affichait que 3 (filtre sur le tag
  // « Exploitation »). On ne porte que les 3 réellement rendus — les 17 autres
  // étaient des données inertes. À élargir si le besoin est confirmé (plan §2.6).
  ressources: {
    title: 'Nos ressources pour lancer votre élevage de poules pondeuses',
    subtitle:
      'Guides, conseils pratiques et ressources expertes pour vous aider à structurer votre projet.',
    items: [
      {
        tag: 'Exploitation',
        title:
          "Vente d'œufs : quelles obligations pour marquer, conditionner et commercialiser sa production ?",
        image: articleImage(
          5296,
          "Vente d'œufs : quelles obligations pour marquer, conditionner et commercialiser sa production ?"
        ),
        href: conseilUrl(
          'vente-d-ufs-quelles-obligations-pour-marquer-conditionner-et-commercialiser-sa-production',
          5296
        ),
      },
      {
        tag: 'Exploitation',
        title: "Vente directe d'œufs : quel matériel prévoir pour stocker, emballer et vendre ?",
        image: articleImage(
          5290,
          "Vente directe d'œufs : quel matériel prévoir pour stocker, emballer et vendre ?"
        ),
        href: conseilUrl(
          'vente-de-oeufs-quelles-obligations-pour-marquer-conditionner-et-commercialiser-sa-production',
          5290
        ),
      },
      {
        tag: 'Exploitation',
        title:
          'Gestion des fientes et nettoyage du bâtiment avicole : quels équipements prévoir ?',
        image: articleImage(
          5306,
          'Gestion des fientes et nettoyage du bâtiment avicole : quels équipements prévoir ?'
        ),
        href: conseilUrl(
          'gestion-des-fientes-et-nettoyage-du-batiment-avicole-quels-equipements-prevoir',
          5306
        ),
      },
    ],
  },

  grandesEtapes: {
    title: "Explorez les grandes étapes de votre projet d'élevage",
    items: [
      {
        label: 'Budgets & financement',
        href: '#budget-financement',
        image: { src: `${IMG}/etapes/budget-financement.jpg`, alt: 'Budgets & financement' },
      },
      {
        label: 'Dimensionnement du projet',
        href: '#dimensionnement-projet',
        image: { src: `${IMG}/etapes/dimensionnement.jpg`, alt: 'Dimensionnement du projet' },
      },
      {
        label: 'Équipements',
        href: '#equipements',
        image: { src: `${IMG}/etapes/equipements.jpg`, alt: 'Équipements' },
      },
      {
        label: 'Réglementation & démarches',
        href: '#reglementation-demarches',
        image: {
          src: `${IMG}/etapes/reglementation.jpg`,
          alt: 'Réglementation & démarches',
        },
      },
      {
        // Aucun bloc thématique « Exploitation » : la tuile renvoie vers le bloc
        // ressources, dont les 3 articles portent justement ce tag.
        label: 'Exploitation',
        href: `#${HUB_SECTION_IDS.ressources}`,
        image: { src: `${IMG}/etapes/exploitation.jpg`, alt: 'Exploitation' },
      },
    ],
  },

  editos: [
    {
      // Ancres dérivées du titre de la section : elles portent les mots-clés de la
      // page et restent lisibles dans un lien partagé.
      id: 'pourquoi-lancer-un-elevage',
      title: "Pourquoi lancer un élevage de poules pondeuses aujourd'hui ?",
      bodyHtml:
        "<p>Le marché français de l'œuf connaît une croissance soutenue. En 2025, la production nationale a atteint environ <strong>15,9 milliards d'œufs</strong>, en hausse de 0,8 % sur un an. Dans le même temps, la consommation a établi un nouveau record avec <strong>237 œufs par habitant</strong>, soit une progression de la demande nationale de 5 %. La France reste le premier producteur d'œufs de l'Union européenne, mais sa production ne couvre plus totalement ses besoins : le taux d'auto-approvisionnement est passé de 99,4 % en 2024 à 95,8 % en 2025.</p>" +
        "<p>Cette situation ouvre des perspectives pour de nouveaux projets, à condition de sécuriser les débouchés avant d'investir. Les œufs issus d'élevages alternatifs occupent une place croissante : fin 2025, ils concerneraient 77 % des poules pondeuses françaises, dont 32 % en plein air, 26 % au sol, 13 % en bio et 6 % en Label Rouge.</p>",
      items: [
        '<strong>Production indicative :</strong> Entre 250 et 320 œufs par poule et par cycle annuel courant',
        '<strong>Production de 500 poules :</strong> Environ 125 000 à 160 000 œufs par an',
        '<strong>Prix en gros :</strong> Environ 0,17 à 0,19 € par œuf selon les cotations et les calibres',
        '<strong>Prix avec valorisation en circuit court ou par intermédiaire :</strong> Environ 0,26 à 0,30 € par œuf dans les références disponibles',
        "<strong>Chiffre d'affaires brut pour 500 poules :</strong> Environ 21 000 à 48 000 € par an selon le volume commercialisable et le circuit de vente",
      ],
    },
    {
      id: 'quel-budget-prevoir',
      title: 'Quel budget prévoir pour créer un élevage de poules pondeuses ?',
      intro:
        "Le <strong>budget pour créer un élevage de poules pondeuses</strong> va de 30 000 à 1,5 millions d'euros selon la capacité du bâtiment, le mode d'élevage, le niveau d'automatisation et des installations déjà présentes sur l'exploitation.",
      items: [
        '<strong>Élevage de 500 à 1 500 pondeuses :</strong> Entre 30 000 et 100 000 €',
        '<strong>Élevage de 3 000 à 10 000 pondeuses :</strong> Entre 150 000 et 550 000 €',
        '<strong>Élevage de 20 000 à 25 000 pondeuses :</strong> Entre 1 000 000 et 1 500 000 €',
      ],
      note: "À noter : Le poulailler représente en moyenne <strong>40 à 60 % du budget global</strong>. Le foncier, le besoin en fonds de roulement et plusieurs mois d'alimentation doivent être budgétés séparément.",
    },
    {
      id: 'quel-modele-elevage-choisir',
      title: "Quel modèle d'élevage choisir pour maximiser la performance ?",
      intro:
        "Le choix du modèle d'élevage détermine directement la rentabilité, les contraintes réglementaires et les investissements de départ.",
      bodyHtml:
        '<ul>' +
        '<li><strong>Élevage intensif</strong> : densité élevée, coûts maîtrisés, forte productivité mais prix de vente bas et contraintes de bien-être animal renforcées.</li>' +
        "<li><strong>Élevage au sol</strong> : bon équilibre entre productivité et coût d'installation, adapté aux exploitations souhaitant sortir du système cage.</li>" +
        '<li><strong>Élevage plein air</strong> : densité réduite, valorisation supérieure des œufs, investissement plus important en foncier et bâtiment.</li>' +
        '<li><strong>Élevage biologique</strong> : cahier des charges strict, coûts de production élevés mais prix de vente parmi les plus valorisés du marché.</li>' +
        '</ul>',
    },
    {
      id: 'pourquoi-se-faire-accompagner',
      title: "Pourquoi se faire accompagner dans son projet d'élevage ?",
      intro:
        "Un projet d'élevage de poules pondeuses mobilise de nombreuses expertises : dimensionnement, réglementation, équipements, financement. Un accompagnement adapté permet de :",
      items: [
        'Sécuriser les investissements initiaux',
        'Éviter les erreurs de dimensionnement',
        'Optimiser la rentabilité dès les premières phases d’exploitation',
      ],
    },
  ],

  // Contenu partagé par les 3 pages HUB — cf. `_shared.ts`. Seule la position
  // d'insertion est propre à cette page (entre les editos budget et modèle).
  howItWorks: { ...HOW_IT_WORKS, afterEditoId: 'quel-budget-prevoir' },

  // Contenu partagé par les 3 pages HUB — cf. `_shared.ts`. Seul le visuel est
  // propre à la page.
  accompagnement: {
    ...ACCOMPAGNEMENT,
    image: { src: `${IMG}/accompagnement-expert.jpg`, alt: 'Échange avec un conseiller Hellopro' },
  },

  finalCta: {
    badge: '🎁 100% Gratuit & sans engagement',
    titleParts: [
      { text: 'Recevez gratuitement votre ' },
      { text: 'guide et plan projet', accent: true },
      { text: ' pour lancer votre élevage de poules pondeuses' },
    ],
    text: 'Un plan projet personnalisé et des conseils pratiques pour structurer votre élevage, étape par étape, et maximiser vos chances de réussite.',
    items: [
      { icon: 'clipboard', label: 'Plan projet personnalisé' },
      { icon: 'users-group', label: "Conseils d'expert et retours terrain" },
      { icon: 'shield', label: 'Contenu fiable et à jour' },
    ],
    ctaLabel: 'Recevoir mon guide gratuit',
    reassurance: 'Vos informations sont sécurisées et ne seront jamais partagées.',
    image: {
      src: `${IMG}/Livre_poules_pondeuses_removebg.png`,
      alt: 'Guide complet — Lancer votre élevage de poules pondeuses',
    },
  },

  // Contenu intégralement partagé par les 3 pages HUB — cf. `_shared.ts`.
  faq: FAQ,

  stickyCtaLabel: 'Être accompagné gratuitement',

  /* ------------------------------------------------------------------ POC ---
     Les 3 formulaires ci-dessous sont portés en UI seule : aucune soumission
     n'est transmise (décision du 28/07/2026). Aucun lead n'est donc collecté.
     -------------------------------------------------------------------------- */

  assistant: {
    cardTitle: 'Recevez votre plan projet personnalisé',
    ctaLabel: "Démarrer l'étude du projet",
    reassurance: 'Un guide de démarrage vous sera envoyé immédiatement après validation.',
    steps: [
      {
        id: 'projet',
        label: 'Quel projet d’élevage souhaitez-vous concrétiser ?',
        multi: false,
        options: [
          'Création d’un premier élevage',
          'Reprise d’un élevage existant',
          'Agrandissement ou modernisation',
          'Ajout d’un atelier de ponte',
          'Projet encore en réflexion',
        ],
        illustrations: ['lightbulb', 'handshake', 'activity', 'factory', 'compass'],
      },
      {
        id: 'volume',
        label: 'Combien de poules pondeuses prévoyez-vous ?',
        multi: false,
        options: [
          'Moins de 1 000 poules',
          'Entre 1 000 et 5 000 poules',
          'Entre 5 000 et 10 000 poules',
          'Entre 10 000 et 40 000 poules',
          'Plus de 40 000 poules',
          'Je ne sais pas encore',
        ],
      },
      {
        id: 'budget',
        label: 'Avez-vous déjà estimé le budget de votre projet ?',
        multi: false,
        options: [
          'Oui, le budget et le financement sont définis',
          'Oui, mais le financement reste à trouver',
          'Le budget est en cours d’estimation',
          'Non, je souhaite connaître le budget à prévoir',
        ],
      },
      {
        id: 'delai',
        label: 'Quand souhaitez-vous démarrer votre projet d’élevage de poules pondeuses ?',
        multi: false,
        options: [
          'D’ici 3 mois',
          'Dans 3 à 6 mois',
          'Dans 6 à 12 mois',
          'Plus de 12 mois',
          'Je n’ai pas encore défini de date',
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
      image: {
        src: `${IMG}/Livre_poules_pondeuses_removebg.png`,
        alt: 'Guide complet — Lancer votre élevage de poules pondeuses',
      },
      downloadLabel: 'Télécharger à nouveau le guide',
      // PDF de test (même origine → téléchargement forcé OK). À remplacer par l'URL réelle.
      fileUrl: '/seo_masterclass_detailed.pdf',
    },
  },

  guideDialog: {
    badge: 'Télécharger le guide complet',
    titleParts: [
      { text: 'Recevez le ' },
      { text: 'guide complet', accent: true },
      { text: ' pour lancer votre élevage de ' },
      { text: 'poules pondeuses', accent: true },
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
      image: {
        src: `${IMG}/Livre_poules_pondeuses_removebg.png`,
        alt: 'Guide complet — Lancer votre élevage de poules pondeuses',
      },
      buttonLabel: 'Télécharger à nouveau le guide',
      // PDF de test (même origine → téléchargement forcé OK). À remplacer par l'URL réelle.
      fileUrl: '/seo_masterclass_detailed.pdf',
    },
  },

  leadPopup: {
    badge: '🎁 Guide 100% gratuit + contenus exclusifs',
    title: 'Lancez votre élevage de poules pondeuses',
    scriptLine: 'avec un guide complet',
    text: "Un guide complet pour structurer votre projet de A à Z : étapes clés, équipements indispensables, budget estimatif et points de vigilance d'un marché en forte demande en France.",
    emailPlaceholder: 'Votre adresse e-mail',
    submitLabel: 'Continuer',
    reassurance: '100% gratuit, sans engagement',
    circleBadgeLines: ['100%', 'Gratuit'],
    // Visuel du livret — même asset que le CTA guide.
    image: {
      src: `${IMG}/Livre_poules_pondeuses_removebg.png`,
      alt: 'Guide complet — Lancer votre élevage de poules pondeuses',
    },
    bannerImage: {
      src: `${IMG}/hero-section-pop-up.jpg`,
      alt: 'Élevage de poules pondeuses',
    },
    triggerSectionId: 'reglementation-demarches',
  },
};
