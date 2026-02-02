"use client";

import { useQuery } from '@tanstack/react-query';
import { fetchQuestions } from '@/lib/api/services/questions.service';

export function useQuestions() {
  return useQuery({
    queryKey: ['questions'],
    queryFn: async () => {
      const response = await fetchQuestions();
      if (response.error) throw new Error(response.error);
      return response.data;
    },
    staleTime: 1000 * 60 * 60, // 1 hour
  });
}
