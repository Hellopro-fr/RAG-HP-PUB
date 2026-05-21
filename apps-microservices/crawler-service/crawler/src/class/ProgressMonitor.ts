type ProgressSample = { at: number; finished: number };

export class ProgressMonitor {
    private samples: ProgressSample[] = [];
    private pollHandle?: ReturnType<typeof setInterval>;
    private fired = false;

    constructor(
        private readonly readFinishedCount: () => number,
        private readonly stallThresholdMs: number,
        private readonly onStalled: (reason: string) => void,
        private readonly sampleIntervalMs: number = 30_000,
        private readonly clock: () => number = () => Date.now(),
    ) {}

    start(): void {
        this.pollHandle = setInterval(() => this.tick(), this.sampleIntervalMs);
    }

    stop(): void {
        if (this.pollHandle) {
            clearInterval(this.pollHandle);
            this.pollHandle = undefined;
        }
    }

    private tick(): void {
        if (this.fired) return;
        const finished = this.readFinishedCount();
        const now = this.clock();
        this.samples.push({ at: now, finished });
        const cutoff = now - (this.stallThresholdMs + 60_000);
        this.samples = this.samples.filter(s => s.at >= cutoff);

        const oldest = this.samples[0];
        if (!oldest) return;
        const windowAge = now - oldest.at;
        if (windowAge < this.stallThresholdMs) return;
        if (finished === oldest.finished) {
            this.fired = true;
            this.stop();
            this.onStalled(`No URL progress for ${Math.round(windowAge / 1000)}s (stuck at ${finished} finished)`);
        }
    }
}
