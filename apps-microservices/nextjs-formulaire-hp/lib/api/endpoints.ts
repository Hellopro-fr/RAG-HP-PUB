// ========================================
// API ENDPOINTS CONFIGURATION
// ========================================

// Base URL for API - configured via environment variable (Next.js format)
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || '/api';

// Endpoints configuration
export const ENDPOINTS = {
  // Questions
  questions: {
    list: () => `${API_BASE_URL}/questions`,
    getById: (id: number) => `${API_BASE_URL}/questions/${id}`,
  },

  // Companies (for SIREN lookup)
  companies: {
    search: (query: string) => `${API_BASE_URL}/companies/search?q=${encodeURIComponent(query)}`,
    getBySiren: (siren: string) => `${API_BASE_URL}/companies/${siren}`,
  },

  // Location
  location: {
    searchPostalCodes: (prefix: string) => `${API_BASE_URL}/location/postal-codes?prefix=${encodeURIComponent(prefix)}`,
    getCitiesByPostalCode: (postalCode: string) => `${API_BASE_URL}/location/cities?postalCode=${encodeURIComponent(postalCode)}`,
    countries: () => `${API_BASE_URL}/location/countries`,
  },

  // Suppliers
  suppliers: {
    list: () => `${API_BASE_URL}/suppliers`,
    getById: (id: string) => `${API_BASE_URL}/suppliers/${id}`,
    search: (params: Record<string, string>) => {
      const searchParams = new URLSearchParams(params);
      return `${API_BASE_URL}/suppliers/search?${searchParams.toString()}`;
    },
    getRecommended: (answers: Record<number, string[]>) => {
      const params = new URLSearchParams();
      Object.entries(answers).forEach(([key, values]) => {
        values.forEach(v => params.append(`q${key}`, v));
      });
      return `${API_BASE_URL}/suppliers/recommended?${params.toString()}`;
    },
  },

  // Leads
  leads: {
    submit: () => `${API_BASE_URL}/leads`,
    getById: (id: string) => `${API_BASE_URL}/leads/${id}`,
  },

  // Criteria
  criteria: {
    capacities: () => `${API_BASE_URL}/criteria/capacities`,
    zones: () => `${API_BASE_URL}/criteria/zones`,
    options: () => `${API_BASE_URL}/criteria/options`,
    voltages: () => `${API_BASE_URL}/criteria/voltages`,
  },
} as const;
