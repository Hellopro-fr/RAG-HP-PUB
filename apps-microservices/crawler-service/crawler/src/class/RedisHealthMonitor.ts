type ClientName = 'heartbeat' | 'dedup';

export class RedisHealthMonitor {
    private lastSuccessAt: Map<ClientName, number> = new Map();
    private lastErrorAt: Map<ClientName, number> = new Map();
    private errorCounters: Map<ClientName, number> = new Map();
    private pollHandle?: ReturnType<typeof setInterval>;
    private fired = false;

    constructor(
        private readonly lossThresholdMs: number,
        private readonly onLost: (reason: string) => void,
        private readonly clock: () => number = () => Date.now(),
    ) {}

    attach(name: ClientName): void {
        this.lastSuccessAt.set(name, this.clock());
        this.errorCounters.set(name, 0);
    }

    onSuccess(name: ClientName): void {
        this.lastSuccessAt.set(name, this.clock());
        this.errorCounters.set(name, 0);
    }

    onError(name: ClientName, _err: unknown): void {
        this.lastErrorAt.set(name, this.clock());
        this.errorCounters.set(name, (this.errorCounters.get(name) ?? 0) + 1);
    }

    start(): void {
        this.pollHandle = setInterval(() => this.evaluate(), 5000);
    }

    stop(): void {
        if (this.pollHandle) {
            clearInterval(this.pollHandle);
            this.pollHandle = undefined;
        }
    }

    private evaluate(): void {
        if (this.fired) return;
        const now = this.clock();
        const successValues = Array.from(this.lastSuccessAt.values());
        if (successValues.length === 0) return;
        const globalLastSuccess = Math.max(...successValues);
        const sinceSuccess = now - globalLastSuccess;
        const recentErrors = Array.from(this.lastErrorAt.values()).some(t => now - t < 30_000);
        if (sinceSuccess > this.lossThresholdMs && recentErrors) {
            this.fire(`No Redis op succeeded for ${Math.round(sinceSuccess/1000)}s across ${this.lastSuccessAt.size} client(s)`);
            return;
        }
        for (const [name, errCount] of this.errorCounters) {
            if (errCount < 30) continue;
            const lastSuccess = this.lastSuccessAt.get(name) ?? 0;
            if (now - lastSuccess > 60_000) {
                this.fire(`Client '${name}' had ${errCount} consecutive errors, no success for ${Math.round((now - lastSuccess)/1000)}s`);
                return;
            }
        }
    }

    private fire(reason: string): void {
        this.fired = true;
        this.stop();
        try {
            this.onLost(reason);
        } catch (e) {
            // Caller's onLost should not break the monitor; log and swallow.
            console.error('[RedisHealthMonitor] onLost callback threw:', e);
        }
    }

    snapshot() {
        return {
            lastSuccessAt: Object.fromEntries(this.lastSuccessAt),
            lastErrorAt: Object.fromEntries(this.lastErrorAt),
            errorCounters: Object.fromEntries(this.errorCounters),
        };
    }
}
