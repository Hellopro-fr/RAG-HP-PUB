// apps-microservices/crawler-monitor-frontend/src/coherence/rules/running_count_parity.test.js
import { describe, it, expect } from 'vitest';
import rule from './running_count_parity';
import { mkJob } from '../__fixtures__/mocks';

describe('running_count_parity', () => {
  it('returns [] when counts match exactly', () => {
    const capacity = { running_jobs: 3 };
    const jobs = [mkJob('a'), mkJob('b'), mkJob('c')];
    expect(rule.evaluate({ capacity, jobs })).toEqual([]);
  });

  it('returns [] within ±1 tolerance', () => {
    const capacity = { running_jobs: 3 };
    const jobs = [mkJob('a'), mkJob('b'), mkJob('c'), mkJob('d')];
    expect(rule.evaluate({ capacity, jobs })).toEqual([]);
  });

  it('flags mismatch beyond tolerance', () => {
    const capacity = { running_jobs: 5 };
    const jobs = [mkJob('a'), mkJob('b')];
    const result = rule.evaluate({ capacity, jobs });
    expect(result).toHaveLength(1);
    expect(result[0].data).toEqual({
      kind: 'running_count_mismatch',
      backendRunning: 5,
      listRunning: 2,
      diff: 3,
    });
  });

  it('returns null (indeterminate) when capacity is missing', () => {
    expect(rule.evaluate({ capacity: null, jobs: [mkJob('a')] })).toBeNull();
    expect(rule.evaluate({ capacity: {}, jobs: [mkJob('a')] })).toBeNull();
  });

  it('returns null (indeterminate) when jobs is missing', () => {
    expect(rule.evaluate({ capacity: { running_jobs: 3 }, jobs: null })).toBeNull();
  });

  it('garde une cle d\'hysteresis stable quand les compteurs bougent', () => {
    const a = rule.evaluate({ capacity: { running_jobs: 6 }, jobs: [] })[0];
    const b = rule.evaluate({ capacity: { running_jobs: 7 }, jobs: [] })[0];
    // Le message change (il porte les compteurs) mais data.kind, lui, ne bouge pas :
    // c'est lui que le provider utilise comme cle d'hysteresis.
    expect(a.message).not.toBe(b.message);
    expect(a.data.kind).toBe(b.data.kind);
  });

  it('ignores non-running jobs', () => {
    const capacity = { running_jobs: 1 };
    const jobs = [
      mkJob('running1', { status: 'running' }),
      mkJob('finished1', { status: 'finished' }),
      mkJob('failed1', { status: 'failed' }),
    ];
    // backend=1, listRunning=1 → OK
    expect(rule.evaluate({ capacity, jobs })).toEqual([]);
  });

  it('has autoRetry configured with both query keys', () => {
    expect(rule.autoRetry).toBeDefined();
    expect(rule.autoRetry.maxAttempts).toBe(2);
    expect(rule.autoRetry.invalidate).toEqual([['capacity'], ['jobs']]);
  });
});
