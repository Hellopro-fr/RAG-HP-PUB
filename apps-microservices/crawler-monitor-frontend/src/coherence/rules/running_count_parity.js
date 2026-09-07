// apps-microservices/crawler-monitor-frontend/src/coherence/rules/running_count_parity.js
/** @type {import('../types').Rule} */
const rule = {
  id: 'running_count_parity',
  label: 'Parité running jobs REST/UI',
  description:
    'capacity.running_jobs (REST) doit correspondre au nombre de jobs ' +
    'status=running dans la liste. Un écart > 1 indique une désync REST qui ' +
    'devrait se résoudre au prochain refetch.',
  severity: 'info',
  sources: ['capacity', 'jobs'],
  attachUiHint: { path: '/', label: 'Vue d\'ensemble · compteur « En cours »' },
  evaluate: ({ capacity, jobs }) => {
    // Source absente → non évaluable (≠ « tout va bien »).
    if (capacity?.running_jobs == null || !jobs) return null;
    const backendRunning = capacity.running_jobs;
    const listRunning = jobs.filter((j) => j?.status === 'running').length;
    if (backendRunning === listRunning) return [];
    if (Math.abs(backendRunning - listRunning) <= 1) return []; // race tolerance
    return [
      {
        message: `Le compteur REST indique ${backendRunning} jobs en cours, la liste en affiche ${listRunning} — désync REST`,
        data: {
          // `kind` est la clé d'hystérésis : elle DOIT rester stable pendant que
          // les compteurs bougent, sinon la règle ne sonne jamais.
          kind: 'running_count_mismatch',
          backendRunning,
          listRunning,
          diff: backendRunning - listRunning,
        },
      },
    ];
  },
  autoRetry: {
    maxAttempts: 2,
    delayMs: 3000,
    invalidate: [['capacity'], ['jobs']],
  },
};

export default rule;
