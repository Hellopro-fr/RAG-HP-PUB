import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
    resolveMaxConcurrency,
    resolveRequestHandlerTimeoutSecs,
    resolveBackpressureMaxPending,
    shouldAcceptNewPage,
    isPageClosedError,
} from '../httpStatusPolicy.js';

test('resolveMaxConcurrency defaults to 20 on missing/invalid/non-positive', () => {
    assert.equal(resolveMaxConcurrency(undefined), 20);
    assert.equal(resolveMaxConcurrency(''), 20);
    assert.equal(resolveMaxConcurrency('abc'), 20);
    assert.equal(resolveMaxConcurrency('0'), 20);
    assert.equal(resolveMaxConcurrency('-5'), 20);
    assert.equal(resolveMaxConcurrency('Infinity'), 20);
});

test('resolveMaxConcurrency parses a positive int (floored)', () => {
    assert.equal(resolveMaxConcurrency('1'), 1);
    assert.equal(resolveMaxConcurrency('8'), 8);
    assert.equal(resolveMaxConcurrency('25'), 25);
    assert.equal(resolveMaxConcurrency('8.9'), 8);
});

test('resolveRequestHandlerTimeoutSecs defaults to 200 on missing/invalid/non-positive', () => {
    assert.equal(resolveRequestHandlerTimeoutSecs(undefined), 200);
    assert.equal(resolveRequestHandlerTimeoutSecs(''), 200);
    assert.equal(resolveRequestHandlerTimeoutSecs('abc'), 200);
    assert.equal(resolveRequestHandlerTimeoutSecs('0'), 200);
    assert.equal(resolveRequestHandlerTimeoutSecs('-1'), 200);
    assert.equal(resolveRequestHandlerTimeoutSecs('Infinity'), 200);
});

test('resolveRequestHandlerTimeoutSecs parses a positive int (floored)', () => {
    assert.equal(resolveRequestHandlerTimeoutSecs('120'), 120);
    assert.equal(resolveRequestHandlerTimeoutSecs('200'), 200);
    assert.equal(resolveRequestHandlerTimeoutSecs('300.5'), 300);
});

test('resolveBackpressureMaxPending defaults to 5; 0 valid; negative/invalid/Infinity → 5', () => {
    assert.equal(resolveBackpressureMaxPending(undefined), 5);
    assert.equal(resolveBackpressureMaxPending(''), 5);
    assert.equal(resolveBackpressureMaxPending('abc'), 5);
    assert.equal(resolveBackpressureMaxPending('-1'), 5);
    assert.equal(resolveBackpressureMaxPending('Infinity'), 5);
    assert.equal(resolveBackpressureMaxPending('0'), 0);
    assert.equal(resolveBackpressureMaxPending('5'), 5);
    assert.equal(resolveBackpressureMaxPending('10'), 10);
    assert.equal(resolveBackpressureMaxPending('5.9'), 5);
});

test('shouldAcceptNewPage accepts at/below threshold, rejects above', () => {
    assert.equal(shouldAcceptNewPage(0, 5), true);
    assert.equal(shouldAcceptNewPage(5, 5), true);
    assert.equal(shouldAcceptNewPage(6, 5), false);
    assert.equal(shouldAcceptNewPage(0, 0), true);
    assert.equal(shouldAcceptNewPage(1, 0), false);
});

test('isPageClosedError matches the teardown class, rejects others', () => {
    assert.equal(isPageClosedError('page.$$eval: Target page, context or browser has been closed'), true);
    assert.equal(isPageClosedError('Navigation timed out after 90000ms'), false);
    assert.equal(isPageClosedError(''), false);
});
