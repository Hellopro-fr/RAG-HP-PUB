// apps-microservices/crawler-monitor-frontend/src/coherence/rules/replica_job_mapping.test.js
import { describe, it, expect } from 'vitest';
import rule from './replica_job_mapping';
import { mkReplica, mkJob } from '../__fixtures__/mocks';

const replicasDict = (list) =>
  Object.fromEntries(list.map((r) => [r.replicaId, r]));

describe('replica_job_mapping', () => {
  it('returns [] when all replicas have a valid jobId pointing to running jobs', () => {
    const replicas = replicasDict([mkReplica('r1', { jobId: 'j1', cpu: 0.5 })]);
    const jobs = [mkJob('j1')];
    expect(rule.evaluate({ replicas, jobs })).toEqual([]);
  });

  it('flags replica with CPU > 30% but no jobId (ghost crawler)', () => {
    const replicas = replicasDict([mkReplica('r1', { cpu: 0.45, jobId: null })]);
    const jobs = [];
    const result = rule.evaluate({ replicas, jobs });
    expect(result).toHaveLength(1);
    expect(result[0].itemKey).toBe('r1');
    expect(result[0].data.kind).toBe('replica_without_job');
  });

  it('does NOT flag replica with low CPU and no jobId (idle replica)', () => {
    const replicas = replicasDict([mkReplica('r1', { cpu: 0.1, jobId: null })]);
    const jobs = [];
    expect(rule.evaluate({ replicas, jobs })).toEqual([]);
  });

  it('flags stale jobId reference (job not in running list)', () => {
    const replicas = replicasDict([mkReplica('r1', { cpu: 0.3, jobId: 'j_old' })]);
    const jobs = [mkJob('j_new')];
    const result = rule.evaluate({ replicas, jobs });
    expect(result.some((v) => v.data.kind === 'stale_job_reference')).toBe(true);
  });

  it('skips replicas with status restarting_oom', () => {
    const replicas = replicasDict([
      mkReplica('r1', { status: 'restarting_oom', jobId: 'old_job', cpu: 0.5 }),
    ]);
    const jobs = [];
    expect(rule.evaluate({ replicas, jobs })).toEqual([]);
  });

  it('skips stale-heartbeat replicas (>30s)', () => {
    const replicas = replicasDict([
      mkReplica('r1', { cpu: 0.8, jobId: null, timestamp: Date.now() - 60_000 }),
    ]);
    const jobs = [];
    expect(rule.evaluate({ replicas, jobs })).toEqual([]);
  });

  it('returns multiple violations for multiple replicas', () => {
    const replicas = replicasDict([
      mkReplica('r1', { cpu: 0.5, jobId: null }),
      mkReplica('r2', { cpu: 0.4, jobId: null }),
    ]);
    const jobs = [];
    const result = rule.evaluate({ replicas, jobs });
    expect(result).toHaveLength(2);
    expect(result.map((v) => v.itemKey).sort()).toEqual(['r1', 'r2']);
  });
});
