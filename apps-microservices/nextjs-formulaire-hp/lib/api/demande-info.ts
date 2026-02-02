// ========================================
// SERVICE API - DEMANDE D'INFORMATION
// ========================================

import type {
  DemandeInfoPayload,
  DemandeInfoResponse,
  DemandeInfoPHPPayload,
  ProduitSelection,
} from '@/types/demande';
import { basePath } from '@/lib/utils';

// Utilise le proxy Next.js pour éviter les problèmes CORS
const getApiBasePath = () => basePath || '';

/**
 * Convertit les données du formulaire Next.js vers le format PHP attendu
 */
function formatPayloadForPHP(
  payload: DemandeInfoPayload,
  produit: ProduitSelection
): DemandeInfoPHPPayload {
  const { acheteur } = payload;

  // Construire le payload PHP
  const phpPayload: DemandeInfoPHPPayload = {
    // Type de formulaire - utiliser un type reconnu par le PHP
    form_ab: 'form_fiche_produit',

    // Statut acheteur
    statut: acheteur.statut,
    rep_prof_part: acheteur.statut,

    // Identité
    civilite: acheteur.civilite || '',
    'nom-acheteur': acheteur.nom,
    'prenom-acheteur': acheteur.prenom,

    // Contact
    'mail-acheteur': acheteur.mail,
    'telephone-acheteur': acheteur.telephone,
    indicatif_tel: acheteur.indicatif_tel || '+33',

    // Entreprise
    'societe-acheteur': acheteur.societe,

    // Adresse
    'adresse-acheteur': acheteur.adresse || '',
    'code-postal-acheteur': acheteur.code_postal,
    'ville-acheteur': acheteur.ville,
    'pays-acheteur': acheteur.pays || '1', // 1 = France

    // Fonction/Service
    fonction: acheteur.fonction || '',
    service: acheteur.service || '',
    metier: acheteur.fonction || '',

    // Message
    'message-acheteur': payload.message || 'Demande de devis',

    // Produit/Société
    soc: produit.id_societe,
    [`check_id_prod_soc_${produit.id_societe}`]: produit.id_produit,

    // Options demande
    souhait_devis_prod_sim: payload.souhait_devis ? '1' : '0',
    souhaiter_devis: payload.souhait_devis ? 'on' : '',
    souhaiter_infos: payload.souhait_infos ? 'on' : '',
    souhaiter_rdv: payload.souhait_rdv ? 'on' : '',

    // Tracking
    abtest: payload.abtest || '',
    origine: payload.origine || '52', // 52 = origine par défaut
    provenance_di: payload.provenance_di || 'ux_matching',

    // Anti-robot (sera généré côté serveur)
    ddc_is_i: generateAntiRobotToken(),

    // Demande IA
    demande_ia: payload.demande_ia ? '1' : '',
  };

  // Ajouter SIRET/INSEE si disponible
  if (acheteur.id_siret_insee) {
    phpPayload.id_siret_insee = acheteur.id_siret_insee;
  }
  if (acheteur.id_cartegie) {
    phpPayload.id_cartegie_siret = acheteur.id_cartegie;
  }

  return phpPayload;
}

/**
 * Génère un token anti-robot simple
 */
function generateAntiRobotToken(): string {
  return btoa(Date.now().toString());
}

/**
 * Convertit un objet en FormData pour l'envoi POST
 */
function objectToFormData(obj: Record<string, unknown>): FormData {
  const formData = new FormData();

  Object.entries(obj).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      formData.append(key, String(value));
    }
  });

  return formData;
}

/**
 * Envoie une demande d'information pour UN produit
 */
async function envoyerDemandeUnique(
  payload: DemandeInfoPayload,
  produit: ProduitSelection
): Promise<DemandeInfoResponse> {
  const phpPayload = formatPayloadForPHP(payload, produit);

  try {
    const response = await fetch(`${getApiBasePath()}/api/demande-info`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(phpPayload),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const text = await response.text();

    // Le PHP retourne l'URL de redirection directement
    if (text.startsWith('http')) {
      return {
        success: true,
        redirect_url: text.trim(),
      };
    }

    // Essayer de parser comme JSON si ce n'est pas une URL
    try {
      const data = JSON.parse(text);
      return {
        success: true,
        ...data,
      };
    } catch {
      return {
        success: true,
        redirect_url: text.trim(),
      };
    }
  } catch (error) {
    console.error('Erreur envoi demande:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Erreur inconnue',
    };
  }
}

/**
 * Envoie les demandes d'information pour TOUS les produits sélectionnés
 * 1 produit sélectionné = 1 demande créée
 */
export async function envoyerDemandes(
  payload: DemandeInfoPayload
): Promise<DemandeInfoResponse[]> {
  const resultats: DemandeInfoResponse[] = [];

  // Envoyer une demande pour chaque produit sélectionné
  for (const produit of payload.produits) {
    const resultat = await envoyerDemandeUnique(payload, produit);
    resultats.push(resultat);

    // Petit délai entre les requêtes pour ne pas surcharger le serveur
    if (payload.produits.length > 1) {
      await new Promise(resolve => setTimeout(resolve, 200));
    }
  }

  return resultats;
}

/**
 * Envoie les demandes en parallèle (plus rapide mais plus de charge serveur)
 */
export async function envoyerDemandesParallele(
  payload: DemandeInfoPayload
): Promise<DemandeInfoResponse[]> {
  const promesses = payload.produits.map(produit =>
    envoyerDemandeUnique(payload, produit)
  );

  return Promise.all(promesses);
}

/**
 * Export par défaut : envoi séquentiel (recommandé)
 */
export default envoyerDemandes;
