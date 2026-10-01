/**
 * limitDiez stop predicate. Reads the LIVE bypass/skip flags so a mid-crawl
 * tier-1/tier-2 commit (which sets context.config.bypassDiez/skipDiez) actually
 * disables the stop. Phase-1 read by-value startCrawler params here, so runtime
 * commits never disabled the stop (latent bug).
 */
export const shouldStopForDiez = (
	count: number,
	bypassDiez: boolean,
	skipDiez: boolean,
	limit: number,
): boolean => !bypassDiez && !skipDiez && count >= limit;
