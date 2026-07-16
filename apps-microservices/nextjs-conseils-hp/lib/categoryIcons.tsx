import type { LucideIcon } from 'lucide-react';
import {
  Construction,
  TreePine,
  Blocks,
  Tractor,
  UtensilsCrossed,
  Warehouse,
  Package,
  CookingPot,
  Store,
  Briefcase,
  Thermometer,
  Wrench,
  ShieldCheck,
  Car,
  Recycle,
  Gauge,
  Zap,
  Droplets,
  Network,
  Megaphone,
  HeartPulse,
  FlaskConical,
  SprayCan,
  Factory,
  LayoutGrid,
} from 'lucide-react';

/** Plage des marques diacritiques combinantes (accents) à retirer après NFD. */
const DIACRITICS = /[̀-ͯ]/g;

/**
 * Normalise un libellé pour un matching robuste :
 * minuscules + suppression des accents.
 */
function normalize(input: string): string {
  return input.toLowerCase().normalize('NFD').replace(DIACRITICS, '');
}

/**
 * Règles d'association catégorie produit HelloPro → icône lucide.
 * Matching par mots-clés (accent-insensible), robuste aux variations de libellé.
 * ⚠️ L'ordre = la priorité : la première règle qui matche gagne.
 * Les règles spécifiques (ex. "alimentaire") doivent précéder les génériques
 * (ex. "industrie") pour ne pas être court-circuitées.
 */
const RULES: Array<{ keywords: string[]; icon: LucideIcon }> = [
  { keywords: ['chantier', 'engin'], icon: Construction },
  { keywords: ['exterieur', 'urbain', 'amenagement', 'espace vert'], icon: TreePine },
  { keywords: ['materiaux'], icon: Blocks },
  { keywords: ['agriculture', 'elevage', 'forestier', 'agricole'], icon: Tractor },
  { keywords: ['chr', 'restaurant', 'hotel', 'cafe'], icon: UtensilsCrossed },
  { keywords: ['logistique', 'entrepot', 'stockage'], icon: Warehouse },
  { keywords: ['emballage', 'conditionnement'], icon: Package },
  { keywords: ['alimentaire'], icon: CookingPot }, // avant "industrie"
  { keywords: ['magasin', 'commerce', 'boutique'], icon: Store },
  { keywords: ['entreprise', 'service'], icon: Briefcase },
  { keywords: ['chauffage', 'climatisation', 'ventilation', 'cvc'], icon: Thermometer },
  { keywords: ['outillage', 'fourniture'], icon: Wrench }, // avant "industrie"
  { keywords: ['securite'], icon: ShieldCheck },
  { keywords: ['transport', 'automobile', 'vehicule'], icon: Car },
  { keywords: ['dechet', 'environnement'], icon: Recycle },
  { keywords: ['mesure', 'analyse', 'capteur', 'metrologie'], icon: Gauge },
  { keywords: ['electricite', 'electronique', 'energie'], icon: Zap },
  { keywords: ['pompe', 'hydraulique', 'pneumatique'], icon: Droplets },
  { keywords: ['informatique', 'reseau', 'numerique'], icon: Network },
  { keywords: ['communication', 'evenementiel'], icon: Megaphone },
  { keywords: ['sante', 'medical'], icon: HeartPulse },
  { keywords: ['laboratoire', 'labo'], icon: FlaskConical },
  { keywords: ['nettoyage', 'entretien', 'hygiene'], icon: SprayCan },
  { keywords: ['industrie'], icon: Factory }, // après "alimentaire" et "outillage"
];

/**
 * Retourne l'icône lucide la plus adaptée au nom de catégorie.
 * Fallback : LayoutGrid (icône générique) si aucun mot-clé ne matche.
 */
export function getCategoryIcon(nom: string): LucideIcon {
  const n = normalize(nom);
  for (const { keywords, icon } of RULES) {
    if (keywords.some((k) => n.includes(k))) return icon;
  }
  return LayoutGrid;
}
