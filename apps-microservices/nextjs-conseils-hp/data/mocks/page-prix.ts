import type { ConseilPage } from '@/types/conseils';

export const mockPagePrix: ConseilPage = {
  slug: 'combien-coute-un-batiment-elevage',
  pageType: 'prix',
  meta: {
    title: "Combien coûte un bâtiment d'élevage ? Prix 2026 | HelloPro",
    description:
      "Prix d'un bâtiment d'élevage : de 200 € à 13 500 € par place selon le type. Devis gratuits, simulateur et guide expert.",
    ogImage: 'https://cdn.hellopro.fr/conseils/batiment-elevage-og.jpg',
  },
  hero: {
    title: "Combien coûte un bâtiment d'élevage ?",
    subtitle:
      "Le prix de construction varie de 200 € à 13 500 € par place, selon le type d'élevage et les équipements.",
    image: 'https://cdn.hellopro.fr/conseils/batiment-elevage-hero.jpg',
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
      id: 'b-faq',
      type: 'faq',
      order: 7,
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
};
