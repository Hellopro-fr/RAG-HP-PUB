"use client";

import { useQuery } from '@tanstack/react-query';
import { fetchSuppliers, fetchRecommendedSuppliers } from '@/lib/api/services/suppliers.service';
import type { UserAnswers } from '@/types';

export function useSuppliers() {
  return useQuery({
    queryKey: ['suppliers'],
    queryFn: async () => {
      const response = await fetchSuppliers();
      if (response.error) throw new Error(response.error);
      return response.data;
    },
  });
}

export function useRecommendedSuppliers(answers: UserAnswers) {
  return useQuery({
    queryKey: ['suppliers', 'recommended', answers],
    queryFn: async () => {
      const response = await fetchRecommendedSuppliers(answers);
      if (response.error) throw new Error(response.error);
      return response.data;
    },
  });
}
