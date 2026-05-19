import { create } from 'zustand';
import { persist, createJSONStorage, type StateStorage } from 'zustand/middleware';
import { useEffect, useState } from 'react';
import type { ContactFormData, ProfileData, UserAnswers, Supplier } from '@/types';
import type { CharacteristicsMap } from '@/types/characteristics';
import type { PriceEstimationState } from '@/types/prix';

// =============================================================================
// STORAGE WRAPPER - Gère le reset sur reload (F5) et changement manuel d'URL
// =============================================================================

// Clé de sessionStorage pour le flag de redirection
const NEEDS_REDIRECT_KEY = 'flow-needs-redirect';

// Clé de sessionStorage pour le token original (ne pas effacer au reload)
const ORIGINAL_TOKEN_KEY = 'flow-original-token';

// Clé localStorage pour marquer soumission réussie (survit à window.location.href)
const SUBMISSION_COMPLETED_KEY = 'flow-submission-completed';

// Exporter les clés pour FlowStorageReset et questionnaire-client
export const FLOW_NEEDS_REDIRECT_KEY = NEEDS_REDIRECT_KEY;
export const FLOW_ORIGINAL_TOKEN_KEY = ORIGINAL_TOKEN_KEY;
export const FLOW_SUBMISSION_COMPLETED_KEY = SUBMISSION_COMPLETED_KEY;

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

    // Vérifier si l'utilisateur revient après une soumission externe
    const submissionDataRaw = localStorage.getItem(SUBMISSION_COMPLETED_KEY);
    let hasCompletedSubmission = false;
    let submissionToken: string | undefined;

    if (submissionDataRaw) {
      try {
        const submissionData = JSON.parse(submissionDataRaw);
        const now = Date.now();

        // Vérifier si le flag n'a pas expiré (48h - sécurité)
        if (submissionData.expiresAt && now < submissionData.expiresAt) {
          hasCompletedSubmission = true;
          submissionToken = submissionData.originalToken;
        } else {
          // Expiration : nettoyer le flag
          localStorage.removeItem(SUBMISSION_COMPLETED_KEY);
        }
      } catch (e) {
        // JSON invalide : nettoyer
        localStorage.removeItem(SUBMISSION_COMPLETED_KEY);
      }
    }

    let shouldClear = false;
    let needsRedirect = false;
    let reason = 'unknown';

    if (navType === 'reload') {
      // F5 / Actualiser
      shouldClear = true;
      needsRedirect = true;
      reason = 'reload';
    } else if (navType === 'back_forward' && hasCompletedSubmission) {
      // Retour navigateur APRÈS soumission externe
      // → Clear store + redirect vers Q1/Q2
      shouldClear = true;
      needsRedirect = true;
      reason = 'back-after-submission';

      // Sauvegarder le token pour redirection vers Q2
      if (submissionToken) {
        sessionStorage.setItem(ORIGINAL_TOKEN_KEY, submissionToken);
      }

      // Nettoyer le flag après utilisation (une seule redirection)
      localStorage.removeItem(SUBMISSION_COMPLETED_KEY);
    } else if (navType === 'back_forward') {
      // Bouton retour/avancer du navigateur NORMAL (pas après soumission)
      // Permettre la navigation naturelle dans le flow (pas de reset ni redirection)
      shouldClear = false;
      needsRedirect = false;
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
    }

    if (needsRedirect) {
      sessionStorage.setItem(NEEDS_REDIRECT_KEY, 'true');
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
export type FlowType = 'principal' | 'pas_assez_produits' | 'pas_trouve_recherchez' | 'budget_ne_correspond_pas' | null;

// Structure pour stocker les questions et réponses de l'utilisateur
export interface UserQuestionAnswer {
  questionId: number | string;
  questionCode?: string;
  questionLabel?: string;
  answerId: string | string[];
  answerLabel?: string | string[];
  equivalences?: any[];
  timestamp: number;
}

// Paramètres de test pour le scoring du matching (passés via URL)
export interface MatchingTestParams {
  z_unmatched?: number;
  e_unmatched?: number;
  g_unknown_score?: number;
  c_unknown_score?: number;
  v_blocked?: number;
  v_different?: number;
  t_unmatched?: number;
}

// Statistiques de la catégorie (nb produits, nb fournisseurs)
export interface CategoryStats {
  productsCount: number;
  suppliersCount: number;
}

// Données de géolocalisation (country, postalCode, city)
export interface GeoData {
  countryId: number;
  country: string;
  postalCode: string;
  city: string;
}

export interface FlowState {
  // ID de la catégorie (depuis le token URL ou query param)
  categoryId: number | null;

  // Version A/B test piloté par le token URL (champ abtest_UX_lead_version du payload décrypté)
  abtestUxLeadVersion: number | null;

  // Nom de la catégorie (depuis l'API questionnaire)
  categoryName: string | null;

  // Statistiques de la catégorie (depuis l'API info-categorie)
  categoryStats: CategoryStats | null;

  // Vignette de la catégorie (depuis l'API vignette-categorie)
  categoryVignette: string | null;

  // Type de parcours (pour tracking GTM)
  flowType: FlowType;

  // État du questionnaire
  userAnswers: Record<number, string[]>;
  otherTexts: Record<number, string>;

  // État du questionnaire dynamique
  dynamicAnswers: Record<string, string[]>;
  dynamicEquivalences: Record<string, any[]>;

  // Réponse de l'utilisateur à la question budget (page /budget intercalée
  // entre le loader matching et /selection). Contient le label de l'option
  // choisie (les options viennent de /api/prix.budget_reponse), ou null si
  // non répondu.
  userBudgetRange: string | null;

  // État du profil
  profileData: ProfileData | null;

  // Données de géolocalisation
  geoData: GeoData | null;

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

  ddc: string ;

  // Map des caractéristiques (lookup table pour ID -> label/valeurs)
  characteristicsMap: CharacteristicsMap;

  // Produits orphelins (sélectionnés mais plus dans les nouveaux résultats après modification critères)
  orphanedSelectedSuppliers: Supplier[];

  // Flag pour indiquer que les critères ont été modifiés
  criteriaHaveChanged: boolean;

  // IDs des critères supprimés par catégorie (pour pouvoir les réajouter)
  removedCritiqueCriteriaIds: number[];
  removedSecondaireCriteriaIds: number[];

  // Historique des questions/réponses de l'utilisateur (pour tracking et debug)
  userQuestionAnswers: UserQuestionAnswer[];

  // Paramètres de test pour le scoring du matching (passés via URL)
  matchingTestParams: MatchingTestParams | null;

  // Activation du rerank via RAG (passé via URL ?rerank=1)
  useRerank: boolean;

  // IDs des produits à soumettre (pour le devis unique vs sélection multiple)
  supplierIdsToSubmit: string[] | null;

  // Caractéristiques prix (prefetched au chargement Q1)
  caracteristiquesPrix: any[];

  // Résultat de l'estimation de prix
  priceEstimation: PriceEstimationState | null;

  // Indique si la page d'assurance (intercalée avant Q1/Q2) a déjà été vue
  // dans cette session — pour ne l'afficher qu'une seule fois.
  hasSeenAssurance: boolean;

  setMatchingResults: (results: { recommended: any[], others: any[] }) => void;
  setSupplierIdsToSubmit: (ids: string[] | null) => void;
  setMatchingTestParams: (params: MatchingTestParams | null) => void;
  setUseRerank: (useRerank: boolean) => void;
  setCharacteristicsMap: (characteristics: CharacteristicsMap) => void;
  setOrphanedSelectedSuppliers: (suppliers: Supplier[]) => void;
  setCriteriaHaveChanged: (changed: boolean) => void;

  setUserQuestionAnswers: (answers: UserQuestionAnswer[]) => void;
  addUserQuestionAnswer: (answer: UserQuestionAnswer) => void;
  updateUserQuestionAnswer: (questionCode: string, updates: Partial<UserQuestionAnswer>) => void;
  clearUserQuestionAnswers: () => void;
  truncateAnswersAfterIndex: (currentIndex: number) => void;

  setRemovedCritiqueCriteriaIds: (ids: number[]) => void;
  setRemovedSecondaireCriteriaIds: (ids: number[]) => void;
  addRemovedCriteriaId: (id: number, isCritique: boolean) => void;
  removeRemovedCriteriaId: (id: number) => void;

  setFilesStore: (files: File[]) => void;
  addFilesStore: (newFiles: File[]) => void;

  // Actions
  setCategoryId: (id: number) => void;
  setAbtestUxLeadVersion: (value: number | null) => void;
  setCategoryName: (name: string | null) => void;
  setCategoryStats: (stats: CategoryStats | null) => void;
  setCategoryVignette: (url: string | null) => void;
  setDdc: (ddc: string) => void;
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

  setUserBudgetRange: (range: string | null) => void;

  setEquivalenceCaracteristique: (equivalences: any[]) => void;

  resetDynamicAnswers: () => void;
  setProfileData: (data: ProfileData) => void;
  setGeoData: (data: GeoData) => void;
  setContactData: (data: ContactFormData) => void;
  setSelectedSupplierIds: (ids: string[]) => void;
  toggleSupplier: (supplierId: string) => void;
  setStartTime: (time: number) => void;
  reset: () => void;
  setHasSeenAssurance: (seen: boolean) => void;
  setEntryUrl: (url: string) => void;
  setFlowType: (flowType: FlowType) => void;
  setCaracteristiquesPrix: (data: any[]) => void;
  setPriceEstimation: (estimation: PriceEstimationState | null) => void;
}

const initialState = {
  categoryId: null,
  abtestUxLeadVersion: null as number | null,
  categoryName: null,
  categoryStats: null,
  categoryVignette: null,
  flowType: null as FlowType,
  userAnswers: {},
  otherTexts: {},
  dynamicAnswers: {},
  dynamicEquivalences: {},
  userBudgetRange: null,
  profileData: null,
  geoData: null,
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
  removedCritiqueCriteriaIds: [],
  removedSecondaireCriteriaIds: [],
  userQuestionAnswers: [],
  matchingTestParams: null,
  useRerank: false,
  ddc: "",
  supplierIdsToSubmit: null,
  caracteristiquesPrix: [],
  priceEstimation: null,
  hasSeenAssurance: false,
};

export const useFlowStore = create<FlowState>()(
  persist(
    (set, get) => ({
      ...initialState,

      setCategoryId: (id) => set({ categoryId: id }),

      setAbtestUxLeadVersion: (value) => set({ abtestUxLeadVersion: value }),

      setCategoryName: (name) => set({ categoryName: name }),

      setCategoryStats: (stats) => set({ categoryStats: stats }),

      setCategoryVignette: (url) => set({ categoryVignette: url }),

      setUserAnswers: (answers) => set({ userAnswers: answers }),

      setOtherTexts: (texts) => set({ otherTexts: texts }),

      setDdc: (ddc: string) => set({ ddc }),

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

      setUserBudgetRange: (range) => set({ userBudgetRange: range }),

      setEquivalenceCaracteristique: (data) => set({ equivalenceCaracteristique: data }),

      // resetDynamicAnswers: () => set({ dynamicAnswers: {} }),

      // N'oubliez pas de mettre à jour la fonction reset si vous en avez une
      resetDynamicAnswers: () =>
        set((state) => ({
          dynamicAnswers: {},
          dynamicEquivalences: {},
        })),

      setProfileData: (data) => set({ profileData: data }),

      setGeoData: (data) => set({ geoData: data }),

      setContactData: (data) => set({ contactData: data }),

      setFilesStore: (files) => set({ files }),
      addFilesStore: (newFiles) => set((state) => ({ 
        files: [...state.files, ...newFiles] 
      })),

      setSelectedSupplierIds: (ids) => set({ selectedSupplierIds: ids }),

      setSupplierIdsToSubmit: (ids) => set({ supplierIdsToSubmit: ids }),

      setCaracteristiquesPrix: (data) => set({ caracteristiquesPrix: data }),

      setPriceEstimation: (estimation) => set({ priceEstimation: estimation }),

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

      setHasSeenAssurance: (seen) => set({ hasSeenAssurance: seen }),

      setEntryUrl: (url) => set({ entryUrl: url }),     

      setMatchingResults: (results) => set({ matchingResults: results }),

      setMatchingTestParams: (params) => set({ matchingTestParams: params }),

      setUseRerank: (useRerank) => set({ useRerank }),

      setFlowType: (flowType) => set({ flowType }),

      setCharacteristicsMap: (characteristics) => set({ characteristicsMap: characteristics }),

      setOrphanedSelectedSuppliers: (suppliers) => set({ orphanedSelectedSuppliers: suppliers }),

      setCriteriaHaveChanged: (changed) => set({ criteriaHaveChanged: changed }),

      setUserQuestionAnswers: (answers) => set({ userQuestionAnswers: answers }),

      // Upsert par questionCode : remplace l'entrée existante si elle existe,
      // sinon ajoute. Aligne la sémantique sur dynamicAnswers/dynamicEquivalences
      // (qui sont des Records indexés par questionCode).
      addUserQuestionAnswer: (answer) =>
        set((state) => {
          const existing = state.userQuestionAnswers.findIndex(
            (qa) => qa.questionCode === answer.questionCode
          );
          if (existing >= 0) {
            const next = [...state.userQuestionAnswers];
            next[existing] = answer;
            return { userQuestionAnswers: next };
          }
          return { userQuestionAnswers: [...state.userQuestionAnswers, answer] };
        }),

      updateUserQuestionAnswer: (questionCode, updates) =>
        set((state) => ({
          userQuestionAnswers: state.userQuestionAnswers.map((qa) =>
            qa.questionCode === questionCode ? { ...qa, ...updates } : qa
          ),
        })),

      clearUserQuestionAnswers: () => set({ userQuestionAnswers: [] }),

      // Purge les réponses des questions postérieures à currentIndex (0-based).
      // Appelé avant submitAnswer pour éviter les entrées orphelines après
      // un retour-arrière + changement de réponse (ex: si Q1 change, le parcours Qn change).
      truncateAnswersAfterIndex: (currentIndex) =>
        set((state) => {
          // questionCode "Qn" est 1-based ; on garde Q1..Q(currentIndex+1).
          // Si code est absent ou non conforme : on garde par sécurité.
          const keep = (code: string | undefined) => {
            if (!code) return true;
            const m = code.match(/^Q(\d+)$/);
            return m ? parseInt(m[1], 10) <= currentIndex + 1 : true;
          };
          return {
            userQuestionAnswers: state.userQuestionAnswers.filter((qa) =>
              keep(qa.questionCode)
            ),
            dynamicAnswers: Object.fromEntries(
              Object.entries(state.dynamicAnswers).filter(([code]) => keep(code))
            ),
            dynamicEquivalences: Object.fromEntries(
              Object.entries(state.dynamicEquivalences).filter(([code]) => keep(code))
            ),
          };
        }),

      setRemovedCritiqueCriteriaIds: (ids: number[]) => set({ removedCritiqueCriteriaIds: ids }),

      setRemovedSecondaireCriteriaIds: (ids: number[]) => set({ removedSecondaireCriteriaIds: ids }),

      addRemovedCriteriaId: (id: number, isCritique: boolean) =>
        set((state) => {
          if (isCritique) {
            return {
              removedCritiqueCriteriaIds: state.removedCritiqueCriteriaIds.includes(id)
                ? state.removedCritiqueCriteriaIds
                : [...state.removedCritiqueCriteriaIds, id],
            };
          } else {
            return {
              removedSecondaireCriteriaIds: state.removedSecondaireCriteriaIds.includes(id)
                ? state.removedSecondaireCriteriaIds
                : [...state.removedSecondaireCriteriaIds, id],
            };
          }
        }),

      removeRemovedCriteriaId: (id: number) =>
        set((state) => ({
          removedCritiqueCriteriaIds: state.removedCritiqueCriteriaIds.filter((i) => i !== id),
          removedSecondaireCriteriaIds: state.removedSecondaireCriteriaIds.filter((i) => i !== id),
        })),

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
