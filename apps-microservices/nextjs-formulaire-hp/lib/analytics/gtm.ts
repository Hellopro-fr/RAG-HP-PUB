// Global types are declared in types/global.d.ts

// =============================================================================
// TYPES
// =============================================================================

type StepType = 'init' | 'question' | 'localisation' | 'choix-propart' | 'selection' | 'contact' | 'conversion' | 'prix';

type FlowType = 'principal' | 'pas_assez_produits' | 'pas_trouve_recherchez' | 'budget_ne_correspond_pas' | null;

interface FunnelContext {
  rubrique_id?: number;
  'product.category5'?: string;
  abtest2?: string;
}



// =============================================================================
// HELPERS
// =============================================================================

/**
 * Push un événement dans le dataLayer GTM
 */
export function pushToDataLayer(event: string, data?: Record<string, unknown>) {
  if (typeof window !== 'undefined' && window.dataLayer) {
    window.dataLayer.push({
      event,
      ...data,
    });
  }
}

/**
 * Obtenir ou créer un ID utilisateur unique (persistant)
 */
function getUserId(): string {
  if (typeof window === 'undefined') return 'unknown';

  let userId = localStorage.getItem('hp_user_id');
  if (!userId) {
    userId = `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    localStorage.setItem('hp_user_id', userId);
  }
  return userId;
}

/**
 * Obtenir ou créer un ID de session (temporaire)
 */
/**
 * Obtenir ou créer un ID de session (temporaire)
 */
export function getSessionId(): string {
  if (typeof window === 'undefined') return 'unknown';

  let sessionId = sessionStorage.getItem('hp_session_id');
  if (!sessionId) {
    sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    sessionStorage.setItem('hp_session_id', sessionId);
  }
  return sessionId;
}

/**
 * Vérifier si c'est la première vue d'un modal/page pour cet utilisateur
 */
function isFirstView(key: string): boolean {
  if (typeof window === 'undefined') return true;

  const storageKey = `hp_viewed_${key}`;
  const alreadyViewed = sessionStorage.getItem(storageKey);

  if (!alreadyViewed) {
    sessionStorage.setItem(storageKey, 'true');
    return true;
  }
  return false;
}

/**
 * Réinitialiser tous les états de tracking (appelé lors d'un F5/reload)
 * Nettoie les flags de déduplication et le session_id
 */
export function resetTrackingState(): void {
  if (typeof window === 'undefined') return;

  // Supprimer toutes les clés hp_viewed_* (déduplication)
  const keysToRemove: string[] = [];
  for (let i = 0; i < sessionStorage.length; i++) {
    const key = sessionStorage.key(i);
    if (key && key.startsWith('hp_viewed_')) {
      keysToRemove.push(key);
    }
  }
  keysToRemove.forEach((key) => sessionStorage.removeItem(key));

  // Supprimer le session_id pour en générer un nouveau
  sessionStorage.removeItem('hp_session_id');

  // Réinitialiser le contexte funnel, le step index et le flow type
  funnelContext = {};
  currentStepIndex = 0;
  currentFlowType = null;
}

/**
 * Obtenir le type d'appareil
 */
function getDeviceType(): string {
  if (typeof window === 'undefined') return 'unknown';

  const width = window.innerWidth;
  if (width < 768) return 'mobile';
  if (width < 1024) return 'tablet';
  return 'desktop';
}

/**
 * Obtenir les informations de l'appareil
 */
function getDeviceInfo() {
  if (typeof window === 'undefined') {
    return {
      device_type: 'unknown',
      screen_width: 0,
      screen_height: 0,
      user_agent: '',
    };
  }

  return {
    device_type: getDeviceType(),
    screen_width: window.innerWidth,
    screen_height: window.innerHeight,
    user_agent: navigator.userAgent,
  };
}

// =============================================================================
// CONTEXTE FUNNEL (stocké en session)
// =============================================================================

let funnelContext: FunnelContext = {};
let currentFlowType: FlowType = null;

/**
 * Initialiser le contexte du funnel (à appeler au début)
 */
export function setFunnelContext(context: FunnelContext) {
  funnelContext = { ...funnelContext, ...context };
}

/**
 * Récupérer le contexte actuel
 */
export function getFunnelContext(): FunnelContext {
  return funnelContext;
}

/**
 * Définir le type de parcours (pour tracking)
 * @param flowType - 'principal' | 'pas_assez_produits' | 'pas_trouve_recherchez'
 */
export function setFlowType(flowType: FlowType) {
  currentFlowType = flowType;
}

/**
 * Récupérer le type de parcours actuel
 */
export function getFlowType(): FlowType {
  return currentFlowType;
}

// =============================================================================
// ÉVÉNEMENT PRINCIPAL : devis_funnel_formulaire
// =============================================================================

/**
 * Track une étape du funnel avec l'événement unique devis_funnel_formulaire
 */
export function trackQuoteFunnel(
  stepIndex: number,
  stepName: string,
  stepType: StepType,
  additionalData?: Record<string, unknown>
) {
  const userId = getUserId();
  const sessionId = getSessionId();

  pushToDataLayer('devis_funnel_formulaire', {
    // Progression
    step_name: stepName,
    step_number: stepIndex + 1,
    step_type: stepType,

    // Contexte funnel
    rubrique_id: funnelContext.rubrique_id,
    'product.category5': funnelContext['product.category5'],

    // A/B test secondaire (token URL) — omis si absent
    ...(funnelContext.abtest2 && { abtest2: funnelContext.abtest2 }),

    // Type de parcours (seulement si défini)
    ...(currentFlowType && { flow_type: currentFlowType }),

    // Identifiants
    user_id: userId,
    session_id: sessionId,

    // Données additionnelles
    ...additionalData,
  });
}

// =============================================================================
// FONCTIONS DE TRACKING SPÉCIFIQUES (utilisent trackQuoteFunnel)
// =============================================================================

// Variable pour suivre le step_index courant
let currentStepIndex = 0;

/**
 * Track le début du funnel
 */
export function trackFunnelStart(context?: FunnelContext) {
  currentStepIndex = 0;
  if (context) {
    setFunnelContext(context);
  }
  trackQuoteFunnel(currentStepIndex, 'funnel-start', 'init');
}

// =============================================================================
// ÉTAPE ASSURANCE (page avant Q1)
// =============================================================================

/**
 * Track l'affichage de la page Assurance (avant Q1).
 * Rendue uniquement au premier passage (`hasSeenAssurance` flag) et hors
 * variante A/B 2 — donc l'event ne fire que pour les cohortes 0/1/null.
 */
export function trackAssuranceView() {
  currentStepIndex++;
  trackQuoteFunnel(currentStepIndex, 'assurance', 'init');
}

/**
 * Track la validation de la page Assurance (clic "Continuer").
 */
export function trackAssuranceComplete() {
  currentStepIndex++;
  trackQuoteFunnel(currentStepIndex, 'assurance-complete', 'init');
}

/**
 * Track l'affichage d'une question
 */
export function trackQuestionView(questionIndex: number) {
  currentStepIndex = questionIndex + 1; // +1 car funnel-start est à 0
  const stepName = questionIndex === 0 ? '1ere-question' : `${questionIndex + 1}eme-question`;

  trackQuoteFunnel(currentStepIndex, stepName, 'question');
}

/**
 * Track la fin du questionnaire
 */
export function trackQuestionnaireComplete(totalQuestions: number, timeSpentSeconds: number) {
  currentStepIndex++;
  trackQuoteFunnel(currentStepIndex, 'questionnaire-complete', 'question', {
    total_questions: totalQuestions,
    time_spent_seconds: timeSpentSeconds,
  });
}

/**
 * Track l'affichage de la page geo-zone
 */
export function trackGeoZoneView() {
  currentStepIndex++;
  const isFirstViewForSession = isFirstView('geo_zone_page');

  trackQuoteFunnel(currentStepIndex, 'geo-zone', 'localisation', {
    is_first_view: isFirstViewForSession,
  });
}

/**
 * Track la complétion de la geo-zone (validation et passage à l'étape suivante)
 */
export function trackGeoZoneComplete() {
  currentStepIndex++;
  trackQuoteFunnel(currentStepIndex, 'geo-zone-complete', 'localisation');
}

/**
 * Track l'affichage de la page profil (choix pro/part)
 */
export function trackProfileView() {
  currentStepIndex++;
  trackQuoteFunnel(currentStepIndex, 'choix-propart', 'choix-propart');
}

/**
 * Track la complétion du profil (choix pro/part terminé)
 */
export function trackProfileComplete(profileType: string) {
  currentStepIndex++;
  trackQuoteFunnel(currentStepIndex, 'choix-propart-complete', 'choix-propart', {
    profile_type: profileType,
  });
}

/**
 * Track l'affichage de la page de sélection produits
 */
export function trackSelectionPageView(recommendedCount: number, totalCount: number) {
  currentStepIndex++;
  trackQuoteFunnel(currentStepIndex, 'selection-produits', 'selection', {
    recommended_count: recommendedCount,
    total_count: totalCount,
  });
}

/**
 * Track le changement de sélection produit
 */
export function trackProductSelectionChange(
  productId: string,
  action: 'ajouter' | 'retirer',
  totalSelected: number
) {
  // Vérifier si c'est la première action de ce type pour cet utilisateur dans la session
  const isFirstAdd = action === 'ajouter' && isFirstView('product_selection_ajouter');
  const isFirstRemove = action === 'retirer' && isFirstView('product_selection_retirer');

  trackQuoteFunnel(currentStepIndex, 'product-selection', 'selection', {
    product_id: productId,
    action,
    total_selected: totalSelected,
    // Envoyer is_first_add uniquement si true (premier ajout)
    ...(isFirstAdd && { is_first_add: true }),
    // Envoyer is_first_remove uniquement si true (premier retrait)
    ...(isFirstRemove && { is_first_remove: true }),
  });
}

// =============================================================================
// ÉTAPE PRIX (page /budget)
// =============================================================================

/**
 * Track l'affichage de la page /budget.
 * Émis au mount uniquement quand la card BudgetEstimate est rendue
 * (fourchette valide + > 2 exemples produits) — la page elle-même est
 * skippée sinon par la logique de routage dans questionnaire-client.tsx.
 */
export function trackBudgetView() {
  currentStepIndex++;
  trackQuoteFunnel(currentStepIndex, 'budget', 'prix');
}

/**
 * Track la validation de l'étape budget (clic "Voir ma sélection").
 * Le bouton est désactivé tant qu'aucune fourchette n'est choisie,
 * donc budgetRange est toujours défini ici.
 */
export function trackBudgetComplete(budgetRange: string) {
  currentStepIndex++;
  trackQuoteFunnel(currentStepIndex, 'budget-complete', 'prix', {
    budget_range: budgetRange,
  });
}

/**
 * Track le retour au questionnaire depuis /budget (clic "Précédent").
 * budgetRange peut être null si l'utilisateur n'avait rien choisi.
 * Pas d'incrément de step_index : recul dans le funnel.
 */
export function trackBudgetReturn(budgetRange: string | null) {
  trackQuoteFunnel(currentStepIndex, 'budget-retour', 'prix', {
    budget_range: budgetRange,
  });
}

/**
 * Track l'ouverture du modal de comparaison
 */
export function trackComparisonModalView() {
  currentStepIndex++;
  const isFirstViewForSession = isFirstView('comparison_modal');

  trackQuoteFunnel(currentStepIndex, 'vue-comparaison', 'selection', {
    is_first_view: isFirstViewForSession,
  });
}

/**
 * Track l'affichage du formulaire de contact
 */
export function trackContactFormView(selectedSuppliersCount: number) {
  currentStepIndex++;
  trackQuoteFunnel(currentStepIndex, 'formulaire-contact', 'contact', {
    selected_count: selectedSuppliersCount,
  });
}

/**
 * Track les erreurs de validation
 */
export function trackFormValidationErrors(
  errorsCount: number,
  errors?: Array<{ field: string; type: string; message: string }>
) {
  trackQuoteFunnel(currentStepIndex, 'validation-error', 'contact', {
    errors_count: errorsCount,
    errors,
  });
}

/**
 * Track la soumission réussie du lead
 */
export function trackLeadSubmitted(suppliersCount: number, profileType: string, userKnownStatus: 'known' | 'unknown') {
  currentStepIndex++;
  trackQuoteFunnel(currentStepIndex, 'submit-success', 'conversion', {
    nombre_fournisseur: suppliersCount,
    profile_type: profileType,
    user_known_status: userKnownStatus,
    conversion: true,
  });
}

/**
 * Track une erreur de soumission
 */
export function trackLeadSubmissionError(errorType: string, errorMessage: string) {
  trackQuoteFunnel(currentStepIndex, 'submit-error', 'conversion', {
    error_type: errorType,
    error_message: errorMessage,
    conversion: false,
  });
}

// =============================================================================
// ÉVÉNEMENTS SECONDAIRES (intégrés dans devis_funnel_formulaire)
// =============================================================================

/**
 * Track l'ouverture du modal de modification de critères
 */
export function trackModifyCriteriaModalView() {
  currentStepIndex++;
  const isFirstViewForSession = isFirstView('modify_criteria_modal');

  trackQuoteFunnel(currentStepIndex, 'vue-criteres', 'selection', {
    is_first_view: isFirstViewForSession,
  });
}

/**
 * Track la modification effective de critères
 */
export function trackCriteriaModified(criteriaCount: number) {
  currentStepIndex++;

  trackQuoteFunnel(currentStepIndex, 'criteres-modifies', 'selection', {
    criteria_count: criteriaCount,
  });
}

/**
 * Track l'arrivée sur la page "Quelque chose à ajouter" (/something-to-add) - Étape 1: Votre besoin
 * Cette page s'affiche quand il y a peu de produits correspondant à la recherche
 * ou quand l'utilisateur clique "pas trouvé ce que vous cherchez"
 */
export function trackCustomNeedPageView() {
  currentStepIndex++;
  const isFirstViewForSession = isFirstView('custom_need_page');

  trackQuoteFunnel(currentStepIndex, 'description-besoin', 'contact', {
    is_first_view: isFirstViewForSession,
  }); 
}

/**
 * Track l'affichage de l'étape coordonnées sur /something-to-add - Étape 2: Vos coordonnées
 */
export function trackCustomNeedContactView() {
  currentStepIndex++;
  trackQuoteFunnel(currentStepIndex, 'formulaire-contact-simple', 'contact');
}

/**
 * Track l'ouverture du modal fiche produit
 */
export function trackProductModalView(productId: string) {
  currentStepIndex++;
  const isFirstViewForSession = isFirstView('product_modal');

  trackQuoteFunnel(currentStepIndex, 'vue-produit', 'selection', {
    product_id: productId,
    is_first_view: isFirstViewForSession,
  });
}

/**
 * Track un abandon à une étape spécifique
 */
export function trackFunnelAbandonment(
  step: string,
  stepNumber: number,
  timeSpentSeconds: number,
  lastAction?: string
) {
  const userId = getUserId();
  const sessionId = getSessionId();
  const deviceInfo = getDeviceInfo();

  pushToDataLayer('abandon_funnel', {
    user_id: userId,
    session_id: sessionId,
    step,
    step_number: stepNumber,
    time_spent_seconds: timeSpentSeconds,
    last_action: lastAction,
    ...deviceInfo,
    timestamp: new Date().toISOString(),
  });
}

/**
 * Track les informations de device au début de session
 */
export function trackDeviceInfo() {
  const userId = getUserId();
  const sessionId = getSessionId();
  const deviceInfo = getDeviceInfo();

  pushToDataLayer('device_info', {
    user_id: userId,
    session_id: sessionId,
    ...deviceInfo,
    timestamp: new Date().toISOString(),
  });
}

/**
 * Track les sources de trafic (UTM parameters)
 */
export function trackTrafficSource() {
  if (typeof window === 'undefined') return;

  const userId = getUserId();
  const sessionId = getSessionId();
  const urlParams = new URLSearchParams(window.location.search);

  const source = urlParams.get('utm_source') || 'direct';
  const medium = urlParams.get('utm_medium') || 'none';
  const campaign = urlParams.get('utm_campaign') || 'none';
  const term = urlParams.get('utm_term') || '';
  const content = urlParams.get('utm_content') || '';
  const referrer = document.referrer || 'direct';

  pushToDataLayer('source_trafic', {
    user_id: userId,
    session_id: sessionId,
    utm_source: source,
    utm_medium: medium,
    utm_campaign: campaign,
    utm_term: term,
    utm_content: content,
    referrer,
    landing_page: window.location.pathname,
    timestamp: new Date().toISOString(),
  });
}

// =============================================================================
// EXPORTS POUR RÉTROCOMPATIBILITÉ (deprecated)
// =============================================================================

/** @deprecated Utiliser trackQuoteFunnel à la place */
export function trackQuestionNavigation(
  fromQuestion: number,
  toQuestion: number,
  direction: 'next' | 'back'
) {
  // Redirige vers le nouveau système
  trackQuoteFunnel(toQuestion, `${toQuestion}eme-question`, 'question', {
    from_question: fromQuestion,
    direction,
  });
}

/** @deprecated Utiliser trackComparisonModalView à la place */
export function trackComparisonModalOpen() {
  trackComparisonModalView();
}

/** @deprecated Utiliser trackFormValidationErrors à la place */
export function trackFormValidationError(
  _formName: string,
  fieldName: string,
  errorType: string,
  errorMessage: string
) {
  trackFormValidationErrors(1, [{ field: fieldName, type: errorType, message: errorMessage }]);
}
