import { useQuery, useMutation } from '@tanstack/react-query';
import {
  checkBuyerExists,
  getKnownBuyerInfo,
  type BuyerCheckParams,
  type BuyerCheckResult,
  type KnownBuyerInfo,
} from '@/lib/api/services/buyer.service';

/**
 * Hook pour vérifier si un acheteur existe (doublon DI)
 * Ne lance la vérification que si l'email est valide
 */
export function useBuyerCheck(params: BuyerCheckParams, enabled = true) {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const isEmailValid = params.email && emailRegex.test(params.email.trim());

  return useQuery({
    queryKey: ['buyer', 'check', params.email, params.rubriqueId],
    queryFn: async () => {
      const response = await checkBuyerExists(params);
      if (response.error) {
        throw new Error(response.error);
      }
      return response.data;
    },
    enabled: enabled && !!isEmailValid,
    staleTime: 1000 * 60 * 2, // 2 minutes
    retry: false, // Pas de retry pour ne pas spammer l'API
  });
}

/**
 * Hook pour récupérer les informations d'un acheteur connu
 */
export function useKnownBuyerInfo(email: string, enabled = true) {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const isEmailValid = email && emailRegex.test(email.trim());

  return useQuery({
    queryKey: ['buyer', 'info', email],
    queryFn: async () => {
      const response = await getKnownBuyerInfo(email);
      if (response.error) {
        throw new Error(response.error);
      }
      return response.data;
    },
    enabled: enabled && !!isEmailValid,
    staleTime: 1000 * 60 * 5, // 5 minutes
    retry: 1,
  });
}

/**
 * Hook mutation pour vérifier un acheteur de manière impérative
 */
export function useBuyerCheckMutation() {
  return useMutation({
    mutationFn: async (params: BuyerCheckParams) => {
      const response = await checkBuyerExists(params);
      if (response.error) {
        throw new Error(response.error);
      }
      return response.data;
    },
  });
}

/**
 * Hook combiné pour la gestion complète d'un acheteur
 */
export function useBuyerManagement() {
  return {
    useCheck: useBuyerCheck,
    useInfo: useKnownBuyerInfo,
    useCheckMutation: useBuyerCheckMutation,
  };
}
