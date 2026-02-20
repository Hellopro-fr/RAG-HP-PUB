'use client';

import { useMemo, useEffect, useCallback } from 'react';
import { useBuyerCheck } from '@/hooks/api';
import type { ContactFormData } from '@/types';

interface BuyerInfo {
  firstName: string;
  lastName: string;
  phone: string;
  civility: string;
  company?: string;
  id_acheteur?: string;
}

interface UseBuyerAutoFillParams {
  email: string;
  categoryId: number | null;
  formData: ContactFormData;
  setFormData: (data: ContactFormData) => void;
}

interface UseBuyerAutoFillResult {
  isEmailValid: boolean;
  isCheckingBuyer: boolean;
  isExistingBuyer: boolean;
  isKnownBuyer: boolean;
  buyerInfo: BuyerInfo | null;
  duplicateMessage: string | null;
}

/**
 * Hook pour la validation email et le pré-remplissage automatique des données acheteur.
 *
 * Encapsule:
 * - Validation du format email
 * - Appel API buyer check
 * - Auto-remplissage du formulaire si l'acheteur est connu
 */
export function useBuyerAutoFill({
  email,
  categoryId,
  formData,
  setFormData,
}: UseBuyerAutoFillParams): UseBuyerAutoFillResult {
  // Email validation
  const isEmailValid = useMemo(() => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  }, [email]);

  // Buyer check API call
  const { data: buyerCheckResult, isLoading: isCheckingBuyer } = useBuyerCheck(
    {
      email,
      rubriqueId: categoryId?.toString(),
    },
    isEmailValid
  );

  const isExistingBuyer = buyerCheckResult?.isDuplicate || false;
  const isKnownBuyer = buyerCheckResult?.isKnown || false;

  // Extract buyer info if known
  const buyerInfo: BuyerInfo | null = useMemo(() => {
    if (!isKnownBuyer || !buyerCheckResult?.infoBuyer) {
      return null;
    }
    const info = buyerCheckResult.infoBuyer as any;
    return {
      firstName: info.prenom || '',
      lastName: info.nom || '',
      phone: info.tel || '',
      civility: info.cv || '',
      company: info.societe || undefined,
      id_acheteur: info.id?.toString() || undefined,
    };
  }, [isKnownBuyer, buyerCheckResult?.infoBuyer]);

  // Auto-fill form data when buyer info changes
  useEffect(() => {
    if (isKnownBuyer && buyerInfo) {
      setFormData({
        ...formData,
        email,
        isKnown: true,
        firstName: buyerInfo.firstName,
        lastName: buyerInfo.lastName,
        phone: buyerInfo.phone,
        civility: buyerInfo.civility,
        company: buyerInfo.company || formData.company || '',
        id_acheteur: buyerInfo.id_acheteur,
      });
    } else if (!isKnownBuyer && buyerCheckResult !== undefined) {
      // Only reset if we got a response (not on initial load)
      setFormData({
        ...formData,
        email,
        isKnown: false,
        firstName: '',
        lastName: '',
        phone: '',
        countryCode: formData.countryCode || '+33',
        id_pays_tel: formData.id_pays_tel || 1,
        id_acheteur: undefined,
      });
    }
    // Only trigger when buyer status changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isKnownBuyer, buyerInfo]);

  // Message pour doublon (si existant)
  const duplicateMessage = buyerCheckResult?.message || null;

  return {
    isEmailValid,
    isCheckingBuyer,
    isExistingBuyer,
    isKnownBuyer,
    buyerInfo,
    duplicateMessage,
  };
}
