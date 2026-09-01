export const API_URL = '/api';
export const JOBS_PER_PAGE = 20;

/**
 * Table unique des statuts de job renvoyés par le crawler-service.
 *
 * Source de vérité pour la couleur (`tone`, consommé par <Pill>) et le libellé
 * français affiché. Toute page qui rend un statut doit passer par
 * `statusTone()` / `statusLabel()` — plus de table locale divergente.
 */
export const JOB_STATUS = {
  running:        { tone: 'accent',  label: 'En cours' },
  starting:       { tone: 'accent',  label: 'Démarrage' },
  stopping:       { tone: 'warn',    label: 'Arrêt en cours' },
  stopped:        { tone: 'warn',    label: 'Arrêté' },
  restarting_oom: { tone: 'warn',    label: 'Redémarrage OOM' },
  stashing:       { tone: 'warn',    label: 'Mise en réserve' },
  unstashed:      { tone: 'info',    label: 'Restauré' },
  pending_upload: { tone: 'info',    label: 'Upload en attente' },
  deferred:       { tone: 'warn',    label: 'Différé' },
  finished:       { tone: 'ok',      label: 'Terminé' },
  failed:         { tone: 'err',     label: 'Échec' },
  archived:       { tone: 'neutral', label: 'Archivé' },
};

/** Ordre d'affichage canonique (utilisé pour construire les filtres). */
export const JOB_STATUS_KEYS = Object.keys(JOB_STATUS);

/** Statuts considérés comme « en vol » (job encore actif côté crawler). */
export const ACTIVE_JOB_STATUSES = [
  'running', 'starting', 'stopping', 'restarting_oom', 'stashing',
];

/** Statuts terminaux : plus aucune mise à jour à attendre. */
export const TERMINAL_JOB_STATUSES = ['finished', 'failed', 'archived', 'stopped'];

const normalize = (status) => String(status ?? '').toLowerCase();

/** Ton <Pill> d'un statut — repli `neutral` sur un statut inconnu. */
export function statusTone(status) {
  return JOB_STATUS[normalize(status)]?.tone ?? 'neutral';
}

/** Libellé français d'un statut — repli sur la valeur brute. */
export function statusLabel(status) {
  const key = normalize(status);
  return JOB_STATUS[key]?.label ?? (status ? String(status) : '—');
}

/** true si le job n'évoluera plus (utile pour couper le polling). */
export function isTerminalStatus(status) {
  return TERMINAL_JOB_STATUSES.includes(normalize(status));
}

/**
 * Fenêtres temporelles des sélecteurs de période.
 *
 * La VALEUR est celle attendue par l'API (`7d`, `30d`) ; seul le LIBELLÉ est
 * francisé (`7j`, `30j`). Ne jamais envoyer le libellé au backend.
 */
export const WINDOW_LABELS = {
  '1h': '1h',
  '6h': '6h',
  '24h': '24h',
  '7d': '7j',
  '30d': '30j',
};

export const windowLabel = (value) => WINDOW_LABELS[value] ?? value;
