// Global types are declared in types/global.d.ts

/**
 * Envoie un événement Hotjar
 */
export function hotjarEvent(eventName: string) {
  if (typeof window !== 'undefined' && window.hj) {
    window.hj('event', eventName);
  }
}

/**
 * Identifie un utilisateur dans Hotjar
 */
export function hotjarIdentify(userId: string, attributes?: Record<string, unknown>) {
  if (typeof window !== 'undefined' && window.hj) {
    window.hj('identify', userId, attributes);
  }
}

/**
 * Notifie Hotjar d'un changement de page (pour SPA)
 */
export function hotjarStateChange(url: string) {
  if (typeof window !== 'undefined' && window.hj) {
    window.hj('stateChange', url);
  }
}

/**
 * Tag un enregistrement Hotjar pour filtrage
 */
export function hotjarTagRecording(tags: string[]) {
  if (typeof window !== 'undefined' && window.hj) {
    window.hj('tagRecording', tags);
  }
}

/**
 * Déclenche un sondage Hotjar
 */
export function hotjarTriggerSurvey(surveyId: string) {
  if (typeof window !== 'undefined' && window.hj) {
    window.hj('trigger', surveyId);
  }
}

// Tags prédéfinis pour le funnel
export const HOTJAR_TAGS = {
  STARTED_FUNNEL: 'started_funnel',
  COMPLETED_QUESTIONNAIRE: 'completed_questionnaire',
  COMPLETED_PROFILE: 'completed_profile',
  USED_COMPARISON: 'used_comparison',
  CONVERTED: 'converted',
} as const;

/**
 * Tag un utilisateur avec un tag spécifique
 */
export function tagHotjarUser(tag: string) {
  hotjarTagRecording([tag]);
}
