// Tests for isBlanketBlock function
// Verifies that blanket blocks (Disallow: * or Disallow: /) are detected
// while selective blocks (Disallow: /products/) return false

import { RobotsFile } from 'crawlee';
import { isBlanketBlock } from '../robotsTxtGuard.js';

// Mock RobotsFile for testing
interface MockRobotsFile {
    isAllowed(url: string, userAgent: string): boolean;
}

function createMockRobotsFile(robotsTxtContent: string): MockRobotsFile {
    const disallowRules: { userAgent: string; paths: string[] }[] = [];
    const lines = robotsTxtContent.split('\n');
    let currentUserAgent = '*';

    for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('User-agent:')) {
            currentUserAgent = trimmed.replace('User-agent:', '').trim();
        } else if (trimmed.startsWith('Disallow:')) {
            const path = trimmed.replace('Disallow:', '').trim();
            const existing = disallowRules.find(r => r.userAgent === currentUserAgent);
            if (existing) {
                existing.paths.push(path);
            } else {
                disallowRules.push({ userAgent: currentUserAgent, paths: [path] });
            }
        }
    }

    return {
        isAllowed(url: string, userAgent: string): boolean {
            const rule = disallowRules.find(r => r.userAgent === userAgent || r.userAgent === '*');
            if (!rule) return true;

            const urlObj = new URL(url);
            const path = urlObj.pathname;

            for (const disallowPath of rule.paths) {
                if (disallowPath === '*' || disallowPath === '/') {
                    return false;
                }
                if (path.startsWith(disallowPath)) {
                    return false;
                }
            }
            return true;
        },
    };
}

function testBlanketBlockDetection() {
    let passed = 0;
    let failed = 0;

    // Test 1: Disallow: * blocks all paths
    try {
        const robots = createMockRobotsFile('User-agent: *\nDisallow: *');
        const result = isBlanketBlock(robots as any, 'https://example.com');
        if (result === true) {
            console.log('✓ Disallow: * returns true');
            passed++;
        } else {
            console.error('✗ Disallow: * should return true, got false');
            failed++;
        }
    } catch (e) {
        console.error(`✗ Disallow: * test failed with error: ${e}`);
        failed++;
    }

    // Test 2: Disallow: / blocks all paths
    try {
        const robots = createMockRobotsFile('User-agent: *\nDisallow: /');
        const result = isBlanketBlock(robots as any, 'https://example.com');
        if (result === true) {
            console.log('✓ Disallow: / returns true');
            passed++;
        } else {
            console.error('✗ Disallow: / should return true, got false');
            failed++;
        }
    } catch (e) {
        console.error(`✗ Disallow: / test failed with error: ${e}`);
        failed++;
    }

    // Test 3: Selective block /products/ returns false
    try {
        const robots = createMockRobotsFile('User-agent: *\nDisallow: /products/');
        const result = isBlanketBlock(robots as any, 'https://example.com');
        if (result === false) {
            console.log('✓ Disallow: /products/ returns false');
            passed++;
        } else {
            console.error('✗ Disallow: /products/ should return false, got true');
            failed++;
        }
    } catch (e) {
        console.error(`✗ Disallow: /products/ test failed with error: ${e}`);
        failed++;
    }

    // Test 4: Selective block /admin/ returns false
    try {
        const robots = createMockRobotsFile('User-agent: *\nDisallow: /admin/');
        const result = isBlanketBlock(robots as any, 'https://example.com');
        if (result === false) {
            console.log('✓ Disallow: /admin/ returns false');
            passed++;
        } else {
            console.error('✗ Disallow: /admin/ should return false, got true');
            failed++;
        }
    } catch (e) {
        console.error(`✗ Disallow: /admin/ test failed with error: ${e}`);
        failed++;
    }

    // Test 5: Multiple selective blocks return false
    try {
        const robots = createMockRobotsFile('User-agent: *\nDisallow: /products/\nDisallow: /admin/\nDisallow: /private/');
        const result = isBlanketBlock(robots as any, 'https://example.com');
        if (result === false) {
            console.log('✓ Multiple selective blocks return false');
            passed++;
        } else {
            console.error('✗ Multiple selective blocks should return false, got true');
            failed++;
        }
    } catch (e) {
        console.error(`✗ Multiple selective blocks test failed with error: ${e}`);
        failed++;
    }

    // Test 6: Empty robots.txt returns false
    try {
        const robots = createMockRobotsFile('');
        const result = isBlanketBlock(robots as any, 'https://example.com');
        if (result === false) {
            console.log('✓ Empty robots.txt returns false');
            passed++;
        } else {
            console.error('✗ Empty robots.txt should return false, got true');
            failed++;
        }
    } catch (e) {
        console.error(`✗ Empty robots.txt test failed with error: ${e}`);
        failed++;
    }

    // Test 7: No disallow rules returns false
    try {
        const robots = createMockRobotsFile('User-agent: *\n');
        const result = isBlanketBlock(robots as any, 'https://example.com');
        if (result === false) {
            console.log('✓ No disallow rules returns false');
            passed++;
        } else {
            console.error('✗ No disallow rules should return false, got true');
            failed++;
        }
    } catch (e) {
        console.error(`✗ No disallow rules test failed with error: ${e}`);
        failed++;
    }

    // Test 8: URL with path and query extracts origin correctly
    try {
        const robots = createMockRobotsFile('User-agent: *\nDisallow: /');
        const result = isBlanketBlock(robots as any, 'https://example.com/some/path?query=value');
        if (result === true) {
            console.log('✓ URL with path/query returns true');
            passed++;
        } else {
            console.error('✗ URL with path/query should return true, got false');
            failed++;
        }
    } catch (e) {
        console.error(`✗ URL with path/query test failed with error: ${e}`);
        failed++;
    }

    // Test 9: URL with port number handles correctly
    try {
        const robots = createMockRobotsFile('User-agent: *\nDisallow: /');
        const result = isBlanketBlock(robots as any, 'https://example.com:8443/');
        if (result === true) {
            console.log('✓ URL with port returns true');
            passed++;
        } else {
            console.error('✗ URL with port should return true, got false');
            failed++;
        }
    } catch (e) {
        console.error(`✗ URL with port test failed with error: ${e}`);
        failed++;
    }

    // Test 10: User agent specificity - uses default user agent
    try {
        const robots = createMockRobotsFile('User-agent: BadBot\nDisallow: /\nUser-agent: *\nDisallow: /public/');
        const result = isBlanketBlock(robots as any, 'https://example.com');
        if (result === false) {
            console.log('✓ User agent specificity correctly uses default user agent');
            passed++;
        } else {
            console.error('✗ User agent specificity should return false, got true');
            failed++;
        }
    } catch (e) {
        console.error(`✗ User agent specificity test failed with error: ${e}`);
        failed++;
    }

    console.log(`\nisBlanketBlock: ${passed} passed, ${failed} failed`);
    if (failed > 0) process.exit(1);
}

testBlanketBlockDetection();
