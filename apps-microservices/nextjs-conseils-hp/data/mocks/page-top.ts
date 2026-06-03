import type { ConseilPage } from '@/types/conseils';

export const mockPageTop: ConseilPage = {
  slug: 'top-10-fabricants-portes-industrielles',
  pageType: 'top',
  meta: {
    title: 'Top 10 des fabricants de portes industrielles 2026 | HelloPro',
    description:
      "Comparatif 2026 des 10 meilleurs fabricants de portes sectionnelles industrielles en France. Gammes, points forts, normes EN 13241 et devis gratuits.",
  },
  hero: {
    title: 'Top 10 des meilleurs fabricants de portes sectionnelles industrielles',
    subtitle:
      "Sélection des 10 fabricants actifs en France, retenus sur leur gamme, leurs caractéristiques techniques et leur capacité de service.",
    image: 'https://cdn.hellopro.fr/conseils/portes-industrielles-hero.jpg',
  },
  author: {
    name: 'Myriam Soumah',
    role: 'Experte équipements industriels',
    bio: 'Myriam suit le marché des fermetures industrielles depuis 8 ans et coordonne les comparatifs experts HelloPro.',
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
          { label: 'Critères de sélection', text: 'Gamme produits, isolation thermique, SAV national, conformité CE.' },
          { label: 'Norme de référence', text: 'EN 13241 obligatoire pour toutes les portes industrielles sur le marché européen.' },
          { label: 'Budget moyen', text: 'Entre 2 500 € et 15 000 € pose comprise selon la dimension et les options.' },
        ],
      },
    },
    {
      id: 'b-h2-selection',
      type: 'h2',
      order: 2,
      data: {
        id: 'selection',
        title: 'Notre sélection des meilleurs fabricants',
        intro:
          "Comparer les portes sectionnelles industrielles exige les bons repères techniques. Cette sélection présente 10 fabricants actifs en France.",
      },
    },
    {
      id: 'b-cta-1',
      type: 'cta',
      order: 3,
      data: {
        title: 'Obtenez des devis de fabricants vérifiés',
        subtitle: 'Comparez les offres en moins de 2 minutes',
        ctaLabel: 'Demander des devis gratuits',
      },
    },
    {
      id: 'b-h2-faq',
      type: 'h2',
      order: 4,
      data: {
        id: 'faq',
        title: 'Questions fréquentes sur les portes industrielles',
      },
    },
    {
      id: 'b-faq',
      type: 'faq',
      order: 5,
      data: {
        items: [
          {
            q: 'Quelle norme pour une porte sectionnelle industrielle ?',
            a: "La norme EN 13241 est obligatoire pour toute porte industrielle commercialisée en Europe. Elle couvre la résistance au vent, l'isolation thermique et la sécurité.",
          },
          {
            q: 'Quel est le délai de livraison d\'une porte industrielle sur mesure ?',
            a: "Comptez 4 à 8 semaines pour une porte standard et jusqu'à 12 semaines pour les grandes dimensions sur mesure.",
          },
          {
            q: "Quelle épaisseur de panneau choisir ?",
            a: "40 mm pour une isolation standard (Ud ≈ 1,5 W/m²K), 67 ou 80 mm pour une isolation renforcée (entrepôts frigorifiques, zones industrielles froides).",
          },
        ],
      },
    },
  ],
};
