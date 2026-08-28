import { describe, it, expect } from 'vitest';
import {
  replicaLastSeen,
  replicaAge,
  isReplicaLive,
  REPLICA_TTL_MS,
  aggregateReplicasRamSeries,
} from './replicas';

describe('replicaLastSeen', () => {
  it('préfère receivedAt à timestamp quand les deux sont présents', () => {
    const replica = { receivedAt: 9000, timestamp: 1000 };
    expect(replicaLastSeen(replica)).toBe(9000);
  });

  it('fallback sur timestamp si receivedAt absent', () => {
    const replica = { timestamp: 5000 };
    expect(replicaLastSeen(replica)).toBe(5000);
  });

  it('retourne 0 si aucun champ présent', () => {
    expect(replicaLastSeen({})).toBe(0);
    expect(replicaLastSeen(null)).toBe(0);
    expect(replicaLastSeen(undefined)).toBe(0);
  });
});

describe('replicaAge', () => {
  it('retourne now - replicaLastSeen', () => {
    const now = 100_000;
    const replica = { receivedAt: 90_000 };
    expect(replicaAge(replica, now)).toBe(10_000);
  });

  it('utilise receivedAt (pas timestamp) pour le calcul', () => {
    const now = 100_000;
    const replica = { receivedAt: 80_000, timestamp: 50_000 };
    expect(replicaAge(replica, now)).toBe(20_000);
  });
});

describe('isReplicaLive', () => {
  it('retourne true si receivedAt est frais (< TTL)', () => {
    const now = 100_000;
    const replica = { receivedAt: now - 5_000, timestamp: now - 5_000 };
    expect(isReplicaLive(replica, now)).toBe(true);
  });

  it('scénario skew : timestamp périmé (now-60000) MAIS receivedAt frais (now) → true', () => {
    const now = 100_000;
    const replica = { receivedAt: now, timestamp: now - 60_000 };
    expect(isReplicaLive(replica, now)).toBe(true);
  });

  it('retourne false si receivedAt est vieux (>= TTL)', () => {
    const now = 100_000;
    const replica = { receivedAt: now - 40_000 };
    expect(isReplicaLive(replica, now)).toBe(false);
  });

  it('fallback : pas de receivedAt, timestamp frais → true', () => {
    const now = 100_000;
    const replica = { timestamp: now - 5_000 };
    expect(isReplicaLive(replica, now)).toBe(true);
  });

  it('retourne false si aucun champ (age = now, >> TTL)', () => {
    const now = 100_000;
    const replica = {};
    // replicaLastSeen → 0, age = 100_000 > 30_000
    expect(isReplicaLive(replica, now)).toBe(false);
  });
});

describe('REPLICA_TTL_MS', () => {
  it('vaut 30 000 ms', () => {
    expect(REPLICA_TTL_MS).toBe(30_000);
  });
});

describe('aggregateReplicasRamSeries', () => {
  const MB = 1024 * 1024;
  // 2 buckets de 30s : t0 = 0-29999, t1 = 30000-59999.
  const history = {
    'replica-a': [
      { ts: 1_000,  ram: 100 * MB, totalRam: 800 * MB },
      { ts: 20_000, ram: 200 * MB, totalRam: 800 * MB }, // dernier du bucket 0
      { ts: 40_000, ram: 300 * MB, totalRam: 800 * MB }, // dernier du bucket 1
    ],
    'replica-b': [
      { ts: 5_000,  ram: 50 * MB,  totalRam: 400 * MB },
      { ts: 45_000, ram: 150 * MB, totalRam: 400 * MB },
    ],
  };

  it('somme le DERNIER point de chaque replica par bucket de 30s, en Mo', () => {
    const { points } = aggregateReplicasRamSeries(history);
    // bucket 0 : 200 (a) + 50 (b) ; bucket 1 : 300 (a) + 150 (b)
    expect(points).toEqual([250, 450]);
  });

  it('expose la capacité (somme des totalRam) et la dernière valeur', () => {
    const { capacityMb, lastMb } = aggregateReplicasRamSeries(history);
    expect(capacityMb).toBe(1200);
    expect(lastMb).toBe(450);
  });

  it('ignore un replica sans échantillon dans le bucket (pas de prolongation)', () => {
    const { points } = aggregateReplicasRamSeries({
      a: [{ ts: 1_000, ram: 100 * MB, totalRam: 800 * MB }],
      b: [{ ts: 40_000, ram: 60 * MB, totalRam: 400 * MB }],
    });
    expect(points).toEqual([100, 60]);
  });

  it('respecte une taille de bucket personnalisée', () => {
    const { points } = aggregateReplicasRamSeries(
      { a: [{ ts: 0, ram: 10 * MB }, { ts: 5_000, ram: 20 * MB }] },
      10_000,
    );
    expect(points).toEqual([20]); // les deux points tombent dans le même bucket
  });

  it('tolère une charge utile vide, nulle ou mal formée', () => {
    expect(aggregateReplicasRamSeries(null)).toEqual({ points: [], capacityMb: null, lastMb: null });
    expect(aggregateReplicasRamSeries({})).toEqual({ points: [], capacityMb: null, lastMb: null });
    expect(aggregateReplicasRamSeries({ a: [{ ts: 'nope', ram: 1 }] }).points).toEqual([]);
  });
});
