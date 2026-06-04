import type { ConseilPage } from '@/types/conseils';

export const mockPagePrix: ConseilPage = {
  slug: 'combien-coute-un-batiment-elevage',
  pageType: 'prix',
  formulaire_ao: {
    id: 2001661,
    question: "Quel type d'élevage souhaitez-vous réaliser dans le bâtiment ?",
    avecImage: true,
    typeSelection: 1, // 1 = choix unique → clic direct ouvre le modal
    choix: [
      { id: 101, label: 'Élevage bovin',    image: 'https://www.hellopro.fr/images/vignettes/vache.png' },
      { id: 102, label: 'Élevage porcin',   image: 'https://www.hellopro.fr/images/vignettes/cochon.png' },
      { id: 103, label: 'Élevage ovin',     image: 'https://www.hellopro.fr/images/vignettes/mouton.png' },
      { id: 104, label: 'Élevage caprin',   image: 'https://www.hellopro.fr/images/vignettes/chevre.png' },
      { id: 105, label: 'Élevage cunicole', image: '' },
      { id: 106, label: 'Autre',            image: '' },
      { id: 107, label: 'Je ne sais pas encore', image: '' },
    ],
  },
  meta: {
    title: "Combien coûte un bâtiment d'élevage ? Prix 2026 | HelloPro",
    description:
      "Prix d'un bâtiment d'élevage : de 200 € à 13 500 € par place selon le type. Devis gratuits, simulateur et guide expert.",
    ogImage: 'https://www.hellopro.fr/images/page_conseil/3/9/0/scie-ruban-professionnelle-157519.jpg',
  },
  hero: {
    title: "Combien coûte un bâtiment d'élevage ?",
    subtitle:
      "Le prix de construction varie de 200 € à 13 500 € par place, selon le type d'élevage et les équipements.",
    image: 'https://www.hellopro.fr/images/page_conseil/3/9/0/scie-ruban-bois-157520.jpg',
    estimation: { min: 200, max: 13500, unit: '€ / place' },
  },
  author: {
    name: 'Myriam Soumah',
    role: 'Responsable des contenus agricoles',
    bio: "Diplômée d'une école d'ingénieur agronome, Myriam suit le secteur des bâtiments agricoles depuis plus de 10 ans. Elle accompagne les éleveurs dans leurs projets de construction.",
    linkedinUrl: 'https://www.linkedin.com/in/myriam-soumah',
    contactEmail: 'myriam.soumah@hellopro.fr',
  },
  blocks: [
    {
      id: 'b-resume',
      type: 'resume',
      order: 1,
      data: {
        items: [
          {
            label: 'Prix de construction neuve',
            text: "de 130 à 410 €/m² pour un bâtiment ovin, jusqu'à 3 400 €/m² pour un laitier complet.",
          },
          {
            label: 'Prix par place',
            text: 'de 200 € (ovin tunnel) à 13 500 € (vache laitière en logettes équipée).',
          },
          {
            label: 'Postes de coût clés',
            text: 'structure, bardage, dallage, ventilation, équipements intérieurs et bloc traite.',
          },
          {
            label: 'Aides & financement',
            text: 'PCAE, aides régionales et FEADER peuvent couvrir 20 à 40 % de l\'investissement.',
          },
        ],
      },
    },
    {
      id: 'b-h2-prix',
      type: 'h2',
      order: 2,
      data: {
        id: 'prix-construction',
        title: "Prix de construction d'un bâtiment d'élevage",
        intro:
          "Le coût varie entre 130 et 3 400 €/m² selon la taille du troupeau, le type d'élevage et les équipements.",
      },
    },
    {
      id: 'b-tableau-prix',
      type: 'tableau-prix',
      order: 3,
      data: {
        rows: [
          { type: 'Vaches allaitantes', price: '2 900 – 4 150 €', surface: '13 – 15 m²', pricePerM2: '190 – 310 €/m²' },
          { type: 'Vaches laitières', price: '11 000 – 13 500 €', surface: '8 – 11 m²', pricePerM2: '1 200 – 1 600 €/m²' },
          { type: 'Élevage porcin (truie)', price: '8 000 – 12 000 €', surface: '3,5 – 5 m²', pricePerM2: '1 600 – 3 430 €/m²' },
          { type: 'Élevage caprin', price: '500 – 1 000 €', surface: '2 – 2,5 m²', pricePerM2: '200 – 500 €/m²' },
          { type: 'Élevage ovin', price: '250 – 500 €', surface: '1,2 – 1,8 m²', pricePerM2: '130 – 410 €/m²' },
        ],
      },
    },
    {
      id: 'b-h2-avantages',
      type: 'h2',
      order: 4,
      data: {
        id: 'avantages',
        title: "Avantages & inconvénients d'un bâtiment d'élevage",
      },
    },
    {
      id: 'b-pros-cons',
      type: 'pros-cons',
      order: 5,
      data: {
        pros: [
          "Investissement long terme valorisant l'exploitation",
          'Bien-être animal et productivité accrus',
          'Possibilité d\'intégrer du photovoltaïque en toiture',
          'Éligible à plusieurs aides agricoles (PCAE, FEADER…)',
        ],
        cons: [
          "Investissement initial conséquent (jusqu'à 1,1 M€ pour 80 vaches)",
          'Démarches administratives longues (permis, ICPE)',
          'Travaux pouvant durer plusieurs mois',
        ],
      },
    },
    {
      id: 'b-cta-1',
      type: 'cta',
      order: 6,
      data: {
        title: 'Estimez le prix de votre projet en 30 secondes',
        subtitle: 'Recevez jusqu\'à 3 devis gratuits de constructeurs locaux',
        ctaLabel: 'Estimer le prix de mon projet',
      },
    },
    {
      id: 'b-h2-par-type',
      type: 'h2',
      order: 7,
      data: {
        id: 'prix-par-type',
        title: "Prix d'un bâtiment d'élevage selon le type",
        intro: "Détail des coûts par filière : bovin allaitant, bovin laitier, porcin, caprin et ovin.",
      },
    },
    {
      id: 'b-type-allaitant',
      type: 'type-section',
      order: 8,
      data: {
        id: 'type-allaitant',
        title: "Bâtiment d'élevage pour vaches allaitantes",
        estimate: '2 900 – 4 150 € / place',
        imageUrl: 'https://www.hellopro.fr/images/page_conseil/3/9/0/scie-ruban-fixe-157521.jpg',
        imageAlt: 'Vaches allaitantes en stabulation',
        descriptionHtml: "<p>Une vache allaitante logée en bâtiment occupe en moyenne <strong>13 à 15 m² de surface utile</strong>. L'aire paillée représente la majorité de l'espace, avec environ 9 à 11 m² affectés au couchage, complétés par 3 à 4 m² pour la circulation et l'alimentation.</p>",
        bullets: [
          'Stabulation libre avec aire paillée intégrale',
          'Cases de vêlage et zone veaux',
          'Couloirs d\'alimentation et stockage paille',
          'Coût moyen hors équipement : ≈ 3 400 €',
        ],
        ctaLabel: 'Demander un devis',
      },
    },
    {
      id: 'b-type-laitier',
      type: 'type-section',
      order: 9,
      data: {
        id: 'type-laitier',
        title: "Bâtiment d'élevage pour vaches laitières",
        estimate: '11 000 – 13 500 € / place',
        imageUrl: 'https://www.hellopro.fr/images/page_conseil/3/9/0/scie-a-ruban-portative-62788.jpg',
        imageAlt: 'Vaches laitières en logettes',
        descriptionHtml: "<p>Le bâtiment vaches laitières se distingue par la complexité de ses équipements : logettes, aire raclée, système de traite, gestion des effluents. Un élevage de <strong>80 vaches</strong> représente un budget global de <strong>1 000 000 € à 1 150 000 €</strong> hors foncier.</p>",
        bullets: [
          'Logement (aire paillée ou logettes) : 6 500–8 800 €/vache',
          'Bloc traite (salle ou roto) : 4 000–4 700 €/vache',
          'Équipements intérieurs : 1 000–1 500 €',
          'Surface utile : 8 à 11 m² par vache',
        ],
        ctaLabel: 'Demander un devis',
      },
    },
    {
      id: 'b-quote-form',
      type: 'quote-form',
      order: 10,
      data: {
        title: "Maintenant que vous connaissez les prix,",
        subtitle: "passez à l'action.",
        ctaLabel: 'Faire une demande groupée (1 min)',
      },
    },
    {
      id: 'b-type-porcin',
      type: 'type-section',
      order: 11,
      data: {
        id: 'type-porcin',
        title: "Bâtiment d'élevage porcin",
        estimate: '8 000 – 12 000 € / truie productive',
        imageUrl: 'https://www.hellopro.fr/images/page_conseil/3/9/0/scie-ruban-bois-157520.jpg',
        imageAlt: 'Bâtiment porcin intérieur',
        descriptionHtml: "<p>Les bâtiments porcins sont les plus techniques : ils combinent hygiène, confort thermique, ventilation contrôlée et alimentation mécanisée. Le coût cumulé pour un atelier <strong>maternité + post-sevrage + engraissement</strong> atteint 10 000 à 12 000 € par truie productive.</p>",
        bullets: [
          'Engraissement caillebotis : 1 800–2 300 € / place',
          'Maternité liberté : 7 000–8 500 € / place',
          'Post-sevrage : 600–900 € / place',
          'Versions plein air / bio : +20 à 30 %',
        ],
        ctaLabel: 'Demander un devis',
      },
    },
    {
      id: 'b-type-caprin',
      type: 'type-section',
      order: 12,
      data: {
        id: 'type-caprin',
        title: "Bâtiment d'élevage caprin",
        estimate: '500 – 1 000 € / place',
        imageUrl: 'https://www.hellopro.fr/images/page_conseil/3/9/0/scie-ruban-fixe-157521.jpg',
        imageAlt: 'Élevage caprin en chèvrerie',
        descriptionHtml: "<p>Pour un <strong>bâtiment de 200 chèvres</strong>, comptez environ 45 000 à 60 000 € pour la structure et le bardage, 25 000 à 35 000 € pour le bloc traite caprin et 20 000 à 25 000 € pour les équipements intérieurs.</p>",
        bullets: [
          'Logement avec aire paillée ou tapis',
          'Bloc traite et salle d\'alimentation',
          'Surface utile : 2 à 2,5 m² par chèvre adulte',
          'Économie d\'échelle au-delà de 500 chèvres',
        ],
        ctaLabel: 'Demander un devis',
      },
    },
    {
      id: 'b-type-ovin',
      type: 'type-section',
      order: 13,
      data: {
        id: 'type-ovin',
        title: "Bâtiment d'élevage ovin",
        estimate: '250 – 500 € / place',
        imageUrl: 'https://www.hellopro.fr/images/page_conseil/3/9/0/scie-a-ruban-portative-62788.jpg',
        imageAlt: 'Bergerie élevage ovin',
        descriptionHtml: "<p>Le coût au m² pour un bâtiment d'élevage ovin se situe entre <strong>130 € et 410 €</strong> selon le degré d'isolation et de ventilation. Un tunnel plastique avec distribution manuelle coûte 150 à 200 €/place ; un bâtiment maçonné avec dérouleuse 350 à 450 €/place.</p>",
        bullets: [
          'Aire paillée et parc de contention',
          'Zone d\'agnelage et stockage fourrage',
          'Surface utile : 1,2 à 1,5 m² par brebis',
          'Tri automatique, porte de tri, balances',
        ],
        ctaLabel: 'Demander un devis',
      },
    },
    {
      id: 'b-brochure',
      type: 'brochure',
      order: 14,
      data: {
        title: "Le guide complet pour bien choisir votre bâtiment d'élevage",
        description: "Toutes les clés pour cadrer votre projet, comparer les solutions et négocier les meilleurs devis — rédigé par nos experts achats pros.",
        bullets: [
          'Méthode pour estimer votre budget au juste prix',
          'Comparatifs matériaux, équipements & constructeurs',
          'Aides, financement et démarches administratives',
          'Check-lists prêtes à l\'emploi avant signature',
        ],
        ctaLabel: 'Recevoir le guide gratuit',
      },
    },
    {
      id: 'b-faq',
      type: 'faq',
      order: 15,
      data: {
        items: [
          {
            q: "Combien coûte un bâtiment d'élevage bovin laitier ?",
            a: "Le prix varie entre 11 000 et 13 500 € par place. Pour un troupeau de 80 vaches, prévoyez 1 000 000 à 1 150 000 € hors foncier.",
          },
          {
            q: "Quelles aides pour la construction d'un bâtiment d'élevage ?",
            a: "PCAE, aides FEADER, subventions régionales et prêts bonifiés. La TVA peut être récupérée sous régime réel.",
          },
          {
            q: 'Quels sont les délais de construction ?',
            a: "Comptez 6 à 18 mois entre l'étude initiale et la livraison clé en main.",
          },
          {
            q: "Vaut-il mieux choisir une structure bois ou acier ?",
            a: "L'acier est souvent moins cher (–15 à 20 %). Le bois offre une meilleure intégration paysagère et une bonne durabilité en milieu humide.",
          },
        ],
      },
    },
  ],
  liensIntexts: [
    {
      id: 1,
      type: 0,
      photo: 'https://www.hellopro.fr/images/produit/2/6/5/batiment-elevage-bovin-562.jpg',
      titre: 'Bâtiment modulaire',
      description: 'Bâtiment acier galvanisé adapté à l\'élevage avec toiture isolée, bardage bac acier et charpente galvanisée.',
      url: 'https://www.hellopro.fr/batiment-elevage-bovin-562.html',
    },
    {
      id: 2,
      type: 0,
      photo: 'https://www.hellopro.fr/images/produit/3/1/4/barriere-stabulation-314.jpg',
      titre: 'Stabulation',
      description: 'Barrière de stabulation agricole pour bovins, tube acier galvanisé Ø 60 mm, réglable en largeur.',
      url: 'https://www.hellopro.fr/barriere-stabulation-314.html',
      prix: 'Dès 280 €',
    },
    {
      id: 3,
      type: 0,
      photo: 'https://www.hellopro.fr/images/produit/7/8/2/pailleuse-distributrice-782.jpg',
      titre: 'Pailleuse',
      description: 'Pailleuse-distributrice tractée 12 m³, distribution latérale ou arrière, compatible balles rondes et carrées.',
      url: 'https://www.hellopro.fr/pailleuse-distributrice-782.html',
      prix: 'Dès 14 900 €',
    },
    {
      id: 4,
      type: 0,
      photo: 'https://www.hellopro.fr/images/produit/4/5/9/hangar-photovoltaique-459.jpg',
      titre: 'Photovoltaïque',
      description: 'Hangar photovoltaïque clé en main 1 000 m², structure acier et toiture panneaux monocristallins.',
      url: 'https://www.hellopro.fr/hangar-photovoltaique-459.html',
    },
  ],
};
