import { test } from 'node:test';
import assert from 'node:assert/strict';
import { shouldSkipAsDownload } from '../httpStatusPolicy.js';

/**
 * Models the failedRequestHandler branch ordering (functions.ts): a download
 * error increments filtered_pdf + writes the pdf dataset and returns BEFORE the
 * errors counter / error-{domain} dataset path. Mirrors the routes.pushedSet.test
 * pattern (functions.ts is not importable by the test runner).
 */
function simulateFailedRequest(errorStr: string, skipDownloads: boolean, isExisting: boolean) {
    const counters = { filtered_pdf: 0, errors: 0 };
    const datasets = { pdf: [] as string[], error: [] as string[] };
    if (shouldSkipAsDownload(skipDownloads, errorStr)) {
        counters.filtered_pdf++;
        datasets.pdf.push('row');
        return { counters, datasets }; // early return — no error accounting
    }
    if (isExisting) counters.errors++;
    datasets.error.push('row');
    return { counters, datasets };
}

test('download error → filtered_pdf + pdf dataset, no errors, no error dataset', () => {
    const r = simulateFailedRequest('page.goto: Download is starting', true, true);
    assert.equal(r.counters.filtered_pdf, 1);
    assert.equal(r.counters.errors, 0);
    assert.deepEqual(r.datasets.pdf, ['row']);
    assert.deepEqual(r.datasets.error, []);
});

test('SKIP_DOWNLOADS=false → download error falls through to error path', () => {
    const r = simulateFailedRequest('Download is starting', false, true);
    assert.equal(r.counters.filtered_pdf, 0);
    assert.equal(r.counters.errors, 1);
    assert.deepEqual(r.datasets.error, ['row']);
});

test('non-download error → normal error path', () => {
    const r = simulateFailedRequest('Navigation timed out', true, true);
    assert.equal(r.counters.filtered_pdf, 0);
    assert.equal(r.counters.errors, 1);
});
