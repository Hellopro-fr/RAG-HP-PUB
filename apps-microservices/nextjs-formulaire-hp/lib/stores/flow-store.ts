import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { useEffect, useState } from 'react';
import type { ContactFormData, ProfileData, UserAnswers } from '@/types';
import type { CharacteristicsMap } from '@/types/characteristics';

// Types de parcours pour le tracking GTM
export type FlowType = 'principal' | 'pas_assez_produits' | 'pas_trouve_recherchez' | null;

export interface FlowState {
  // ID de la catégorie (depuis le token URL ou query param)
  categoryId: number | null;

  // Type de parcours (pour tracking GTM)
  flowType: FlowType;

  // État du questionnaire
  userAnswers: Record<number, string[]>;
  otherTexts: Record<number, string>;

  // État du questionnaire dynamique
  dynamicAnswers: Record<string, string[]>;
  dynamicEquivalences: Record<string, any[]>;

  // État du profil
  profileData: ProfileData | null;

  contactData: ContactFormData | null;

  // État de la sélection
  selectedSupplierIds: string[];

  // Timestamp de début (pour tracking)
  startTime: number | null;

  files: File[];

  entryUrl: string | null;

  equivalenceCaracteristique: any[];

  matchingResults: {
    recommended: any[];
    others: any[];
  } | null;

  // Map des caractéristiques (lookup table pour ID -> label/valeurs)
  characteristicsMap: CharacteristicsMap;

  setMatchingResults: (results: { recommended: any[], others: any[] }) => void;
  setCharacteristicsMap: (characteristics: CharacteristicsMap) => void;

  setFilesStore: (files: File[]) => void;
  addFilesStore: (newFiles: File[]) => void;

  // Actions
  setCategoryId: (id: number) => void;
  setUserAnswers: (answers: Record<number, string[]>) => void;
  setOtherTexts: (texts: Record<number, string>) => void;
  setAnswer: (questionId: number, answerIds: string[]) => void;
  setOtherText: (questionId: number, text: string) => void;
  // setDynamicAnswer: (questionCode: string, answerCodes: string[]) => void;
  // Dans votre flow-store.ts (aperçu conceptuel)
  setDynamicAnswer: (
    questionCode: string, 
    codes: string[], 
    equivalences?: any[]
  ) => void;

  setEquivalenceCaracteristique: (equivalences: any[]) => void;

  resetDynamicAnswers: () => void;
  setProfileData: (data: ProfileData) => void;
  setContactData: (data: ContactFormData) => void;
  setSelectedSupplierIds: (ids: string[]) => void;
  toggleSupplier: (supplierId: string) => void;
  setStartTime: (time: number) => void;
  reset: () => void;
  setEntryUrl: (url: string) => void;
  setFlowType: (flowType: FlowType) => void;
}

const initialState = {
  categoryId: null,
  flowType: null as FlowType,
  userAnswers: {},
  otherTexts: {},
  dynamicAnswers: {},
  dynamicEquivalences: {},
  profileData: null,
  contactData: null,
  selectedSupplierIds: [],
  startTime: null,
  files: [],
  entryUrl: "",
  equivalenceCaracteristique: [],
  matchingResults: null,
  characteristicsMap: {},
};

export const useFlowStore = create<FlowState>()(
  persist(
    (set, get) => ({
      ...initialState,

      setCategoryId: (id) => set({ categoryId: id }),

      setUserAnswers: (answers) => set({ userAnswers: answers }),

      setOtherTexts: (texts) => set({ otherTexts: texts }),

      setAnswer: (questionId, answerIds) =>
        set((state) => ({
          userAnswers: {
            ...state.userAnswers,
            [questionId]: answerIds,
          },
        })),

      setOtherText: (questionId, text) =>
        set((state) => ({
          otherTexts: {
            ...state.otherTexts,
            [questionId]: text,
          },
        })),

      // setDynamicAnswer: (questionCode, answerCodes) =>
      //   set((state) => ({
      //     dynamicAnswers: {
      //       ...state.dynamicAnswers,
      //       [questionCode]: answerCodes,
      //     },
      //   })),

      // Mise à jour de l'action pour accepter les équivalences
      setDynamicAnswer: (questionCode, codes, equivalences = []) =>
        set((state) => ({
          dynamicAnswers: {
            ...state.dynamicAnswers,
            [questionCode]: codes,
          },
          dynamicEquivalences: {
            ...state.dynamicEquivalences,
            [questionCode]: equivalences,
          },
        })),

      setEquivalenceCaracteristique: (data) => set({ equivalenceCaracteristique: data }),

      // resetDynamicAnswers: () => set({ dynamicAnswers: {} }),

      // N'oubliez pas de mettre à jour la fonction reset si vous en avez une
      resetDynamicAnswers: () =>
        set((state) => ({
          dynamicAnswers: {},
          dynamicEquivalences: {},
        })),

      setProfileData: (data) => set({ profileData: data }),

      setContactData: (data) => set({ contactData: data }),

      setFilesStore: (files) => set({ files }),
      addFilesStore: (newFiles) => set((state) => ({ 
        files: [...state.files, ...newFiles] 
      })),

      setSelectedSupplierIds: (ids) => set({ selectedSupplierIds: ids }),

      toggleSupplier: (supplierId) =>
        set((state) => {
          const isSelected = state.selectedSupplierIds.includes(supplierId);
          return {
            selectedSupplierIds: isSelected
              ? state.selectedSupplierIds.filter((id) => id !== supplierId)
              : [...state.selectedSupplierIds, supplierId],
          };
        }),

      setStartTime: (time) => set({ startTime: time }),

      reset: () => set(initialState),

      setEntryUrl: (url) => set({ entryUrl: url }),     

      setMatchingResults: (results) => set({ matchingResults: results }),

      setFlowType: (flowType) => set({ flowType }),

      setCharacteristicsMap: (characteristics) => set({ characteristicsMap: characteristics }),

    }),
    {
      name: 'flow-storage',
      storage: createJSONStorage(() => sessionStorage),
      // ✅ AJOUT IMPORTANT : partialize
      // On exclut 'files' de la persistance car un objet File ne se JSON.stringify pas.
      partialize: (state) => {
        const { files, ...rest } = state;
        return rest;
      },
    }
  )
);

// Sélecteurs utilitaires
export const selectHasCompletedQuestionnaire = (state: FlowState, totalQuestions: number) =>
  Object.keys(state.userAnswers).length >= totalQuestions;

export const selectHasCompletedProfile = (state: FlowState) =>
  state.profileData !== null;

export const selectTimeSpentSeconds = (state: FlowState) =>
  state.startTime ? Math.round((Date.now() - state.startTime) / 1000) : 0;

// =============================================================================
// HYDRATION HOOK - Attendre que le store soit hydraté depuis sessionStorage
// =============================================================================

/**
 * Hook pour attendre l'hydratation du store Zustand
 * Utiliser ce hook avant d'accéder aux données persistées
 *
 * @example
 * const isHydrated = useFlowStoreHydration();
 * if (!isHydrated) return <Loading />;
 * // Maintenant dynamicAnswers contient les vraies données
 */
export const useFlowStoreHydration = () => {
  const [isHydrated, setIsHydrated] = useState(false);

  useEffect(() => {
    // onFinishHydration est appelé quand le store est hydraté
    const unsubFinishHydration = useFlowStore.persist.onFinishHydration(() => {
      setIsHydrated(true);
    });

    // Si déjà hydraté (ex: navigation client-side), mettre à jour immédiatement
    if (useFlowStore.persist.hasHydrated()) {
      setIsHydrated(true);
    }

    return () => {
      unsubFinishHydration();
    };
  }, []);

  return isHydrated;
};
