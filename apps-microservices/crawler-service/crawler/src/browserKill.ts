// Browser-engine kill pattern + helper (Spec-A 2026-05-21).
// Used by main.ts pre-flight check and Tier 2 Phase A recovery to kill orphan
// browser children before measuring cgroup memory.
//
// Matches against /proc/*/cmdline via pkill -f. Covers:
//   - chrome / chromium / headless_shell: Playwright Chromium variants
//   - firefox: standard Playwright Firefox AND Camoufox bundled binary
//   - camoufox: cache directory path component (defensive)
//   - playwright: internal helper processes (e.g., playwright-driver)
//
// Per-container kill — Docker default PID namespace prevents cross-replica reach.

import { exec } from 'node:child_process';
import { promisify } from 'node:util';

const execAsync = promisify(exec);

export const BROWSER_KILL_PATTERN =
    "chrome|chromium|firefox|camoufox|playwright|headless_shell";

export async function killBrowserProcesses(timeoutMs = 5000): Promise<void> {
    try {
        await execAsync(
            `pkill -9 -f "${BROWSER_KILL_PATTERN}" 2>/dev/null || true`,
            // killSignal aligns with `pkill -9` semantics: if exec's own timeout fires,
            // send SIGKILL rather than Node's default SIGTERM, keeping the suppression
            // list (ETIMEDOUT, SIGKILL) correct.
            { timeout: timeoutMs, killSignal: 'SIGKILL' },
        );
        // Engine list derived from the constant so it never drifts.
        const engines = BROWSER_KILL_PATTERN.replace(/\|/g, "/");
        console.log(`✅ Orphan browser processes cleaned (engines: ${engines}).`);
    } catch (e: any) {
        if (e.code !== 'ETIMEDOUT' && e.signal !== 'SIGKILL') {
            console.warn('⚠️  killBrowserProcesses warning:', e.message);
        }
    }
}
