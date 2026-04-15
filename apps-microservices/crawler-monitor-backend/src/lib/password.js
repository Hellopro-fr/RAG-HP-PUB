/**
 * Password hashing & verification using built-in Node crypto (scrypt).
 *
 * Hash format: "scrypt$<N>$<r>$<p>$<saltHex>$<derivedHex>"
 *   N=16384, r=8, p=1 → ~64 MiB RAM, ~80ms on a modern CPU
 *
 * Why scrypt: built-in (no npm dep), modern KDF, designed against ASIC/GPU.
 *
 * Helper to generate a hash from CLI:
 *   node -e "import('./src/lib/password.js').then(m => m.hashPassword('mypass').then(console.log))"
 */

import { scrypt, randomBytes, timingSafeEqual } from 'crypto';
import { promisify } from 'util';

const scryptAsync = promisify(scrypt);

const N = 16384;
const r = 8;
const p = 1;
const KEY_LEN = 64;
const SALT_LEN = 16;
const PREFIX = 'scrypt';

export async function hashPassword(plain) {
  if (typeof plain !== 'string' || plain.length === 0) {
    throw new Error('Password must be a non-empty string');
  }
  const salt = randomBytes(SALT_LEN);
  const derived = await scryptAsync(plain, salt, KEY_LEN, { N, r, p });
  return `${PREFIX}$${N}$${r}$${p}$${salt.toString('hex')}$${derived.toString('hex')}`;
}

export async function verifyPassword(plain, hash) {
  if (typeof plain !== 'string' || typeof hash !== 'string') return false;
  const parts = hash.split('$');
  if (parts.length !== 6 || parts[0] !== PREFIX) return false;
  const [, nStr, rStr, pStr, saltHex, derivedHex] = parts;
  const Np = Number(nStr); const rp = Number(rStr); const pp = Number(pStr);
  if (!Number.isFinite(Np) || !Number.isFinite(rp) || !Number.isFinite(pp)) return false;
  let salt, expected;
  try {
    salt = Buffer.from(saltHex, 'hex');
    expected = Buffer.from(derivedHex, 'hex');
  } catch { return false; }
  if (expected.length === 0) return false;
  let candidate;
  try {
    candidate = await scryptAsync(plain, salt, expected.length, { N: Np, r: rp, p: pp });
  } catch {
    return false;
  }
  if (candidate.length !== expected.length) return false;
  return timingSafeEqual(candidate, expected);
}

/** Returns true if `s` looks like our hash format (cheap shape check, no crypto). */
export function looksLikeScryptHash(s) {
  return typeof s === 'string' && s.startsWith(PREFIX + '$') && s.split('$').length === 6;
}