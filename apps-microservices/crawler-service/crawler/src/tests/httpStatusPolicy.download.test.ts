import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
    isDownloadError,
    resolveSkipDownloads,
    shouldSkipAsDownload,
    pdfDatasetName,
} from '../httpStatusPolicy.js';

test('isDownloadError matches the Playwright download trigger', () => {
    assert.equal(isDownloadError('page.goto: Download is starting'), true);
    assert.equal(isDownloadError('Error: Download is starting\nCall log: ...'), true);
});

test('isDownloadError rejects unrelated errors', () => {
    assert.equal(isDownloadError('Navigation timed out after 90000ms'), false);
    assert.equal(isDownloadError('net::ERR_NAME_NOT_RESOLVED'), false);
    assert.equal(isDownloadError(''), false);
});

test('resolveSkipDownloads defaults true; only "false" disables', () => {
    assert.equal(resolveSkipDownloads(undefined), true);
    assert.equal(resolveSkipDownloads(''), true);
    assert.equal(resolveSkipDownloads('true'), true);
    assert.equal(resolveSkipDownloads('false'), false);
    assert.equal(resolveSkipDownloads('FALSE'), false);
    assert.equal(resolveSkipDownloads(' false '), false);
});

test('shouldSkipAsDownload requires both the flag and a download error', () => {
    assert.equal(shouldSkipAsDownload(true, 'Download is starting'), true);
    assert.equal(shouldSkipAsDownload(false, 'Download is starting'), false);
    assert.equal(shouldSkipAsDownload(true, 'Navigation timed out'), false);
});

test('pdfDatasetName prefers crawleeStorageName, falls back to domain', () => {
    assert.equal(pdfDatasetName('store-1', 'caravi.com'), 'pdf-store-1');
    assert.equal(pdfDatasetName(undefined, 'caravi.com'), 'pdf-caravi.com');
    assert.equal(pdfDatasetName('', 'caravi.com'), 'pdf-caravi.com');
});
