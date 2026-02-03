import type { ApiResponse } from '../types';
import { basePath } from '@/lib/utils';

// Toujours utiliser le proxy Next.js pour éviter les problèmes CORS
const getApiBasePath = () => {
  return basePath || '';
};

export interface BuyerCheckParams {
  email: string;
  rubriqueId?: string;
  urlPage?: string;
}

export interface BuyerCheckResult {
  isKnown: boolean;
  isDuplicate: boolean;
  message?: string;
  infoBuyer?: object;
}

/**
 * Vérifier si un acheteur est connu (doublon DI)
 * Compatible avec l'API Legacy: https://www.hellopro.fr/annuaire_hp/ajax/demande_information/verif_doublon_di.php
 */
export async function checkBuyerExists(
  params: BuyerCheckParams
): Promise<ApiResponse<BuyerCheckResult>> {
  try {
    // Validation email
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!params.email || !emailRegex.test(params.email.trim())) {
      return {
        data: null,
        error: 'Email invalide',
      };
    }

    // Construction du body FormData pour l'API Legacy
    const formData = new FormData();
    formData.append('email', params.email.trim());
    if (params.rubriqueId) {
      formData.append('id_rubrique', params.rubriqueId);
    }
    if (params.urlPage) {
      formData.append('url_page', encodeURIComponent(params.urlPage));
    }

    // Toujours utiliser le proxy Next.js pour éviter CORS
    const apiBase = getApiBasePath();
    const apiUrl = `${apiBase}/api/buyer/check`;

    const response = await fetch(apiUrl, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const result = await response.text();

    // L'API Legacy retourne '' si pas de doublon, 'notifier' si doublon
    const isDuplicate = result.trim() === 'notifier';
    let isKnown = result.trim() !== '';

    const data = {
        // "rubrique": "integer",
        // "id_produit_ia": "mixed",
        // "dir": "integer",
        // "target": "string",
        "value": "string",
        // "mhp": "integer",
        // "abtest": "string",
        "init": {
            "mail": params.email.trim(),
            "rub" : params.rubriqueId || '',
            // "msg": "string",
            // "obj": "string",
            // "qtte": "dsd",
            // "frns": "integer", 
            // "prod": "integer",
            // "origine": "string",
            // "type": "string",
            // "critere": "string",
            // "f_qtte": "string"
        }
    };

    const formData_verif = new FormData();

    Object.keys(data).forEach(key => { 
        // On transtype "key" pour rassurer TypeScript
        const typedKey = key as keyof typeof data;
        const value = data[typedKey];

        if (typeof value === 'object' && value !== null) {
            // Traitement pour l'objet "init"
            Object.keys(value).forEach(subKey => {
                const typedSubKey = subKey as keyof typeof value;
                formData_verif.append(`${key}[${subKey}]`, value[typedSubKey]);
            });
        } else {
            // Traitement pour les variables simples
            formData_verif.append(key, value as string);
        }
    });

    const apiUrlVerif = `${apiBase}/api/buyer/verif-mail-acheteur`;

    const responseVerif = await fetch(apiUrlVerif, {
      method: 'POST',
      body: formData_verif,
    });

    
    if (!responseVerif.ok) {
      throw new Error(`HTTP error! status: ${responseVerif.status}`); 
    }
    
    const VerifResponse = await responseVerif.json();

    // On vérifie si la clé 'verif' existe dans l'objet
    // Si 'verif' est présent -> l'utilisateur n'est pas connu (isKnown = false)
    // Si 'verif' est absent -> l'utilisateur est connu (isKnown = true)
    isKnown = !('verif' in VerifResponse);

    return {
      data: {
        isKnown,
        isDuplicate,
        message: isDuplicate
          ? 'Vous avez déjà effectué une demande dans cette même catégorie, elle est en cours de traitement.'
          : undefined,
        infoBuyer: VerifResponse
      },
      error: null,
    };
  } catch (error) {
    console.error('Error checking buyer:', error);

    // En cas d'erreur API, on considère l'acheteur comme inconnu (pas de blocage)
    return {
      data: {
        isKnown: false,
        isDuplicate: false,
      },
      error: null, // Pas d'erreur côté utilisateur, juste un log
    };
  }
}

/**
 * Récupérer les informations d'un acheteur connu
 * (si l'API Legacy fournit ces données)
 */
export interface KnownBuyerInfo {
  email: string;
  firstName?: string;
  lastName?: string;
  company?: string;
  phone?: string;
}

export async function getKnownBuyerInfo(
  email: string
): Promise<ApiResponse<KnownBuyerInfo>> {
  try {
    // Validation email
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!email || !emailRegex.test(email.trim())) {
      return {
        data: null,
        error: 'Email invalide',
      };
    }

    // TODO: Implémenter l'endpoint Legacy si disponible
    // Pour l'instant, l'API Legacy ne fournit pas directement les infos acheteur
    return {
      data: null,
      error: 'Endpoint non disponible dans l\'API Legacy',
    };
  } catch (error) {
    console.error('Error getting buyer info:', error);
    return {
      data: null,
      error: error instanceof Error ? error.message : 'Erreur lors de la récupération',
    };
  }
}
