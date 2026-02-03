import { useQuery, useMutation } from '@tanstack/react-query';
import {
  searchCompanyBySiren,
  selectCompany,
  type SirenSearchParams,
  type SelectCompanyParams,
  type SirenCompanyData,
} from '@/lib/api/services/siret.service';

/**
 * Hook pour rechercher une entreprise par nom ou SIREN
 * Ne lance la recherche que si les paramètres sont valides
 */
export function useSirenSearch(params: SirenSearchParams, enabled = true) {
  return useQuery({
    queryKey: ['siren', 'search', params.query],
    queryFn: async () => {
      const response = await searchCompanyBySiren(params);
      if (response.error) {
        throw new Error(response.error);
      }
      return response.data;
    },
    enabled: enabled && !!params.query && params.query.trim().length >= 2,
    staleTime: 1000 * 60 * 5, // 5 minutes
    retry: 1,
  });
}

/**
 * Hook pour sélectionner une entreprise dans les résultats
 */
export function useSelectCompany() {
  return useMutation({
    mutationFn: async (params: SelectCompanyParams) => {
      const response = await selectCompany(params);
      if (response.error) {
        throw new Error(response.error);
      }
      return response.data;
    },
  });
}

/**
 * Hook combiné pour la gestion complète du SIREN
 * Retourne les fonctions de recherche et sélection
 */
export function useSirenManagement() {
  return {
    useSearch: useSirenSearch,
    useSelect: useSelectCompany,
  };
}
