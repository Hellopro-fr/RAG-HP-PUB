// ========================================
// COMPANIES SERVICE - API CALLS
// ========================================

import { get } from '@/lib/api/client';
import { ENDPOINTS } from '@/lib/api/endpoints';
import type { CompanyResult, ApiResponse } from '@/types';
import { COMPANIES_DATA } from '@/data/companies';

/**
 * Search companies by name or SIREN
 */
export async function searchCompanies(query: string): Promise<ApiResponse<CompanyResult[]>> {
  if (!query || query.length < 2) {
    return { data: [], error: null, status: 200 };
  }

  try {
    const response = await get<CompanyResult[]>(ENDPOINTS.companies.search(query));

    // Fallback to local data if API fails
    if (response.error || !response.data) {
      const searchQuery = query.toLowerCase();
      const results = COMPANIES_DATA.filter(
        c => c.name.toLowerCase().includes(searchQuery) || c.siren.includes(query)
      ).slice(0, 10);

      return { data: results, error: null, status: 200 };
    }

    return response;
  } catch {
    const searchQuery = query.toLowerCase();
    const results = COMPANIES_DATA.filter(
      c => c.name.toLowerCase().includes(searchQuery) || c.siren.includes(query)
    ).slice(0, 10);

    return { data: results, error: null, status: 200 };
  }
}

/**
 * Get company by SIREN
 */
export async function getCompanyBySiren(siren: string): Promise<ApiResponse<CompanyResult>> {
  try {
    const response = await get<CompanyResult>(ENDPOINTS.companies.getBySiren(siren));

    if (response.error || !response.data) {
      const company = COMPANIES_DATA.find(c => c.siren === siren);
      return {
        data: company || null,
        error: company ? null : 'Company not found',
        status: company ? 200 : 404,
      };
    }

    return response;
  } catch {
    const company = COMPANIES_DATA.find(c => c.siren === siren);
    return {
      data: company || null,
      error: company ? null : 'Company not found',
      status: company ? 200 : 404,
    };
  }
}
