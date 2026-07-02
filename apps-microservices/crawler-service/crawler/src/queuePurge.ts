/**
 * Queue-purge (D1): before RequestQueue.open, flag already-queued stale variants
 * with skipNavigation so they are dropped without a fetch at dispatch (handler
 * early-guard). Disk-only + loss-proof: the "known base" anchor is the set of
 * already-handled files on disk. Never touches orderNo/uniqueKey/id, so pending/
 * handled/total counts stay consistent (repairQueueMetadata runs after). Strip is
 * injected so this module stays crawlee-free (loadable under tsx --test).
 *
 * ANCHOR NOTE: "handled" on disk means Crawlee finished the request — success OR
 * retries-exhausted. So a variant whose collapsed base FAILED terminally last run
 * is still flagged skipNavigation here (skipped this run), unlike the mid-run A /
 * C2 paths which anchor on the Redis success-set. Deliberate: the committed
 * decision declared these variants the same page, a failed base implies the
 * variant fails too, and the next scheduled crawl retries. Kept disk-only for
 * self-containment (no Redis dependency at startup).
 */
import * as fs from "node:fs";
import * as path from "node:path";

const isPending = (orderNo: unknown): boolean =>
    typeof orderNo === "number" && Number.isFinite(orderNo);

export const flagStaleVariantsOnDisk = (
    queueDir: string,
    stripFn: (url: string) => string,
): { flagged: number; kept: number } => {
    let flagged = 0;
    let kept = 0;
    let names: string[];
    try {
        names = fs.readdirSync(queueDir);
    } catch {
        return { flagged, kept };
    }

    type Rec = { file: string; obj: any };
    const pending: Rec[] = [];
    const canonical = new Set<string>();

    for (const name of names) {
        if (!name.endsWith(".json") || name === "__metadata__.json" || name.startsWith(".")) continue;
        const file = path.join(queueDir, name);
        let obj: any;
        try {
            obj = JSON.parse(fs.readFileSync(file, "utf-8"));
        } catch {
            continue; // memory-storage ignores unparseable files too
        }
        if (isPending(obj.orderNo)) {
            pending.push({ file, obj });
        } else {
            try { canonical.add(stripFn(obj.url)); } catch { /* skip */ }
        }
    }

    for (const { file, obj } of pending) {
        let stripped: string;
        try { stripped = stripFn(obj.url); } catch { kept++; continue; }
        if (stripped !== obj.url && canonical.has(stripped)) {
            obj.userData = obj.userData ?? {};
            obj.userData.__crawlee = obj.userData.__crawlee ?? {};
            obj.userData.__crawlee.skipNavigation = true;
            try {
                const inner = JSON.parse(obj.json);
                inner.userData = inner.userData ?? {};
                inner.userData.__crawlee = inner.userData.__crawlee ?? {};
                inner.userData.__crawlee.skipNavigation = true;
                obj.json = JSON.stringify(inner);
            } catch { /* inner missing/malformed: root flag still applies */ }
            fs.writeFileSync(file, JSON.stringify(obj, null, 2));
            flagged++;
        } else {
            canonical.add(stripped);
            kept++;
        }
    }
    return { flagged, kept };
};
