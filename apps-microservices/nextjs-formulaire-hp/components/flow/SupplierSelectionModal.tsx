'use client';

import { useState, useMemo, useEffect, useRef } from "react";
import { Send } from "lucide-react";
import { cn } from "@/lib/utils";
import { useFlowStore } from "@/lib/stores/flow-store";
import { useFlowNavigation } from "@/hooks/useFlowNavigation";
import {
  getCharacteristicLabel,
  formatSelectedValues,
} from "@/lib/utils/characteristics-helpers";
import ProgressHeader from "./ProgressHeader";
import CriteriaTags from "./CriteriaTags";
import ContactForm from "./ContactForm";
import ModifyCriteriaForm from "./ModifyCriteriaForm";
import CustomNeedForm, { CustomNeedVariant } from "./CustomNeedForm";
import ProductDetailModal from "./ProductDetailModal";
import CriteriaChangedBanner from "./CriteriaChangedBanner";
import BudgetEstimate from "./BudgetEstimate";
import SelectionTableViewB from "./selection-views/SelectionTableViewB";
import {
  trackProductSelectionChange,
  trackCustomNeedPageView,
  setFlowType,
} from "@/lib/analytics";
import { Supplier } from "@/types";
import { hasPriceEstimation } from "@/types/prix";
import { buildPriceTrackingPayload } from "@/lib/utils/build-price-tracking-payload";
import { useDbTracking } from "@/hooks/tracking/useDbTracking";

type ViewState = "selection" | "contact" | "modify-criteria" | "custom-need";

const STEPS = [
  { id: 1, label: "Votre besoin" },
  { id: 2, label: "Sélection" },
  { id: 3, label: "Demande de devis" },
];
interface SupplierSelectionModalProps {
  userAnswers          ?: Record<number, string[]>;
  onBackToQuestionnaire?: () => void;
}



const SupplierSelectionModal = ({userAnswers, onBackToQuestionnaire }: SupplierSelectionModalProps) => {
  // Navigation hook
  const { goToProfile } = useFlowNavigation();

  // Récupérer les résultats de matching et les caractéristiques depuis le store
  const {
    matchingResults,
    equivalenceCaracteristique,
    characteristicsMap,
    orphanedSelectedSuppliers,
    criteriaHaveChanged,
    removedCritiqueCriteriaIds,
    removedSecondaireCriteriaIds,
    priceEstimation
  } = useFlowStore();

  // Utiliser uniquement les résultats dynamiques du matching (pas de fallback statique)
  const RECOMMENDED = matchingResults?.recommended ?? [];
  const OTHERS = matchingResults?.others ?? [];
  // Merger les produits orphelins avec les nouveaux résultats
  const ALL_SUPPLIERS = [...orphanedSelectedSuppliers, ...RECOMMENDED, ...OTHERS];

  // Formater les critères pour CriteriaTags depuis equivalenceCaracteristique
  // Filtrer les critères supprimés pour ne pas les afficher dans le résumé
  const { essentialCriteria, secondaryCriteria } = useMemo(() => {
    const essential: { label: string; value: string }[] = [];
    const secondary: { label: string; value: string }[] = [];

    if (!equivalenceCaracteristique || equivalenceCaracteristique.length === 0) {
      return { essentialCriteria: essential, secondaryCriteria: secondary };
    }

    // Créer un Set des IDs supprimés pour une recherche rapide
    const removedIdsSet = new Set([...removedCritiqueCriteriaIds, ...removedSecondaireCriteriaIds]);

    for (const c of equivalenceCaracteristique) {
      // Skip les critères supprimés
      if (removedIdsSet.has(c.id_caracteristique)) continue;

      const label = getCharacteristicLabel(characteristicsMap, c.id_caracteristique);
      const value = formatSelectedValues(characteristicsMap, c.id_caracteristique, c.valeurs_cibles);

      // Skip si pas de valeur à afficher
      if (!value) continue;

      const criterion = { label, value };
      const poids = c.poids_caracteristique?.toLowerCase();

      if (poids === 'critique') {
        essential.push(criterion);
      } else {
        secondary.push(criterion);
      }
    }

    return { essentialCriteria: essential, secondaryCriteria: secondary };
  }, [equivalenceCaracteristique, characteristicsMap, removedCritiqueCriteriaIds, removedSecondaireCriteriaIds]);

  const [animatingCount, setAnimatingCount] = useState(false);
  const [viewState, setViewState] = useState<ViewState>("selection");
  const [customNeedVariant, setCustomNeedVariant] = useState<CustomNeedVariant>('initial');
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [criteriaModified, setCriteriaModified] = useState(false);
  // État pour le devis unique (ne modifie pas la sélection principale)
  const [singleQuoteProductId, setSingleQuoteProductId] = useState<string | null>(null);

  // Zustand store pour la sélection des fournisseurs et le flowType
  const {
    selectedSupplierIds,
    setSelectedSupplierIds,
    setSupplierIdsToSubmit,
    setFlowType: setStoreFlowType,
    setEquivalenceCaracteristique,
    setOrphanedSelectedSuppliers,
    setCriteriaHaveChanged,
    categoryId,
    categoryName,
    categoryStats
  } = useFlowStore();

  const { trackDbEvent } = useDbTracking();

  // Refs pour éviter les stale closures dans le handler popstate
  const selectedProductIdRef = useRef<string | null>(null);
  const viewStateRef = useRef<ViewState>('selection');

  useEffect(() => { selectedProductIdRef.current = selectedProductId; }, [selectedProductId]);
  useEffect(() => { viewStateRef.current = viewState; }, [viewState]);

  // Push une entrée dans l'historique quand on quitte la vue "selection"
  useEffect(() => {
    if (viewState !== 'selection') {
      history.pushState({ viewState }, '');
    }
  }, [viewState]);

  // Intercept bouton "précédent" du navigateur : ferme les modals ou revient à "selection"
  useEffect(() => {
    const handlePopState = () => {
      if (selectedProductIdRef.current !== null) {
        setSelectedProductId(null);
      } else if (viewStateRef.current !== 'selection') {
        setSingleQuoteProductId(null); // Réinitialiser le devis unique au retour
        setSupplierIdsToSubmit(null); // Réinitialiser les IDs à soumettre
        setViewState('selection');
      }
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  // Convertir le tableau en Set pour les opérations
  const selectedIds = useMemo(() => new Set(selectedSupplierIds), [selectedSupplierIds]);

  // Initialiser avec les fournisseurs recommandés (top_produits) au chargement des résultats
  useEffect(() => {
    if (matchingResults && selectedSupplierIds.length === 0) {
      const topProduits = matchingResults.recommended ?? [];
      if (topProduits.length > 0) {
        setSelectedSupplierIds(topProduits.map((s) => s.id));
      }
    }
  }, [matchingResults]);

  // Séparer les produits en fonction de leur sélection
  // Note: ALL_SUPPLIERS doit être dans les dépendances pour que les listes se recalculent
  // quand matchingResults change (ex: après modification des critères)
  const selectedSuppliersList = useMemo(() => {
    return ALL_SUPPLIERS.filter((s) => selectedIds.has(s.id));
  }, [ALL_SUPPLIERS, selectedIds]);

  const unselectedSuppliersList = useMemo(() => {
    const unselected = ALL_SUPPLIERS.filter((s) => !selectedIds.has(s.id));
    if (!searchQuery.trim()) return unselected;
    const query = searchQuery.toLowerCase();
    return unselected.filter(
      (s) =>
        s.productName.toLowerCase().includes(query) ||
        s.supplierName.toLowerCase().includes(query) ||
        s.description.toLowerCase().includes(query)
    );
  }, [ALL_SUPPLIERS, selectedIds, searchQuery]);

  const initialSelectedIds = useMemo(
    () => new Set(RECOMMENDED.map((s) => s.id)),
    [RECOMMENDED]
  );

  const isModified = useMemo(() => {
    if (selectedIds.size !== initialSelectedIds.size) return true;
    for (const id of selectedIds) {
      if (!initialSelectedIds.has(id)) return true;
    }
    return false;
  }, [selectedIds, initialSelectedIds]);

  const selectedCount = selectedIds.size;

  const toggleSupplier = (id: string) => {
    const isRemoving = selectedIds.has(id);
    const newIds = isRemoving
      ? selectedSupplierIds.filter((sid) => sid !== id)
      : [...selectedSupplierIds, id];
    setSelectedSupplierIds(newIds);
    setAnimatingCount(true);

    // Track add/remove selection (GTM)
    trackProductSelectionChange(id, isRemoving ? 'retirer' : 'ajouter', newIds.length, hasPriceEstimation(priceEstimation));

    // Track DB
    trackDbEvent('selection', isRemoving ? 'deselect' : 'select', {
      product_id: id,
      action: isRemoving ? 'retirer' : 'ajouter',
      total_selected: newIds.length,
      price_estimation: buildPriceTrackingPayload(priceEstimation),
    }, categoryId);
  };

  const resetSelection = () => {
    setSelectedSupplierIds(RECOMMENDED.map((s) => s.id));
  };

  const handleViewDetails = (id: string) => {
    setSelectedProductId(id);
    history.pushState({ modal: 'product' }, '');
    // Note: Le tracking est fait dans ProductDetailModal au montage
  };

  const selectedProduct = selectedProductId
    ? ALL_SUPPLIERS.find((s) => s.id === selectedProductId)
    : null;

  useEffect(() => {
    if (animatingCount) {
      const timer = setTimeout(() => setAnimatingCount(false), 300);
      return () => clearTimeout(timer);
    }
  }, [animatingCount]);

  const getProgress = () => {
    switch (viewState) {
      case "selection":
        return 66;
      case "contact":
      case "modify-criteria":
      case "custom-need":
        return 90;
      default:
        return 66;
    }
  };

  const getCurrentStep = () => {
    switch (viewState) {
      case "selection":
        return 2;
      case "contact":
      case "modify-criteria":
      case "custom-need":
        return 3;
      default:
        return 2;
    }
  };



  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background">
      {/* Header */}
      <ProgressHeader
        steps={STEPS}
        currentStep={getCurrentStep()}
        progress={getProgress()}
      />

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {viewState === "selection" && (
          <div className="mx-auto max-w-7xl p-6 lg:p-10 space-y-8">
              {/* Title + Critères */}
              <div className="text-center relative">
                <h2 className="text-2xl font-bold text-foreground">
                  Votre sélection personnalisée
                </h2>
                <p className="mt-1 text-muted-foreground">
                  {RECOMMENDED.length} fournisseur{RECOMMENDED.length > 1 ? "s" : ""}{" "}
                  recommandé{RECOMMENDED.length > 1 ? "s" : ""} pour vous
                </p>
              </div>
              <CriteriaTags
                essentialCriteria={essentialCriteria}
                secondaryCriteria={secondaryCriteria}
                onModify={() => {
                  setViewState("modify-criteria");
                  setCriteriaModified(true);
                }}
              />

              {/* Budget Estimate — affiché seulement si données prix valides */}
              {priceEstimation?.data && priceEstimation.data.fourchette.borne_basse !== 0 && priceEstimation.data.fourchette.borne_basse !== priceEstimation.data.fourchette.borne_haute && (priceEstimation.data.exemples_produits?.length ?? 0) > 2 && (() => {
                const { fourchette, exemples_produits, phrase_prix } = priceEstimation.data!;
                const fmtPrice = (n: number) =>
                  new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(n) + " €";

                const priceItems = (exemples_produits || []).map((ex) => ({
                  price: `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(ex.prix)} €${ex.tva && ex.tva !== "inconnu" ? ` ${ex.tva}` : ""}`,
                  equipment: `${ex.nom}${ex.fournisseur ? ` — ${ex.fournisseur}` : ""}`,
                  date: ex.date || "",
                }));

                return (
                  <BudgetEstimate
                    priceMin={fmtPrice(fourchette.borne_basse)}
                    priceMax={fmtPrice(fourchette.borne_haute)}
                    priceMoy={fmtPrice(fourchette.prix_moyen)}
                    priceCount={priceItems.length}
                    priceItems={priceItems.length > 0 ? priceItems : undefined}
                    detailDescription={phrase_prix}
                    handleClickNeCorrespondPas={() => {
                      setStoreFlowType('budget_ne_correspond_pas');
                      setFlowType('budget_ne_correspond_pas');
                      trackCustomNeedPageView();
                      setCustomNeedVariant('budget');
                      setViewState("custom-need");
                    }}
                  />
                );
              })()}

              {/* Criteria Changed Banner */}
              {criteriaHaveChanged && selectedSupplierIds.length > 0 && (
                <CriteriaChangedBanner
                  onNewSelection={() => {
                    // Récupérer les IDs des nouveaux top_produits (recommandés)
                    const newRecommendedIds = RECOMMENDED.map((s) => s.id);

                    // Mise à jour atomique de tous les états en un seul batch
                    // pour éviter les problèmes de synchronisation
                    useFlowStore.setState({
                      orphanedSelectedSuppliers: [],
                      selectedSupplierIds: newRecommendedIds,
                      criteriaHaveChanged: false
                    });
                  }}
                  onDismiss={() => {
                    // Garder la sélection actuelle, juste cacher la bannière
                    setCriteriaHaveChanged(false);
                  }}
                />
              )}

              {/* Selection view (B uniquement) */}
              <SelectionTableViewB
                selectedSuppliers={selectedSuppliersList}
                otherSuppliers={unselectedSuppliersList}
                selectedIds={selectedIds}
                onToggle={toggleSupplier}
                onViewDetails={handleViewDetails}
              />
            </div>
          )}

          {viewState === "contact" && (
            <ContactForm
              selectedSuppliers={
                // Si devis unique, passer seulement ce produit; sinon, la sélection complète
                singleQuoteProductId
                  ? ALL_SUPPLIERS.filter((s) => s.id === singleQuoteProductId)
                  : selectedSuppliersList
              }
              onBack={() => {
                setSingleQuoteProductId(null); // Réinitialiser le devis unique au retour
                setSupplierIdsToSubmit(null); // Réinitialiser les IDs à soumettre
                setViewState("selection");
              }}
              onContactComplete={(isExistingBuyer) => {
                setSingleQuoteProductId(null); // Réinitialiser après soumission
                setSupplierIdsToSubmit(null); // Réinitialiser les IDs à soumettre
                if (isExistingBuyer) {
                  // Acheteur connu : le formulaire a déjà soumis le lead et navigue automatiquement
                  // Pas besoin d'action supplémentaire ici
                } else {
                  // Acheteur inconnu : naviguer vers Profile pour compléter les informations
                  goToProfile();
                }
              }}
            />
          )}

          {viewState === "modify-criteria" && (
            <ModifyCriteriaForm
              onBack={() => {
                setViewState("selection");
              }}
              onApply={(updatedEquivalences) => {
                // Mettre à jour le store avec les nouvelles équivalences
                setEquivalenceCaracteristique(updatedEquivalences);
                setViewState("selection");
                // Le flag criteriaHaveChanged est déjà géré par refetchMatchingWithUpdatedCriteria
              }}
            />
          )}

          {viewState === "custom-need" && (
            <CustomNeedForm
              variant={customNeedVariant}
              onBack={() => {
                // Remettre flowType à 'principal' quand l'utilisateur annule
                // depuis le formulaire "pas trouvé ce que vous cherchez"
                setStoreFlowType('principal');
                setFlowType('principal');
                setViewState("selection");
              }}
              onContactComplete={(isExistingBuyer) => {
                if (isExistingBuyer) {
                  // Acheteur connu : le formulaire a déjà soumis le lead et navigue automatiquement
                  // Pas besoin d'action supplémentaire ici
                } else {
                  // Acheteur inconnu : naviguer vers Profile pour compléter les informations
                  goToProfile();
                }
              }}
            />
          )}
        </div>

      {/* Footer - Floating compact bar */}
      {viewState === "selection" && (
        <div className="border-t border-border bg-card/95 backdrop-blur-sm px-4 py-3 md:py-4 md:px-6">
          <div className="mx-auto max-w-7xl flex flex-col lg:flex-row items-stretch lg:items-center gap-2 md:gap-3 lg:justify-between">
            {/* CTA group: mention + button */}
            <div className="order-1 lg:order-2 flex flex-col lg:flex-row items-center gap-2 lg:gap-3 w-full lg:w-auto">
              <span className="text-xs text-muted-foreground hidden lg:block">
                ⏱️ 1er retour sous 1 heure
              </span>
              <button
                disabled={selectedCount === 0}
                onClick={() => {
                  setSupplierIdsToSubmit(selectedSupplierIds); // Tous les produits sélectionnés
                  setViewState("contact");
                }}
                className={cn(
                  "rounded-lg px-6 py-3 text-base font-semibold transition-all duration-200 w-full lg:w-auto",
                  selectedCount > 0
                    ? "bg-accent text-accent-foreground hover:bg-accent/90 shadow-lg shadow-accent/25"
                    : "bg-muted text-muted-foreground cursor-not-allowed"
                )}
              >
                <span className="flex items-center justify-center gap-2">
                  <Send className="h-5 w-5" />
                  Recevoir {selectedCount} devis
                </span>
              </button>
              <span className="text-xs text-muted-foreground lg:hidden">
                ⏱️ 1er retour sous 1 heure
              </span>
            </div>

            {/* Secondary actions */}
            <div className="order-2 lg:order-1 flex flex-wrap items-center gap-2 md:gap-3">
              <button
                onClick={() => setViewState("modify-criteria")}
                className="flex-1 min-w-[120px] md:flex-none h-10 md:h-11 rounded-lg border-2 border-muted-foreground/30 bg-muted/50 px-3 md:px-4 text-xs md:text-sm font-medium text-foreground hover:bg-muted hover:border-muted-foreground/50 transition-colors flex items-center justify-center"
              >
                Modifier critères
              </button>

              <button
                onClick={() => {
                  // Définir flowType = 'pas_trouve_recherchez' car l'utilisateur a cliqué "pas trouvé"
                  setStoreFlowType('pas_trouve_recherchez');
                  setFlowType('pas_trouve_recherchez');
                  setCustomNeedVariant('initial');
                  setViewState("custom-need");
                }}
                className="flex-1 min-w-[200px] md:flex-none h-10 md:h-11 rounded-lg border-2 border-muted-foreground/30 bg-muted/50 px-3 md:px-4 text-xs md:text-sm font-medium text-foreground hover:bg-muted hover:border-muted-foreground/50 transition-colors flex items-center justify-center"
              >
                Pas trouvé ce que vous cherchez ?
              </button>
            </div>
          </div>
        </div>
      )}
      {/* Product Detail Modal */}
      {selectedProduct && (
        <ProductDetailModal
          product={{
            id: selectedProduct.id,
            name: selectedProduct.productName,
            images: selectedProduct.images,
            media: selectedProduct.media,
            description: selectedProduct.description,
            descriptionHtml: selectedProduct.descriptionHtml,
            specs: selectedProduct.specs,
            supplier: selectedProduct.supplier,
            matchScore: selectedProduct.matchScore,
            matchReasons: selectedProduct.matchGaps,
          }}
          onClose={() => history.back()}
          onSelect={() => toggleSupplier(selectedProduct.id)}
          isSelected={selectedIds.has(selectedProduct.id)}
          onProceed={() => {
            setSupplierIdsToSubmit(selectedSupplierIds); // Tous les produits sélectionnés
            setSelectedProductId(null); // Ferme la modale
            setViewState("contact");
          }}
          onRequestSingleQuote={() => {
            setSupplierIdsToSubmit([selectedProduct.id]); // Uniquement ce produit
            setSingleQuoteProductId(selectedProduct.id); // Garde la sélection, juste marque le produit pour devis unique
            setSelectedProductId(null); // Ferme la modale
            setViewState("contact");
          }}
          selectedCount={selectedCount}
        />
      )}
    </div>
  );
};

export default SupplierSelectionModal;
