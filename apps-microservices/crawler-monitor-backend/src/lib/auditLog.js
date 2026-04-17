/**
 * Audit log infrastructure — append-only JSON-lines, rotated daily by date.
 *
 * Usage:
 *   import { auditMiddleware, logAuditEntry, readAuditEntries, rotateOldLogs } from './lib/auditLog.js';
 *
 *   // 1. Wrap a sensitive endpoint
 *   app.post('/api/jobs/:id/drop', authenticateToken,
 *     auditMiddleware('drop_queue', { captureParams: ['id'] }),
 *     handler);
 *
 *   // 2. Read entries
 *   const { items, total } = await readAuditEntries({ from, to, action, user, limit });
 *
 *   // 3. Periodic rotation (call at boot + setInterval)
 *   await rotateOldLogs(90);
 *
 * ENV:
 *   AUDIT_LOG_DIR        path of audit logs directory (default ./logs/audit/)
 *   AUDIT_RETENTION_DAYS keep N days of logs (default 90)
 */

import { mkdir, appendFile, readdir, readFile, unlink } from 'fs/promises';
import { join } from 'path';

const AUDIT_LOG_DIR = process.env.AUDIT_LOG_DIR || './logs/audit/';
const AUDIT_RETENTION_DAYS = parseInt(process.env.AUDIT_RETENTION_DAYS || '90', 10);
const FILE_PREFIX = 'audit-';
const FILE_SUFFIX = '.log';
// regex matches `audit-YYYY-MM-DD.log`
const FILE_RE = /^audit-(\d{4}-\d{2}-\d{2})\.log$/;

let dirEnsured = false;

async function ensureDir(dir) {
  if (dirEnsured) return;
  await mkdir(dir, { recursive: true });
  dirEnsured = true;
}

function todayUtcDateStr() {
  return new Date().toISOString().slice(0, 10); // YYYY-MM-DD
}

function fileForDate(dateStr, dir = AUDIT_LOG_DIR) {
  return join(dir, `${FILE_PREFIX}${dateStr}${FILE_SUFFIX}`);
}

/**
 * Append a single audit entry. Tolerant: never throws, only logs to console.error.
 */
export async function logAuditEntry({
  user = 'unknown',
  action,
  target = null,
  metadata = null,
  status = 'ok',
  ip = null,
} = {}) {
  if (!action) {
    console.error('[audit] logAuditEntry called without action');
    return;
  }
  const entry = {
    ts: new Date().toISOString(),
    user,
    action,
    target,
    status,
    ip,
    metadata,
  };
  try {
    const dir = AUDIT_LOG_DIR;
    await ensureDir(dir);
    await appendFile(fileForDate(todayUtcDateStr(), dir), JSON.stringify(entry) + '\n', 'utf8');
  } catch (err) {
    console.error('[audit] failed to write entry:', err.message);
  }
}

/**
 * Express middleware factory. Logs after response is sent.
 *
 * @param {string} actionName - audit action key, e.g. 'drop_queue'
 * @param {object} [options]
 * @param {string[]} [options.captureParams] - req.params keys to include in metadata
 * @param {string[]} [options.captureQuery]  - req.query keys to include in metadata
 * @param {string[]} [options.captureBody]   - req.body keys to include in metadata
 * @param {(req,res)=>string} [options.targetFn] - custom target extractor (overrides default)
 */
export function auditMiddleware(actionName, options = {}) {
  const { captureParams, captureQuery, captureBody, targetFn } = options;

  return (req, res, next) => {
    res.on('finish', () => {
      const metadata = {};
      if (captureParams && req.params) {
        for (const k of captureParams) if (req.params[k] !== undefined) metadata[k] = req.params[k];
      }
      if (captureQuery && req.query) {
        for (const k of captureQuery) if (req.query[k] !== undefined) metadata[k] = req.query[k];
      }
      if (captureBody && req.body) {
        for (const k of captureBody) if (req.body[k] !== undefined) metadata[k] = req.body[k];
      }
      let target = null;
      if (targetFn) {
        try { target = targetFn(req, res); } catch { /* swallow */ }
      } else if (req.params && req.params.id) {
        target = req.params.id;
      }
      // Fire-and-forget — don't block response cycle
      logAuditEntry({
        user: (req.user && (req.user.username || req.user.role)) || 'anonymous',
        action: actionName,
        target,
        metadata: Object.keys(metadata).length ? metadata : null,
        status: res.statusCode < 400 ? 'ok' : 'error',
        ip: req.ip || null,
      });
    });
    next();
  };
}

/**
 * Delete log files older than `retentionDays`. Idempotent.
 */
export async function rotateOldLogs(retentionDays = AUDIT_RETENTION_DAYS) {
  const dir = AUDIT_LOG_DIR;
  let entries;
  try {
    entries = await readdir(dir);
  } catch (err) {
    if (err.code === 'ENOENT') return { deleted: 0 };
    throw err;
  }
  const cutoff = Date.now() - retentionDays * 24 * 60 * 60 * 1000;
  let deleted = 0;
  for (const name of entries) {
    const m = name.match(FILE_RE);
    if (!m) continue;
    const fileTs = Date.parse(m[1] + 'T00:00:00Z');
    if (Number.isFinite(fileTs) && fileTs < cutoff) {
      try {
        await unlink(join(dir, name));
        deleted++;
      } catch (err) {
        console.error(`[audit] failed to delete ${name}:`, err.message);
      }
    }
  }
  return { deleted };
}

/**
 * Read entries with optional filters. Caps at 30-day window to avoid OOM.
 *
 * @param {object} [opts]
 * @param {string|Date} [opts.from] - inclusive lower bound
 * @param {string|Date} [opts.to]   - inclusive upper bound
 * @param {string}      [opts.action]
 * @param {string}      [opts.user]
 * @param {number}      [opts.limit=100]  max 500
 * @param {number}      [opts.offset=0]
 */
export async function readAuditEntries({
  from,
  to,
  action,
  user,
  target,
  limit = 100,
  offset = 0,
} = {}) {
  const dir = AUDIT_LOG_DIR;
  const fromDate = from ? new Date(from) : new Date(Date.now() - 24 * 60 * 60 * 1000); // default last 24h
  const toDate = to ? new Date(to) : new Date();

  if (!(fromDate instanceof Date) || isNaN(fromDate)) throw new Error('Invalid `from` date');
  if (!(toDate instanceof Date) || isNaN(toDate)) throw new Error('Invalid `to` date');
  if (toDate < fromDate) throw new Error('`to` must be >= `from`');

  // Hard cap: 30-day window
  const MAX_WINDOW_MS = 30 * 24 * 60 * 60 * 1000;
  if (toDate - fromDate > MAX_WINDOW_MS) {
    throw new Error('Window too wide (max 30 days)');
  }

  const cappedLimit = Math.min(Math.max(parseInt(limit, 10) || 100, 1), 500);
  const cappedOffset = Math.max(parseInt(offset, 10) || 0, 0);

  // Build list of dates to read (UTC days from `from` to `to`, inclusive)
  const dates = [];
  const cursor = new Date(Date.UTC(fromDate.getUTCFullYear(), fromDate.getUTCMonth(), fromDate.getUTCDate()));
  const endDay = new Date(Date.UTC(toDate.getUTCFullYear(), toDate.getUTCMonth(), toDate.getUTCDate()));
  while (cursor <= endDay) {
    dates.push(cursor.toISOString().slice(0, 10));
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }

  const matches = [];
  for (const d of dates) {
    let raw;
    try {
      raw = await readFile(fileForDate(d, dir), 'utf8');
    } catch (err) {
      if (err.code === 'ENOENT') continue;
      throw err;
    }
    for (const line of raw.split('\n')) {
      if (!line) continue;
      let entry;
      try { entry = JSON.parse(line); } catch { continue; }
      const ts = Date.parse(entry.ts);
      if (!Number.isFinite(ts)) continue;
      if (ts < fromDate.getTime() || ts > toDate.getTime()) continue;
      if (action && entry.action !== action) continue;
      if (user && entry.user !== user) continue;
      if (target && entry.target !== target) continue;
      matches.push(entry);
    }
  }

  // Newest first
  matches.sort((a, b) => Date.parse(b.ts) - Date.parse(a.ts));
  const items = matches.slice(cappedOffset, cappedOffset + cappedLimit);
  return { items, total: matches.length, limit: cappedLimit, offset: cappedOffset };
}