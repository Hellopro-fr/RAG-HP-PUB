import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
    resolveMaxConcurrency,
    resolveRequestHandlerTimeoutSecs,
} from '../httpStatusPolicy.js';

test('resolveMaxConcurrency defaults to 10 on missing/invalid/non-positive', () => {
    assert.equal(resolveMaxConcurrency(undefined), 10);
    assert.equal(resolveMaxConcurrency(''), 10);
    assert.equal(resolveMaxConcurrency('abc'), 10);
    assert.equal(resolveMaxConcurrency('0'), 10);
    assert.equal(resolveMaxConcurrency('-5'), 10);
    assert.equal(resolveMaxConcurrency('Infinity'), 10);
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
