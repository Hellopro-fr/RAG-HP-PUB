// ========================================
// SUPPLIERS SERVICE - API CALLS
// ========================================

import { get } from '@/lib/api/client';
import { ENDPOINTS } from '@/lib/api/endpoints';
import type { Supplier, ApiResponse, UserAnswers } from '@/types';
import { RECOMMENDED_SUPPLIERS_DATA, OTHER_SUPPLIERS_DATA } from '@/data/suppliers';

/**
 * Fetch all suppliers
 */
export async function fetchSuppliers(): Promise<ApiResponse<Supplier[]>> {
  try {
    const response = await get<Supplier[]>(ENDPOINTS.suppliers.list());

    if (response.error || !response.data) {
      const allSuppliers = [...RECOMMENDED_SUPPLIERS_DATA, ...OTHER_SUPPLIERS_DATA];
      return { data: allSuppliers, error: null, status: 200 };
    }

    return response;
  } catch {
    const allSuppliers = [...RECOMMENDED_SUPPLIERS_DATA, ...OTHER_SUPPLIERS_DATA];
    return { data: allSuppliers, error: null, status: 200 };
  }
}

/**
 * Fetch supplier by ID
 */
export async function fetchSupplierById(id: string): Promise<ApiResponse<Supplier>> {
  try {
    const response = await get<Supplier>(ENDPOINTS.suppliers.getById(id));

    if (response.error || !response.data) {
      const allSuppliers = [...RECOMMENDED_SUPPLIERS_DATA, ...OTHER_SUPPLIERS_DATA];
      const supplier = allSuppliers.find(s => s.id === id);
      return {
        data: supplier || null,
        error: supplier ? null : 'Supplier not found',
        status: supplier ? 200 : 404,
      };
    }

    return response;
  } catch {
    const allSuppliers = [...RECOMMENDED_SUPPLIERS_DATA, ...OTHER_SUPPLIERS_DATA];
    const supplier = allSuppliers.find(s => s.id === id);
    return {
      data: supplier || null,
      error: supplier ? null : 'Supplier not found',
      status: supplier ? 200 : 404,
    };
  }
}

/**
 * Fetch recommended suppliers based on user answers
 */
export async function fetchRecommendedSuppliers(answers: UserAnswers): Promise<ApiResponse<{
  recommended: Supplier[];
  others: Supplier[];
}>> {
  try {
    const response = await get<{ recommended: Supplier[]; others: Supplier[] }>(
      ENDPOINTS.suppliers.getRecommended(answers)
    );

    if (response.error || !response.data) {
      return {
        data: {
          recommended: RECOMMENDED_SUPPLIERS_DATA,
          others: OTHER_SUPPLIERS_DATA,
        },
        error: null,
        status: 200,
      };
    }

    return response;
  } catch {
    return {
      data: {
        recommended: RECOMMENDED_SUPPLIERS_DATA,
        others: OTHER_SUPPLIERS_DATA,
      },
      error: null,
      status: 200,
    };
  }
}

/**
 * Search suppliers with filters
 */
export async function searchSuppliers(
  params: Record<string, string>
): Promise<ApiResponse<Supplier[]>> {
  try {
    const response = await get<Supplier[]>(ENDPOINTS.suppliers.search(params));

    if (response.error || !response.data) {
      // Apply basic filtering on local data
      const allSuppliers = [...RECOMMENDED_SUPPLIERS_DATA, ...OTHER_SUPPLIERS_DATA];
      const query = params.q?.toLowerCase();

      if (!query) return { data: allSuppliers, error: null, status: 200 };

      const filtered = allSuppliers.filter(
        s =>
          s.productName.toLowerCase().includes(query) ||
          s.supplierName.toLowerCase().includes(query) ||
          s.description.toLowerCase().includes(query)
      );

      return { data: filtered, error: null, status: 200 };
    }

    return response;
  } catch {
    const allSuppliers = [...RECOMMENDED_SUPPLIERS_DATA, ...OTHER_SUPPLIERS_DATA];
    return { data: allSuppliers, error: null, status: 200 };
  }
}
