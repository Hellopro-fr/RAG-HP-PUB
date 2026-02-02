// ========================================
// LOCATION SERVICE - API CALLS
// ========================================

import { get } from '@/lib/api/client';
import { ENDPOINTS } from '@/lib/api/endpoints';
import type { PostalCodeCity, ApiResponse } from '@/types';
import { POSTAL_CODE_CITIES_DATA, COUNTRIES_DATA } from '@/data/location';

/**
 * Search postal codes by prefix
 */
export async function searchPostalCodes(prefix: string): Promise<ApiResponse<PostalCodeCity[]>> {
  if (!prefix || prefix.length < 2) {
    return { data: [], error: null, status: 200 };
  }

  try {
    const response = await get<PostalCodeCity[]>(ENDPOINTS.location.searchPostalCodes(prefix));

    if (response.error || !response.data) {
      const results = POSTAL_CODE_CITIES_DATA
        .filter(item => item.postalCode.startsWith(prefix))
        .slice(0, 8);
      return { data: results, error: null, status: 200 };
    }

    return response;
  } catch {
    const results = POSTAL_CODE_CITIES_DATA
      .filter(item => item.postalCode.startsWith(prefix))
      .slice(0, 8);
    return { data: results, error: null, status: 200 };
  }
}

/**
 * Get cities by postal code
 */
export async function getCitiesByPostalCode(postalCode: string): Promise<ApiResponse<string[]>> {
  try {
    const response = await get<string[]>(ENDPOINTS.location.getCitiesByPostalCode(postalCode));

    if (response.error || !response.data) {
      const cities = POSTAL_CODE_CITIES_DATA
        .filter(item => item.postalCode === postalCode)
        .map(item => item.city);
      return { data: cities, error: null, status: 200 };
    }

    return response;
  } catch {
    const cities = POSTAL_CODE_CITIES_DATA
      .filter(item => item.postalCode === postalCode)
      .map(item => item.city);
    return { data: cities, error: null, status: 200 };
  }
}

/**
 * Get list of countries
 */
export async function getCountries(): Promise<ApiResponse<string[]>> {
  try {
    const response = await get<string[]>(ENDPOINTS.location.countries());

    if (response.error || !response.data) {
      return { data: COUNTRIES_DATA, error: null, status: 200 };
    }

    return response;
  } catch {
    return { data: COUNTRIES_DATA, error: null, status: 200 };
  }
}
