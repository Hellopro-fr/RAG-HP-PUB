// ========================================
// TYPES & INTERFACES - API READY
// ========================================

// ========================================
// QUESTIONNAIRE TYPES
// ========================================
export interface Answer {
  id: string;
  mainText: string;
  secondaryText?: string;
}

export interface BulleAide {
  libelle?: string;
  explication?: string[];
  astuce?: string;
}

export interface Question {
  id: number;
  title: string;
  multiSelect: boolean;
  answers: Answer[];
  bulleAide?: BulleAide | null;
}

export type UserAnswers = Record<number, string[]>;

// ========================================
// PROFILE TYPES
// ========================================
export type ProfileType = "pro_france" | "creation" | "pro_foreign" | "particulier" | null;

export interface CompanyResult {
  siren      : string;
  name       : string;
  address    : string;
  postalCode?: string;
  city      ?: string;
  naf       ?: string;
  siret     ?: string;
}

export interface ProfileData {
  type         : ProfileType;
  company     ?: CompanyResult;
  companyName ?: string;
  postalCode  ?: string;
  city        ?: string;
  country     ?: string;
  siren       ?: string;
  siret       ?: string;
  countryID   ?: number;
  naf         ?: string;
  address     ?: string;
  type_societe?: number | string;
}

export interface PostalCodeCity {
  postalCode: string;
  city: string;
}

// ========================================
// SUPPLIER & PRODUCT TYPES
// ========================================
export interface ProductSpec {
  /** ID de la caractéristique (pour filtrage des critères supprimés) */
  id_caracteristique?: number;
  label: string;
  value: string;
  matches?: boolean;
  expected?: string;
  isRequested?: boolean;
  /** Statut de matching: 1=match, 2=ecart, 3=bloquant, 4=non_renseigne */
  matchingStatus?: 1 | 2 | 3 | 4;
}

export interface MediaItem {
  type: "image" | "video";
  url: string;
  thumbnail?: string;
}

export interface PriceInfo {
  amount?: number;
  isStartingFrom?: boolean;
}

export interface SupplierInfo {
  id?: string;
  name: string;
  description: string;
  location: string;
  responseTime: string;
  logo?: string;
  rating?: number;
  reviewCount?: number;
  yearsActive?: number;
  certifications?: string[];
}

export interface Supplier {
  id: string;
  productName: string;
  supplierName: string;
  rating: number;
  distance: number;
  matchScore: number;
  image: string;
  images: string[];
  media?: MediaItem[];
  isRecommended: boolean;
  isCertified?: boolean;
  matchGaps: string[];
  description: string;
  descriptionHtml?: string;
  specs: ProductSpec[];
  supplier: SupplierInfo;
  price?: PriceInfo;
  priceLabel?: string;  // Prix brut retourné par l'API (ex: "699,00 € HT")
  debugInfo?: {
    coeff_geo: number;
    coeff_type_frns: number;
    coeff_caracteristique?: number;
    coeff_etat_score?: number;
    score?: number;
    characteristics_debug: Array<{
      id_caracteristique: number;
      bareme: number;
      poids_question: number;
      poids?: number;
    }>;
    llm_response?: any; // ou LlmResponse importé
  };
}

// ========================================
// LEAD / CONTACT TYPES
// ========================================
export interface ContactFormData {
  email: string;
  isKnown: boolean;
  civility: string;
  firstName: string;
  lastName: string;
  company?: string;
  countryCode?: string;
  id_pays_tel?: number;  // ID du pays pour le téléphone
  phone: string;
  message?: string;
  budget?: string;
  files?: File[];  // Pièces jointes (PJ)
  id_acheteur?: string;  // ID de l'acheteur si le mail est connu
}

export interface LeadSubmission {
  contact: ContactFormData;
  profile: ProfileData;
  answers: UserAnswers;
  selectedSupplierIds: string[];
  submittedAt: string;
  userKnownStatus: 'known' | 'unknown';
  categoryId?: string;
  source?: number;
}

export interface LeadResponse {
  success: boolean;
  leadId?: string;
  message?: string;
  redirectUrl?: string;
}

// ========================================
// CRITERIA TYPES
// ========================================
export interface CriteriaOption {
  value: string;
  label: string;
}

export interface ModifyCriteriaData {
  liftType: string;
  capacities: string[];
  voltage: string;
  zones: string[];
  options: string[];
  expandSearch: boolean;
}

// ========================================
// API RESPONSE TYPES
// ========================================
export interface ApiResponse<T> {
  data: T | null;
  error: string | null;
  status: number;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
}

// ========================================
// FLOW STATE TYPES
// ========================================
export type FlowStep = "questionnaire" | "profile" | "selection";
export type ViewState = "selection" | "contact" | "modify-criteria" | "custom-need";

// ========================================
// STEP CONFIGURATION
// ========================================
export interface StepConfig {
  id: number;
  label: string;
}

export const FLOW_STEPS: StepConfig[] = [
  { id: 1, label: "Votre besoin" },
  { id: 2, label: "Sélection" },
  { id: 3, label: "Demande de devis" },
];

// ========================================
// DEMANDE D'INFORMATION TYPES
// ========================================
export * from './demande';
