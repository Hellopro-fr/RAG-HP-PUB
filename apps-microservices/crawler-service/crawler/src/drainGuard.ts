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
