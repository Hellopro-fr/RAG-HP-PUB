"use client";

import { useMutation } from '@tanstack/react-query';
import { envoyerDemandes } from '@/lib/api/demande-info';
import { useFlowNavigation } from '@/hooks/useFlowNavigation';
import type { LeadSubmission, Supplier, ProfileType } from '@/types';
import type { DemandeInfoPayload, StatutAcheteur, ProduitSelection } from '@/types/demande';

// Analytics imports
import { trackLeadSubmitted, trackLeadSubmissionError } from '@/lib/analytics/gtm';
import { trackGA4LeadSubmitted } from '@/lib/analytics/ga4';
import { tagHotjarUser, HOTJAR_TAGS } from '@/lib/analytics/hotjar';

/**
 * Convertit le ProfileType vers StatutAcheteur pour le PHP
 */
function profileTypeToStatut(profileType: ProfileType): StatutAcheteur {
  switch (profileType) {
    case 'pro_france':
      return '1'; // Entreprise avec SIRET
    case 'creation':
      return '4'; // Création d'entreprise
    case 'pro_foreign':
      return '6'; // Professionnel étranger
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
    return {
      // Pour l'instant, on utilise l'id comme id_produit et id_societe
      // À terme, ces IDs viendront de l'API HelloPro
      id_produit: supplier?.id || id,
      id_societe: supplier?.id || id,
      nom_produit: supplier?.productName,
      nom_fournisseur: supplier?.supplierName,
      info_acheteur_matching: construireTabMatchingAcheteur({  values: data, id_produit: supplier?.id || id , id_societe: supplier?.id || id  }),
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
    categoryId } = values;

  const type_lead = id_produit ? "exclusif" : "apo";

  const objectInfoAcheteur = {
    id_acheteur     : '',
    type_lead       : type_lead,
    mail            : contact.email,
    cp              : profile.postalCode || '',
    pays            : profile.countryID || 1,
    typologie       : profileTypeToStatut(profile.type),
    id_rubrique     : categoryId || '0',
    id_produit      : id_produit || '',
    naf_acheteur    : profile.naf || '',
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

  return useMutation({
    mutationFn: async (data: LeadSubmission) => {
      // Transformer les données vers le format DemandeInfoPayload
      const payload: DemandeInfoPayload = {
        form_ab : 'form_ux_matching',
        acheteur: {
          civilite      : '',
          nom           : data.contact.lastName,
          prenom        : data.contact.firstName,
          mail          : data.contact.email,
          isKnown       : data.contact.isKnown ? '1'                                                          : '0',
          telephone     : data.contact.phone,
          indicatif_tel : data.contact.countryCode || '+33',
          societe       : data.contact.company || data.profile.company?.name || data.profile.companyName || '',
          id_siret_insee: data.profile.siret || '',
          code_postal   : data.profile.postalCode || '',
          ville         : data.profile.city || '',
          pays          : data.profile.countryID || 1,                                                                // 1 = France par défaut
          statut        : profileTypeToStatut(data.profile.type),
          naf           : data.profile.naf || '',
        },
        message      : data.contact.message || 'Demande de devis via UX Matching',
        produits     : suppliersToProduitsSelection(data.selectedSupplierIds, suppliers, data),
        criteres     : data.answers,
        souhait_devis: true,
        demande_ia   : true,
        provenance_di: 'ux_matching',
        id_rubrique  : data.categoryId || '0'
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

      return {
        data: {
          leadId,
          redirectUrl: redirectUrl || '/confirmation',
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
        const profileType = variables.profile.type ?? 'unknown';
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

      // Navigate to confirmation page (avec conservation des paramètres GET)
      if (response.data?.redirectUrl) {
        const url = response.data.redirectUrl;
        // Si c'est une URL relative interne, conserver les paramètres GET
        if (url.startsWith('/')) {
          navigateTo(url);
        } else {
          // URL externe (redirection PHP) : naviguer directement
          window.location.href = url;
        }
      }
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
