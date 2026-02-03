// ========================================
// TYPES POUR DEMANDE D'INFORMATION
// ========================================

/**
 * Statut du profil acheteur
 * 1 = Entreprise avec SIRET (France)
 * 2 = Administration/Collectivité
 * 3 = Association
 * 4 = Création d'entreprise
 * 5 = Auto-entrepreneur
 * 6 = Professionnel étranger
 * 7 = Particulier (B2C)
 */
export type StatutAcheteur = '1' | '2' | '3' | '4' | '5' | '6' | '7';

/**
 * Type de formulaire
 */
export type FormType = 'form_dd_v2' | 'form_di_merci' | 'form_fiche_produit' | 'form_ao' | 'form_fullao' | 'form_ux_matching';

/**
 * Données de l'acheteur
 */
export interface AcheteurData {
  // Identité
  civilite: string;
  nom: string;
  prenom: string;

  // Contact
  mail: string;
  telephone: string;
  indicatif_tel?: string;

  // Entreprise
  societe: string;
  siret?: string;
  id_siret_insee?: string;
  id_cartegie?: string;

  // Adresse
  adresse?: string;
  code_postal: string;
  ville: string;
  pays: string;

  // Profil
  statut: StatutAcheteur;
  fonction?: string;
  service?: string;
  secteur?: string;
  effectif?: string;

  // Options
  website?: string;
  reception_alerte?: boolean;
}

/**
 * Données du produit/fournisseur sélectionné
 */
export interface ProduitSelection {
  id_produit: string;
  id_societe: string;
  id_rubrique?: string;
  nom_produit?: string;
  nom_fournisseur?: string;
}

/**
 * Données complètes de la demande d'information
 */
export interface DemandeInfoPayload {
  // Type de formulaire
  form_ab: FormType;

  // Acheteur
  acheteur: AcheteurData;

  // Message
  message: string;

  // Produits sélectionnés (1 produit = 1 demande)
  produits: ProduitSelection[];

  // Critères du questionnaire (réponses)
  criteres?: Record<number, string[]>;

  // Tracking
  abtest?: string;
  origine?: string;
  provenance_di?: string;

  // Options demande
  souhait_devis?: boolean;
  souhait_infos?: boolean;
  souhait_rdv?: boolean;

  // Demande IA
  demande_ia?: boolean;
}

/**
 * Réponse de l'API après création de demande
 */
export interface DemandeInfoResponse {
  success: boolean;
  id_demande?: string;
  redirect_url?: string;
  error?: string;
}

/**
 * Payload formaté pour le fichier PHP (format $_POST)
 */
export interface DemandeInfoPHPPayload {
  // Identifiant formulaire
  form_ab: string;

  // Statut acheteur
  statut: string;
  rep_prof_part: string;

  // Identité
  civilite: string;
  'nom-acheteur': string;
  'prenom-acheteur': string;

  // Contact
  'mail-acheteur': string;
  'telephone-acheteur': string;
  indicatif_tel: string;

  // Entreprise
  'societe-acheteur': string;
  id_siret_insee?: string;
  id_cartegie_siret?: string;

  // Adresse
  'adresse-acheteur': string;
  'code-postal-acheteur': string;
  'ville-acheteur': string;
  'pays-acheteur': string;

  // Fonction/Service
  fonction?: string;
  service?: string;
  metier?: string;

  // Message
  'message-acheteur': string;

  // Produit/Société
  soc: string;
  [key: `check_id_prod_soc_${string}`]: string;

  // Options
  souhait_devis_prod_sim?: string;
  souhaiter_devis?: string;
  souhaiter_infos?: string;
  souhaiter_rdv?: string;

  // Tracking
  abtest?: string;
  origine?: string;
  provenance_di?: string;

  // Anti-robot
  ddc_is_i?: string;

  // Demande IA
  demande_ia?: string;
  id_produit_ia?: string;
}
