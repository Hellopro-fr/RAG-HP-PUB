import { create } from 'zustand';
import { persist, createJSONStorage, type StateStorage } from 'zustand/middleware';
import { useEffect, useState } from 'react';
import type { ContactFormData, ProfileData, UserAnswers, Supplier } from '@/types';
import type { CharacteristicsMap } from '@/types/characteristics';

// =============================================================================
// STORAGE WRAPPER - Gère le reset sur reload (F5) et changement manuel d'URL
// =============================================================================

// Clé de sessionStorage pour le flag de redirection
const NEEDS_REDIRECT_KEY = 'flow-needs-redirect';

// Exporter la clé pour FlowStorageReset
export const FLOW_NEEDS_REDIRECT_KEY = NEEDS_REDIRECT_KEY;

// =============================================================================
// EXÉCUTION IMMÉDIATE - Doit s'exécuter AVANT que Zustand hydrate
// =============================================================================
// NOTE: Ce bloc ne s'exécute que lors d'un FULL page load (F5, nav manuelle,
// premier accès, back/forward). La navigation SPA ne ré-exécute jamais le
// code module-level car le module est déjà chargé en mémoire.
// =============================================================================
if (typeof window !== 'undefined') {
  try {
    const navEntries = performance.getEntriesByType('navigation') as PerformanceNavigationTiming[];
    const navType = navEntries.length > 0 ? navEntries[0].type : 'navigate';

    // Flag pour savoir si une session flow était déjà active
    const SESSION_ACTIVE_KEY = 'flow-session-active';
    const wasSessionActive = sessionStorage.getItem(SESSION_ACTIVE_KEY) === 'true';

    let shouldClear = false;
    let needsRedirect = false;
    let reason = 'unknown';

    if (navType === 'reload') {
      // F5 / Actualiser
      shouldClear = true;
      needsRedirect = true;
      reason = 'reload';
    } else if (navType === 'back_forward') {
      // Bouton retour/avancer du navigateur
      shouldClear = true;
      needsRedirect = true;
      reason = 'back-forward';
    } else if (navType === 'navigate' && wasSessionActive) {
      // Changement manuel d'URL (la session existait déjà)
      shouldClear = true;
      needsRedirect = true;
      reason = 'manual-url-change';
    } else if (navType === 'navigate' && !wasSessionActive) {
      // Première visite → partir propre, pas de redirect
      shouldClear = true;
      needsRedirect = false;
      reason = 'first-visit';
    }

    if (shouldClear) {
      sessionStorage.removeItem('flow-storage');
      console.log('[FlowStore] Storage cleared -', reason);
    }

    if (needsRedirect) {
      sessionStorage.setItem(NEEDS_REDIRECT_KEY, 'true');
      console.log('[FlowStore] Redirect flag set');
    }

    // Marquer la session comme active
    sessionStorage.setItem(SESSION_ACTIVE_KEY, 'true');

  } catch (e) {
    console.error('[FlowStore] Error in navigation detection:', e);
  }
}

/**
 * Storage wrapper simple pour sessionStorage
 */
const createSessionStorage = (): StateStorage => {
  return {
    getItem: (name: string): string | null => {
      if (typeof window === 'undefined') return null;
      try {
        return sessionStorage.getItem(name);
      } catch {
        return null;
      }
    },
    setItem: (name: string, value: string): void => {
      if (typeof window === 'undefined') return;
      try {
        sessionStorage.setItem(name, value);
      } catch {
        // Ignore les erreurs de quota
      }
    },
    removeItem: (name: string): void => {
      if (typeof window === 'undefined') return;
      try {
        sessionStorage.removeItem(name);
      } catch {
        // Ignore
      }
    },
  };
};

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

  // Produits orphelins (sélectionnés mais plus dans les nouveaux résultats après modification critères)
  orphanedSelectedSuppliers: Supplier[];

  // Flag pour indiquer que les critères ont été modifiés
  criteriaHaveChanged: boolean;

  setMatchingResults: (results: { recommended: any[], others: any[] }) => void;
  setCharacteristicsMap: (characteristics: CharacteristicsMap) => void;
  setOrphanedSelectedSuppliers: (suppliers: Supplier[]) => void;
  setCriteriaHaveChanged: (changed: boolean) => void;

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
  orphanedSelectedSuppliers: [],
  criteriaHaveChanged: false,
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

      setOrphanedSelectedSuppliers: (suppliers) => set({ orphanedSelectedSuppliers: suppliers }),

      setCriteriaHaveChanged: (changed) => set({ criteriaHaveChanged: changed }),

    }),
    {
      name: 'flow-storage',
      // Utiliser notre storage wrapper qui clear automatiquement lors d'un F5
      storage: createJSONStorage(createSessionStorage),
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
