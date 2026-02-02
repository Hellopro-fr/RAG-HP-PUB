"use client";

import { useQuery } from '@tanstack/react-query';
import { searchCompanies } from '@/lib/api/services/companies.service';

export function useCompanySearch(query: string) {
  return useQuery({
    queryKey: ['companies', 'search', query],
    queryFn: async () => {
      const response = await searchCompanies(query);
      if (response.error) throw new Error(response.error);
      return response.data;
    },
    enabled: query.length >= 2,
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
}
