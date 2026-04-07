'use client';

import { useState, useMemo, useEffect, useRef } from "react";
import { ChevronDown, ChevronUp, RotateCcw, ArrowLeft, Send, Search, LayoutGrid, List, ThumbsUp, ThumbsDown } from "lucide-react";
import { cn, getAssetPath } from "@/lib/utils";
import { toast } from "@/hooks/use-toast";
import { useFlowStore } from "@/lib/stores/flow-store";
import { useFlowNavigation } from "@/hooks/useFlowNavigation";
import {
  getCharacteristicLabel,
  formatSelectedValues,
} from "@/lib/utils/characteristics-helpers";
import ProgressHeader from "./ProgressHeader";
import CriteriaTags from "./CriteriaTags";
import SupplierCard from "./SupplierCard";
import WarningBanner from "./WarningBanner";
import ContactForm from "./ContactForm";
import ModifyCriteriaForm from "./ModifyCriteriaForm";
import CustomNeedForm, { CustomNeedVariant } from "./CustomNeedForm";
import ProductDetailModal from "./ProductDetailModal";
import ProductComparisonModal from "./ProductComparisonModal";
import CriteriaChangedBanner from "./CriteriaChangedBanner";
import BudgetEstimate from "./BudgetEstimate";
import {
  trackComparisonModalView,
  trackProductSelectionChange,
  trackCustomNeedPageView,
  setFlowType,
} from "@/lib/analytics";
import { Supplier } from "@/types";
import { hasPriceEstimation } from "@/types/prix";
import { buildPriceTrackingPayload } from "@/lib/utils/build-price-tracking-payload";
import { useDbTracking } from "@/hooks/tracking/useDbTracking";
import { getCategorySelection } from "@/data/category-static-content";

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

  const [isExpanded, setIsExpanded] = useState(false);
  const [animatingCount, setAnimatingCount] = useState(false);
  const [viewState, setViewState] = useState<ViewState>("selection");
  const [customNeedVariant, setCustomNeedVariant] = useState<CustomNeedVariant>('initial');
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [showComparison, setShowComparison] = useState(false);
  const [criteriaModified, setCriteriaModified] = useState(false);
  const [mobileViewMode, setMobileViewMode] = useState<"grid" | "list">("list");
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
  const showComparisonRef = useRef<boolean>(false);
  const viewStateRef = useRef<ViewState>('selection');

  useEffect(() => { selectedProductIdRef.current = selectedProductId; }, [selectedProductId]);
  useEffect(() => { showComparisonRef.current = showComparison; }, [showComparison]);
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
      } else if (showComparisonRef.current) {
        setShowComparison(false);
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
    setIsExpanded(false);
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
              {/* Title + View Toggle */}
              <div className="text-center relative">
                <h2 className="text-2xl font-bold text-foreground">
                  Votre sélection personnalisée
                </h2>
                <p className="mt-1 text-muted-foreground">
                  {selectedCount} fournisseur{selectedCount > 1 ? "s" : ""}{" "}
                  recommandé{selectedCount > 1 ? "s" : ""} pour vous
                </p>
              </div>
              {/* Criteria Tags - Affiche les caractéristiques matchées depuis equivalenceCaracteristique */}
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
                    priceMoy={fmtPrice(fourchette.prix_median)}
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

              {/* Warning Banner (only when expanded and modified) */}
              {isExpanded && isModified && (
                <WarningBanner message="En modifiant notre sélection, vous risquez de passer à côté des fournisseurs les plus adaptés à votre besoin." />
              )}

              {/* Supplier Lists */}
              <div className="space-y-6">
                {/* When collapsed: show only selected suppliers */}
                {!isExpanded && (
                  <div className={cn(
                    "grid gap-4 sm:gap-5",
                    "grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4"
                  )}>
                    {selectedSuppliersList.map((supplier) => (
                      <SupplierCard
                        key={supplier.id}
                        {...supplier}
                        isSelected={true}
                        onToggle={toggleSupplier}
                        onViewDetails={handleViewDetails}
                        viewMode={mobileViewMode}
                      />
                    ))}
                  </div>
                )}

                {/* When expanded: show all with sections */}
                {isExpanded && (
                  <>
                    {/* Selected Section */}
                    <div className="space-y-4">
                      <h3 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                        <span className="h-px flex-1 bg-border" />
                        Produits sélectionnés ({selectedSuppliersList.length})
                        <span className="h-px flex-1 bg-border" />
                      </h3>
                      {selectedSuppliersList.length > 0 ? (
                        <div className={cn(
                          "grid gap-4 sm:gap-5",
                          "grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4"
                        )}>
                          {selectedSuppliersList.map((supplier) => (
                            <SupplierCard
                              key={supplier.id}
                              {...supplier}
                              isSelected={true}
                              onToggle={toggleSupplier}
                              onViewDetails={handleViewDetails}
                              viewMode={mobileViewMode}
                            />
                          ))}
                        </div>
                      ) : (
                        <div className="text-center py-8 text-muted-foreground">
                          <p>Aucun produit sélectionné</p>
                        </div>
                      )}
                    </div>

                    {/* Other Results Section */}
                    <div className="space-y-4 pt-4">
                      <h3 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                        <span className="h-px flex-1 bg-border" />
                        Autres résultats ({unselectedSuppliersList.length})
                        <span className="h-px flex-1 bg-border" />
                      </h3>


                      {unselectedSuppliersList.length > 0 ? (
                        <div className={cn(
                          "grid gap-4 sm:gap-5",
                          "grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4"
                        )}>
                          {unselectedSuppliersList.map((supplier) => (
                            <SupplierCard
                              key={supplier.id}
                              {...supplier}
                              isSelected={false}
                              onToggle={toggleSupplier}
                              onViewDetails={handleViewDetails}
                              viewMode={mobileViewMode}
                            />
                          ))}
                        </div>
                      ) : (
                        <div className="text-center py-8 text-muted-foreground">
                          {searchQuery ? (
                            <p>Aucun résultat pour "{searchQuery}"</p>
                          ) : (
                            <p>Tous les produits sont sélectionnés</p>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Reset link */}
                    {isModified && (
                      <button
                        onClick={resetSelection}
                        className="flex w-full items-center justify-center gap-2 py-2 text-sm text-primary hover:text-primary/80 transition-colors"
                      >
                        <RotateCcw className="h-4 w-4" />
                        Revenir à la sélection recommandée
                      </button>
                    )}
                  </>
                )}

                {/* Expand/Collapse toggle */}
                <button
                  onClick={() => setIsExpanded(!isExpanded)}
                  className={cn(
                    "flex w-full items-center justify-center gap-2 py-3 text-sm transition-colors rounded-lg border",
                    isExpanded
                      ? "text-muted-foreground hover:text-foreground border-transparent"
                      : "text-foreground font-medium border-border hover:bg-muted"
                  )}
                >
                  {isExpanded ? (
                    <>
                      Réduire
                      <ChevronUp className="h-4 w-4" />
                    </>
                  ) : (
                    <>
                      {(categoryId && getCategorySelection(categoryId)?.voirPlus) || `Voir plus de ${(categoryName || "produits").toLowerCase()}`}
                      <ChevronDown className="h-4 w-4" />
                    </>
                  )}
                </button>
              </div>

              {/* Bloc réassurance "Recommandé" */}
              {categoryId && getCategorySelection(categoryId)?.recommandeReassurance && (
                <div className="mt-4 rounded-lg border border-border bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
                  <span className="font-semibold text-foreground">Idéal</span> = {getCategorySelection(categoryId)!.recommandeReassurance.replace(/xx/g, String(categoryStats?.productsCount ?? ""))}
                </div>
              )}
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
                onClick={() => {
                  trackComparisonModalView();
                  setShowComparison(true);
                  history.pushState({ modal: 'comparison' }, '');
                }}
                className="flex-1 min-w-[120px] md:flex-none h-10 md:h-11 rounded-lg border-2 border-muted-foreground/30 bg-muted/50 px-3 md:px-4 text-xs md:text-sm font-medium text-foreground hover:bg-muted hover:border-muted-foreground/50 transition-colors flex items-center justify-center gap-1.5 md:gap-2"
              >
                <LayoutGrid className="h-4 w-4 shrink-0" />
                Comparer
              </button>

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
      {/* Comparison Modal */}
      {showComparison && (
        <ProductComparisonModal
          products={ALL_SUPPLIERS}
          selectedIds={selectedIds}
          onToggle={toggleSupplier}
          onClose={() => history.back()}
        />
      )}
    </div>
  );
};

export default SupplierSelectionModal;
