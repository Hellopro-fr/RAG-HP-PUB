/**
 * Service pour récupérer les villes par code postal
 * Proxy via /api/geo
 */

import { basePath } from '@/lib/utils';

export interface PostalCodeCity {
  postalCode: string;
  city: string;
}

export async function searchPostalCodeCities(
  postalCode: string
): Promise<PostalCodeCity[]> {
  if (postalCode.length < 3) {
    return [];
  }

  try {
    const apiBase = basePath || '';
    const response = await fetch(
      `${apiBase}/api/geo?t=2&cp=${encodeURIComponent(postalCode)}`,
      {
        method: "GET",
        headers: {
          'Accept': 'application/json',
        },
      }
    );

    if (!response.ok) {
      console.error(`Erreur API: ${response.status}`);
      return [];
    }
    console.log("Postal code search response status:", response);
    const data = await response.json();
    console.log("Raw postal code search data:", data);
    // Transformer les données de l'API au format attendu
    if (Array.isArray(data)) {
      return data.map((item: any) => ({
        postalCode: item.cp || item.postalCode || "",
        city: item.ville || item.city || "",
      }));
    }
    console.log("AFTER MAP postal code search data:", data);


    return data.data || [];
  } catch (error) {
    console.error("Erreur lors de la recherche de code postal:", error);
    return [];
  }
}