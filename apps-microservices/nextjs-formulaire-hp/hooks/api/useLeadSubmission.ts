"use client";

import { useMutation } from '@tanstack/react-query';
import { envoyerDemandes } from '@/lib/api/demande-info';
import { useFlowNavigation } from '@/hooks/useFlowNavigation';
import { useFlowStore, FLOW_SUBMISSION_COMPLETED_KEY, FLOW_ORIGINAL_TOKEN_KEY } from '@/lib/stores/flow-store';
import type { LeadSubmission, Supplier, ProfileType } from '@/types';
import type { DemandeInfoPayload, StatutAcheteur, ProduitSelection } from '@/types/demande';

// Analytics imports
import { trackLeadSubmitted, trackLeadSubmissionError } from '@/lib/analytics/gtm';
import { trackGA4LeadSubmitted } from '@/lib/analytics/ga4';
import { tagHotjarUser, HOTJAR_TAGS } from '@/lib/analytics/hotjar';

interface UserAnswer {
  questionId: string | number;
  answerId?: string | string[] | number;
}

type QAResult = Record<string | number, string | string[] | number>;

function formatUserQuestionAnswers(data: UserAnswer[]): QAResult {
  return data.reduce<QAResult>((acc, { questionId, answerId }) => {
    if (answerId !== undefined) acc[questionId] = answerId;
    return acc;
  }, {});
}

/**
 * Convertit le ProfileType vers StatutAcheteur pour le PHP
 */
function profileTypeToStatut(profileType: ProfileType | undefined): StatutAcheteur {
  if (!profileType) return '1'; // Par défaut entreprise
  switch (profileType) {
    case 'pro_france':
      return '1'; // Entreprise avec SIRET
    case 'creation':
      return '4'; // Création d'entreprise
    case 'pro_foreign':
      return '1'; // Professionnel étranger
    case 'particulier':
      return '7'; // Particulier
    default:
      return '1'; // Par défaut entreprise
  }
}

/**
 * Convertit les suppliers sélectionnés en format ProduitSelection pour le PHP
 */
function suppliersToProduitsSelection(
  selectedSupplierIds: string[],
  suppliers: Supplier[],
  data: LeadSubmission
): ProduitSelection[] {
  return selectedSupplierIds.map(id => {
    const supplier = suppliers.find(s => s.id === id);
    const supplierId = supplier?.supplier.id ? String(supplier.supplier.id) : '0';
    return {
      // Pour l'instant, on utilise l'id comme id_produit et id_societe
      // À terme, ces IDs viendront de l'API HelloPro
      id_produit: supplier?.id || id,
      id_societe: supplierId,
      nom_produit: supplier?.productName,
      nom_fournisseur: supplier?.supplierName,
      info_acheteur_matching: construireTabMatchingAcheteur({ values: data, id_produit: supplier?.id || id, id_societe: supplierId }),
    };
  });
}


function construireTabMatchingAcheteur({
  values,
  id_produit, id_societe
}: {
  values: LeadSubmission;
  id_produit?: number | string;
  id_societe?: number | string;
}) {
  let typologie = 1;

  const {
    contact,
    profile,
    answers,
    selectedSupplierIds,
    submittedAt,
    userKnownStatus,
    categoryId,
    source } = values;

  const type_lead = source == 2 ? "exclusif" : "apo";

  const objectInfoAcheteur = {
    id_acheteur: contact.id_acheteur || '',
    type_lead: type_lead,
    mail: contact.email,
    cp: profile?.postalCode || '',
    pays: profile?.countryID || 1,
    typologie: profileTypeToStatut(profile?.type),
    id_rubrique: categoryId || '0',
    id_produit: id_produit || '',
    naf_acheteur: profile?.naf || '',
    societe_originel: id_societe,
  };

  const infoAcheteur = JSON.stringify(objectInfoAcheteur);

  return infoAcheteur;
}

interface UseLeadSubmissionOptions {
  suppliers?: Supplier[];
}

export function useLeadSubmission(options: UseLeadSubmissionOptions = {}) {
  const { navigateTo } = useFlowNavigation();
  const { suppliers = [] } = options;

  // Récupérer les réponses Q/R de l'utilisateur depuis le flow store
  const userQuestionAnswers        = formatUserQuestionAnswers(useFlowStore.getState().userQuestionAnswers) || [];

  const equivalenceCaracteristique = useFlowStore.getState().equivalenceCaracteristique || [];
  const ddc                        = useFlowStore.getState().ddc || '';

  return useMutation({
    mutationFn: async (data: LeadSubmission) => {
      // Transformer les données vers le format DemandeInfoPayload
      const payload: DemandeInfoPayload = {
        form_ab: 'form_ux_matching',
        acheteur: {
          civilite           : data.contact.civility || '',
          nom                : data.contact.lastName,
          prenom             : data.contact.firstName,
          mail               : data.contact.email,
          isKnown            : data.contact.isKnown ? '1'                                                          : '0',
          telephone          : data.contact.phone,
          indicatif_tel      : data.contact.countryCode || '+33',
          societe            : data.contact.company || data.profile?.company?.name || data.profile?.companyName || '',
          id_siret_insee     : data.profile?.siret || '',
          code_postal        : data.profile?.postalCode || '',
          ville              : data.profile?.city || '',
          pays               : data.profile?.countryID || 1,                                                                // 1 = France par défaut
          statut             : profileTypeToStatut(data.profile?.type),
          naf                : data.profile?.naf || '',
          id_pays_tel        : data.contact.id_pays_tel || 1,
          id_societe_acheteur: data.contact.isKnown ? data.contact.id_acheteur                                     : 0,
          address            : data.profile?.address || '',
          type_societe       : data.profile?.type_societe || '',
        },
        message               : data.contact.message || '',
        budget                : data.contact.budget || '',
        produits              : data.source === 2 ? suppliersToProduitsSelection(data.selectedSupplierIds, suppliers, data): [],
        criteres              : data.answers,
        souhait_devis         : data.source === 2,
        demande_ia            : true,
        provenance_di         : 'ux_matching',
        id_rubrique           : data.categoryId || '0',
        info_acheteur_matching: construireTabMatchingAcheteur({ values: data }),
        ddc_is_i              : ddc,
        // JSON stringifié des questions/réponses utilisateur (debug / tracking)
        question_reponse_acheteur: userQuestionAnswers ? JSON.stringify(userQuestionAnswers) : undefined,
        caracteristiques: equivalenceCaracteristique.length > 0 ? JSON.stringify(equivalenceCaracteristique.map(
          function (o) {
            return {
              "id": o.id_caracteristique,
              "cible": o.valeurs_cibles
            }
          })) : undefined,
        // Pièces jointes
        files: data.contact.files,
      };

      // Envoyer les demandes au PHP
      const results = await envoyerDemandes(payload);

      // Vérifier si au moins une demande a réussi
      const successfulResults = results.filter(r => r.success);
      const hasSuccess = successfulResults.length > 0;

      if (!hasSuccess) {
        throw new Error('Aucune demande n\'a pu être envoyée');
      }

      // Retourner la première URL de redirection trouvée ou générer un leadId
      const redirectUrl = successfulResults.find(r => r.redirect_url)?.redirect_url;
      const leadId = successfulResults.find(r => r.id_demande)?.id_demande || `lead_${Date.now()}`;

      // Vérifier si c'est une vraie URL externe (succès) ou pas (erreur PHP)
      const isExternalRedirect = redirectUrl?.startsWith('http') ?? false;

      // URL de fallback vers la page catégorie si erreur
      const categoryId = data.categoryId || '0';
      const fallbackUrl = `https://www.hellopro.fr/-${categoryId}-fr-1-feuille.html`;

      // ⚠️ IMPORTANT: Créer le flag localStorage ICI (dans mutationFn) car le composant
      // pourrait se démonter avant que onSuccess ne soit appelé
      if (isExternalRedirect || (!isExternalRedirect && fallbackUrl)) {
        try {
          const originalToken = typeof window !== 'undefined'
            ? sessionStorage.getItem(FLOW_ORIGINAL_TOKEN_KEY)
            : undefined;

          const submissionData = {
            timestamp: Date.now(),
            originalToken: originalToken || undefined,
            categoryId: categoryId,
            expiresAt: Date.now() + (48 * 60 * 60 * 1000), // 48h
          };

          localStorage.setItem(
            FLOW_SUBMISSION_COMPLETED_KEY,
            JSON.stringify(submissionData)
          );
        } catch (e) {
          console.error('[LeadSubmission] ❌ Failed to set flag:', e);
        }
      }

      return {
        data: {
          leadId,
          redirectUrl: isExternalRedirect ? redirectUrl : null,
          isExternalRedirect,
          fallbackUrl,
          totalSent: successfulResults.length,
          totalRequested: data.selectedSupplierIds.length,
        },
        error: null,
        status: 200,
      };
    },
    onSuccess: (response, variables) => {
      // Track successful lead submission
      if (response.data?.leadId) {
        const profileType = variables.profile?.type ?? 'unknown';
        trackLeadSubmitted(
          variables.selectedSupplierIds.length,
          profileType,
          variables.userKnownStatus
        );
        trackGA4LeadSubmitted(
          response.data.leadId,
          variables.selectedSupplierIds.length,
          profileType
        );
        tagHotjarUser(HOTJAR_TAGS.CONVERTED);
      }

      // Redirection uniquement si URL externe (succès PHP)
      // Note: Le flag localStorage est déjà créé dans mutationFn
      if (response.data?.isExternalRedirect && response.data?.redirectUrl) {
        window.location.href = response.data.redirectUrl;
      }
      // Si isExternalRedirect === false, les formulaires afficheront le message d'erreur
      // et redirigeront vers fallbackUrl après 2 secondes
    },
    onError: (error) => {
      // Track submission error
      trackLeadSubmissionError(
        'submission_failed',
        error instanceof Error ? error.message : 'Unknown error'
      );
    },
  });
}
