import fs from "fs";

export interface QueueCounts {
    pending: number;
    handled: number;
    total: number;
}

export interface RepairResult {
    repaired: boolean;
    before: QueueCounts | null; // null when __metadata__.json was missing
    after: QueueCounts;
}

/**
 * Recount a memory-storage request-queue directory from the request files on disk.
 * Mirrors what @crawlee/memory-storage counts into requests.size: parseable *.json
 * request files only (excludes __metadata__.json, dotfiles, non-json). A finite
 * numeric orderNo => pending; anything else (null/undefined/non-finite) => handled.
 * Classifying a malformed orderNo as handled is deliberate: it prevents an
 * undispatchable-but-unhandled file from re-deadlocking isFinished(). Pure read;
 * a missing/unreadable directory => zeros.
 */
export const recountQueueFromDisk = (queueDir: string): QueueCounts => {
    let pending = 0;
    let handled = 0;
    let files: string[];
    try {
        files = fs.readdirSync(queueDir);
    } catch {
        return { pending: 0, handled: 0, total: 0 };
    }
    for (const file of files) {
        if (!file.endsWith(".json") || file === "__metadata__.json" || file.startsWith(".")) continue;
        try {
            const req = JSON.parse(fs.readFileSync(`${queueDir}/${file}`, "utf-8"));
            if (typeof req.orderNo === "number" && Number.isFinite(req.orderNo)) pending++;
            else handled++;
        } catch {
            // Unparseable file — memory-storage ignores it too (not in requests.size).
        }
    }
    return { pending, handled, total: pending + handled };
};

/**
 * Repair a request-queue's __metadata__.json when its counts disagree with the
 * ground-truth recount of the request files. memory-storage loads pending/handled
 * counts from the debounced __metadata__.json but totalRequestCount from the request
 * files; an interrupted / lost-flush prior run leaves them inconsistent, which
 * deadlocks Crawlee's isFinished() (it believes there is unhandled work it can never
 * dispatch) => 1200s progress stall. We rewrite the counts to match the files.
 *
 * Compares the per-state split (not just the sum): a sum-correct but split-wrong
 * metadata also deadlocks. No-op when counts already match (healthy queue) or the
 * queue is empty. Preserves other metadata fields; constructs a minimal valid file
 * when metadata is missing.
 */
export const repairQueueMetadata = (queueDir: string): RepairResult => {
    const counts = recountQueueFromDisk(queueDir);
    const metaPath = `${queueDir}/__metadata__.json`;

    let meta: any = null;
    try {
        meta = JSON.parse(fs.readFileSync(metaPath, "utf-8"));
    } catch {
        meta = null;
    }

    const before: QueueCounts | null = meta
        ? { pending: meta.pendingRequestCount ?? 0, handled: meta.handledRequestCount ?? 0, total: counts.total }
        : null;

    // Empty/nonexistent queue: nothing to repair (do not create metadata for it).
    if (counts.total === 0) {
        return { repaired: false, before, after: counts };
    }

    const consistent =
        !!meta &&
        meta.pendingRequestCount === counts.pending &&
        meta.handledRequestCount === counts.handled;
    if (consistent) {
        return { repaired: false, before, after: counts };
    }

    const now = new Date().toISOString();
    const name = queueDir.split(/[\\/]/).filter(Boolean).pop() ?? queueDir;
    const fixed = {
        ...(meta ?? {}),
        id: meta?.id ?? name,
        name: meta?.name ?? name,
        createdAt: meta?.createdAt ?? now,
        accessedAt: now,
        modifiedAt: now,
        hadMultipleClients: meta?.hadMultipleClients ?? false,
        pendingRequestCount: counts.pending,
        handledRequestCount: counts.handled,
        totalRequestCount: counts.total,
        stats: meta?.stats ?? {},
        forefrontRequestIds: meta?.forefrontRequestIds ?? [],
        userId: meta?.userId ?? "1",
    };
    fs.writeFileSync(metaPath, JSON.stringify(fixed, null, 2));
    return { repaired: true, before, after: counts };
};
