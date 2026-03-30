'use client';

import { X, GripVertical, Sparkles, Target, Gift, Check, Loader2, AlertCircle, Plus } from "lucide-react";
import { useState, useEffect, useRef, useCallback, memo } from "react";
import { trackModifyCriteriaModalView, trackCriteriaModified } from "@/lib/analytics";
import { useFlowStore } from "@/lib/stores/flow-store";
// import { useProcessMatchingLogic } from "@/hooks/api/useProcessMatchingLogic";
import { useProcessMatching } from "@/hooks/api/useProcessMatching";
import type {
  ConsolidatedCharacteristic,
  PoidsCaracteristique,
} from "@/lib/utils/equivalence-merger";
import {
  getCharacteristicLabel,
  getCharacteristicOptions,
} from "@/lib/utils/characteristics-helpers";
import type { CharacteristicsMap } from "@/types/characteristics";

interface ModifyCriteriaFormProps {
  onBack: () => void;
  onApply: (updatedEquivalences: ConsolidatedCharacteristic[]) => void;
}

// =============================================================================
// TYPES INTERNES POUR L'ÉTAT DU FORMULAIRE
// =============================================================================

interface CriterionFormState {
  id_caracteristique: number;
  label: string;
  type: 'textuelle' | 'numerique';
  poids_question: number;
  poids_caracteristique: PoidsCaracteristique;
  unite?: string;

  // Valeurs éditables
  valeurs_cibles_ids: number[];
  valeurs_bloquantes_ids: number[];
  // Pour numérique: toujours min/max (pas de valeur exacte séparée)
  valeur_numerique_min?: number;
  valeur_numerique_max?: number;

  // Options disponibles (à remplir via API caractéristiques)
  options_disponibles: { id: number; label: string }[];
  isMulti: boolean;
}

// =============================================================================
// COMPOSANT CRITERION CARD (memo pour éviter re-renders inutiles)
// =============================================================================

interface CriterionCardProps {
  criterion: CriterionFormState;
  isCritique: boolean;
  canRemove: boolean;
  onRemove: (id: number, isCritique: boolean) => void;
  onToggleMultiValue: (id: number, valueId: number, isCritique: boolean) => void;
  onUpdateSingleValue: (id: number, valueId: number, isCritique: boolean) => void;
  onUpdateNumericValue: (id: number, field: 'min' | 'max', value: string, isCritique: boolean) => void;
}

const CriterionCard = memo(({
  criterion,
  isCritique,
  canRemove,
  onRemove,
  onToggleMultiValue,
  onUpdateSingleValue,
  onUpdateNumericValue,
}: CriterionCardProps) => {
  // État local pour les inputs numériques (évite la perte de focus)
  const [localMin, setLocalMin] = useState<string>(
    criterion.valeur_numerique_min !== undefined ? String(criterion.valeur_numerique_min) : ''
  );
  const [localMax, setLocalMax] = useState<string>(
    criterion.valeur_numerique_max !== undefined ? String(criterion.valeur_numerique_max) : ''
  );

  // Synchroniser avec les props quand elles changent de l'extérieur
  useEffect(() => {
    setLocalMin(criterion.valeur_numerique_min !== undefined ? String(criterion.valeur_numerique_min) : '');
  }, [criterion.valeur_numerique_min]);

  useEffect(() => {
    setLocalMax(criterion.valeur_numerique_max !== undefined ? String(criterion.valeur_numerique_max) : '');
  }, [criterion.valeur_numerique_max]);

  // Validation: max doit être >= min
  const hasValidationError = (() => {
    if (localMin === '' || localMax === '') return false;
    const minVal = Number(localMin);
    const maxVal = Number(localMax);
    return !isNaN(minVal) && !isNaN(maxVal) && maxVal < minVal;
  })();

  // Handlers pour les inputs numériques (mise à jour locale immédiate, propagation sur blur)
  // Filtrer pour n'accepter que les chiffres, le point décimal et le signe moins
  const handleMinChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    // Autoriser uniquement: chiffres, point décimal, signe moins au début
    if (value === '' || /^-?\d*\.?\d*$/.test(value)) {
      setLocalMin(value);
    }
  };

  const handleMaxChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    // Autoriser uniquement: chiffres, point décimal, signe moins au début
    if (value === '' || /^-?\d*\.?\d*$/.test(value)) {
      setLocalMax(value);
    }
  };

  // Bloquer les touches non-numériques (lettres, caractères spéciaux sauf point et moins)
  const handleNumericKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    // Autoriser: chiffres, point, moins, Backspace, Delete, Tab, Enter, Arrows, Home, End
    const allowedKeys = ['Backspace', 'Delete', 'Tab', 'Enter', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'];
    const isNumber = /^[0-9]$/.test(e.key);
    const isDecimalPoint = e.key === '.' && !e.currentTarget.value.includes('.');
    const isMinus = e.key === '-' && e.currentTarget.selectionStart === 0 && !e.currentTarget.value.includes('-');

    if (!isNumber && !isDecimalPoint && !isMinus && !allowedKeys.includes(e.key) && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
    }
  };

  const handleMinBlur = () => {
    onUpdateNumericValue(criterion.id_caracteristique, 'min', localMin, isCritique);
  };

  const handleMaxBlur = () => {
    onUpdateNumericValue(criterion.id_caracteristique, 'max', localMax, isCritique);
  };

  return (
    <div className="flex items-start gap-3 rounded-xl border border-border bg-card p-3 transition-all hover:border-primary/30 hover:shadow-sm">
      <div className="flex-shrink-0 text-muted-foreground/40 mt-1">
        <GripVertical className="h-4 w-4" />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-xs font-medium text-muted-foreground">
            {criterion.label}
          </span>
          {criterion.unite && (
            <span className="text-[10px] bg-muted/60 text-muted-foreground px-1.5 py-0.5 rounded">
              {criterion.unite}
            </span>
          )}
        </div>

        {criterion.type === 'textuelle' ? (
          criterion.isMulti ? (
            // Multi-select: toggle buttons
            <div className="flex flex-wrap gap-1.5">
              {criterion.options_disponibles.map((option) => {
                const isSelected = criterion.valeurs_cibles_ids.includes(option.id);
                return (
                  <button
                    key={option.id}
                    onClick={() => onToggleMultiValue(criterion.id_caracteristique, option.id, isCritique)}
                    className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium transition-all ${
                      isSelected
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted/50 text-muted-foreground hover:bg-muted"
                    }`}
                  >
                    {isSelected && <Check className="h-3 w-3" />}
                    {option.label}
                  </button>
                );
              })}
            </div>
          ) : (
            // Single-select: dropdown
            <select
              value={criterion.valeurs_cibles_ids[0] ?? ''}
              onChange={(e) => onUpdateSingleValue(criterion.id_caracteristique, Number(e.target.value), isCritique)}
              className="w-full rounded-lg border-0 bg-muted/50 px-3 py-1.5 text-sm font-medium text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
            >
              {criterion.options_disponibles.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          )
        ) : (
          // Numérique: toujours min et max
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground w-8">Min</span>
              <input
                type="text"
                inputMode="decimal"
                value={localMin}
                onChange={handleMinChange}
                onKeyDown={handleNumericKeyDown}
                onBlur={handleMinBlur}
                placeholder="min"
                className={`w-24 rounded-lg border-0 bg-muted/50 px-3 py-1.5 text-sm font-medium text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 ${
                  hasValidationError ? 'ring-2 ring-destructive/50' : ''
                }`}
              />
              {criterion.unite && <span className="text-xs text-muted-foreground">{criterion.unite}</span>}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground w-8">Max</span>
              <input
                type="text"
                inputMode="decimal"
                value={localMax}
                onChange={handleMaxChange}
                onKeyDown={handleNumericKeyDown}
                onBlur={handleMaxBlur}
                placeholder="max"
                className={`w-24 rounded-lg border-0 bg-muted/50 px-3 py-1.5 text-sm font-medium text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 ${
                  hasValidationError ? 'ring-2 ring-destructive/50' : ''
                }`}
              />
              {criterion.unite && <span className="text-xs text-muted-foreground">{criterion.unite}</span>}
            </div>
            {hasValidationError && (
              <div className="flex items-center gap-1 text-xs text-destructive">
                <AlertCircle className="h-3 w-3" />
                <span>Le max doit être supérieur ou égal au min</span>
              </div>
            )}
          </div>
        )}
      </div>

      {canRemove && (
        <button
          onClick={() => onRemove(criterion.id_caracteristique, isCritique)}
          className="flex-shrink-0 rounded-full p-1.5 text-muted-foreground/60 hover:bg-destructive/10 hover:text-destructive transition-colors"
          title="Supprimer ce critère"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
});

CriterionCard.displayName = 'CriterionCard';

// =============================================================================
// HELPERS : ConsolidatedCharacteristic <-> CriterionFormState
// =============================================================================

function characteristicToFormState(
  c: ConsolidatedCharacteristic,
  characteristicsMap: CharacteristicsMap
): CriterionFormState {
  // Récupérer le label et les options depuis characteristicsMap
  const label = getCharacteristicLabel(characteristicsMap, c.id_caracteristique);
  const options = getCharacteristicOptions(characteristicsMap, c.id_caracteristique);
  const charDef = characteristicsMap[c.id_caracteristique];

  // Déterminer le type : prioriser characteristicsMap (source fiable), sinon fallback sur l'équivalence
  // L'API retourne 'Textuelle'/'Numérique' (majuscule), on normalise en minuscule
  const resolvedType: 'textuelle' | 'numerique' = charDef
    ? (charDef.type.toLowerCase() as 'textuelle' | 'numerique')
    : c.type_caracteristique;

  const state: CriterionFormState = {
    id_caracteristique: c.id_caracteristique,
    label,
    type: resolvedType,
    poids_question: c.poids_question,
    poids_caracteristique: c.poids_caracteristique,
    unite: c.unite || charDef?.unite || undefined,
    valeurs_cibles_ids: [],
    valeurs_bloquantes_ids: [],
    options_disponibles: options.length > 0 ? options : [],
    isMulti: false,
  };

  if (resolvedType === 'textuelle') {
    state.valeurs_cibles_ids = Array.isArray(c.valeurs_cibles)
      ? [...(c.valeurs_cibles as number[])]
      : [];
    state.valeurs_bloquantes_ids = Array.isArray(c.valeurs_bloquantes)
      ? [...c.valeurs_bloquantes]
      : [];

    // Si pas d'options depuis l'API, fallback sur les IDs connus
    if (state.options_disponibles.length === 0) {
      const allKnownIds = [...new Set([...state.valeurs_cibles_ids, ...state.valeurs_bloquantes_ids])];
      state.options_disponibles = allKnownIds.map(id => ({
        id,
        label: `Valeur ${id}`,
      }));
    }

    // Toujours autoriser la sélection multiple pour les caractéristiques textuelles
    state.isMulti = true;
  } else {
    // Numérique : toujours min/max
    // Si une valeur exacte est définie, l'utiliser comme min ET max
    // Note: Forcer la conversion en Number car les valeurs peuvent être des strings (venant de l'API)
    const val = c.valeurs_cibles;
    if (val && !Array.isArray(val)) {
      if (val.exact !== undefined) {
        // Valeur exacte → mettre en min et max identiques
        const exactNum = Number(val.exact);
        state.valeur_numerique_min = isNaN(exactNum) ? undefined : exactNum;
        state.valeur_numerique_max = isNaN(exactNum) ? undefined : exactNum;
      } else {
        const minNum = val.min !== undefined ? Number(val.min) : undefined;
        const maxNum = val.max !== undefined ? Number(val.max) : undefined;
        state.valeur_numerique_min = minNum !== undefined && !isNaN(minNum) ? minNum : undefined;
        state.valeur_numerique_max = maxNum !== undefined && !isNaN(maxNum) ? maxNum : undefined;
      }
    }
  }

  return state;
}

function formStateToCharacteristic(s: CriterionFormState): ConsolidatedCharacteristic {
  const result: ConsolidatedCharacteristic = {
    id_caracteristique: s.id_caracteristique,
    type_caracteristique: s.type,
    poids_question: s.poids_question,
    poids_caracteristique: s.poids_caracteristique,
    valeurs_cibles: [],
    valeurs_bloquantes: [],
  };

  if (s.unite) {
    result.unite = s.unite;
  }

  if (s.type === 'textuelle') {
    result.valeurs_cibles = [...s.valeurs_cibles_ids];
    result.valeurs_bloquantes = [...s.valeurs_bloquantes_ids];
  } else {
    // Toujours utiliser le format min/max
    const numVal: { min?: number; max?: number; exact?: number } = {};

    // Si min et max sont identiques, utiliser exact
    if (s.valeur_numerique_min !== undefined && s.valeur_numerique_max !== undefined
        && s.valeur_numerique_min === s.valeur_numerique_max) {
      numVal.exact = s.valeur_numerique_min;
    } else {
      if (s.valeur_numerique_min !== undefined) numVal.min = s.valeur_numerique_min;
      if (s.valeur_numerique_max !== undefined) numVal.max = s.valeur_numerique_max;
    }

    result.valeurs_cibles = Object.keys(numVal).length > 0 ? numVal : [];
    result.valeurs_bloquantes = [];
  }

  return result;
}

// =============================================================================
// COMPOSANT PRINCIPAL
// =============================================================================

const ModifyCriteriaForm = ({ onBack, onApply }: ModifyCriteriaFormProps) => {
  const {
    equivalenceCaracteristique,
    characteristicsMap,
    removedCritiqueCriteriaIds,
    removedSecondaireCriteriaIds,
    setRemovedCritiqueCriteriaIds,
    setRemovedSecondaireCriteriaIds,
  } = useFlowStore();
  // const { refetchMatchingWithUpdatedCriteria, isRefetching } = useProcessMatchingLogic();
  const { refetchMatchingWithUpdatedCriteria, isRefetching } = useProcessMatching();

  const [critiqueCriteria, setCritiqueCriteria] = useState<CriterionFormState[]>([]);
  const [secondaireCriteria, setSecondaireCriteria] = useState<CriterionFormState[]>([]);

  // Critères supprimés par catégorie (pour pouvoir les réajouter)
  const [removedCritiqueCriteria, setRemovedCritiqueCriteria] = useState<CriterionFormState[]>([]);
  const [removedSecondaireCriteria, setRemovedSecondaireCriteria] = useState<CriterionFormState[]>([]);
  const [showAddEssential, setShowAddEssential] = useState(false);
  const [showAddSecondary, setShowAddSecondary] = useState(false);

  const hasTrackedView = useRef(false);
  const hasInitialized = useRef(false);

  // Initialiser les critères depuis le store
  useEffect(() => {
    const consolidated = equivalenceCaracteristique as ConsolidatedCharacteristic[];
    const hasCharacteristicsData = Object.keys(characteristicsMap).length > 0;

    // Si pas de données dynamiques, ne rien faire
    if (!consolidated || consolidated.length === 0) {
      return;
    }

    // Si on a les données consolidées mais pas encore characteristicsMap, attendre
    // (sauf si on a déjà initialisé avec des données partielles)
    if (!hasCharacteristicsData && !hasInitialized.current) {
      // Initialiser avec les données partielles (labels génériques)
      hasInitialized.current = true;
    }

    const critiques: CriterionFormState[] = [];
    const secondaires: CriterionFormState[] = [];
    const removedCritiques: CriterionFormState[] = [];
    const removedSecondaires: CriterionFormState[] = [];

    // Récupérer les IDs des critères précédemment supprimés depuis le store (par catégorie)
    const removedCritiqueIdsSet = new Set(removedCritiqueCriteriaIds);
    const removedSecondaireIdsSet = new Set(removedSecondaireCriteriaIds);

    // Set pour éviter les doublons (déduplication par id_caracteristique)
    const seenIds = new Set<number>();

    for (const c of consolidated) {
      // Éviter les doublons
      if (seenIds.has(c.id_caracteristique)) {
        continue;
      }
      seenIds.add(c.id_caracteristique);

      const formState = characteristicToFormState(c, characteristicsMap);

      // Si ce critère était précédemment supprimé en tant que critique
      if (removedCritiqueIdsSet.has(c.id_caracteristique)) {
        removedCritiques.push({ ...formState, poids_caracteristique: 'critique' });
        continue;
      }

      // Si ce critère était précédemment supprimé en tant que secondaire
      if (removedSecondaireIdsSet.has(c.id_caracteristique)) {
        removedSecondaires.push({ ...formState, poids_caracteristique: 'secondaire' });
        continue;
      }

      // Normaliser en minuscule pour éviter les problèmes de casse ('Critique' vs 'critique')
      const poids = c.poids_caracteristique?.toLowerCase();
      if (poids === 'critique') {
        critiques.push(formState);
      } else {
        secondaires.push(formState);
      }
    }

    setCritiqueCriteria(critiques);
    setSecondaireCriteria(secondaires);
    setRemovedCritiqueCriteria(removedCritiques);
    setRemovedSecondaireCriteria(removedSecondaires);
  }, [equivalenceCaracteristique, characteristicsMap, removedCritiqueCriteriaIds, removedSecondaireCriteriaIds]);

  // Track modal view on mount
  useEffect(() => {
    if (!hasTrackedView.current) {
      hasTrackedView.current = true;
      trackModifyCriteriaModalView();
    }
  }, []);

  // =========================================================================
  // ACTIONS
  // =========================================================================

  const removeCriterion = useCallback((id: number, isCritique: boolean) => {
    if (isCritique) {
      setCritiqueCriteria(prev => {
        const criterionToRemove = prev.find(c => c.id_caracteristique === id);
        if (criterionToRemove) {
          // Conserver le critère supprimé dans la liste des critiques supprimés (éviter les doublons)
          setRemovedCritiqueCriteria((removed: CriterionFormState[]) => {
            if (removed.some(r => r.id_caracteristique === criterionToRemove.id_caracteristique)) {
              return removed; // Déjà présent, ne pas ajouter
            }
            return [...removed, criterionToRemove];
          });
        }
        return prev.filter(c => c.id_caracteristique !== id);
      });
    } else {
      setSecondaireCriteria(prev => {
        const criterionToRemove = prev.find(c => c.id_caracteristique === id);
        if (criterionToRemove) {
          // Conserver le critère supprimé dans la liste des secondaires supprimés (éviter les doublons)
          setRemovedSecondaireCriteria((removed: CriterionFormState[]) => {
            if (removed.some(r => r.id_caracteristique === criterionToRemove.id_caracteristique)) {
              return removed; // Déjà présent, ne pas ajouter
            }
            return [...removed, criterionToRemove];
          });
        }
        return prev.filter(c => c.id_caracteristique !== id);
      });
    }
  }, []);

  // Restaurer un critère supprimé (depuis la liste correspondante à sa catégorie d'origine)
  // Les valeurs sont réinitialisées (vierges) lors de la restauration
  const restoreCriterion = useCallback((id: number, fromEssential: boolean) => {
    if (fromEssential) {
      // Restaurer depuis la liste des critiques supprimés → vers critiques actifs
      setRemovedCritiqueCriteria((prev: CriterionFormState[]) => {
        const criterionToRestore = prev.find((c: CriterionFormState) => c.id_caracteristique === id);
        if (criterionToRestore) {
          // Réinitialiser les valeurs (vierge) et définir le poids
          const restored: CriterionFormState = {
            ...criterionToRestore,
            poids_caracteristique: 'critique' as PoidsCaracteristique,
            // Réinitialiser les valeurs
            valeurs_cibles_ids: [],
            valeurs_bloquantes_ids: [],
            valeur_numerique_min: undefined,
            valeur_numerique_max: undefined,
          };
          // Éviter les doublons
          setCritiqueCriteria(current => {
            if (current.some((c: CriterionFormState) => c.id_caracteristique === id)) {
              return current; // Déjà présent
            }
            return [...current, restored];
          });
        }
        return prev.filter((c: CriterionFormState) => c.id_caracteristique !== id);
      });
    } else {
      // Restaurer depuis la liste des secondaires supprimés → vers secondaires actifs
      setRemovedSecondaireCriteria((prev: CriterionFormState[]) => {
        const criterionToRestore = prev.find((c: CriterionFormState) => c.id_caracteristique === id);
        if (criterionToRestore) {
          // Réinitialiser les valeurs (vierge) et définir le poids
          const restored: CriterionFormState = {
            ...criterionToRestore,
            poids_caracteristique: 'secondaire' as PoidsCaracteristique,
            // Réinitialiser les valeurs
            valeurs_cibles_ids: [],
            valeurs_bloquantes_ids: [],
            valeur_numerique_min: undefined,
            valeur_numerique_max: undefined,
          };
          // Éviter les doublons
          setSecondaireCriteria(current => {
            if (current.some((c: CriterionFormState) => c.id_caracteristique === id)) {
              return current; // Déjà présent
            }
            return [...current, restored];
          });
        }
        return prev.filter((c: CriterionFormState) => c.id_caracteristique !== id);
      });
    }
    // Fermer les dropdowns
    setShowAddEssential(false);
    setShowAddSecondary(false);
  }, []);

  const updateSingleValue = useCallback((id: number, valueId: number, isCritique: boolean) => {
    const updateFn = (prev: CriterionFormState[]) =>
      prev.map(c => {
        if (c.id_caracteristique !== id) return c;
        return { ...c, valeurs_cibles_ids: [valueId] };
      });

    if (isCritique) setCritiqueCriteria(updateFn);
    else setSecondaireCriteria(updateFn);
  }, []);

  const toggleMultiValue = useCallback((id: number, valueId: number, isCritique: boolean) => {
    const updateFn = (prev: CriterionFormState[]) =>
      prev.map(c => {
        if (c.id_caracteristique !== id) return c;
        const isSelected = c.valeurs_cibles_ids.includes(valueId);
        if (isSelected) {
          if (c.valeurs_cibles_ids.length <= 1) return c;
          return { ...c, valeurs_cibles_ids: c.valeurs_cibles_ids.filter(v => v !== valueId) };
        }
        return { ...c, valeurs_cibles_ids: [...c.valeurs_cibles_ids, valueId] };
      });

    if (isCritique) setCritiqueCriteria(updateFn);
    else setSecondaireCriteria(updateFn);
  }, []);

  const updateNumericValue = useCallback((
    id: number,
    field: 'min' | 'max',
    value: string,
    isCritique: boolean
  ) => {
    const parsed = value === '' ? undefined : Number(value);
    const updateFn = (prev: CriterionFormState[]) =>
      prev.map(c => {
        if (c.id_caracteristique !== id) return c;
        if (field === 'min') {
          return { ...c, valeur_numerique_min: parsed };
        }
        return { ...c, valeur_numerique_max: parsed };
      });

    if (isCritique) setCritiqueCriteria(updateFn);
    else setSecondaireCriteria(updateFn);
  }, []);

  const handleApply = async () => {
    // Inclure TOUS les critères (y compris les supprimés) pour les stocker dans le store
    const allCriteria = [
      ...critiqueCriteria.map(formStateToCharacteristic),
      ...secondaireCriteria.map(formStateToCharacteristic),
      ...removedCritiqueCriteria.map(formStateToCharacteristic),
      ...removedSecondaireCriteria.map(formStateToCharacteristic),
    ];

    // Sauvegarder les IDs des critères supprimés dans le store (par catégorie)
    const newRemovedCritiqueIds = removedCritiqueCriteria.map((c: CriterionFormState) => c.id_caracteristique);
    const newRemovedSecondaireIds = removedSecondaireCriteria.map((c: CriterionFormState) => c.id_caracteristique);
    setRemovedCritiqueCriteriaIds(newRemovedCritiqueIds);
    setRemovedSecondaireCriteriaIds(newRemovedSecondaireIds);

    trackCriteriaModified(critiqueCriteria.length + secondaireCriteria.length);

    // Relancer le matching avec les nouvelles caractéristiques
    // Passer les IDs supprimés directement pour éviter le problème de stale closure
    const success = await refetchMatchingWithUpdatedCriteria(allCriteria, newRemovedCritiqueIds, newRemovedSecondaireIds);

    if (success) {
      // Appeler onApply pour fermer le modal et mettre à jour l'UI
      // Passer TOUS les critères (y compris les supprimés) pour que le store les conserve
      onApply(allCriteria);
    }
  };


  // =========================================================================
  // COMPOSANT DROPDOWN POUR AJOUTER UN CRITÈRE
  // =========================================================================

  const AddCriterionDropdown = ({
    isEssential,
    onClose
  }: {
    isEssential: boolean;
    onClose: () => void;
  }) => {
    // Utiliser la liste correspondante à la catégorie
    const criteriaList = isEssential ? removedCritiqueCriteria : removedSecondaireCriteria;

    if (criteriaList.length === 0) {
      return (
        <div className="rounded-xl border border-border bg-card p-4 text-center text-sm text-muted-foreground">
          Aucun critère à ajouter
          <button
            onClick={onClose}
            className="ml-2 text-primary hover:underline"
          >
            Fermer
          </button>
        </div>
      );
    }

    return (
      <div className="rounded-xl border border-border bg-card p-2 shadow-lg">
        <div className="text-xs font-medium text-muted-foreground px-2 py-1 mb-1">
          Ajouter un critère
        </div>
        {criteriaList.map((criterion: CriterionFormState) => (
          <button
            key={criterion.id_caracteristique}
            onClick={() => restoreCriterion(criterion.id_caracteristique, isEssential)}
            className="w-full text-left rounded-lg px-3 py-2 text-sm text-foreground hover:bg-muted transition-colors"
          >
            {criterion.label}
          </button>
        ))}
        <div className="border-t border-border mt-1 pt-1">
          <button
            onClick={onClose}
            className="w-full text-left rounded-lg px-3 py-2 text-sm text-muted-foreground hover:bg-muted transition-colors"
          >
            Annuler
          </button>
        </div>
      </div>
    );
  };

  // =========================================================================
  // RENDU PRINCIPAL
  // =========================================================================

  // Critères actifs (non supprimés) - utilisé pour le bouton "Affiner"
  const hasCriteria = critiqueCriteria.length > 0 || secondaireCriteria.length > 0;
  // Vérifier s'il y a des critères supprimés dans chaque catégorie
  const hasRemovedCritiqueCriteria = removedCritiqueCriteria.length > 0;
  const hasRemovedSecondaireCriteria = removedSecondaireCriteria.length > 0;
  // Vérifier si on a des critères (actifs OU supprimés qui peuvent être restaurés)
  const hasAnyCriteria = hasCriteria || hasRemovedCritiqueCriteria || hasRemovedSecondaireCriteria;
  // Vérifier si une section doit être affichée (critères actifs OU critères supprimés à restaurer)
  const showCritiqueSection = critiqueCriteria.length > 0 || hasRemovedCritiqueCriteria;
  const showSecondaireSection = secondaireCriteria.length > 0 || hasRemovedSecondaireCriteria;

  // Vérifier si tous les critères numériques ont des valeurs valides (max >= min)
  // Note: Forcer la conversion en Number car les valeurs peuvent être des strings (venant de l'API)
  const hasNumericValidationErrors = [...critiqueCriteria, ...secondaireCriteria].some(c => {
    if (c.type !== 'numerique') return false;
    if (c.valeur_numerique_min === undefined || c.valeur_numerique_max === undefined) return false;
    const minVal = Number(c.valeur_numerique_min);
    const maxVal = Number(c.valeur_numerique_max);
    if (isNaN(minVal) || isNaN(maxVal)) return false;
    return maxVal < minVal;
  });

  return (
    <div className="h-full flex flex-col p-4 lg:p-6">
      <div className="mx-auto max-w-2xl w-full flex flex-col h-full">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <button
            onClick={onBack}
            className="flex items-center gap-2 rounded-lg border-2 border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground hover:bg-muted transition-colors"
          >
            <X className="h-4 w-4" />
            Annuler
          </button>
        </div>

        {/* Title */}
        <div className="text-center mb-4">
          <h2 className="text-xl font-bold text-foreground">
            Mes préférences
          </h2>
          <p className="mt-1 text-muted-foreground text-xs max-w-md mx-auto">
            <Sparkles className="inline h-3 w-3 mr-1 text-primary" />
            Ces critères guident notre recommandation, mais ne sont pas des filtres stricts.
          </p>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto space-y-4 min-h-0 pb-4">
          {!hasAnyCriteria ? (
            <div className="text-center py-8 text-muted-foreground text-sm">
              Aucun critère disponible. Complétez le questionnaire pour obtenir des critères personnalisés.
            </div>
          ) : (
            <>
              {/* Section critique */}
              {showCritiqueSection && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <div className="flex items-center justify-center h-6 w-6 rounded-lg bg-primary/10">
                      <Target className="h-3.5 w-3.5 text-primary" />
                    </div>
                    <h3 className="text-sm font-semibold text-foreground">
                      Ce qui compte vraiment
                    </h3>
                    <span className="text-xs text-muted-foreground">
                      — priorité haute
                    </span>
                  </div>
                  <div className="space-y-2">
                    {critiqueCriteria.map((criterion) => (
                      <CriterionCard
                        key={criterion.id_caracteristique}
                        criterion={criterion}
                        isCritique={true}
                        canRemove={critiqueCriteria.length > 1 || hasRemovedCritiqueCriteria || secondaireCriteria.length > 0 || hasRemovedSecondaireCriteria}
                        onRemove={removeCriterion}
                        onToggleMultiValue={toggleMultiValue}
                        onUpdateSingleValue={updateSingleValue}
                        onUpdateNumericValue={updateNumericValue}
                      />
                    ))}

                    {/* Bouton Ajouter un critère essentiel - visible uniquement si des critères essentiels ont été supprimés */}
                    {hasRemovedCritiqueCriteria && (
                      showAddEssential ? (
                        <AddCriterionDropdown
                          isEssential={true}
                          onClose={() => setShowAddEssential(false)}
                        />
                      ) : (
                        <button
                          onClick={() => setShowAddEssential(true)}
                          className="w-full flex items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border py-2.5 text-sm font-medium text-muted-foreground hover:border-primary/50 hover:text-primary transition-colors"
                        >
                          <Plus className="h-4 w-4" />
                          Ajouter un critère essentiel
                        </button>
                      )
                    )}
                  </div>
                </div>
              )}

              {/* Section secondaire */}
              {showSecondaireSection && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <div className="flex items-center justify-center h-6 w-6 rounded-lg bg-amber-500/10">
                      <Gift className="h-3.5 w-3.5 text-amber-600" />
                    </div>
                    <h3 className="text-sm font-semibold text-foreground">
                      Les petits plus
                    </h3>
                    <span className="text-xs text-muted-foreground">
                      — appréciés mais pas indispensables
                    </span>
                  </div>
                  <div className="space-y-2">
                    {secondaireCriteria.map((criterion) => (
                      <CriterionCard
                        key={criterion.id_caracteristique}
                        criterion={criterion}
                        isCritique={false}
                        canRemove={true}
                        onRemove={removeCriterion}
                        onToggleMultiValue={toggleMultiValue}
                        onUpdateSingleValue={updateSingleValue}
                        onUpdateNumericValue={updateNumericValue}
                      />
                    ))}

                    {/* Bouton Ajouter un critère secondaire - visible uniquement si des critères secondaires ont été supprimés */}
                    {hasRemovedSecondaireCriteria && (
                      showAddSecondary ? (
                        <AddCriterionDropdown
                          isEssential={false}
                          onClose={() => setShowAddSecondary(false)}
                        />
                      ) : (
                        <button
                          onClick={() => setShowAddSecondary(true)}
                          className="w-full flex items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border py-2.5 text-sm font-medium text-muted-foreground hover:border-primary/50 hover:text-primary transition-colors"
                        >
                          <Plus className="h-4 w-4" />
                          Ajouter un critère secondaire
                        </button>
                      )
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Fixed Actions */}
        <div className="flex-shrink-0 pt-4 border-t border-border bg-background">
          <div className="flex flex-col sm:flex-row items-center gap-3 w-full">
            <button
              onClick={onBack}
              className="order-2 sm:order-1 w-full sm:w-auto rounded-lg border-2 border-border bg-background px-6 py-2.5 text-sm font-medium text-foreground hover:bg-muted transition-colors"
            >
              Annuler
            </button>
            <button
              onClick={handleApply}
              disabled={!hasCriteria || isRefetching || hasNumericValidationErrors}
              className="order-1 sm:order-2 w-full sm:w-auto flex-1 sm:flex-none rounded-lg bg-accent px-8 py-2.5 text-base font-semibold text-accent-foreground hover:bg-accent/90 shadow-lg shadow-accent/25 transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isRefetching ? (
                <>
                  <Loader2 className="h-5 w-5 animate-spin" />
                  Recherche en cours...
                </>
              ) : (
                <>
                  <Sparkles className="h-5 w-5" />
                  Affiner mes recommandations
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ModifyCriteriaForm;
