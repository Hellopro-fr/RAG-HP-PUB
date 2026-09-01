import { isReplicaLive } from '../../lib/replicas';

/** @type {import('../types').Rule} */
const rule = {
  id: 'replicas_vs_max_slots',
  label: 'Replicas vs slots configurés',
  description:
    'Détecte les slots "phantom" — configuration MAX_GLOBAL_JOBS supérieure ' +
    'au nombre de replicas vivants. Un replica est considéré vivant si son ' +
    'heartbeat est reçu dans les 30 dernières secondes.',
  severity: 'warning',
  sources: ['replicas', 'capacity'],
  attachUiHint: { path: '/', label: 'Vue d\'ensemble · Capacity bar' },
  evaluate: ({ replicas, capacity }) => {
    // Sources absentes / pas encore alimentees -> non evaluable (null),
    // ce qui n'est PAS la meme chose que "aucune violation" ([]).
    if (!capacity?.max_global_jobs) return null;
    const max = capacity.max_global_jobs;
    const alive = Object.values(replicas || {}).filter(
      (r) => r?.replicaId && isReplicaLive(r),
    ).length;
    if (alive === 0) return null; // cold start : aucun heartbeat recu encore
    if (alive >= max) return []; // OK (over-provisioning is a separate concern)
    return [
      {
        message: `${max} slots configurés mais ${alive} replicas vivants — ${
          max - alive
        } slot(s) inutilisable(s)`,
        data: { alive, max, phantom: max - alive },
      },
    ];
  },
};

export default rule;
