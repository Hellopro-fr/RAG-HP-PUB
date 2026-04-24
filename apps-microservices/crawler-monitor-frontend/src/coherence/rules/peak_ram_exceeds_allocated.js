// apps-microservices/crawler-monitor-frontend/src/coherence/rules/peak_ram_exceeds_allocated.js
const GB = 1024 * 1024 * 1024;
const TOLERANCE = 1.02; // 2% — compensates rounding / cgroup jitter

/** @type {import('../types').Rule} */
const rule = {
  id: 'peak_ram_exceeds_allocated',
  label: 'Peak RAM > allocation',
  description:
    'Dans les stats agrégées du capacity planning, peak ne devrait jamais ' +
    'dépasser allocated (hard limit cgroup). Si ça arrive, c\'est un bug de ' +
    'tracking côté backend, pas un incident ops.',
  severity: 'info',
  sources: ['capacityPlanning'],
  attachUiHint: { path: '/capacity-planning', label: 'Capacity Planning · table replicas' },
  evaluate: ({ capacityPlanning }) => {
    const replicas = capacityPlanning?.replicas ?? [];
    const violations = [];
    for (const r of replicas) {
      if (!r.allocated || !r.peak) continue;
      if (r.peak <= r.allocated) continue;
      if (r.peak / r.allocated < TOLERANCE) continue;
      violations.push({
        itemKey: r.replicaId,
        message: `Peak ${(r.peak / GB).toFixed(2)} GB > alloué ${(r.allocated / GB).toFixed(2)} GB — tracking backend incohérent`,
        data: {
          replicaId: r.replicaId,
          peak: r.peak,
          allocated: r.allocated,
          ratio: r.peak / r.allocated,
        },
      });
    }
    return violations;
  },
};

export default rule;
