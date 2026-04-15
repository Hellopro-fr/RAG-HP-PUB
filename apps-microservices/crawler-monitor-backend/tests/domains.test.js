import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseDomainWindow, aggregateDomains, jobsForDomain } from '../src/lib/domains.js';

test('parseDomainWindow accepts 24h, 7d, 30d', () => {
  assert.equal(parseDomainWindow('24h'), 24 * 60 * 60 * 1000);
  assert.equal(parseDomainWindow('7d'),  7 * 24 * 60 * 60 * 1000);
  assert.equal(parseDomainWindow('30d'), 30 * 24 * 60 * 60 * 1000);
  assert.throws(() => parseDomainWindow('1h'), /Invalid window/);
});

test('aggregateDomains groups jobs by domain and computes success_rate', () => {
  const now = Date.now();
  const jobs = [
    { id: 'a', domain: 'amazon.fr',     start_time: new Date(now - 1000).toISOString(),  status: 'finished', crawl_mode: 'standard' },
    { id: 'b', domain: 'amazon.fr',     start_time: new Date(now - 60000).toISOString(), status: 'failed',   oom_restart_count: 1 },
    { id: 'c', domain: 'leroymerlin.fr',start_time: new Date(now - 5000).toISOString(),  status: 'finished', crawl_mode: 'update' },
    { id: 'd', domain: 'leroymerlin.fr',start_time: new Date(now - 8000).toISOString(),  status: 'running' },
    // Outside window
    { id: 'old', domain: 'amazon.fr',   start_time: new Date(now - 8 * 24 * 60 * 60 * 1000).toISOString(), status: 'finished' },
    // Missing domain
    { id: 'no-domain', start_time: new Date(now - 1000).toISOString(), status: 'finished' },
  ];
  const result = aggregateDomains(jobs, now, 7 * 24 * 60 * 60 * 1000);
  assert.equal(result.length, 2);

  const amz = result.find(d => d.domain === 'amazon.fr');
  assert.equal(amz.total_jobs, 2);
  assert.equal(amz.success, 1);
  assert.equal(amz.failure, 1);
  assert.equal(amz.success_rate, 0.5);
  assert.equal(amz.oom_total, 1);

  const lm = result.find(d => d.domain === 'leroymerlin.fr');
  assert.equal(lm.total_jobs, 2);
  assert.equal(lm.success, 1);
  assert.equal(lm.running, 1);
  assert.equal(lm.success_rate, 1); // 1 success / 1 terminal
  assert.equal(lm.update_share, 0.5); // 1/2

  // Sorted by last_run_at desc -> amazon (1000ms ago) first
  assert.equal(result[0].domain, 'amazon.fr');
});

test('aggregateDomains returns null success_rate when no terminal jobs', () => {
  const now = Date.now();
  const jobs = [{ id: 'x', domain: 'foo.com', start_time: new Date(now).toISOString(), status: 'running' }];
  const result = aggregateDomains(jobs, now, 7 * 24 * 60 * 60 * 1000);
  assert.equal(result[0].success_rate, null);
});

test('jobsForDomain filters and builds a chain via previous_crawl_id', () => {
  const now = Date.now();
  const jobs = [
    { id: '4', domain: 'a.com', start_time: new Date(now - 1000).toISOString(),  status: 'running',  previous_crawl_id: '3' },
    { id: '3', domain: 'a.com', start_time: new Date(now - 30000).toISOString(), status: 'failed',   previous_crawl_id: '2' },
    { id: '2', domain: 'a.com', start_time: new Date(now - 60000).toISOString(), status: 'finished', previous_crawl_id: '1' },
    { id: '1', domain: 'a.com', start_time: new Date(now - 90000).toISOString(), status: 'finished' },
    { id: 'other', domain: 'b.com', start_time: new Date(now).toISOString(), status: 'finished' },
  ];
  const { jobs: filtered, chain } = jobsForDomain(jobs, 'a.com', 7 * 24 * 60 * 60 * 1000, now);
  assert.equal(filtered.length, 4);
  assert.equal(filtered[0].id, '4'); // newest first
  assert.equal(chain.length, 4);
  assert.deepEqual(chain.map(c => c.id), ['4', '3', '2', '1']);
});

test('jobsForDomain handles broken chain gracefully', () => {
  const now = Date.now();
  const jobs = [
    { id: '2', domain: 'a.com', start_time: new Date(now).toISOString(),       status: 'running', previous_crawl_id: 'missing' },
    { id: '1', domain: 'a.com', start_time: new Date(now - 60000).toISOString(), status: 'finished' },
  ];
  const { chain } = jobsForDomain(jobs, 'a.com', 86400000, now);
  // Chain stops at id 2 because 'missing' is not in the map
  assert.equal(chain.length, 1);
  assert.equal(chain[0].id, '2');
});