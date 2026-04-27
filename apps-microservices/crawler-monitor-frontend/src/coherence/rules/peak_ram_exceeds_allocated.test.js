// apps-microservices/crawler-monitor-frontend/src/coherence/rules/peak_ram_exceeds_allocated.test.js
import { describe, it, expect } from 'vitest';
import rule from './peak_ram_exceeds_allocated';

const mkCPReplica = (id, peakGB, allocatedGB) => ({
  replicaId: id,
  peak: peakGB * 1024 * 1024 * 1024,
  allocated: allocatedGB * 1024 * 1024 * 1024,
});

describe('peak_ram_exceeds_allocated', () => {
  it('returns [] when peak <= allocated', () => {
    const capacityPlanning = {
      replicas: [mkCPReplica('r1', 4, 6)],
    };
    expect(rule.evaluate({ capacityPlanning })).toEqual([]);
  });

  it('returns [] within 2% tolerance', () => {
    // 6.08 / 6 = 1.0133 → within 2% tolerance
    const capacityPlanning = {
      replicas: [mkCPReplica('r1', 6.08, 6)],
    };
    expect(rule.evaluate({ capacityPlanning })).toEqual([]);
  });

  it('flags when peak > allocated beyond tolerance', () => {
    // 7.2 / 6 = 1.2 → 20% over, exceeds 2% tolerance
    const capacityPlanning = {
      replicas: [mkCPReplica('r1', 7.2, 6)],
    };
    const result = rule.evaluate({ capacityPlanning });
    expect(result).toHaveLength(1);
    expect(result[0].itemKey).toBe('r1');
    expect(result[0].data.ratio).toBeCloseTo(1.2);
  });

  it('returns [] when capacityPlanning is null', () => {
    expect(rule.evaluate({ capacityPlanning: null })).toEqual([]);
  });

  it('skips replicas with missing allocated or peak', () => {
    const capacityPlanning = {
      replicas: [
        { replicaId: 'r_no_alloc', peak: 5 * 1024 * 1024 * 1024 },
        { replicaId: 'r_no_peak', allocated: 6 * 1024 * 1024 * 1024 },
      ],
    };
    expect(rule.evaluate({ capacityPlanning })).toEqual([]);
  });

  it('returns multiple violations for multiple offending replicas', () => {
    const capacityPlanning = {
      replicas: [
        mkCPReplica('r_ok', 5, 6),
        mkCPReplica('r_bad1', 7, 6),
        mkCPReplica('r_bad2', 8, 6),
      ],
    };
    const result = rule.evaluate({ capacityPlanning });
    expect(result).toHaveLength(2);
    expect(result.map((v) => v.itemKey).sort()).toEqual(['r_bad1', 'r_bad2']);
  });
});
