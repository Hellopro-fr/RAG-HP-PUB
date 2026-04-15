import { test } from 'node:test';
import assert from 'node:assert/strict';
import { hashPassword, verifyPassword, looksLikeScryptHash } from '../src/lib/password.js';

test('hashPassword produces a scrypt$ formatted hash', async () => {
  const h = await hashPassword('correct horse battery staple');
  assert.ok(looksLikeScryptHash(h));
  // 6 parts: prefix, N, r, p, salt, derived
  assert.equal(h.split('$').length, 6);
});

test('verifyPassword returns true on the right password', async () => {
  const h = await hashPassword('hunter2');
  assert.equal(await verifyPassword('hunter2', h), true);
});

test('verifyPassword returns false on the wrong password', async () => {
  const h = await hashPassword('hunter2');
  assert.equal(await verifyPassword('hunter3', h), false);
});

test('hashPassword produces different hashes for the same input (random salt)', async () => {
  const a = await hashPassword('same');
  const b = await hashPassword('same');
  assert.notEqual(a, b);
  assert.equal(await verifyPassword('same', a), true);
  assert.equal(await verifyPassword('same', b), true);
});

test('verifyPassword rejects malformed hashes', async () => {
  assert.equal(await verifyPassword('x', ''), false);
  assert.equal(await verifyPassword('x', 'not-a-hash'), false);
  assert.equal(await verifyPassword('x', 'scrypt$bad'), false);
  assert.equal(await verifyPassword('x', 'bcrypt$1$2$3$4$5'), false);
});

test('hashPassword rejects empty / non-string input', async () => {
  await assert.rejects(() => hashPassword(''), /non-empty/);
  await assert.rejects(() => hashPassword(null), /non-empty/);
});

test('looksLikeScryptHash quick shape check', () => {
  assert.equal(looksLikeScryptHash('scrypt$1$2$3$4$5'), true);
  assert.equal(looksLikeScryptHash('scrypt$1$2$3$4'), false);
  assert.equal(looksLikeScryptHash('plain'), false);
  assert.equal(looksLikeScryptHash(''), false);
  assert.equal(looksLikeScryptHash(null), false);
});