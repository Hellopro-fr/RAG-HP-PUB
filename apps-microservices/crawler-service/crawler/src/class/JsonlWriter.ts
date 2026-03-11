import fs from 'fs';
import path from 'path';

/**
 * JsonlWriter — Anti-OOM streaming JSONL writer.
 * 
 * Uses Node.js WriteStreams with backpressure support to write
 * one JSON object per line without accumulating data in memory.
 * Each filename maps to a separate stream.
 */
export class JsonlWriter {
    private streams: Map<string, fs.WriteStream> = new Map();
    private counts: Map<string, number> = new Map();
    private basePath: string;

    constructor(basePath: string) {
        this.basePath = basePath;
        // Ensure the base directory exists
        if (!fs.existsSync(basePath)) {
            fs.mkdirSync(basePath, { recursive: true });
        }
    }

    /**
     * Write a single JSON line to the specified file.
     * Creates the stream lazily on first write.
     * Handles backpressure via drain events.
     */
    async writeLine(filename: string, data: object): Promise<void> {
        let stream = this.streams.get(filename);

        if (!stream) {
            const filePath = path.join(this.basePath, filename);
            stream = fs.createWriteStream(filePath, { flags: 'a', encoding: 'utf-8' });
            this.streams.set(filename, stream);
            this.counts.set(filename, 0);
        }

        const line = JSON.stringify(data) + '\n';
        const canWrite = stream.write(line);

        // Handle backpressure: wait for drain if buffer is full
        if (!canWrite) {
            await new Promise<void>((resolve) => stream!.once('drain', resolve));
        }

        this.counts.set(filename, (this.counts.get(filename) || 0) + 1);
    }

    /**
     * Get the line count for a specific file.
     */
    getCount(filename: string): number {
        return this.counts.get(filename) || 0;
    }

    /**
     * Get all counts as a summary object.
     */
    getAllCounts(): Record<string, number> {
        const result: Record<string, number> = {};
        for (const [filename, count] of this.counts) {
            result[filename] = count;
        }
        return result;
    }

    /**
     * Close all open streams. Call during graceful shutdown.
     */
    async closeAll(): Promise<void> {
        const promises: Promise<void>[] = [];

        for (const [filename, stream] of this.streams) {
            promises.push(
                new Promise<void>((resolve, reject) => {
                    stream.end(() => {
                        console.log(`[JsonlWriter] Closed ${filename} (${this.counts.get(filename) || 0} lines)`);
                        resolve();
                    });
                    stream.on('error', reject);
                })
            );
        }

        await Promise.all(promises);
        this.streams.clear();
        console.log(`[JsonlWriter] All streams closed.`);
    }
}
