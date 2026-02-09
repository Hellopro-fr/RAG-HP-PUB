'use client';

import { X, GripVertical, Sparkles, Target, Gift, Check, Loader2 } from "lucide-react";
import { useState, useEffect, useRef } from "react";
import { trackModifyCriteriaModalView, trackCriteriaModified } from "@/lib/analytics";
import { useFlowStore } from "@/lib/stores/flow-store";
import { useProcessMatchingLogic } from "@/hooks/api/useProcessMatchingLogic";
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
  valeur_numerique_exact?: number;
  valeur_numerique_min?: number;
  valeur_numerique_max?: number;

  // Options disponibles (à remplir via API caractéristiques)
  options_disponibles: { id: number; label: string }[];
  isMulti: boolean;
}

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
    // Numérique : inputs min/max ou exact
    const val = c.valeurs_cibles;
    if (val && !Array.isArray(val)) {
      state.valeur_numerique_exact = val.exact;
      state.valeur_numerique_min = val.min;
      state.valeur_numerique_max = val.max;
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
    if (s.valeur_numerique_exact !== undefined) {
      result.valeurs_cibles = { exact: s.valeur_numerique_exact };
    } else {
      const numVal: { min?: number; max?: number } = {};
      if (s.valeur_numerique_min !== undefined) numVal.min = s.valeur_numerique_min;
      if (s.valeur_numerique_max !== undefined) numVal.max = s.valeur_numerique_max;
      result.valeurs_cibles = Object.keys(numVal).length > 0 ? numVal : [];
    }
    result.valeurs_bloquantes = [];
  }

  return result;
}

// =============================================================================
// COMPOSANT PRINCIPAL
// =============================================================================

const ModifyCriteriaForm = ({ onBack, onApply }: ModifyCriteriaFormProps) => {
  const { equivalenceCaracteristique, characteristicsMap } = useFlowStore();
  const { refetchMatchingWithUpdatedCriteria, showLoader } = useProcessMatchingLogic();

  const [critiqueCriteria, setCritiqueCriteria] = useState<CriterionFormState[]>([]);
  const [secondaireCriteria, setSecondaireCriteria] = useState<CriterionFormState[]>([]);

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

    for (const c of consolidated) {
      const formState = characteristicToFormState(c, characteristicsMap);
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
  }, [equivalenceCaracteristique, characteristicsMap]);

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

  const removeCriterion = (id: number, isCritique: boolean) => {
    if (isCritique) {
      setCritiqueCriteria(prev => prev.filter(c => c.id_caracteristique !== id));
    } else {
      setSecondaireCriteria(prev => prev.filter(c => c.id_caracteristique !== id));
    }
  };

  const updateSingleValue = (id: number, valueId: number, isCritique: boolean) => {
    const updateFn = (prev: CriterionFormState[]) =>
      prev.map(c => {
        if (c.id_caracteristique !== id) return c;
        return { ...c, valeurs_cibles_ids: [valueId] };
      });

    if (isCritique) setCritiqueCriteria(updateFn);
    else setSecondaireCriteria(updateFn);
  };

  const toggleMultiValue = (id: number, valueId: number, isCritique: boolean) => {
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
  };

  const updateNumericValue = (
    id: number,
    field: 'exact' | 'min' | 'max',
    value: string,
    isCritique: boolean
  ) => {
    const parsed = value === '' ? undefined : Number(value);
    const updateFn = (prev: CriterionFormState[]) =>
      prev.map(c => {
        if (c.id_caracteristique !== id) return c;
        if (field === 'exact') {
          return { ...c, valeur_numerique_exact: parsed, valeur_numerique_min: undefined, valeur_numerique_max: undefined };
        } else if (field === 'min') {
          return { ...c, valeur_numerique_min: parsed, valeur_numerique_exact: undefined };
        }
        return { ...c, valeur_numerique_max: parsed, valeur_numerique_exact: undefined };
      });

    if (isCritique) setCritiqueCriteria(updateFn);
    else setSecondaireCriteria(updateFn);
  };

  const handleApply = async () => {
    const allCriteria = [
      ...critiqueCriteria.map(formStateToCharacteristic),
      ...secondaireCriteria.map(formStateToCharacteristic),
    ];

    const modifiedFields = [...critiqueCriteria, ...secondaireCriteria].map(c => String(c.id_caracteristique));
    trackCriteriaModified(critiqueCriteria.length + secondaireCriteria.length, modifiedFields);

    // Relancer le matching avec les nouvelles caractéristiques
    const success = await refetchMatchingWithUpdatedCriteria(allCriteria);

    if (success) {
      // Appeler onApply pour fermer le modal et mettre à jour l'UI
      onApply(allCriteria);
    }
  };

  // =========================================================================
  // RENDU D'UN CRITÈRE
  // =========================================================================

  const CriterionCard = ({
    criterion,
    isCritique,
    canRemove = true
  }: {
    criterion: CriterionFormState;
    isCritique: boolean;
    canRemove?: boolean;
  }) => {
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
                      onClick={() => toggleMultiValue(criterion.id_caracteristique, option.id, isCritique)}
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
                onChange={(e) => updateSingleValue(criterion.id_caracteristique, Number(e.target.value), isCritique)}
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
            // Numérique: inputs
            <div className="flex items-center gap-2">
              {criterion.valeur_numerique_exact !== undefined ? (
                <>
                  <span className="text-xs text-muted-foreground">Valeur :</span>
                  <input
                    type="number"
                    value={criterion.valeur_numerique_exact ?? ''}
                    onChange={(e) => updateNumericValue(criterion.id_caracteristique, 'exact', e.target.value, isCritique)}
                    className="w-24 rounded-lg border-0 bg-muted/50 px-3 py-1.5 text-sm font-medium text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
                  />
                  {criterion.unite && <span className="text-xs text-muted-foreground">{criterion.unite}</span>}
                </>
              ) : (
                <>
                  <span className="text-xs text-muted-foreground">De</span>
                  <input
                    type="number"
                    value={criterion.valeur_numerique_min ?? ''}
                    onChange={(e) => updateNumericValue(criterion.id_caracteristique, 'min', e.target.value, isCritique)}
                    placeholder="min"
                    className="w-20 rounded-lg border-0 bg-muted/50 px-3 py-1.5 text-sm font-medium text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
                  />
                  <span className="text-xs text-muted-foreground">à</span>
                  <input
                    type="number"
                    value={criterion.valeur_numerique_max ?? ''}
                    onChange={(e) => updateNumericValue(criterion.id_caracteristique, 'max', e.target.value, isCritique)}
                    placeholder="max"
                    className="w-20 rounded-lg border-0 bg-muted/50 px-3 py-1.5 text-sm font-medium text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
                  />
                  {criterion.unite && <span className="text-xs text-muted-foreground">{criterion.unite}</span>}
                </>
              )}
            </div>
          )}
        </div>

        {canRemove && (
          <button
            onClick={() => removeCriterion(criterion.id_caracteristique, isCritique)}
            className="flex-shrink-0 rounded-full p-1.5 text-muted-foreground/60 hover:bg-destructive/10 hover:text-destructive transition-colors"
            title="Supprimer ce critère"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
    );
  };

  // =========================================================================
  // RENDU PRINCIPAL
  // =========================================================================

  const hasCriteria = critiqueCriteria.length > 0 || secondaireCriteria.length > 0;

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
          {!hasCriteria ? (
            <div className="text-center py-8 text-muted-foreground text-sm">
              Aucun critère disponible. Complétez le questionnaire pour obtenir des critères personnalisés.
            </div>
          ) : (
            <>
              {/* Section critique */}
              {critiqueCriteria.length > 0 && (
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
                        canRemove={critiqueCriteria.length > 1}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Section secondaire */}
              {secondaireCriteria.length > 0 && (
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
                      />
                    ))}
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
              disabled={!hasCriteria || showLoader}
              className="order-1 sm:order-2 w-full sm:w-auto flex-1 sm:flex-none rounded-lg bg-accent px-8 py-2.5 text-base font-semibold text-accent-foreground hover:bg-accent/90 shadow-lg shadow-accent/25 transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {showLoader ? (
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
