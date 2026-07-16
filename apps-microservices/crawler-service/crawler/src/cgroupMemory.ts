// Cgroup memory reader with page-cache subtraction (Spec-B 2026-05-21).
//
// `memory.current` (v2) and `memory.usage_in_bytes` (v1) include page cache
// (reclaimable filesystem cache). Linux reclaims that on demand before invoking
// the OOM-killer. Treating it as "used" inflates the percentage when prior I/O
// loaded the cache — observed at 99.7% on shop.monlabofermier.fr crawl 6334.
//
// Fix: subtract the `file` (v2) / `cache` (v1) bytes from memory.current to get
// the "usable used" view (anon + slab + kernel + sock — non-reclaimable).
//
// Module is side-effect-free so it can be unit-tested in isolation (main.ts has
// top-level execution that fires on import, breaking direct test imports —
// same constraint that drove browserKill.ts extraction in Spec-A).

import fsPromises from 'node:fs/promises';
import os from 'node:os';

export interface UsableMemory {
    /** memory.current - file (v2) or memory.usage_in_bytes - cache (v1). */
    usableUsed: number;
    /** memory.max (v2) or memory.limit_in_bytes (v1) or os.totalmem() (host fallback). */
    totalMem: number;
    /** memory.current (v2) or memory.usage_in_bytes (v1) or os.totalmem()-os.freemem() (host fallback). */
    rawCurrent: number;
    /** file (v2) or cache (v1); 0 on host fallback (no cgroup visibility). */
    pageCache: number;
}

/**
 * Parses a cgroup memory.stat file content and returns the page-cache bytes.
 * v2 uses the `file` key; v1 uses the `cache` key. Returns { file: 0 } when
 * neither key is present. Malformed lines (blank, missing value, non-numeric)
 * are skipped silently.
 */
export function parseMemoryStat(content: string): { file: number } {
    let file = 0;
    for (const line of content.split('\n')) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        const parts = trimmed.split(/\s+/);
        if (parts.length < 2) continue;
        const [key, rawValue] = parts;
        if (key !== 'file' && key !== 'cache') continue;
        const value = parseInt(rawValue, 10);
        // Number.isFinite returns false for NaN, so one check covers both.
        if (!Number.isFinite(value)) continue;
        file = value;
    }
    return { file };
}

async function readFileOrNull(path: string): Promise<string | null> {
    try {
        return await fsPromises.readFile(path, 'utf-8');
    } catch {
        return null;
    }
}

/**
 * Reads cgroup memory.{max,current,stat} (v2 first, v1 fallback, host last)
 * and returns the usable-used view. Returns null only when all three fallback
 * paths fail (true I/O failure — never expected in a Linux Docker container).
 */
export async function readUsableMemory(): Promise<UsableMemory | null> {
    // cgroup v2
    const v2Max = await readFileOrNull('/sys/fs/cgroup/memory.max');
    const v2Current = await readFileOrNull('/sys/fs/cgroup/memory.current');
    const v2Stat = await readFileOrNull('/sys/fs/cgroup/memory.stat');
    if (v2Max && v2Current && v2Stat && v2Max.trim() !== 'max') {
        const totalMem = parseInt(v2Max.trim(), 10);
        const rawCurrent = parseInt(v2Current.trim(), 10);
        const { file: pageCache } = parseMemoryStat(v2Stat);
        return { usableUsed: rawCurrent - pageCache, totalMem, rawCurrent, pageCache };
    }

    // cgroup v1
    const v1Limit = await readFileOrNull('/sys/fs/cgroup/memory/memory.limit_in_bytes');
    const v1Usage = await readFileOrNull('/sys/fs/cgroup/memory/memory.usage_in_bytes');
    const v1Stat = await readFileOrNull('/sys/fs/cgroup/memory/memory.stat');
    if (v1Limit && v1Usage && v1Stat) {
        const totalMem = parseInt(v1Limit.trim(), 10);
        const rawCurrent = parseInt(v1Usage.trim(), 10);
        const { file: pageCache } = parseMemoryStat(v1Stat);
        return { usableUsed: rawCurrent - pageCache, totalMem, rawCurrent, pageCache };
    }

    // Host fallback (no cgroup, e.g., local dev outside Docker)
    try {
        const totalMem = os.totalmem();
        const rawCurrent = totalMem - os.freemem();
        return { usableUsed: rawCurrent, totalMem, rawCurrent, pageCache: 0 };
    } catch {
        return null;
    }
}
