import type { ApiResponse } from '../types';
import { basePath } from '@/lib/utils';

// Toujours utiliser le proxy Next.js pour éviter les problèmes CORS
// Le proxy côté serveur fait l'appel à hellopro.fr sans restriction CORS
const getApiBasePath = () => {
  return basePath || '';
};

export interface SirenCompanyData {
  siren     : string;
  siret     : string;
  name      : string;
  address   : string;
  postalCode: string;
  city      : string;
  naf       : string;
}

export interface SirenSearchParams {
  query: string; // Nom de société OU SIREN
}

/**
 * Interface pour la réponse de l'API INSEE v2
 */
interface InseeV2Response {
  status: string;
  nb    : number;
  max   : number;
  result: Array<{
    naf    : string;
    siret  : string;
    nomen  : string;
    cp     : string;
    adresse: string;
    ville  : string;
  }>;
}

/**
 * Parser la réponse JSON de l'API Legacy INSEE v2
 * Format: { status, nb, max, result: [{ siret, nomen, cp, adresse, ville }] }
 */
function parseInseeV2Response(data: InseeV2Response): SirenCompanyData[] {
  const companies: SirenCompanyData[] = [];

  try {
    if (!data.result || !Array.isArray(data.result)) {
      return [];
    }

    data.result.forEach((company) => {
      const siren = company.siret.substring(0, 9); // Extraire les 9 premiers chiffres = SIREN

      companies.push({
        siren,
        siret: company.siret,
        name: company.nomen,
        address: company.adresse,
        postalCode: company.cp,
        city: company.ville,
        naf: company.naf,
      });
    });

    return companies;
  } catch (error) {
    console.error('Error parsing INSEE v2 response:', error);
    return [];
  }
}

/**
 * Rechercher une entreprise par nom ou SIREN
 * Compatible avec l'API Legacy INSEE v2 (retourne du JSON)
 * URL: https://www.hellopro.fr/api_insee/_ag_web_service_insee_v2.php
 */
export async function searchCompanyBySiren(
  params: SirenSearchParams
): Promise<ApiResponse<SirenCompanyData[]>> {
  try {
    // Validation du paramètre query
    if (!params.query || params.query.trim().length < 2) {
      return {
        data: null,
        error: 'Veuillez saisir au moins 2 caractères',
      };
    }

    // Construction URL - toujours utiliser le proxy Next.js pour éviter CORS
    const apiBase = getApiBasePath();
    const url = new URL(`${apiBase}/api/siren/search`, window.location.origin);
    url.searchParams.append('soc', params.query.trim());
    url.searchParams.append('p', 'demande_information_v2');

    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      },
    });

    if (!response.ok) {
      return {
        data: null,
        error: `Erreur API: ${response.status}`,
      };
    }

    const jsonData: InseeV2Response = await response.json();

    // L'API retourne status: "no records found" si aucun résultat
    if (jsonData.status === 'no records found' || !jsonData.result) {
      return {
        data: [],
        error: null,
      };
    }

    // Parser la réponse JSON de l'API Legacy v2
    const companies = parseInseeV2Response(jsonData);

    return {
      data: companies,
      error: null,
    };
  } catch (error) {
    console.error('Error searching company by SIREN:', error);
    return {
      data: null,
      error: error instanceof Error ? error.message : 'Erreur lors de la recherche',
    };
  }
}

/**
 * Sélectionner une entreprise dans les résultats SIREN
 */
export interface SelectCompanyParams {
  siren: string;
  siret: string;
  naf: string;
  name: string;
  address: string;
  postalCode: string;
  city: string;
}

export async function selectCompany(
  params: SelectCompanyParams
): Promise<ApiResponse<SirenCompanyData>> {
  try {
    // Validation du SIREN (9 chiffres)
    if (!/^\d{9}$/.test(params.siren)) {
      return {
        data: null,
        error: 'Le SIREN doit contenir 9 chiffres',
      };
    }

    // Retourne les données sélectionnées
    return {
      data: {
        siren: params.siren,
        siret: params.siret,
        name: params.name,
        address: params.address,
        postalCode: params.postalCode,
        city: params.city,
        naf: params.naf || '',
      },
      error: null,
    };
  } catch (error) {
    console.error('Error selecting company:', error);
    return {
      data: null,
      error: error instanceof Error ? error.message : 'Erreur lors de la sélection',
    };
  }
}
