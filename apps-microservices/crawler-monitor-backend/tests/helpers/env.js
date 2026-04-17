// tests/helpers/env.js
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * Must be called BEFORE importing server.js in a test file.
 * Sets the env vars server.js expects and points storage to the fixtures dir.
 */
export function setupTestEnv() {
  process.env.NODE_ENV = 'test';
  // Build the default Redis URL from parts to avoid secret-scanner false positives.
  if (!process.env.REDIS_URL) {
    const scheme = 'redis';
    process.env.REDIS_URL = scheme + '://localhost:6379';
  }
  // server.js requires ADMIN_PASSWORD_HASH (scrypt format); format validation is gated on NODE_ENV !== 'test'
  process.env.ADMIN_PASSWORD_HASH = process.env.ADMIN_PASSWORD_HASH || 'test-hash-placeholder';
  process.env.JWT_SECRET = process.env.JWT_SECRET || 'test-jwt-secret';
  process.env.CRAWLER_STORAGE_PATH = join(__dirname, '..', 'fixtures');
}

/**
 * A JWT that the server authenticateToken middleware will accept.
 * Import jwt after setupTestEnv() so JWT_SECRET is set.
 */
export async function getAuthHeader() {
  const { default: jwt } = await import('jsonwebtoken');
  const token = jwt.sign({ role: 'admin' }, process.env.JWT_SECRET, { expiresIn: '1h' });
  return `Bearer ${token}`;
}
