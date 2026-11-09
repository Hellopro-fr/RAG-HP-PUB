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
  nav: {
    projects: 'Projets',
    questions: 'Questions',
    agents: 'Agents',
    access: 'Accès',
    logout: 'Déconnexion',
  },
  level: { admin: 'Admin', classic: 'Classique' } as Record<string, string>,
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
    sso: 'Se connecter avec le compte HelloPro',
    local: 'Connexion locale (compte de secours)',
    errors: {
      sso_disabled: 'La connexion HelloPro n’est pas configurée sur ce serveur.',
      sso_denied: 'Connexion annulée.',
      sso_state: 'La connexion a expiré. Recommencez.',
      sso_exchange: 'Le compte HelloPro n’a pas pu confirmer votre identité. Recommencez.',
      sso_not_allowed: 'Votre compte HelloPro est bloqué. Contactez un administrateur.',
      sso_internal: 'Erreur pendant la connexion. Recommencez dans un instant.',
    } as Record<string, string>,
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
  noAccess: {
    title: 'Accès refusé',
    body: 'Vous n’avez pas l’accès à cette page. Un administrateur peut vous le donner depuis la page Accès.',
  },
  access: {
    title: 'Accès',
    users: 'Utilisateurs',
    teams: 'Équipes',
    priority:
      'Priorité : l’accès individuel l’emporte sur celui des équipes ; sans réglage, l’accès est refusé. Les Admins ont tous les accès.',
    noDirectory:
      'Le compte HelloPro n’est pas configuré : pas d’équipes. Seuls les réglages individuels s’appliquent.',
    select: 'Sélectionnez un utilisateur ou une équipe.',
    level: 'Niveau',
    levelHint: 'Un Admin a tous les accès, les réglages ci-dessous ne s’appliquent pas.',
    levelSelf: 'Vous ne pouvez pas changer votre propre niveau.',
    permission: 'Autorisation',
    setting: 'Réglage',
    effective: 'Accès effectif',
    inherit: 'Hériter des équipes',
    unset: 'Non défini',
    allow: 'Autorisé',
    deny: 'Refusé',
    adminOnly: 'Admins uniquement',
    members: (n: number) => `${n} membre${n > 1 ? 's' : ''}`,
    exceptions: (n: number) =>
      n === 0 ? '' : `${n} exception${n > 1 ? 's' : ''} individuelle${n > 1 ? 's' : ''}`,
    noTeam: 'Aucune équipe',
    notSignedIn: 'pas encore connecté·e',
    perms: {
      'projects.create': ['Créer des projets', ''],
      'questions.answer': ['Répondre aux questions', 'Questions posées par les agents'],
      'agents.manage': ['Connecter ses agents', 'Créer un agent et son jeton'],
      'agents.view': ['Voir la page Agents', ''],
      'users.view': ['Voir la page Utilisateurs', ''],
      'access.manage': ['Gérer les accès', 'Niveaux et autorisations'],
    } as Record<string, [string, string]>,
    source: {
      admin_level: 'Niveau Admin',
      admin_only: 'Réservé aux Admins',
      default: 'Aucun réglage',
      individual: (teams: string) => `Individuel, prioritaire${teams ? ` (l’équipe donnerait : ${teams})` : ''}`,
      teamsAllowed: (names: string) => `via ${names}`,
      teamsDenied: (names: string) => `refusé par ${names}`,
    },
  },
  errors: {
    generic: 'Une erreur est survenue.',
    forbidden: 'Vous n’avez pas l’accès pour faire cela. Demandez-le à un administrateur (page Accès).',
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
