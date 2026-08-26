import type { HubPage } from '@/types/hub';
import { HUB_SECTION_IDS } from '@/lib/hub/anchors';
import { ACCOMPAGNEMENT, FAQ, HOW_IT_WORKS } from './_shared';

/**
 * Page HUB 1002 — « Ouvrir une laverie automatique ».
 * URL : /ouvrir-laverie-automatique-1002-projet.html
 *
 * Contenu issu du cahier des charges « Ouvrir une laverie automatique » et du
 * tableur de maillage (20 articles conseils, ids 5382 à 5410). Même gabarit que
 * les pages 1000 et 1001 : 4 blocs thématiques, sommaire à 8 entrées, blocs
 * communs mutualisés dans `_shared.ts`.
 *
 * IMAGES — 26 emplacements sur 26, tous pourvus depuis le 2026-08-07.
 *
 * Règle du modèle : un emplacement sans visuel livré n'a PAS de champ `image`,
 * jamais de chemin inventé — `registry.test.ts` refuse une image déclarée absente
 * du disque, et refuse aussi un fichier livré non référencé. Les composants
 * dégradent proprement (aplat + icône).
 *
 * Les vignettes d'articles ont été livrées avec leur H1 en nom de fichier
 * (espaces, accents, `&`, parenthèses, apostrophes typographiques) : renommées
 * par id de page conseil. Suivi : `docs/hub-assets-a-livrer.md`.
 *
 * ⚠️ Les cartes LATÉRALES des layouts `overlay-*` n'ont pas d'emplacement image
 * (seule l'icône y est rendue). Les vignettes des articles 5406, 5396, 5410,
 * 5392, 5395 et 5400 ont donc été sorties de `/public` : les laisser aurait fait
 * échouer le contrôle des fichiers orphelins, sans rien afficher de plus.
 */
const SLUG = 'ouvrir-laverie-automatique';
const IMG = `/images/hub/${SLUG}`;
const CONSEILS = 'https://conseils.hellopro.fr';

/**
 * Vignette d'article, nommée par l'id de la page conseil.
 *
 * Les fichiers source portent le H1 en nom : espaces, apostrophes typographiques,
 * accents, esperluettes et parenthèses, inexploitables dans une URL. On les
 * renomme par id à la copie dans `/public` — court, stable, insensible à une
 * retouche de titre.
 */
const articleImage = (id: number, alt: string) => ({
  src: `${IMG}/articles/${id}.jpg`,
  alt,
});

/**
 * Photo d'intérieur de laverie — affichée à DEUX endroits : le fond du héros et
 * le bandeau de la pop-up.
 *
 * ⚠️ Le lot livré contenait bien un second fichier destiné à la pop-up, mais
 * c'était une CAPTURE D'ÉCRAN de la maquette de pop-up (le modal photographié à
 * l'intérieur du modal) — exactement l'erreur détectée sur la page 1001. Il a été
 * sorti du dépôt. En attendant une seconde photo, la pop-up réutilise celle du
 * héros : c'est cohérent visuellement et ça reste une vraie photo.
 */
const LAVERIE_PHOTO = {
  src: `${IMG}/hero-laverie.jpg`,
  alt: 'Intérieur d’une laverie automatique en libre-service',
};

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
  src: `${IMG}/livre-laverie.png`,
  alt: 'Guide complet — Ouvrir une laverie automatique',
};

/** URL publique d'un article conseil. */
const conseilUrl = (slug: string, id: number) => `${CONSEILS}/${slug}-${id}.html`;

export const ouvrirLaverieAutomatique: HubPage = {
  id: 1002,
  slug: SLUG,

  // Métadonnées validées le 2026-08-06 (cf. docs/hub-pages-meta.md).
  // `title` part VERBATIM : le suffixe « | Hellopro » fait partie de la chaîne.
  meta: {
    title: 'Ouvrir une laverie automatique : guide complet | Hellopro',
    description:
      'Lancez votre projet de laverie automatique : budget, matériel, emplacement, réglementation et revenus prévisionnels. Guide gratuit et accompagnement dédié.',
  },

  /**
   * 1er = Accueil, dernier = titre de page. Les items intermédiaires alimentent
   * `product.category1` et `category5` dans GA4 (cf. GtmFooterScripts).
   *
   * ⚠️ ABSENT du cahier des charges — relevé le 2026-08-07 sur l'article 5382,
   * dont le fil d'ariane réel est `CHR - Café Hôtel Restaurant › Matériel pour
   * laverie et pressing › Bungalow laverie`. On retient les DEUX premiers
   * niveaux : « Bungalow laverie » est la catégorie produit feuille, bien plus
   * étroite que le périmètre de ce HUB (qui couvre aussi les laveries en local
   * commercial). À faire confirmer par l'équipe : la dimension GA4 n'est pas
   * rétroactive, une correction après mise en ligne laisserait un trou.
   */
  breadcrumb: [
    { label: 'Accueil', href: 'https://www.hellopro.fr/' },
    { label: 'CHR - Café Hôtel Restaurant' },
    { label: 'Matériel pour laverie et pressing' },
    { label: 'Ouvrir une laverie automatique' },
  ],

  hero: {
    // « Phrase d'accroche : Ouvrir une laverie automatique rentable » au cahier
    // des charges. Le H1 portant déjà « Ouvrir une laverie automatique », le
    // badge reprend l'angle sans répéter la formule mot pour mot.
    badge: 'Préparez lʼouverture de votre laverie automatique',
    titleParts: [
      { text: 'Ouvrir une ' },
      { text: 'laverie automatique', accent: true },
      { text: ' : budget, rentabilité et étapes clés' },
    ],
    // « Promesse : RAS » et « Social proof : RAS » au cahier des charges →
    // repris des pages 1000/1001, ces formulations ne portent aucun vocabulaire
    // métier.
    subtitle:
      'Recevez en moins de 2 minutes une estimation de budget, les équipements nécessaires et les étapes clés de votre projet.',
    background: LAVERIE_PHOTO,
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
    { id: 'local-implantation', label: 'Local & implantation', icon: 'home' },
    { id: 'reglementation-demarches', label: 'Réglementation', icon: 'file-text' },
    { id: 'equipements', label: 'Équipements', icon: 'wrench' },
    { id: HUB_SECTION_IDS.guideCta, label: 'Guide gratuit', icon: 'download' },
    { id: HUB_SECTION_IDS.faq, label: 'FAQ', icon: 'help' },
    { id: HUB_SECTION_IDS.finalCta, label: 'Être accompagné', icon: 'mail' },
  ],

  // « Ce que vous gagnez : RAS » au cahier des charges → repris tel quel des
  // pages 1000/1001. Ces quatre arguments portent sur le parcours HelloPro, pas
  // sur le métier : ils valent pour les trois verticales.
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
        /**
         * ⚠️ Ce titre est RIGOUREUSEMENT IDENTIQUE au `title` de l'édito
         * `quel-budget-prevoir` plus bas — les deux viennent tels quels du
         * cahier des charges. La même phrase apparaît donc deux fois sur la
         * page, en `h3` ici et en `h2` là-bas. Signalé le 2026-08-07 : sur la
         * page 1001, un doublon comparable avait été reformulé par l'équipe. En
         * attente d'arbitrage, on applique la valeur fournie.
         */
        title: 'Quel budget prévoir pour ouvrir une laverie automatique ?',
        image: articleImage(5382, 'Quel budget prévoir pour ouvrir une laverie automatique ?'),
        /**
         * ⚠️ Et les fourchettes des deux blocs DIVERGENT : 60 000–150 000 € ici,
         * 50 000–150 000 € dans l'édito, tous deux au cahier des charges.
         * L'article 5382 lui-même annonce 50 000–150 000 €. Les deux montants
         * sont visibles sur le même écran. Signalé, valeurs appliquées telles
         * que fournies.
         */
        intro:
          "Le budget pour ouvrir une laverie automatique se situe entre <strong>60 000 et 150 000 €</strong> selon l'état du local, le nombre de machines et les travaux de réseaux.",
        bullets: [
          '<strong>60 000 à 150 000 €</strong> de budget indicatif',
          "Environ <strong>30 % d'apport personnel</strong> pour faciliter l'obtention d'un financement",
          '<strong>Prêt professionnel</strong> remboursé sur 3 à 7 ans, parfois dès 2 ans',
        ],
        ctaLabel: 'Lire la suite',
        href: conseilUrl('quel-budget-prevoir-pour-ouvrir-une-laverie-automatique', 5382),
      },
      cards: [
        {
          icon: 'calculator',
          title: 'Ouvrir une laverie clé en main : quels postes faire chiffrer avant de signer',
          descriptionHtml:
            'Un projet de laverie clé en main représente <strong>60 000 à 150 000 €</strong> : comparez le prix des machines, des travaux et de la mise en service.',
          linkLabel: "Lire l'article",
          href: conseilUrl(
            'ouvrir-une-laverie-cle-en-main-quels-postes-faire-chiffrer-avant-de-signer',
            5406
          ),
        },
        {
          icon: 'activity',
          title: "Quelle est la rentabilité d'une laverie automatique ?",
          descriptionHtml:
            'Une laverie bien située peut dégager une <strong>marge nette de 20 à 35 %</strong> et atteindre son retour sur investissement en <strong>3 à 6 ans</strong>.',
          linkLabel: "Lire l'article",
          href: conseilUrl('quelle-est-la-rentabilite-d-une-laverie-automatique', 5396),
        },
        {
          icon: 'hand-coins',
          title: 'Quelles subventions et financement pour ouvrir une laverie automatique ?',
          descriptionHtml:
            "Apport, prêt bancaire, ARCE ou prêt d'honneur : l'ARCE peut représenter <strong>60 % des droits ARE restants</strong> et le prêt d'honneur <strong>80 000 € à taux zéro</strong>.",
          linkLabel: "Lire l'article",
          href: conseilUrl(
            'quelles-subventions-et-financement-pour-ouvrir-une-laverie-automatique',
            5410
          ),
        },
      ],
      guideButtonLabel: 'Télécharger le guide complet',
    },
    {
      id: 'local-implantation',
      tag: 'Local & implantation',
      tagIcon: 'home',
      layout: 'overlay-right',
      overlay: {
        title: 'Quel local choisir pour installer une laverie automatique rentable et conforme ?',
        image: articleImage(
          5386,
          'Quel local choisir pour installer une laverie automatique rentable et conforme ?'
        ),
        intro:
          "Le local d'une laverie doit être évalué selon sa visibilité, sa fréquentation potentielle, ses réseaux techniques et son accessibilité.",
        bullets: [
          '<strong>3 laveuses + 2 sèche-linge</strong> pour une configuration de départ indicative',
          'Environ <strong>7 litres d’eau par kilogramme</strong> de linge sur certains programmes économes',
          "Jusqu'à <strong>450 G</strong> pour les laveuses à super essorage",
        ],
        ctaLabel: 'Lire la suite',
        href: conseilUrl(
          'quel-local-choisir-pour-installer-une-laverie-automatique-rentable-et-conforme',
          5386
        ),
      },
      cards: [
        {
          icon: 'ruler',
          title:
            "Aménagement d'une laverie automatique : plan type, circulation client et postes indispensables",
          // « des zones séparés par usage » au cahier des charges : accord
          // corrigé en « séparées ». Seule retouche de forme du bloc.
          descriptionHtml:
            "Pour aménager un <strong>local de 30 à 50 m²</strong>, prévoyez des allées d'au moins 1,20 m, une zone de rotation de 1,50 m et des zones séparées par usage.",
          linkLabel: "Lire l'article",
          href: conseilUrl(
            'amenagement-d-une-laverie-automatique-plan-type-circulation-client-et-postes-indispensables',
            5392
          ),
        },
        {
          icon: 'handshake',
          title:
            'Franchise ou laverie indépendante : quel impact sur le choix du matériel et du budget ?',
          descriptionHtml:
            "Selon les réseaux, l'apport va de <strong>9 000 à 75 000 €</strong>. Comparez équipements imposés, accompagnement, droits, redevances et autonomie.",
          linkLabel: "Lire l'article",
          href: conseilUrl(
            'franchise-ou-laverie-independante-quel-impact-sur-le-choix-du-materiel-et-du-budget',
            5395
          ),
        },
        {
          icon: 'search-check',
          title: "Comment choisir l'implantation de sa laverie automatique ?",
          descriptionHtml:
            'Analysez la population et la <strong>concurrence à 500-800 m</strong>, puis choisissez un local visible dont le loyer reste sous 25 à 30 % du CA.',
          linkLabel: "Lire l'article",
          href: conseilUrl('comment-choisir-l-implantation-de-sa-laverie-automatique', 5400),
        },
      ],
      guideButtonLabel: 'Télécharger le guide complet',
    },
    {
      id: 'reglementation-demarches',
      tag: 'Réglementation & démarches',
      tagIcon: 'scale',
      // `carousel` sur toutes les pages HUB depuis le 2026-08-07 : en grille,
      // une dernière ligne à moitié vide déséquilibre le bloc.
      layout: 'carousel',
      intro:
        'Anticipez les obligations administratives pour sécuriser votre projet et éviter les erreurs dès le départ.',
      cards: [
        {
          title: 'Quel statut juridique pour ouvrir une laverie automatique ?',
          image: articleImage(5397, 'Quel statut juridique pour ouvrir une laverie automatique ?'),
          // ⚠️ Le slug de l'URL ne dérive PAS du titre affiché (il contient
          // « choisir » et « en-france »). Repris tel quel du tableur.
          href: conseilUrl(
            'quel-statut-juridique-choisir-pour-ouvrir-une-laverie-automatique-en-france',
            5397
          ),
        },
        {
          title: "Réglementation d'une laverie automatique : normes et obligations pour ouvrir",
          image: articleImage(
            5391,
            "Réglementation d'une laverie automatique : normes et obligations pour ouvrir"
          ),
          href: conseilUrl(
            'reglementation-d-une-laverie-automatique-normes-et-obligations-pour-ouvrir',
            5391
          ),
        },
        {
          title:
            'Laverie automatique et ERP : accessibilité PMR, sécurité incendie et normes du local',
          image: articleImage(
            5405,
            'Laverie automatique et ERP : accessibilité PMR, sécurité incendie et normes du local'
          ),
          href: conseilUrl(
            'laverie-automatique-et-erp-accessibilite-pmr-securite-incendie-et-normes-du-local',
            5405
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
          title: 'Liste des 18 équipements à prévoir pour ouvrir une laverie automatique',
          image: articleImage(
            5383,
            'Liste des 18 équipements à prévoir pour ouvrir une laverie automatique'
          ),
          href: conseilUrl(
            'liste-des-18-equipements-a-prevoir-pour-ouvrir-une-laverie-automatique',
            5383
          ),
        },
        {
          title: 'Machines à laver professionnelles pour laverie : quelles capacités (kg) choisir ?',
          image: articleImage(
            5387,
            'Machines à laver professionnelles pour laverie : quelles capacités (kg) choisir ?'
          ),
          href: conseilUrl(
            'machines-a-laver-professionnelles-pour-laverie-quelles-capacites-kg-choisir',
            5387
          ),
        },
        {
          title: 'Sèche-linge professionnel gaz ou électrique : quelle solution pour une laverie ?',
          image: articleImage(
            5388,
            'Sèche-linge professionnel gaz ou électrique : quelle solution pour une laverie ?'
          ),
          href: conseilUrl(
            'seche-linge-professionnel-gaz-ou-electrique-quelle-solution-pour-une-laverie',
            5388
          ),
        },
        {
          title:
            'Centrale de paiement, monnayeur ou CB : quel système choisir pour une laverie automatique ?',
          image: articleImage(
            5389,
            'Centrale de paiement, monnayeur ou CB : quel système choisir pour une laverie automatique ?'
          ),
          href: conseilUrl(
            'centrale-de-paiement-monnayeur-ou-cb-quel-systeme-choisir-pour-une-laverie-automatique',
            5389
          ),
        },
        {
          title:
            "Comment dimensionner les arrivées d'eau, évacuations et branchements électriques d'une laverie ?",
          image: articleImage(
            5408,
            "Comment dimensionner les arrivées d'eau, évacuations et branchements électriques d'une laverie ?"
          ),
          href: conseilUrl(
            'comment-dimensionner-les-arrivees-d-eau-evacuations-et-branchements-electriques-d-une-laverie',
            5408
          ),
        },
        {
          title:
            "Sécurité d'une laverie automatique : vidéosurveillance, incendie et protection du matériel",
          image: articleImage(
            5394,
            "Sécurité d'une laverie automatique : vidéosurveillance, incendie et protection du matériel"
          ),
          href: conseilUrl(
            'securite-d-une-laverie-automatique-videosurveillance-incendie-et-protection-du-materiel',
            5394
          ),
        },
      ],
    },
  ],

  accompagnementBanner: {
    tag: 'Accompagnement gratuit',
    title: 'Faites-vous accompagner pour ouvrir votre laverie automatique',
    // « Sous-titre : RAS » → repris des pages 1000/1001, sans vocabulaire métier.
    text: "Bénéficiez d'un échange qualifié pour cadrer votre besoin, valider vos priorités et avancer avec les bons interlocuteurs.",
    ctaLabel: 'Être accompagné gratuitement',
    // Position au cahier des charges : le CTA suit le bloc « Local et implantation ».
    afterThematiqueId: 'local-implantation',
    image: {
      src: `${IMG}/cta-accompagnement-gratuit.jpg`,
      alt: 'Échange avec un conseiller Hellopro',
    },
  },

  // « CTA Guide gratuit : RAS » → repris des pages 1000/1001.
  guideCta: {
    tag: 'Guide gratuit',
    title: 'Téléchargez votre guide de démarrage',
    text: 'Tous les repères essentiels pour cadrer votre budget, choisir vos équipements, comprendre la réglementation et avancer sereinement.',
    ctaLabel: 'Télécharger mon guide',
    image: GUIDE_COVER,
  },

  ressources: {
    title: 'Nos ressources pour ouvrir votre laverie automatique',
    subtitle:
      'Guides, conseils pratiques et ressources expertes pour vous aider à structurer votre projet.',
    items: [
      {
        tag: 'Exploitation',
        title: 'Traitement de lʼeau en laverie : adoucisseur, filtration et économies à prévoir',
        image: articleImage(
          5393,
          'Traitement de lʼeau en laverie : adoucisseur, filtration et économies à prévoir'
        ),
        href: conseilUrl(
          'traitement-de-l-eau-en-laverie-adoucisseur-filtration-et-economies-a-prevoir',
          5393
        ),
      },
      {
        tag: 'Exploitation',
        title: 'Distributeur de lessive en laverie : faut-il vendre, doser ou inclure les produits ?',
        image: articleImage(
          5398,
          'Distributeur de lessive en laverie : faut-il vendre, doser ou inclure les produits ?'
        ),
        href: conseilUrl(
          'distributeur-de-lessive-en-laverie-faut-il-vendre-doser-ou-inclure-les-produits',
          5398
        ),
      },
      {
        tag: 'Exploitation',
        title: 'Maintenance des machines de laverie : contrat, pièces et entretien préventif à prévoir',
        image: articleImage(
          5407,
          'Maintenance des machines de laverie : contrat, pièces et entretien préventif à prévoir'
        ),
        href: conseilUrl(
          'maintenance-des-machines-de-laverie-contrat-pieces-et-entretien-preventif-a-prevoir',
          5407
        ),
      },
    ],
  },

  grandesEtapes: {
    title: "Explorez les grandes étapes pour lʼouverture de votre laverie automatique",
    // Ordre repris VERBATIM du cahier des charges — il ne suit pas l'ordre des
    // blocs dans la page (budget → local → réglementation → équipements). Même
    // écart que sur les pages 1000 et 1001, donc cohérent entre les trois.
    items: [
      {
        label: 'Budget & financement',
        href: '#budget-financement',
        image: { src: `${IMG}/etapes/budget-financement.jpg`, alt: 'Budget & financement' },
      },
      {
        label: 'Équipements',
        href: '#equipements',
        image: { src: `${IMG}/etapes/equipements.jpg`, alt: 'Équipements' },
      },
      {
        label: 'Local & implantation',
        href: '#local-implantation',
        image: { src: `${IMG}/etapes/local-implantation.jpg`, alt: 'Local & implantation' },
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
      id: 'pourquoi-ouvrir-une-laverie',
      title: "Pourquoi ouvrir une laverie automatique aujourd'hui ?",
      intro:
        "Ouvrir une laverie automatique répond à des usages qui dépassent désormais les seuls ménages ne possédant pas de machine à laver. En France, <strong>87 % des ménages disposent d'un lave-linge</strong>, mais plusieurs évolutions entretiennent la demande :",
      items: [
        'la réduction de la surface des logements ;',
        'le développement de la colocation ;',
        'la mobilité des étudiants et des jeunes actifs ;',
        'le faible équipement des foyers en sèche-linge ;',
        'le besoin de laver des couettes, des couvertures et de gros volumes de linge.',
      ],
      bodyHtml:
        "<p>Les laveries équipées de machines de 15 à 30 kg attirent ainsi une clientèle plus large que les seuls particuliers non équipés. Elles peuvent notamment répondre aux besoins des <em>étudiants, locataires de petits logements, touristes, conciergeries, restaurateurs, gestionnaires de locations saisonnières et petites structures d’hébergement</em>.</p>" +
        "<p>Le marché français compte aujourd'hui <strong>entre 5 000 et 7 000 laveries traditionnelles</strong>, auxquelles s'ajoutent plusieurs milliers de laveries extérieures et de kiosques installés sur des parkings.</p>",
    },
    {
      id: 'quel-budget-prevoir',
      // ⚠️ Doublon exact avec le titre de la carte phare du bloc budget
      // (cf. commentaire là-haut). En attente d'arbitrage.
      title: 'Quel budget prévoir pour ouvrir une laverie automatique ?',
      intro:
        "Le budget nécessaire pour ouvrir une laverie automatique se situe généralement entre <strong>50 000 et 150 000 €</strong> pour un établissement indépendant. Il peut atteindre <strong>200 000 €</strong> pour une franchise, un grand établissement ou un local nécessitant d'importants travaux. Les principaux ordres de grandeur sont les suivants :",
      // « … sont les suivants : » annonce la liste, qui doit donc suivre l'intro
      // et non les paragraphes de `bodyHtml` (constaté le 2026-08-24).
      itemsPosition: 'after-intro',
      items: [
        '<strong>Petite laverie de 25 à 30 m² avec 4 à 6 machines :</strong> 50 000 à 70 000 €',
        '<strong>Laverie standard de 35 à 50 m² avec 6 à 10 machines :</strong> 70 000 à 110 000 €',
        '<strong>Grande laverie ou implantation premium :</strong> plus de 100 000 €',
        '<strong>Franchise ou projet avec travaux lourds :</strong> jusqu’à 150 000 à 200 000 €',
      ],
      bodyHtml:
        "<p>Pour le parc machines, il faut prévoir <strong>30 000 à 80 000 €</strong> pour les lave-linge et les sèche-linge, les raccordements d'eau et les évacuations, les travaux électriques, la ventilation ou l'extraction, la centrale de paiement, l'aménagement du local, l'enseigne et la communication, les équipements de sécurité et la trésorerie de départ.</p>" +
        "<p>Un apport personnel correspondant généralement à <strong>15 à 30 % du montant du projet</strong> peut être demandé pour obtenir un financement bancaire.</p>",
    },
    {
      id: 'modele-exploitation',
      title: "Quel modèle d'exploitation choisir pour une laverie automatique ?",
      intro:
        "Quatre modèles coexistent, avec des tickets d'entrée, des contraintes contractuelles et des niveaux d'autonomie très différents.",
      // Deuxième bloc éditorial des pages HUB à comporter des SOUS-TITRES (après
      // « Camion ou remorque » sur la 1001). Les `h3` sont autorisés dans le
      // corps depuis le 2026-08-07 (cf. sanitize.ts) : le titre du bloc étant un
      // `h2`, ils s'y emboîtent correctement.
      bodyHtml:
        '<h3>Laverie automatique indépendante</h3>' +
        "<p>Une laverie indépendante est créée et gérée librement par l'exploitant, sans dépendre d'une enseigne ou d'un réseau. L'investissement initial se situe généralement entre <strong>60 000 et 120 000 €</strong>, selon la taille du local, le nombre de machines et l'importance des travaux. Ce modèle évite les droits d'entrée et les redevances, mais impose de gérer seul l'étude de marché, les fournisseurs, la maintenance et la communication.</p>" +
        '<h3>Laverie automatique en franchise ou en réseau</h3>' +
        "<p>Une laverie en franchise ou en réseau utilise un concept, des équipements et un accompagnement proposés par une enseigne spécialisée. Selon le contrat, l'exploitant peut devoir payer <strong>15 000 à 25 000 € de droit d'entrée</strong> et des redevances représentant environ <strong>4 à 6 % du chiffre d'affaires</strong>. Certains réseaux fonctionnent toutefois sans droit d'entrée ni redevance, notamment sous forme de partenariat ou de concession.</p>" +
        '<h3>Kiosque de laverie extérieure</h3>' +
        "<p>Un kiosque de laverie est un module autonome installé sur un parking de supermarché, de station-service, de camping ou dans une zone commerciale. La France compterait près de <strong>7 000 kiosques</strong>, soit environ deux fois plus qu'il y a cinq ans. Ce modèle convient particulièrement aux zones rurales et périurbaines, mais sa fréquentation dépend fortement de la visibilité, du passage et de l'accessibilité de l'emplacement.</p>" +
        '<h3>Reprise d’une laverie automatique existante</h3>' +
        "<p>La reprise consiste à acheter une laverie déjà en activité, avec son local, ses machines et sa clientèle. Son prix dépend du chiffre d'affaires, de la rentabilité, du bail commercial et de l'état des équipements. Avant l'achat, il faut analyser les <strong>trois derniers bilans</strong>, les consommations d'eau et d'énergie, l'âge des machines et les dépenses de maintenance à prévoir.</p>",
    },
  ],

  // Blocs communs — cf. `_shared.ts`. « Comment ça marche » est inséré APRÈS le
  // dernier édito, conformément à l'ordre du cahier des charges.
  howItWorks: { ...HOW_IT_WORKS, afterEditoId: 'modele-exploitation' },

  accompagnement: {
    ...ACCOMPAGNEMENT,
    image: { src: `${IMG}/accompagnement-expert.jpg`, alt: 'Échange avec un conseiller Hellopro' },
  },

  finalCta: {
    badge: '🎁 100% Gratuit & sans engagement',
    titleParts: [
      { text: 'Recevez gratuitement votre ' },
      { text: 'guide et plan projet', accent: true },
      { text: ' pour ouvrir votre laverie automatique' },
    ],
    text: 'Un plan projet personnalisé et des conseils pratiques pour structurer votre laverie, étape par étape, et maximiser vos chances de réussite.',
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
    // Questionnaire repris VERBATIM de l'onglet « Formulaire » du tableur.
    // Aucune étape à choix multiple sur cette page (contrairement à la 1001).
    steps: [
      {
        id: 'projet',
        label: 'Quel projet de laverie souhaitez-vous lancer ?',
        multi: false,
        options: [
          "Création d'une laverie indépendante",
          'Ouverture en franchise',
          "Reprise d'une laverie existante",
          "Ajout d'un espace laverie à un commerce existant",
          'Autre',
          'Je souhaite être conseillé',
        ],
        // Une icône par option, dans le même ordre.
        illustrations: [
          'lightbulb',
          'handshake',
          'search-check',
          'home',
          'more',
          'headphones',
        ],
      },
      {
        id: 'local',
        label: 'Où en êtes-vous dans la recherche de votre local ?',
        multi: false,
        options: [
          "J'ai déjà trouvé un local",
          "J'ai trouvé un local et je négocie",
          'Je recherche encore un local',
          "Je n'ai pas encore commencé",
          'Je souhaite être conseillé',
        ],
      },
      {
        id: 'budget',
        label: 'Quel budget prévoyez-vous pour lancer votre laverie ?',
        multi: false,
        options: [
          'Moins de 50 000 €',
          '50 000 à 100 000 €',
          '100 000 à 200 000 €',
          'Plus de 200 000 €',
          'Mon budget reste à définir',
        ],
      },
      {
        id: 'echeance',
        label: 'Quand souhaitez-vous ouvrir votre laverie ?',
        multi: false,
        options: [
          "D'ici 3 mois",
          'Dans 3 à 6 mois',
          'Dans 6 à 12 mois',
          'Plus de 12 mois',
          "Je n'ai pas encore défini de date",
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
      // Chemin en kebab-case ASCII, nom d'enregistrement éditorial : cf.
      // `fileName` dans `types/hub.ts`. Le fichier vit dans `public/guides/`.
      fileUrl: '/guides/ouvrir-laverie-automatique.pdf',
      fileName: 'Livre blanc - Ouvrir une laverie automatique.pdf',
    },
  },

  guideDialog: {
    badge: 'Télécharger le guide complet',
    titleParts: [
      { text: 'Recevez le ' },
      { text: 'guide complet', accent: true },
      { text: ' pour ouvrir votre ' },
      { text: 'laverie automatique', accent: true },
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
      fileUrl: '/guides/ouvrir-laverie-automatique.pdf',
      fileName: 'Livre blanc - Ouvrir une laverie automatique.pdf',
    },
  },

  leadPopup: {
    badge: '🎁 Guide 100% gratuit + contenus exclusifs',
    title: 'Lancez votre laverie automatique sur de bonnes bases',
    scriptLine: 'avec un guide complet',
    // « Autre : RAS » → repris des pages 1000/1001, adapté à la verticale.
    text: 'Un guide complet pour structurer votre projet de A à Z : étapes clés, équipements indispensables, budget estimatif et points de vigilance pour ouvrir votre laverie automatique.',
    emailPlaceholder: 'Votre adresse e-mail',
    submitLabel: 'Continuer',
    reassurance: '100% gratuit, sans engagement',
    circleBadgeLines: ['100%', 'Gratuit'],
    image: GUIDE_COVER,
    // Réutilise la photo du héros — cf. `LAVERIE_PHOTO` : le fichier livré pour
    // ce bandeau était une capture de la maquette de pop-up.
    bannerImage: LAVERIE_PHOTO,
    // Même position que les pages 1000 et 1001 : la pop-up se déclenche une fois
    // le bloc réglementation dépassé, signe d'une lecture significative.
    triggerSectionId: 'reglementation-demarches',
  },
};
