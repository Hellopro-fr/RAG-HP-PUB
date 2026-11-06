// All user-facing copy (French). Code, logs and API stay in English.

export const STATE_ORDER = [
  'draft',
  'ready',
  'working',
  'input_required',
  'testing',
  'in_review',
  'done',
  'failed',
  'cancelled',
] as const;

export type TaskState = (typeof STATE_ORDER)[number];

export const fr = {
  app: 'Agent Task Board',
  nav: { projects: 'Projets', questions: 'Questions', agents: 'Agents', logout: 'Déconnexion' },
  state: {
    draft: 'Brouillon',
    ready: 'Prête',
    working: 'En cours',
    input_required: 'En attente de réponse',
    testing: 'En test',
    in_review: 'En revue',
    done: 'Terminée',
    failed: 'Échouée',
    cancelled: 'Annulée',
  } satisfies Record<TaskState, string>,
  login: {
    title: 'Connexion',
    login: 'Identifiant',
    password: 'Mot de passe',
    submit: 'Se connecter',
    failed: 'Identifiant ou mot de passe incorrect.',
  },
  projects: {
    title: 'Projets',
    empty: 'Aucun projet pour le moment.',
    create: 'Créer un projet',
    name: 'Nom du projet',
    open: 'Ouvrir le tableau',
  },
  board: {
    live: 'En direct',
    reconnecting: 'Reconnexion…',
    blocked: 'Bloquée',
    specOutdated: 'Spec obsolète',
    attempt: (n: number) => `Tentative ${n}`,
    questions: (n: number) => `${n} question${n > 1 ? 's' : ''}`,
    priority: (p: number) => `P${p}`,
    leasePaused: 'bail en pause',
    leaseLeft: (s: string) => `bail : ${s}`,
    leaseExpired: 'bail expiré',
    reservedFor: 'réservée',
    dropNotAllowed: 'Ce déplacement n’est pas autorisé. Seule l’annulation se fait par glisser-déposer.',
    confirmCancel: 'Annuler cette tâche ? Cette action est définitive.',
    pending: 'En attente du serveur…',
  },
  task: {
    spec: 'Spécification',
    criteria: 'Critères d’acceptation',
    notVerified: 'non vérifié (phase 2)',
    timeline: 'Historique',
    showThoughts: 'Afficher les réflexions',
    attempts: 'Tentatives',
    handoff: 'Note de passation',
    commit: 'Commit',
    trace: 'Trace',
    questions: 'Questions',
    blockers: 'Bloquée par',
    cancel: 'Annuler la tâche',
    holder: 'Détenteur',
    none: '—',
  },
  questions: {
    title: 'Questions ouvertes',
    empty: 'Aucune question ouverte.',
    blocking: 'Bloquante',
    answer: 'Répondre',
    placeholder: 'Votre réponse…',
    askedBy: (who: string) => `posée par ${who}`,
    task: 'Tâche',
  },
  agents: {
    title: 'Agents',
    actor: 'Acteur',
    kind: 'Type',
    task: 'Tâche en cours',
    heartbeat: 'Dernier battement',
    leaseLeft: 'Bail restant',
    activity: 'Activité (1 h)',
    idle: 'inactif',
  },
  event: {
    'task.created': 'Tâche créée',
    'task.updated': 'Tâche modifiée',
    'task.state_changed': 'Changement d’état',
    'task.link_added': 'Lien ajouté',
    'task.spec_outdated': 'Spec obsolète',
    'task.repinned': 'Spec re-épinglée',
    'lease.claimed': 'Tâche prise',
    'lease.released': 'Tâche libérée',
    'lease.expired': 'Bail expiré',
    'activity.reported': 'Activité',
    'question.asked': 'Question posée',
    'question.answered': 'Question répondue',
    'test.requested': 'Test demandé',
    'test.completed': 'Test terminé',
    'review.submitted': 'Revue soumise',
    'attempt.ended': 'Tentative terminée',
  } as Record<string, string>,
  errors: {
    generic: 'Une erreur est survenue.',
  },
};

/** "2 min 05 s" style remaining time. */
export function formatRemaining(ms: number): string {
  if (ms <= 0) return '0 s';
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const rest = s % 60;
  return m > 0 ? `${m} min ${String(rest).padStart(2, '0')} s` : `${rest} s`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'medium' });
}
