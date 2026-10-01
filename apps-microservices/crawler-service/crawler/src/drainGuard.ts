export interface DrainSample {
    currentConcurrency: number;
    pendingRequestCount: number;
    handledRequestCount: number;
    totalRequestCount: number;
}

/**
 * Consecutive idle+drained samples (at the 30s queue-stats cadence, ~90s) required
 * before concluding the crawl is complete-but-wedged. A healthy crawl with real
 * pending work is never idle this long.
 */
export const DRAIN_CONFIRM_SAMPLES = 3;

/**
 * True for a single sample iff the crawl is genuinely drained: the pool is running
 * nothing, the queue reports nothing pending, and every request is accounted as
 * handled. Inputs come from requestQueue.getInfo() (in-memory resolution counters,
 * accurate even when isEmpty()/queueHeadIds is wedged) + autoscaledPool.currentConcurrency.
 * pendingRequestCount===0 is the key false-positive guard — it stays > 0 during a
 * detect-backpressure pause, memory pause, or rate-throttle. totalRequestCount > 0
 * avoids firing at the pre-dispatch start.
 */
export const isDrainedSample = (s: DrainSample): boolean =>
    s.currentConcurrency === 0 &&
    s.totalRequestCount > 0 &&
    s.pendingRequestCount === 0 &&
    s.handledRequestCount === s.totalRequestCount;

/**
 * Idle but the resolution counters don't reconcile → wedge suspect. Only meaningful
 * at concurrency 0: while the pool runs, in-progress requests make handled+pending < total
 * legitimately; at idle (nothing dispatched) handled+pending MUST equal total on a healthy
 * queue. When it doesn't, getInfo()'s counters are themselves wedged (the 0/0/N deadlock) —
 * which isDrainedSample cannot see. Callers confirm via a disk recount before acting.
 */
export const isUnreconciledIdle = (s: DrainSample): boolean =>
    s.currentConcurrency === 0 &&
    s.totalRequestCount > 0 &&
    s.handledRequestCount + s.pendingRequestCount !== s.totalRequestCount;

/** Resolves the disk-recount drain backstop kill-switch. Default true; only "false" disables. */
export const resolveDrainDiskRecount = (raw: string | undefined): boolean =>
    (raw ?? "true").trim().toLowerCase() !== "false";

/** Derived once at module load. Node-only, inherited by the crawler subprocess. */
export const DRAIN_DISK_RECOUNT_ENABLED: boolean =
    resolveDrainDiskRecount(process.env.DRAIN_DISK_RECOUNT_ENABLED);
