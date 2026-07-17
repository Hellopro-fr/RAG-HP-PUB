// apps-microservices/crawler-monitor-frontend/src/coherence/rules/replica_job_mapping.js
import { isReplicaLive } from '../../lib/replicas';

/** @type {import('../types').Rule} */
const rule = {
  id: 'replica_job_mapping',
  label: 'Cohérence replica ↔ job',
  description:
    'Détecte les replicas qui tournent à fort CPU sans jobId rattaché (ghost ' +
    'crawler) ou qui référencent un jobId qui n\'est plus en running dans la liste ' +
    'REST (désync heartbeat vs REST).',
  severity: 'warning',
  sources: ['replicas', 'jobs'],
  attachUiHint: { path: '/', label: 'Vue d\'ensemble · Replicas' },
  evaluate: ({ replicas, jobs }) => {
    const violations = [];
    const liveReplicas = Object.values(replicas || {}).filter(
      (r) => r?.replicaId && isReplicaLive(r),
    );
    const runningJobIds = new Set(
      (jobs ?? [])
        .filter((j) => j?.status === 'running')
        .map((j) => j.id),
    );

    for (const r of liveReplicas) {
      // Skip replicas that are restarting after OOM — jobId can legitimately
      // be stale during the restart window.
      if (r.status === 'restarting_oom') continue;

      // (a) high CPU but no jobId → ghost crawler
      if ((r.cpu ?? 0) > 0.3 && !r.jobId) {
        violations.push({
          itemKey: r.replicaId,
          message: `Replica ${String(r.replicaId).slice(0, 12)} actif (CPU ${(
            r.cpu * 100
          ).toFixed(0)}%) mais sans jobId rattaché`,
          data: { replicaId: r.replicaId, cpu: r.cpu, kind: 'replica_without_job' },
        });
      }

      // (b) jobId points to a job no longer running in the REST list
      if (r.jobId && !runningJobIds.has(r.jobId)) {
        violations.push({
          itemKey: r.replicaId,
          message: `Replica travaille sur job ${String(r.jobId).slice(
            0,
            12,
          )} mais ce job n'est plus "running" dans la liste`,
          data: {
            replicaId: r.replicaId,
            jobId: r.jobId,
            kind: 'stale_job_reference',
          },
        });
      }
    }
    return violations;
  },
  autoRetry: {
    maxAttempts: 2,
    delayMs: 3000,
    invalidate: [['jobs']],
  },
};

export default rule;
