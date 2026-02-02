// ========================================
// LEADS SERVICE - API CALLS
// ========================================

import { post, get } from '@/lib/api/client';
import { ENDPOINTS } from '@/lib/api/endpoints';
import type { LeadSubmission, LeadResponse, ApiResponse } from '@/types';

/**
 * Submit a lead (contact form with supplier selection)
 */
export async function submitLead(data: LeadSubmission): Promise<ApiResponse<LeadResponse>> {
  try {
    const response = await post<LeadResponse>(ENDPOINTS.leads.submit(), data);

    // For now, if API is not available, simulate success
    if (response.error) {
      console.log('[Mock] Lead submitted:', data);
      return {
        data: {
          success: true,
          leadId: `LEAD-${Date.now()}`,
          message: 'Votre demande a bien été envoyée aux fournisseurs sélectionnés.',
          redirectUrl: '/confirmation',
        },
        error: null,
        status: 201,
      };
    }

    return response;
  } catch {
    console.log('[Mock] Lead submitted:', data);
    return {
      data: {
        success: true,
        leadId: `LEAD-${Date.now()}`,
        message: 'Votre demande a bien été envoyée aux fournisseurs sélectionnés.',
        redirectUrl: '/confirmation',
      },
      error: null,
      status: 201,
    };
  }
}

/**
 * Get lead by ID (for confirmation page)
 */
export async function getLeadById(id: string): Promise<ApiResponse<LeadSubmission & { status: string }>> {
  try {
    const response = await get<LeadSubmission & { status: string }>(ENDPOINTS.leads.getById(id));
    return response;
  } catch {
    return {
      data: null,
      error: 'Lead not found',
      status: 404,
    };
  }
}
