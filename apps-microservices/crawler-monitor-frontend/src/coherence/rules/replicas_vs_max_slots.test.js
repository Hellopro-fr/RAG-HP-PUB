import { describe, it, expect } from 'vitest';
import rule from './replicas_vs_max_slots';
import { mkReplica, mkCapacity } from '../__fixtures__/mocks';

const mkReplicasDict = (list) =>
  Object.fromEntries(list.map((r) => [r.replicaId, r]));

describe('replicas_vs_max_slots', () => {
  it('returns [] when alive matches max', () => {
    const replicas = mkReplicasDict([
      mkReplica('r1'),
      mkReplica('r2'),
    ]);
    const capacity = mkCapacity({ max_global_jobs: 2 });
    expect(rule.evaluate({ replicas, capacity })).toEqual([]);
  });

  it('returns [] on cold start (no replicas)', () => {
    expect(
      rule.evaluate({ replicas: {}, capacity: mkCapacity({ max_global_jobs: 7 }) }),
    ).toEqual([]);
  });

  it('flags phantom slots when alive < max', () => {
    const replicas = mkReplicasDict([
      mkReplica('r1'),
      mkReplica('r2'),
      mkReplica('r3'),
    ]);
    const capacity = mkCapacity({ max_global_jobs: 7 });
    const result = rule.evaluate({ replicas, capacity });
    expect(result).toHaveLength(1);
    expect(result[0].data).toEqual({ alive: 3, max: 7, phantom: 4 });
    expect(result[0].message).toMatch(/7 slots configurés mais 3 replicas/);
  });

  it('ignores stale heartbeats (>30s)', () => {
    const replicas = mkReplicasDict([
      mkReplica('alive'),
      mkReplica('dead', { timestamp: Date.now() - 45_000 }),
    ]);
    const capacity = mkCapacity({ max_global_jobs: 1 });
    // alive count = 1, max = 1 → OK
    expect(rule.evaluate({ replicas, capacity })).toEqual([]);
  });

  it('returns [] when capacity data is missing', () => {
    const replicas = mkReplicasDict([mkReplica('r1')]);
    expect(rule.evaluate({ replicas, capacity: null })).toEqual([]);
    expect(rule.evaluate({ replicas, capacity: {} })).toEqual([]);
  });

  it('returns [] when alive exceeds max (over-provisioning, not this rule)', () => {
    const replicas = mkReplicasDict([mkReplica('r1'), mkReplica('r2'), mkReplica('r3')]);
    const capacity = mkCapacity({ max_global_jobs: 2 });
    expect(rule.evaluate({ replicas, capacity })).toEqual([]);
  });
});
