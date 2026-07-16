/**
 * limitQuestionMark stop predicate. Reads the LIVE bypass/skip flags so the
 * phase-2 default-at-ceiling (which sets context.config.bypassQuestionMark) and
 * any mid-crawl commit actually disable the stop. functions.ts read by-value
 * startCrawler params here (latent bug, same class as the diez stop).
 */
export const shouldStopForQuestionMark = (
    count: number,
    bypassQuestionMark: boolean,
    skipQuestionMark: boolean,
    limit: number,
): boolean => !bypassQuestionMark && !skipQuestionMark && count >= limit;
