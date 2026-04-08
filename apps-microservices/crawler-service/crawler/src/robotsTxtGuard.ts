import { RobotsFile } from 'crawlee';

const ROBOTS_USER_AGENT = 'Googlebot';

/**
 * Probes multiple diverse paths against robots.txt to detect a blanket block.
 * Returns true only if ALL probe URLs are disallowed — indicating Disallow: * or Disallow: /
 * A selective block (e.g., Disallow: /products/) will NOT trigger this.
 */
export function isBlanketBlock(robots: RobotsFile, siteUrl: string): boolean {
    const origin = new URL(siteUrl).origin;
    const probeUrls = [
        origin + '/',
        origin + '/a',
        origin + '/test/page',
    ];
    return probeUrls.every(url => !robots.isAllowed(url, ROBOTS_USER_AGENT));
}
