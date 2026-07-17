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
    if (!capacity?.max_global_jobs) return [];
    const max = capacity.max_global_jobs;
    const alive = Object.values(replicas || {}).filter(
      (r) => r?.replicaId && isReplicaLive(r),
    ).length;
    if (alive === 0) return []; // cold start — skip
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
