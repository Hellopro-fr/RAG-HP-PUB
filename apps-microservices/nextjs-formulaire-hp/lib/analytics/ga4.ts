// Global types are declared in types/global.d.ts

/**
 * Track un événement GA4
 */
export function trackEvent(
  action: string,
  category: string,
  label?: string,
  value?: number
) {
  if (typeof window !== 'undefined' && window.gtag) {
    window.gtag('event', action, {
      event_category: category,
      event_label: label,
      value: value,
    });
  }
}

/**
 * Track une page vue
 */
export function trackPageView(url: string, title?: string) {
  if (typeof window !== 'undefined' && window.gtag) {
    window.gtag('event', 'page_view', {
      page_path: url,
      page_title: title,
    });
  }
}

/**
 * Track le début du funnel
 */
export function trackFunnelStart() {
  trackEvent('funnel_start', 'funnel', 'questionnaire', 1);
}

/**
 * Track la fin du questionnaire
 */
export function trackQuestionnaireComplete(timeSpentSeconds: number) {
  trackEvent('questionnaire_complete', 'funnel', 'all_questions_answered', timeSpentSeconds);
}

/**
 * Track la soumission du lead (conversion)
 */
export function trackLeadSubmitted(leadId: string, suppliersCount: number) {
  trackEvent('lead_submitted', 'conversion', leadId, suppliersCount);
}

/**
 * Track une erreur
 */
export function trackError(errorType: string, errorMessage: string) {
  trackEvent('error', 'error', `${errorType}: ${errorMessage}`);
}

/**
 * Track une question répondue dans le questionnaire
 */
export function trackGA4QuestionAnswered(questionId: number, answersCount: number) {
  trackEvent('question_answered', 'questionnaire', `question_${questionId}`, answersCount);
}

/**
 * Track la complétion du questionnaire
 */
export function trackGA4QuestionnaireComplete(totalQuestions: number, timeSpentSeconds: number) {
  trackEvent('questionnaire_complete', 'funnel', `${totalQuestions}_questions`, timeSpentSeconds);
}

/**
 * Track la complétion du profil
 */
export function trackGA4ProfileComplete(profileType: string, hasCompany: boolean) {
  trackEvent('profile_complete', 'funnel', profileType, hasCompany ? 1 : 0);
}

/**
 * Track une sélection de fournisseur
 */
export function trackGA4SupplierSelection(supplierId: string, action: 'add' | 'remove', totalSelected: number) {
  trackEvent('supplier_selection', 'selection', `${action}_${supplierId}`, totalSelected);
}

/**
 * Track la soumission du lead
 */
export function trackGA4LeadSubmitted(leadId: string, suppliersCount: number, profileType: string) {
  if (typeof window !== 'undefined' && window.gtag) {
    window.gtag('event', 'lead_submitted', {
      event_category: 'conversion',
      lead_id: leadId,
      suppliers_count: suppliersCount,
      profile_type: profileType,
    });
  }
}
