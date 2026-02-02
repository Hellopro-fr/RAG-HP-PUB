// ========================================
// CRITERIA DATA
// ========================================

import type { CriteriaOption } from '@/types';

export const CAPACITY_OPTIONS: CriteriaOption[] = [
  { value: "2.5t", label: "2.5 tonnes" },
  { value: "3t", label: "3 tonnes" },
  { value: "3.5t", label: "3.5 tonnes" },
  { value: "4t", label: "4 tonnes" },
  { value: "5t", label: "5 tonnes" },
  { value: "5t+", label: "Plus de 5 tonnes" },
];

export const ZONE_OPTIONS: CriteriaOption[] = [
  { value: "ile-de-france", label: "Île-de-France" },
  { value: "nord", label: "Nord" },
  { value: "est", label: "Est" },
  { value: "ouest", label: "Ouest" },
  { value: "sud-est", label: "Sud-Est" },
  { value: "sud-ouest", label: "Sud-Ouest" },
  { value: "centre", label: "Centre" },
];

export const VOLTAGE_OPTIONS: CriteriaOption[] = [
  { value: "230v", label: "230V monophasé" },
  { value: "400v", label: "400V triphasé" },
];

export const LIFT_TYPE_OPTIONS: CriteriaOption[] = [
  { value: "2-colonnes", label: "Pont 2 colonnes" },
  { value: "4-colonnes", label: "Pont 4 colonnes" },
  { value: "ciseaux", label: "Pont à ciseaux" },
  { value: "fosse", label: "Pont sur fosse" },
];

export const ADDITIONAL_OPTIONS: CriteriaOption[] = [
  { value: "traverse-sup", label: "Traverse supérieure" },
  { value: "traverse-bas", label: "Traverse basse" },
  { value: "sans-traverse", label: "Sans traverse" },
  { value: "bras-asym", label: "Bras asymétriques" },
  { value: "bras-sym", label: "Bras symétriques" },
  { value: "installation", label: "Installation incluse" },
  { value: "garantie-3ans", label: "Garantie 3 ans" },
  { value: "sav-rapide", label: "SAV rapide" },
];

export const DEFAULT_CRITERIA = [
  "Pont 2 colonnes",
  "4T",
  "Traverse supérieure",
  "400V",
  "Île-de-France",
];
