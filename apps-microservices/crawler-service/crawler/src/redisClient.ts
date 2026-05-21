// Redis connection leak fix Spec-C 2026-05-21 — single named Redis client.
//
// Why single client: each TCP conn to Redis costs a server-side FD. OOM-killed
// Node processes leave orphan conns until server idle-timeout. Halving the
// per-crawl conn count (2 -> 1) halves the orphan blast radius.
//
// Why named: CLIENT LIST attributes conns to a crawl_id for diagnostics.
// `crawler-node-{crawlId}` is unique per crawl + survives reconnect.
//
// Why module: side-effect-free so tests can import without firing main.ts
// top-level execution (same constraint as browserKill.ts + cgroupMemory.ts).

import { createClient as realCreateClient, RedisClientType } from 'redis';
import type { RedisHealthMonitor } from './class/RedisHealthMonitor.js';

export interface SharedRedisClientOpts {
    crawlId: string;
    monitor?: RedisHealthMonitor;
}

// Test seam — production callers ignore this. Tests override via
// __setCreateClientForTests so we can assert the options passed.
let _createClient: typeof realCreateClient = realCreateClient;

export function __setCreateClientForTests(fn: typeof realCreateClient): void {
    _createClient = fn;
}

export function createSharedRedisClient(
    redisUrl: string,
    { crawlId, monitor }: SharedRedisClientOpts,
): RedisClientType {
    const client = _createClient({
        url: redisUrl,
        name: `crawler-node-${crawlId}`,
        socket: {
            keepAlive: 30_000,
            connectTimeout: 5_000,
        },
    }) as RedisClientType;
    client.on('error', (err) => {
        console.error('Redis Client Error:', err);
        monitor?.onError('shared', err);
    });
    return client;
}
