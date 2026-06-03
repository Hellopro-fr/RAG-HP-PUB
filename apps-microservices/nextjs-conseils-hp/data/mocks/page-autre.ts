import type { ConseilPage } from '@/types/conseils';

export const mockPageAutre: ConseilPage = {
  slug: 'regles-usage-balayeuse-voirie',
  pageType: 'autre',
  meta: {
    title: "Règles d'usage d'une balayeuse de voirie : permis, CACES, normes 2026 | HelloPro",
    description:
      "Réglementation d'une balayeuse de voirie : autorisation de conduite, CACES R489, assurance, norme NF EN 15429 et entretien.",
  },
  hero: {
    title: "Règles d'usage d'une balayeuse de voirie",
    subtitle:
      "Autorisation de conduite, CACES, assurance et normes : tout ce qu'un exploitant de balayeuse doit savoir.",
    image: 'https://cdn.hellopro.fr/conseils/balayeuse-voirie-hero.jpg',
  },
  author: {
    name: 'Myriam Soumah',
    role: 'Responsable des contenus agricoles',
    bio: "Diplômée d'une école d'ingénieur agronome, Myriam suit le secteur des équipements de voirie depuis 10 ans.",
    linkedinUrl: 'https://www.linkedin.com/in/myriam-soumah',
  },
  blocks: [
    {
      id: 'b-resume',
      type: 'resume',
      order: 1,
      data: {
        title: "L'essentiel à retenir",
        items: [
          { label: 'Autorisation de conduite', text: 'Document nominatif valable 5 ans, obligatoire pour tout opérateur.' },
          { label: 'CACES R489', text: 'Catégorie 1 requise pour les balayeuses autoportées.' },
          { label: 'Assurance RC pro', text: 'Obligatoire pour couvrir les dommages matériels et corporels.' },
          { label: 'Norme NF EN 15429', text: 'Conformité européenne obligatoire pour la filtration, le bruit et les émissions.' },
        ],
      },
    },
    {
      id: 'b-h2-regles',
      type: 'h2',
      order: 2,
      data: {
        id: 'regles-usage',
        title: "Quelles sont les règles d'usage d'une balayeuse de voirie ?",
        intro:
          "La réglementation se focalise sur 3 points clés : autorisation de conduite, assurance RC et entretien conforme à la norme NF EN 15429.",
      },
    },
    {
      id: 'b-texte-regles',
      type: 'texte',
      order: 3,
      data: {
        html: "<p>Le conducteur doit être <strong>titulaire d'une autorisation de conduite</strong>, document nominatif délivré pour <strong>5 ans</strong>, après formation spécifique et obtention du CACES R489 catégorie 1 pour les modèles autoportés. Une <strong>assurance responsabilité civile</strong> est obligatoire. Enfin, un entretien rigoureux après chaque utilisation est indispensable.</p>",
      },
    },
    {
      id: 'b-h2-avantages',
      type: 'h2',
      order: 4,
      data: {
        id: 'avantages',
        title: 'Avantages & inconvénients d\'une balayeuse de voirie',
      },
    },
    {
      id: 'b-pros-cons',
      type: 'pros-cons',
      order: 5,
      data: {
        pros: [
          'Haute productivité sur grands axes et espaces publics',
          'Réduction des émissions de poussières fines (PM10/PM2,5)',
          'Versions électriques disponibles pour zones urbaines',
          'Amortissement rapide sur marchés publics',
        ],
        cons: [
          'Coût d\'acquisition élevé (80 000 à 300 000 €)',
          'Formation et CACES obligatoires',
          'Entretien rigoureux après chaque utilisation',
        ],
      },
    },
    {
      id: 'b-cta-1',
      type: 'cta',
      order: 6,
      data: {
        title: 'Comparez les balayeuses de voirie en 30 secondes',
        subtitle: 'Recevez jusqu\'à 3 devis gratuits de fournisseurs vérifiés',
        ctaLabel: 'Demander des devis',
      },
    },
    {
      id: 'b-faq',
      type: 'faq',
      order: 7,
      data: {
        items: [
          {
            q: 'Faut-il un permis pour conduire une balayeuse de voirie ?',
            a: "Une autorisation de conduite est obligatoire. Le CACES R489 cat. 1 est requis pour les autoportées. Le permis B ou C s'ajoute selon le PTAC du véhicule.",
          },
          {
            q: 'Quelle norme s\'applique aux balayeuses de voirie ?',
            a: "La norme européenne NF EN 15429 fixe les exigences de filtration des particules fines, de limitation des émissions sonores et atmosphériques.",
          },
          {
            q: "Combien coûte la formation CACES pour une balayeuse ?",
            a: "Entre 500 € et 2 000 € selon l'organisme et le nombre de catégories passées.",
          },
        ],
      },
    },
  ],
};
