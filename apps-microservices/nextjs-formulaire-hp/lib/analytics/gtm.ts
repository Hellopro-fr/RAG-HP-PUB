// Global types are declared in types/global.d.ts

// =============================================================================
// TYPES
// =============================================================================

type StepType = 'init' | 'question' | 'choix-propart' | 'selection' | 'contact' | 'conversion';

type FlowType = 'principal' | 'pas_assez_produits' | 'pas_trouve_recherchez' | null;

interface FunnelContext {
  rubrique_id?: number;
  rubrique_name?: string;
  page_location_uri?: string;
}

interface QuestionData {
  question_id?: number;
  question_title?: string;
  answer_ids?: string[];
  is_multiselect?: boolean;
  total_questions?: number;
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
function getSessionId(): string {
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

/**
 * Obtenir le page_location_uri actuel
 */
function getPageLocationUri(): string {
  if (typeof window === 'undefined') return '';
  return window.location.pathname;
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
    rubrique_name: funnelContext.rubrique_name,
    page_location_uri: getPageLocationUri(),

    // Type de parcours (null si pas encore déterminé)
    flow_type: currentFlowType,

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

/**
 * Track l'affichage d'une question
 */
export function trackQuestionView(
  questionIndex: number,
  data?: QuestionData
) {
  currentStepIndex = questionIndex + 1; // +1 car funnel-start est à 0
  const stepName = questionIndex === 0 ? '1ere-question' : `${questionIndex + 1}eme-question`;

  trackQuoteFunnel(currentStepIndex, stepName, 'question', {
    question_id: data?.question_id,
    question_title: data?.question_title,
  });
}

/**
 * Track une question répondue
 */
export function trackQuestionAnswered(
  questionIndex: number,
  questionId: number,
  questionTitle: string,
  answerIds: string[],
  isMultiSelect: boolean
) {
  currentStepIndex = questionIndex + 1;
  const stepName = questionIndex === 0 ? '1ere-question-answered' : `${questionIndex + 1}eme-question-answered`;

  trackQuoteFunnel(currentStepIndex, stepName, 'question', {
    question_id: questionId,
    question_title: questionTitle,
    answer_ids: answerIds,
    is_multiselect: isMultiSelect,
  });
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
 * Track le clic sur une carte produit
 */
export function trackProductCardClick(
  productId: string,
  productName: string,
  matchScore: number,
  action: 'view_details' | 'toggle_select'
) {
  trackQuoteFunnel(currentStepIndex, 'product-click', 'selection', {
    product_id: productId,
    product_name: productName,
    match_score: matchScore,
    action,
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
  // Vérifier si c'est la première action de chaque type pour cet utilisateur dans la session
  const isFirstAdd = action === 'ajouter' && isFirstView('product_selection_ajouter');
  const isFirstRemove = action === 'retirer' && isFirstView('product_selection_retirer');

  trackQuoteFunnel(currentStepIndex, 'product-selection', 'selection', {
    product_id: productId,
    action,
    total_selected: totalSelected,
    is_first_add: isFirstAdd,
    is_first_remove: isFirstRemove,
  });
}

/**
 * Track l'ouverture du modal de comparaison
 */
export function trackComparisonModalView(supplierIds: string[]) {
  const isFirstViewForSession = isFirstView('comparison_modal');

  trackQuoteFunnel(currentStepIndex, 'comparison-modal', 'selection', {
    suppliers_compared: supplierIds,
    suppliers_count: supplierIds.length,
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
 * Track le remplissage d'un champ du formulaire
 */
export function trackContactFieldFilled(fieldName: string, fieldIndex: number) {
  trackQuoteFunnel(currentStepIndex, `champ-coordonnees-${fieldIndex + 1}`, 'contact', {
    field_name: fieldName,
    field_index: fieldIndex,
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
    suppliers_count: suppliersCount,
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
// ÉVÉNEMENTS SECONDAIRES (hors funnel principal)
// =============================================================================

/**
 * Track l'ouverture du modal de modification de critères
 */
export function trackModifyCriteriaModalView() {
  const userId = getUserId();
  const sessionId = getSessionId();
  const isFirstViewForSession = isFirstView('modify_criteria_modal');

  pushToDataLayer('page_vue_critere', {
    user_id: userId,
    session_id: sessionId,
    is_first_view: isFirstViewForSession,
    timestamp: new Date().toISOString(),
  });
}

/**
 * Track la modification effective de critères
 */
export function trackCriteriaModified(criteriaCount: number, modifiedFields: string[]) {
  const userId = getUserId();

  pushToDataLayer('critere_modifie', {
    user_id: userId,
    criteria_count: criteriaCount,
    modified_fields: modifiedFields,
    timestamp: new Date().toISOString(),
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
export function trackProductModalView(productId: string, productName: string, supplierId: string) {
  const userId = getUserId();
  const sessionId = getSessionId();
  const modalKey = `product_modal_${productId}`;
  const isFirstViewForSession = isFirstView(modalKey);

  pushToDataLayer('vue_modal_produit', {
    user_id: userId,
    session_id: sessionId,
    is_first_view: isFirstViewForSession,
    product_id: productId,
    product_name: productName,
    supplier_id: supplierId,
    timestamp: new Date().toISOString(),
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
export function trackComparisonModalOpen(supplierIds: string[]) {
  trackComparisonModalView(supplierIds);
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
