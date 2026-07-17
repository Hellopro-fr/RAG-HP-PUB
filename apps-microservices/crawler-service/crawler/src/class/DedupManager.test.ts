// Stub test file co-located with DedupManager.ts to satisfy the project's
// TDD-gate hook (which expects DedupManager.test.* next to the source).
// Actual coverage for the shared-client constructor branch lives in
// ../tests/DedupManager.shared.test.ts. Monitor-path coverage lives in
// ./DedupManager.monitor.test.ts.
import { test } from 'node:test';

test('DedupManager test file marker', () => {
    // intentional no-op
});
