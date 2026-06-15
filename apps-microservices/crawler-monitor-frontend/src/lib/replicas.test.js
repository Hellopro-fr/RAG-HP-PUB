import { describe, it, expect } from 'vitest';
import { replicaLastSeen, replicaAge, isReplicaLive, REPLICA_TTL_MS } from './replicas';

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
