import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseMemoryStat } from '../cgroupMemory.js';

test('parseMemoryStat extracts file key from cgroup v2 format', () => {
    const content = [
        'anon 500000000',
        'file 5800000000',
        'kernel_stack 1024',
        'slab 2000000',
        'sock 50000',
        'inactive_file 3400000000',
        'active_file 2400000000',
    ].join('\n') + '\n';
    assert.equal(parseMemoryStat(content).file, 5800000000);
});

test('parseMemoryStat extracts cache key from cgroup v1 format', () => {
    const content = [
        'cache 5800000000',
        'rss 500000000',
        'rss_huge 0',
        'mapped_file 200000',
        'swap 0',
    ].join('\n') + '\n';
    assert.equal(parseMemoryStat(content).file, 5800000000);
});

test('parseMemoryStat returns file: 0 when neither key present', () => {
    const content = [
        'anon 500000000',
        'kernel_stack 1024',
        'slab 2000000',
    ].join('\n') + '\n';
    assert.equal(parseMemoryStat(content).file, 0);
});

test('parseMemoryStat skips malformed lines without throwing', () => {
    const content = [
        '',
        '   ',
        'not_a_keyvalue_line',
        'file abcdef',
        'file 5800000000',
        'kernel_stack 1024',
        '   garbage with spaces',
    ].join('\n') + '\n';
    assert.equal(parseMemoryStat(content).file, 5800000000);
});
