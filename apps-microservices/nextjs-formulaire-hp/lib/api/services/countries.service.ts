import type { ApiResponse } from '../types';

export interface Country {
  id: number;
  libelle: string;
  default?: boolean;
}

export interface CountriesData {
  principal: Country[];
  complet: Country[];
}

/**
 * Récupérer les listes de pays (principal et complet)
 */
export async function fetchCountries(): Promise<ApiResponse<CountriesData>> {
  try {
    const response = await fetch(
      'https://dev-www.hellopro.fr/hellopro_fr/ajax/ajax_get_data.php?t=1',
      {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
        },
        // Cache les données pendant 1 heure
        next: { revalidate: 3600 },
      }
    );

    if (!response.ok) {
      return {
        data: null,
        error: `Erreur API: ${response.status}`,
      };
    }

    const result = await response.json();

    if (!result.success) {
      return {
        data: null,
        error: result.error || 'Erreur lors de la récupération des pays',
      };
    }

    return {
      data: result.data,
      error: null,
    };
  } catch (error) {
    console.error('Error fetching countries:', error);
    return {
      data: null,
      error: error instanceof Error ? error.message : 'Erreur réseau',
    };
  }
}

/**
 * Formater les pays pour le composant ProfileTypeStep
 */
export function formatCountriesForUI(data: CountriesData): {
  priorityCountries: string[];
  otherCountries: string[];
} {
  const priorityCountries = data.principal.map(c => c.libelle);
  const otherCountries = data.complet.map(c => c.libelle);

  return {
    priorityCountries,
    otherCountries,
  };
}