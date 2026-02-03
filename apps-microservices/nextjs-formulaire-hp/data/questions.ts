// ========================================
// QUESTIONS DATA
// ========================================

import type { Question } from '@/types';

export const QUESTIONS_DATA: Question[] = [
  {
    id: 1,
    title: "Quel type de parc automobile allez-vous traiter majoritairement sur ce poste de travail ?",
    justification: "Cette question détermine la capacité de levage nécessaire (3T, 4T, 5T ou plus) et la longueur des bras (symétriques ou asymétriques) pour assurer la stabilité des véhicules.",
    multiSelect: true,
    answers: [
      { id: "1-1", mainText: "Citadines et berlines compactes", secondaryText: "Capacité standard ~3T suffisant" },
      { id: "1-2", mainText: "Berlines, petits SUV", secondaryText: "Polyvalence, capacité 3.2T à 3.5T" },
      { id: "1-3", mainText: "Gros SUV, 4x4, Pick-up", secondaryText: "Nécessite capacité 3.5T à 4T et bras renforcés" },
      { id: "1-4", mainText: "Utilitaires légers (VUL) et fourgons", secondaryText: "Capacité 4T à 5T indispensable" },
      { id: "1-5", mainText: "Utilitaires rallongés et camping-cars", secondaryText: "Capacité 5T+ et bras à longue portée" },
    ],
  },
  {
    id: 2,
    title: "Quelle est la configuration de votre atelier concernant la hauteur sous plafond et le passage au sol ?",
    justification: "Le choix entre un pont 'à embase' (bosse au sol) ou 'sans embase' (arche en haut) dépend strictement de votre hauteur disponible et de votre besoin de circuler librement sous le véhicule.",
    multiSelect: false,
    answers: [
      { id: "2-1", mainText: "Plafond bas (< 3,80m)", secondaryText: "Pont à embase au sol obligatoire" },
      { id: "2-2", mainText: "Plafond haut (> 3,80m)", secondaryText: "Pont sans embase privilégié pour un sol dégagé" },
      { id: "2-3", mainText: "Plafond très haut (> 4,50m)", secondaryText: "Compatible avec le levage de fourgons hauts" },
      { id: "2-4", mainText: "Je ne suis pas sûr", secondaryText: "Je souhaite une visite technique pour valider" },
    ],
  },
  {
    id: 3,
    title: "Quel est votre rythme de travail et la technologie de levage privilégiée ?",
    justification: "Définit le choix entre hydraulique (rapide, moins cher, peu d'entretien) et électromécanique (vis sans fin, précis, robuste, plus cher).",
    multiSelect: false,
    answers: [
      { id: "3-1", mainText: "Service rapide / Pneu / Freinage", secondaryText: "Technologie Hydraulique, montée/descente rapide" },
      { id: "3-2", mainText: "Mécanique générale standard", secondaryText: "Hydraulique, bon compromis coût/performance" },
      { id: "3-3", mainText: "Mécanique de précision / Moteur", secondaryText: "Électromécanique à vis, réglage millimétrique" },
      { id: "3-4", mainText: "Peu importe", secondaryText: "Je privilégie le meilleur rapport qualité/prix" },
    ],
  },
  {
    id: 4,
    title: "Quelle importance accordez-vous à la marque et à la finition du matériel ?",
    justification: "Permet de cibler la gamme de prix (Budget vs Premium) sans demander directement le budget, en se basant sur la durabilité attendue et l'image.",
    multiSelect: false,
    answers: [
      { id: "4-1", mainText: "Fonctionnel avant tout", secondaryText: "Outil certifié et sûr au prix le plus bas" },
      { id: "4-2", mainText: "Rapport Qualité/Prix", secondaryText: "Matériel robuste, marque reconnue, sans options superflues" },
      { id: "4-3", mainText: "Premium / Intensif", secondaryText: "Marque prestigieuse, conçu pour durer 15 ans+" },
      { id: "4-4", mainText: "Image de marque", secondaryText: "Haut de gamme pour rassurer les clients" },
    ],
  },
  {
    id: 5,
    title: "De quelle alimentation électrique disposez-vous à l'emplacement futur du pont ?",
    justification: "Critique pour le chiffrage. Le triphasé est standard pour les ponts pros ; le monophasé nécessite souvent des moteurs spécifiques plus coûteux ou moins puissants.",
    multiSelect: false,
    answers: [
      { id: "5-1", mainText: "Triphasé 380V/400V", secondaryText: "Standard industriel" },
      { id: "5-2", mainText: "Monophasé 220V/230V", secondaryText: "Nécessite un modèle compatible ou adaptation" },
      { id: "5-3", mainText: "Installation neuve", secondaryText: "Je peux faire installer ce qui est recommandé" },
      { id: "5-4", mainText: "Je ne sais pas", secondaryText: "Nécessitera une vérification par un électricien" },
    ],
  },
  {
    id: 6,
    title: "Quel est l'état et l'épaisseur de votre dalle de béton à l'emplacement prévu ?",
    justification: "La sécurité d'un pont 2 colonnes repose entièrement sur l'ancrage au sol. Une dalle insuffisante nécessite des travaux de génie civil (massifs béton) ou un châssis autoporteur coûteux.",
    multiSelect: false,
    answers: [
      { id: "6-1", mainText: "Dalle industrielle standard (> 20cm)", secondaryText: "Béton C20/25 minimum, ancrage chimique possible" },
      { id: "6-2", mainText: "Dalle fine ou ancienne (< 15cm)", secondaryText: "Risque de devoir créer des massifs en béton" },
      { id: "6-3", mainText: "Sol non bétonné", secondaryText: "Terre, bitume, pavés — travaux de maçonnerie à prévoir" },
      { id: "6-4", mainText: "Chauffage au sol présent", secondaryText: "Pose très technique ou impossible sans plan précis" },
      { id: "6-5", mainText: "Inconnu", secondaryText: "Je n'ai pas les plans du bâtiment" },
    ],
  },
  {
    id: 7,
    title: "Où en êtes-vous dans la maturité de ce projet d'équipement ?",
    justification: "Permet au vendeur de prioriser le dossier et de comprendre les contraintes logistiques ou de financement.",
    multiSelect: false,
    answers: [
      { id: "7-1", mainText: "Projet immédiat", secondaryText: "Financement validé, besoin d'installation rapide" },
      { id: "7-2", mainText: "Projet à court terme (1-3 mois)", secondaryText: "En phase de comparaison des devis" },
      { id: "7-3", mainText: "Projet de construction/rénovation", secondaryText: "Bâtiment non fini, besoin des plans de génie civil" },
      { id: "7-4", mainText: "Réflexion budgétaire", secondaryText: "Je me renseigne pour un investissement futur" },
    ],
  },
];

// Re-export as QUESTIONS for backward compatibility
export const QUESTIONS = QUESTIONS_DATA;
