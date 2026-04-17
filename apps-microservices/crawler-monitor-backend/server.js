import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import { createClient } from 'redis';
import { WebSocketServer } from 'ws';
import { createServer } from 'http';
import { readFile, readdir, writeFile, unlink, stat, mkdir, rm } from 'fs/promises';
import { join, normalize } from 'path';
import { existsSync } from 'fs';
import helmet from 'helmet';
import rateLimit from 'express-rate-limit';

import jwt from 'jsonwebtoken';
import { auditMiddleware, readAuditEntries, rotateOldLogs, logAuditEntry } from './src/lib/auditLog.js';
import { replayCallback } from './src/lib/callbacks.js';
import {
  parseWindow as parseCapacityWindow,
  snapshotCapacity,
  readCapacityHistory,
  SNAPSHOT_INTERVAL_MS,
} from './src/lib/capacityHistory.js';
import { parseStatsWindow, computeSystemStats } from './src/lib/systemStats.js';
import { verifyPassword, looksLikeScryptHash } from './src/lib/password.js';
import {
  parseReplicaWindow,
  persistHeartbeat,
  readReplicaHistory,
  readAllReplicasHistory,
} from './src/lib/replicaHistory.js';
import { persistJobPerf, readJobPerf } from './src/lib/jobPerformance.js';
import { computeTimeline } from './src/lib/timeline.js';
import { parseDomainWindow, aggregateDomains, jobsForDomain } from './src/lib/domains.js';
import { evaluateAlerts, DEFAULT_THRESHOLDS } from './src/lib/alerts.js';

const PORT = process.env.PORT || 3001;
const REDIS_URL = process.env.REDIS_URL;
const CRAWLER_STORAGE_PATH = process.env.CRAWLER_STORAGE_PATH || '/app/storage';
const ADMIN_PASSWORD_HASH = process.env.ADMIN_PASSWORD_HASH;
const JWT_SECRET = process.env.JWT_SECRET;
const CORS_ALLOWED_ORIGINS = process.env.CORS_ALLOWED_ORIGINS; // comma-separated, optional

const CRAWL_UPDATES_CHANNEL = 'crawl_updates';
const CRAWL_JOB_PREFIX = 'crawl_job:';
const CRAWL_RUNNING_COUNT_KEY = 'crawl_jobs:running_count';
const CRAWL_MAX_GLOBAL_KEY = 'crawl_jobs:max_global_crawls';
const FAILED_CALLBACKS_KEY = 'crawl_jobs:failed_callbacks';

const missingVars = [];
if (!REDIS_URL) missingVars.push('REDIS_URL');
if (!ADMIN_PASSWORD_HASH) missingVars.push('ADMIN_PASSWORD_HASH');
if (!JWT_SECRET) missingVars.push('JWT_SECRET');

if (missingVars.length > 0) {
  console.error(`FATAL ERROR: Missing required environment variables: ${missingVars.join(', ')}`);
  if (missingVars.includes('ADMIN_PASSWORD_HASH')) {
    console.error('');
    console.error('Generate a hash with:');
    console.error('  node -e "import(\'./src/lib/password.js\').then(m => m.hashPassword(process.argv[1]).then(console.log))" YOUR_PASSWORD');
    console.error('');
    console.error('NOTE: legacy ADMIN_PASSWORD (plain text) is no longer accepted — set ADMIN_PASSWORD_HASH instead.');
  }
  if (process.env.NODE_ENV !== 'test') process.exit(1);
}

if (ADMIN_PASSWORD_HASH && !looksLikeScryptHash(ADMIN_PASSWORD_HASH)) {
  console.error('FATAL ERROR: ADMIN_PASSWORD_HASH does not look like a scrypt$ hash.');
  console.error('It must be generated with src/lib/password.js hashPassword().');
  if (process.env.NODE_ENV !== 'test') process.exit(1);
}

if (process.env.ADMIN_PASSWORD) {
  console.warn('WARN: legacy ADMIN_PASSWORD env var detected — it is ignored. Remove it from your env.');
}

// --- Persistent Redis Client ---
const redisClient = createClient({ url: REDIS_URL });
redisClient.on('error', err => console.error('Redis Client Error:', err));

async function ensureRedisConnected() {
  if (!redisClient.isOpen) {
    await redisClient.connect();
  }
  return redisClient;
}

const app = express();
const server = createServer(app);
const wss = new WebSocketServer({ server });

// Trust the first reverse proxy (nginx in front of us). Required so that
// req.ip / req.ips / X-Forwarded-For are interpreted correctly by
// express-rate-limit and the audit log. Configurable via TRUST_PROXY env var
// (number of proxy hops; default 1 for our nginx -> backend setup).
const TRUST_PROXY_HOPS = parseInt(process.env.TRUST_PROXY || '1', 10);
app.set('trust proxy', Number.isFinite(TRUST_PROXY_HOPS) ? TRUST_PROXY_HOPS : 1);

// Security Middleware
app.use(helmet());

// Global rate limit. Tuned for a live dashboard (React Query background
// refetch every 30s on multiple endpoints + WebSocket-driven invalidations
// can easily reach ~30 req/min/user). The previous 100 req/15min was too low
// and caused 429s after a few minutes of normal use.
//
// /api/login is explicitly skipped at the user's request (internal tool,
// shared NAT egress IP). Audit log still records every login attempt.
//
// Configurable via env: RATE_LIMIT_MAX (default 600), RATE_LIMIT_WINDOW_MS
// (default 900000 = 15 min).
const RATE_LIMIT_MAX = parseInt(process.env.RATE_LIMIT_MAX || '600', 10);
const RATE_LIMIT_WINDOW_MS = parseInt(process.env.RATE_LIMIT_WINDOW_MS || '900000', 10);
const limiter = rateLimit({
  windowMs: RATE_LIMIT_WINDOW_MS,
  max: RATE_LIMIT_MAX,
  standardHeaders: true,
  legacyHeaders: false,
  skip: (req) => req.path === '/api/login',
});
app.use(limiter);

// CORS: allowlist if CORS_ALLOWED_ORIGINS is set, else permissive with a warning.
// Same-origin requests (no Origin header) and tools like curl/postman are always allowed.
if (CORS_ALLOWED_ORIGINS) {
  const allowed = CORS_ALLOWED_ORIGINS.split(',').map(s => s.trim()).filter(Boolean);
  console.log(`[cors] allowlist active (${allowed.length} origins)`);
  app.use(cors({
    origin: (origin, cb) => {
      if (!origin) return cb(null, true); // server-to-server / curl
      if (allowed.includes(origin)) return cb(null, true);
      cb(new Error(`CORS: origin ${origin} not allowed`));
    },
    credentials: true,
  }));
} else {
  console.warn('WARN: CORS_ALLOWED_ORIGINS not set — allowing all origins. Set it for production.');
  app.use(cors());
}
app.use(express.json({ limit: '50mb' })); // Support large JSON payloads for request_urls

// Authentication Middleware
const authenticateToken = (req, res, next) => {
  const authHeader = req.headers['authorization'];
  const token = authHeader && authHeader.split(' ')[1];

  if (!token) return res.sendStatus(401);

  jwt.verify(token, JWT_SECRET, (err, user) => {
    if (err) return res.sendStatus(403);
    req.user = user;
    next();
  });
};

// Login Endpoint — verifies password against scrypt hash in ADMIN_PASSWORD_HASH.
// (No per-endpoint IP rate-limit: removed at user request because the dashboard
// is internal and shared NAT IPs were causing self-DoS. The global limiter
// above still applies in addition to the audit log of every attempt.)
app.post('/api/login', async (req, res) => {
  const { password } = req.body || {};
  if (typeof password !== 'string' || password.length === 0) {
    await logAuditEntry({ user: 'anonymous', action: 'login_attempt', status: 'error', ip: req.ip, metadata: { reason: 'missing_password' } });
    return res.status(400).json({ error: 'Password required' });
  }
  let ok = false;
  try {
    ok = await verifyPassword(password, ADMIN_PASSWORD_HASH);
  } catch (err) {
    console.error('Login verification error:', err);
  }
  if (ok) {
    const token = jwt.sign({ role: 'admin' }, JWT_SECRET, { expiresIn: '24h' });
    await logAuditEntry({ user: 'admin', action: 'login_success', status: 'ok', ip: req.ip });
    res.json({ token });
  } else {
    await logAuditEntry({ user: 'anonymous', action: 'login_failure', status: 'error', ip: req.ip });
    res.status(401).json({ error: 'Invalid password' });
  }
});

// Protect API routes
app.use('/api/jobs', authenticateToken);

const clients = new Set();
wss.on('connection', (ws, req) => {
  // Parse token from query string
  const url = new URL(req.url, `http://${req.headers.host}`);
  const token = url.searchParams.get('token');

  if (!token) {
    ws.close(1008, 'Authentication required');
    return;
  }

  jwt.verify(token, JWT_SECRET, (err, user) => {
    if (err) {
      ws.close(1008, 'Invalid token');
      return;
    }

    // Authentication successful
    clients.add(ws);
    ws.on('close', () => clients.delete(ws));
  });
});

function parseLogFile(content) {
  try {
    // Optimisation: Ne garder que le dernier run
    const startMarker = '[stdout] Changed working directory to:';
    const lastStartIndex = content.lastIndexOf(startMarker);

    if (lastStartIndex !== -1) {
      console.log(`Found multiple runs, keeping only the last one (starting at index ${lastStartIndex})`);
      content = content.substring(lastStartIndex);
    } else {
      console.log('Single run detected or marker not found');
    }

    // 1. Extraire les stats JSON
    const statsMatch = content.match(/{\s*"CrawlingStats"[\s\S]*?}\s*}/);
    let stats = null;
    if (statsMatch) {
      try {
        const parsedStats = JSON.parse(statsMatch[0]);
        stats = parsedStats.CrawlingStats;
        console.log('Stats parsed successfully:', stats);
      } catch (e) {
        console.error('Failed to parse stats JSON:', e);
      }
    } else {
      console.log('No stats found in log file');
    }

    // 2. Extraire les erreurs
    const errors = [];
    const errorRegex = /\[stderr\]\s*ERROR[^\n]*:\s*([^\n]+)/g;
    let match;
    while ((match = errorRegex.exec(content)) !== null) {
      errors.push(match[1].trim());
    }

    // 3. Extraire les warnings
    const warnings = [];
    const warnRegex = /\[stderr\]\s*WARN[^\n]*:\s*([^\n]+)/g;
    while ((match = warnRegex.exec(content)) !== null) {
      warnings.push(match[1].trim());
    }

    console.log(`Parsed log: ${stats ? 'stats found' : 'no stats'}, ${errors.length} errors, ${warnings.length} warnings`);

    return {
      stats,
      errors,
      warnings,
      rawContent: content,
      hasStats: !!stats
    };
  } catch (error) {
    console.error('Error parsing log:', error);
    return {
      stats: null,
      errors: [`Error parsing log: ${error.message}`],
      warnings: [],
      rawContent: content,
      hasStats: false
    };
  }
}

function broadcast(data) {
  const message = JSON.stringify(data);
  clients.forEach(client => {
    if (client.readyState === 1) client.send(message);
  });
}

app.get('/api/jobs', async (req, res) => {
  try {
    const client = await ensureRedisConnected();
    const jobKeys = await client.keys(`${CRAWL_JOB_PREFIX}*`);
    if (jobKeys.length === 0) return res.json([]);

    const jobsData = await client.mGet(jobKeys);
    const jobs = jobsData
      .map(str => {
        if (!str) return null;
        try { return JSON.parse(str); } catch { return null; }
      })
      .filter(Boolean)
      // Skip malformed entries without a crawl_id — they would surface as
      // id: undefined on the front and trigger /api/jobs/undefined/details 404s.
      .filter(job => job && typeof job.crawl_id === 'string' && job.crawl_id.length > 0)
      .map(job => ({
        ...job,
        id: job.crawl_id,
        lastModified: job.start_time
      }));

    jobs.sort((a, b) => new Date(b.start_time) - new Date(a.start_time));
    res.json(jobs);
  } catch (error) {
    console.error('Error fetching initial jobs from Redis:', error);
    res.status(500).json({ error: 'Failed to fetch jobs' });
  }
});

// Per-job CPU/RAM performance history (from heartbeats). Retained 24h.
app.get('/api/jobs/:id/performance', async (req, res) => {
  try {
    const client = await ensureRedisConnected();
    const result = await readJobPerf(client, req.params.id);
    res.json({ job_id: req.params.id, ...result });
  } catch (error) {
    console.error('Error fetching job performance:', error);
    res.status(500).json({ error: error.message || 'Failed to fetch performance' });
  }
});

// Replay endpoint: aggregates everything needed for the scrubber/player UI.
// Returns perf points + job metadata + derived event markers + audit actions.
// High-CPU threshold (fraction 0..1) for marking "hot" zones, default 0.85.
const REPLAY_HIGH_CPU = parseFloat(process.env.REPLAY_HIGH_CPU || '0.85');
app.get('/api/jobs/:id/replay', async (req, res) => {
  try {
    const jobId = req.params.id;
    const client = await ensureRedisConnected();

    // 1. Fetch performance points + summary
    const perf = await readJobPerf(client, jobId);

    // 2. Fetch job metadata from Redis
    let jobInfo = null;
    try {
      const raw = await client.get(`${CRAWL_JOB_PREFIX}${jobId}`);
      if (raw) {
        const parsed = JSON.parse(raw);
        jobInfo = {
          id: parsed.crawl_id || jobId,
          domain: parsed.domain,
          status: parsed.status,
          start_time: parsed.start_time,
          crawl_mode: parsed.crawl_mode,
          oom_restart_count: parsed.oom_restart_count || 0,
          previous_crawl_id: parsed.previous_crawl_id,
        };
      }
    } catch { /* swallow */ }

    // 3. Build event markers from the points
    const events = [];

    if (perf.summary) {
      if (perf.summary.peak_cpu_at) {
        events.push({
          ts: perf.summary.peak_cpu_at,
          kind: 'peak_cpu',
          label: `Peak CPU ${(perf.summary.peak_cpu * 100).toFixed(1)}%`,
          severity: perf.summary.peak_cpu > REPLAY_HIGH_CPU ? 'warn' : 'info',
        });
      }
      if (perf.summary.peak_ram_at) {
        events.push({
          ts: perf.summary.peak_ram_at,
          kind: 'peak_ram',
          label: `Peak RAM ${(perf.summary.peak_ram / 1024 / 1024).toFixed(0)} MB`,
          severity: 'info',
        });
      }
    }

    // 4. High-CPU zones: contiguous segments where cpu > threshold
    const hotZones = [];
    if (perf.points && perf.points.length > 1) {
      let zoneStart = null;
      let zoneMaxCpu = 0;
      for (const p of perf.points) {
        if ((p.cpu || 0) > REPLAY_HIGH_CPU) {
          if (zoneStart === null) zoneStart = p.ts;
          if ((p.cpu || 0) > zoneMaxCpu) zoneMaxCpu = p.cpu;
        } else if (zoneStart !== null) {
          hotZones.push({ from: zoneStart, to: p.ts, max_cpu: zoneMaxCpu });
          zoneStart = null;
          zoneMaxCpu = 0;
        }
      }
      // Close any open zone at the end of the series
      if (zoneStart !== null) {
        hotZones.push({
          from: zoneStart,
          to: perf.points[perf.points.length - 1].ts,
          max_cpu: zoneMaxCpu,
        });
      }
      for (const z of hotZones) {
        events.push({
          ts: z.from,
          kind: 'hot_cpu_zone',
          label: `CPU > ${(REPLAY_HIGH_CPU * 100).toFixed(0)}% pendant ${Math.max(1, Math.round((z.to - z.from) / 1000))}s (max ${(z.max_cpu * 100).toFixed(0)}%)`,
          severity: 'warn',
          duration_ms: z.to - z.from,
        });
      }
    }

    // 5. OOM events (approximate — we only know the final count)
    if (jobInfo && jobInfo.oom_restart_count > 0 && perf.points && perf.points.length > 0) {
      events.push({
        ts: perf.points[0].ts, // anchor at job start (imprecise but safe)
        kind: 'oom_summary',
        label: `${jobInfo.oom_restart_count} OOM restart${jobInfo.oom_restart_count > 1 ? 's' : ''} pendant le crawl`,
        severity: 'critical',
      });
    }

    // 6. Audit actions targeting this job (drop, dedupe, clean, repair, queue_file_edit)
    try {
      const windowMs = 7 * 24 * 60 * 60 * 1000;
      const from = perf.points && perf.points.length
        ? new Date(perf.points[0].ts - 60_000).toISOString()
        : new Date(Date.now() - windowMs).toISOString();
      const to = new Date().toISOString();
      const audit = await readAuditEntries({ from, to, target: jobId, limit: 200 });
      for (const e of audit.items || []) {
        events.push({
          ts: Date.parse(e.ts),
          kind: 'audit',
          label: `${e.action} par ${e.user}${e.status === 'error' ? ' (échec)' : ''}`,
          severity: e.status === 'error' ? 'warn' : 'info',
          action: e.action,
          user: e.user,
        });
      }
    } catch (err) {
      // Audit is best-effort; missing = no annotations
      console.warn('[replay] audit lookup failed:', err.message);
    }

    // Sort events chronologically
    events.sort((a, b) => (a.ts || 0) - (b.ts || 0));

    res.json({
      job_id: jobId,
      job: jobInfo,
      points: perf.points,
      summary: perf.summary,
      events,
      hot_zones: hotZones,
      generated_at: new Date().toISOString(),
    });
  } catch (error) {
    console.error('Error building replay:', error);
    res.status(500).json({ error: error.message || 'Failed to build replay' });
  }
});

app.get('/api/jobs/:id/details', async (req, res) => {
  const { id } = req.params;
  try {
    const client = await ensureRedisConnected();

    // 1. Récupérer les infos de base du job depuis Redis
    const jobDataString = await client.get(`${CRAWL_JOB_PREFIX}${id}`);
    if (!jobDataString) {
      console.log(`Job ${id} not found in Redis`);
      return res.status(404).json({ error: 'Job not found in Redis' });
    }
    const jobData = JSON.parse(jobDataString);
    console.log(`Job ${id} found in Redis with status: ${jobData.status}`);

    // 2. Construire le chemin vers le fichier de log
    const logPath = join(CRAWLER_STORAGE_PATH, id, 'crawler.log');
    console.log(`Looking for log file at: ${logPath}`);

    // 3. Lire et analyser le fichier de log
    let parsedData = { stats: null, errors: [], warnings: [], rawContent: '', hasStats: false };
    try {
      const content = await readFile(logPath, 'utf-8');
      console.log(`Log file read successfully, size: ${content.length} bytes`);
      parsedData = parseLogFile(content);
    } catch (fileError) {
      if (fileError.code === 'ENOENT') {
        console.log(`Log file not found for job ${id}, returning job data without log`);
      } else {
        throw fileError;
      }
    }

    // 4. Fusionner les données de Redis et du log
    const fullDetails = {
      ...jobData,
      id: jobData.crawl_id,
      ...parsedData
    };

    res.json(fullDetails);

  } catch (error) {
    console.error(`Error fetching details for job ${id}:`, error);
    res.status(500).json({
      error: 'Failed to fetch job details',
      message: error.message
    });
  }
});

// Helper to find the request_queues directory
async function findRequestQueuesDir(jobId) {
  // Check possible paths
  const paths = [
    join(CRAWLER_STORAGE_PATH, jobId, 'storage', 'request_queues'),
    join(CRAWLER_STORAGE_PATH, jobId, 'request_queues')
  ];

  for (const p of paths) {
    if (existsSync(p)) return p;
  }
  return null;
}

// --- Pattern Matching ---

const ignoredExtensions = [
  "7z", "7zip", "bz2", "rar", "tar", "tar.gz", "xz", "zip",
  "mng", "pct", "bmp", "gif", "jpg", "jpeg", "png", "pst", "psp", "tif", "tiff", "ai", "drw", "dxf", "eps", "ps", "svg", "cdr", "ico", "webp",
  "mp3", "wma", "ogg", "wav", "ra", "aac", "mid", "au", "aiff",
  "3gp", "asf", "asx", "avi", "mov", "mp4", "mpg", "qt", "rm", "swf", "wmv", "m4a", "m4v", "flv", "webm",
  "xls", "xlsx", "ppt", "pptx", "pps", "doc", "docx", "odt", "ods", "odg", "odp",
  "css", "pdf", "exe", "bin", "rss", "dmg", "iso", "apk", "xml"
].join("|");

const excludePatterns = [
  `**/*.@(${ignoredExtensions}){,\?*}{,\#*}`,
  // === SPIDER TRAPS E-COMMERCE ===
  '**/*order=*', '**/*sort=*', '**/*dir=*', '**/*limit=*',
  '**/*resultsPerPage=*', '**/*filter=*', '**/*filters[*',
  '**/*price=*', '**/*price_min=*', '**/*price_max=*',
  '**/*id_category=*', '**/*categoryId=*', '**/*productListView=*',
  '**/*q=*', '**/*search=*', '**/*query=*',
  '**/*page=*/**/*page=*', '**/*offset=*', '**/*start=*',
  '**/*view=*', '**/*mode=*', '**/*display=*', '**/*per_page=*', '**/*items=*',
  // === AUTH & ACCOUNT ===
  '**/connexion**', '**/login**', '**/signin**', '**/log-in**',
  '**/register**', '**/signup**', '**/inscription**',
  '**/account**', '**/mon-compte**', '**/my-account**',
  '**/profile**', '**/profil**',
  '**/password**', '**/mot-de-passe**', '**/reset-password**',
  '**/logout**', '**/deconnexion**',
  '**/forgot-password**', '**/oubli-mot-de-passe**',
  '**/customer/account/**', '**/customer/**',
  // === SHOPPING ===
  '**/panier**', '**/cart**', '**/basket**',
  '**/checkout**', '**/commande**', '**/order**',
  '**/add-to-cart**', '**/addtocart**',
  '**/payment**', '**/paiement**',
  '**/shipping**', '**/livraison**',
  '**/confirmation**',
  '**/quotation/**', '**/devis/**',
  // === USER ACTIONS ===
  '**/wishlist**', '**/liste-envies**', '**/favoris**',
  '**/compare**', '**/comparateur**',
  '**/sendtoafriend**', '**/send-to-friend**',
  // === CALENDAR ===
  '**/*year=*', '**/*month=*', '**/*day=*',
  '**/*date=*', '**/*from=*', '**/*to=*',
  '**/calendrier/**', '**/calendar/**',
  // === SOCIAL ===
  '**/*facebook*', '**/*twitter*', '**/*linkedin*',
  '**/*instagram*', '**/*youtube*', '**/*pinterest*',
  '**/*tiktok*', '**/*whatsapp*',
  '**/*share*', '**/*partager*',
  '**/mailto:*', '**/tel:*', '**/*://t.me/*',
  // === TRACKING ===
  '**/*redirect*', '**/*track*', '**/*click*',
  '**/*ref=*', '**/*referrer=*', '**/*source=*',
  // === API ===
  '**/api/**', '**/wp-json/**', '**/rest/**',
  '**/feed/**', '**/feeds/**', '**/rss/**',
  '**/PBCPPlayer.asp**', '**/popup/**',
  // === SPECIFIC SITE EXCLUDES (promodis.fr) ===
  '**/download.php*', '**/dhtml/download.php*',
  '**/*imp=1*',
  // === SHOPIFY TRAPS ===
  '**/collections/all*', '**/collections/vendors*', '**/collections/types*'
];

// Unified matchesPattern function
const matchesPattern = (url, pattern) => {
  // Handle extension pattern specifically
  if (pattern.includes('@(')) {
    const extRegex = new RegExp(`\\.(${ignoredExtensions})([?#].*)?$`, 'i');
    return extRegex.test(url);
  }

  // Remove leading/trailing globstars to get the "core" pattern
  let clean = pattern.replace(/^\*\*\//, '').replace(/\*\*$/, '').replace(/^\*\*/, '');

  // If it's a query param pattern (contains =), simple include is usually enough
  if (clean.includes('=')) {
    return url.toLowerCase().includes(clean.replace(/\*/g, '').toLowerCase());
  }

  // Check if it has internal wildcards (e.g. *facebook*)
  if (clean.includes('*')) {
    // It's a glob-like pattern. Escape special chars, then replace * with .*
    const escaped = clean.replace(/[.+^${}()|[\]\\]/g, '\\$&');
    const regexStr = escaped.replace(/\*/g, '.*');
    return new RegExp(regexStr, 'i').test(url);
  } else {
    // It's a segment pattern (e.g. cart, login)
    // Match whole segment to avoid "cartouche" matching "cart"
    const escaped = clean.replace(/[.+^${}()|[\]\\]/g, '\\$&');
    const segmentRegex = new RegExp(`(^|[/?#&=.])${escaped}([/?#&=.]|$)`, 'i');
    return segmentRegex.test(url);
  }
};

// --- API Routes ---

app.get('/api/jobs/:id/request-queues', async (req, res) => {
  const { id } = req.params;
  const page = Math.max(1, parseInt(req.query.page) || 1);
  const limit = Math.min(200, Math.max(1, parseInt(req.query.limit) || 50));
  const search = (req.query.search || '').toLowerCase();
  const status = ['all', 'pending', 'handled'].includes(req.query.status) ? req.query.status : 'all';

  try {
    const baseDir = await findRequestQueuesDir(id);
    if (!baseDir) {
      return res.json({
        items: [], total: 0, page, limit, totalPages: 0,
        counts: { total: 0, pending: 0, handled: 0 },
      });
    }

    // Single pass over every file. Produces both the unfiltered counts AND the filtered page.
    const allFiles = [];
    const entries = await readdir(baseDir, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      const domainDir = join(baseDir, entry.name);
      const domainFiles = await readdir(domainDir);
      for (const file of domainFiles) {
        if (!file.endsWith('.json')) continue;
        const filePath = join(domainDir, file);
        try {
          const content = await readFile(filePath, 'utf-8');
          const data = JSON.parse(content);
          allFiles.push({
            name: file,
            domain: entry.name,
            path: join(entry.name, file),
            url: data.url,
            method: data.method,
            retryCount: data.retryCount,
            errorMessages: data.errorMessages,
            // Crawlee v3 marks a request as handled by setting orderNo to null (pending
            // requests have a positive number used for FIFO ordering). handledAt IS set
            // too, but it lives inside the nested `json` string field, not at the top
            // level — so checking data.handledAt is always undefined here.
            isHandled: data.orderNo === null,
            rawContent: content, // for search (matches legacy behavior)
          });
        } catch {
          // Unreadable / malformed — still counted in total but shown as "Error reading file"
          allFiles.push({
            name: file,
            domain: entry.name,
            path: join(entry.name, file),
            url: 'Error reading file',
            method: 'UNKNOWN',
            isHandled: false,
            rawContent: '',
          });
        }
      }
    }

    // Unfiltered counts — drives the UI counts bar.
    const counts = {
      total: allFiles.length,
      pending: allFiles.filter(f => !f.isHandled).length,
      handled: allFiles.filter(f => f.isHandled).length,
    };

    // Apply search + status filters for the page set.
    let matching = allFiles;
    if (search) matching = matching.filter(f => f.rawContent.toLowerCase().includes(search));
    if (status === 'pending') matching = matching.filter(f => !f.isHandled);
    else if (status === 'handled') matching = matching.filter(f => f.isHandled);

    const total = matching.length;
    const totalPages = Math.ceil(total / limit);
    const startIdx = (page - 1) * limit;
    const pageItems = matching.slice(startIdx, startIdx + limit).map(f => ({
      name: f.name,
      domain: f.domain,
      path: f.path,
      url: f.url,
      method: f.method,
      retryCount: f.retryCount,
      errorMessages: f.errorMessages,
      isHandled: f.isHandled,  // NEW — used by the frontend row status glyph
    }));

    res.json({ items: pageItems, total, page, limit, totalPages, counts });
  } catch (error) {
    console.error(`Error listing request queues for job ${id}:`, error);
    res.status(500).json({ error: 'Failed to list request queues' });
  }
});

app.get('/api/jobs/:id/request-queues/:domain/:filename', async (req, res) => {
  const { id, domain, filename } = req.params;
  try {
    const baseDir = await findRequestQueuesDir(id);
    if (!baseDir) {
      return res.status(404).json({ error: 'Request queues directory not found' });
    }

    const filePath = normalize(join(baseDir, domain, filename));

    // Security check: prevent directory traversal
    if (!filePath.startsWith(baseDir)) {
      return res.status(403).json({ error: 'Access denied' });
    }

    if (!existsSync(filePath)) {
      return res.status(404).json({ error: 'File not found' });
    }

    const content = await readFile(filePath, 'utf-8');
    res.json(JSON.parse(content));
  } catch (error) {
    console.error(`Error reading request queue file ${filename}:`, error);
    res.status(500).json({ error: 'Failed to read file' });
  }
});

app.post('/api/jobs/:id/request-queues/:domain/:filename',
  auditMiddleware('queue_file_edit', { captureParams: ['id', 'domain', 'filename'] }),
  async (req, res) => {
  const { id, domain, filename } = req.params;
  const content = req.body;

  try {
    const baseDir = await findRequestQueuesDir(id);
    if (!baseDir) {
      return res.status(404).json({ error: 'Request queues directory not found' });
    }

    const filePath = normalize(join(baseDir, domain, filename));

    // Security check
    if (!filePath.startsWith(baseDir)) {
      return res.status(403).json({ error: 'Access denied' });
    }

    await writeFile(filePath, JSON.stringify(content, null, 2), 'utf-8');
    res.json({ success: true });
  } catch (error) {
    console.error(`Error saving request queue file ${filename}:`, error);
    res.status(500).json({ error: 'Failed to save file' });
  }
});

app.post('/api/jobs/:id/request-queues/repair',
  auditMiddleware('queue_repair', { captureParams: ['id'] }),
  async (req, res) => {
  const { id } = req.params;
  try {
    const baseDir = await findRequestQueuesDir(id);
    if (!baseDir) {
      return res.status(404).json({ error: 'Request queues directory not found' });
    }

    const entries = await readdir(baseDir, { withFileTypes: true });
    let deletedCount = 0;
    let scannedCount = 0;

    // Iterate over domain directories
    for (const entry of entries) {
      if (entry.isDirectory()) {
        const domainDir = join(baseDir, entry.name);
        const targetDomain = entry.name;
        const domainFiles = await readdir(domainDir);

        for (const file of domainFiles) {
          if (file.endsWith('.json')) {
            scannedCount++;
            try {
              const filePath = join(domainDir, file);
              const content = await readFile(filePath, 'utf-8');
              const data = JSON.parse(content);

              if (data.url) {
                try {
                  const urlObj = new URL(data.url);
                  // Check if hostname includes the target domain (handles subdomains)
                  if (!urlObj.hostname.includes(targetDomain)) {
                    console.log(`[Repair] Deleting invalid URL: ${data.url} (Target: ${targetDomain})`);
                    await unlink(filePath);
                    deletedCount++;
                  }
                } catch (e) {
                  // Invalid URL, skip
                }
              }
            } catch (err) {
              console.error(`Error processing file ${file} for repair:`, err);
            }
          }
        }
      }
    }

    res.json({ scanned: scannedCount, deleted: deletedCount });
  } catch (error) {
    console.error(`Error repairing request queues for job ${id}:`, error);
    res.status(500).json({ error: 'Failed to repair request queues' });
  }

});

// Endpoint to DROP the entire request queue (RESET)
app.post('/api/jobs/:id/request-queues/drop',
  auditMiddleware('queue_drop', { captureParams: ['id'] }),
  async (req, res) => {
  const { id } = req.params;
  try {
    const baseDir = await findRequestQueuesDir(id);
    if (!baseDir) {
      return res.status(404).json({ error: 'Request queues directory not found' });
    }

    console.log(`[Drop] Dropping entire request queue for job ${id}`);

    // Find the domain subdirectory (similar to dataset logic)
    const entries = await readdir(baseDir, { withFileTypes: true });
    const domainDir = entries.find(dirent => dirent.isDirectory());

    if (domainDir) {
      const domainQueuePath = join(baseDir, domainDir.name);
      console.log(`[Drop] Deleting domain queue: ${domainQueuePath}`);

      // Delete the domain-specific queue folder
      await rm(domainQueuePath, { recursive: true, force: true });

      // Recreate empty folder
      await mkdir(domainQueuePath, { recursive: true });

      res.json({ success: true, message: `Queue dropped successfully for ${domainDir.name}` });
    } else {
      // No domain folder found, queue is already empty
      res.json({ success: true, message: "Queue already empty" });
    }
  } catch (error) {
    console.error(`Error dropping request queue for job ${id}:`, error);
    res.status(500).json({ error: 'Failed to drop request queue' });
  }
});

app.get('/api/jobs/:id/request-queues/analyze', async (req, res) => {
  const { id } = req.params;
  try {
    const baseDir = await findRequestQueuesDir(id);
    if (!baseDir) {
      return res.status(404).json({ error: 'Request queues directory not found' });
    }

    const stats = {
      total: 0,
      blocked: 0,      // URLs matching exclude patterns
      valid: 0,        // URLs not matching any pattern
      pending: 0,      // URLs with handledAt === undefined
      handled: 0,      // URLs with handledAt !== undefined
      examples: {
        blocked: [],   // Sample of blocked URLs
        valid: []      // Sample of valid URLs
      }
    };

    const entries = await readdir(baseDir, { withFileTypes: true });

    for (const entry of entries) {
      if (entry.isDirectory()) {
        const domainDir = join(baseDir, entry.name);
        const domainFiles = await readdir(domainDir);

        for (const file of domainFiles) {
          if (file.endsWith('.json')) {
            stats.total++;
            try {
              const filePath = join(domainDir, file);
              const content = await readFile(filePath, 'utf-8');
              const data = JSON.parse(content);

              if (data.url) {
                // Check if URL matches any exclude pattern
                let isBlocked = false;
                let matchedPattern = null;

                for (const pattern of excludePatterns) {
                  if (matchesPattern(data.url, pattern)) {
                    isBlocked = true;
                    matchedPattern = pattern;
                    stats.blocked++;

                    // Store sample (max 5)
                    if (stats.examples.blocked.length < 5) {
                      stats.examples.blocked.push({
                        url: data.url,
                        pattern: matchedPattern
                      });
                    }
                    break;
                  }
                }

                if (!isBlocked) {
                  stats.valid++;

                  // Store sample (max 5)
                  if (stats.examples.valid.length < 5) {
                    stats.examples.valid.push(data.url);
                  }
                }

                // Check if handled — Crawlee v3 sets orderNo to null when a request is
                // marked as handled. handledAt is ALSO set but it lives inside the
                // nested `json` string field, not at the top level, so data.handledAt
                // here is always undefined.
                if (data.orderNo === null) {
                  stats.handled++;
                } else {
                  stats.pending++;
                }
              }
            } catch (err) {
              console.error(`Error analyzing file ${file}:`, err);
            }
          }
        }
      }
    }

    // Calculate percentages
    stats.blockedPercent = stats.total > 0 ? ((stats.blocked / stats.total) * 100).toFixed(1) : 0;
    stats.validPercent = stats.total > 0 ? ((stats.valid / stats.total) * 100).toFixed(1) : 0;

    // Add recommendation
    if (stats.blockedPercent > 90) {
      stats.recommendation = 'Use "Clean Patterns" to remove blocked URLs';
    } else if (stats.valid === 0) {
      stats.recommendation = 'Safe to drop entire queue (no valid URLs)';
    } else {
      stats.recommendation = 'Use "Clean Patterns" to preserve valid URLs';
    }

    res.json(stats);
  } catch (error) {
    console.error(`Error analyzing request queues for job ${id}:`, error);
    res.status(500).json({ error: 'Failed to analyze request queues' });
  }
});

// Helper to find dataset directory
async function findDatasetDir(jobId, datasetName = null) {
  // Structure based on user feedback:
  // CRAWLER_STORAGE_PATH / {jobId} / storage / datasets / {domain}
  // Example: .../4767/storage/datasets/promodis.fr
  // Or for non-French: .../4767/storage/datasets/nfr-promodis.fr

  try {
    const jobDir = join(CRAWLER_STORAGE_PATH, jobId);
    const nestedStorageDatasets = join(jobDir, 'storage', 'datasets');

    // Check if this path exists
    if (existsSync(nestedStorageDatasets)) {
      const entries = await readdir(nestedStorageDatasets, { withFileTypes: true });

      if (datasetName) {
        // Look for specific dataset name
        const targetDir = entries.find(dirent => dirent.isDirectory() && dirent.name === datasetName);
        if (targetDir) {
          return join(nestedStorageDatasets, targetDir.name);
        }
      } else {
        // Find the first directory found inside (which should be the domain)
        const domainDir = entries.find(dirent => dirent.isDirectory());
        if (domainDir) {
          return join(nestedStorageDatasets, domainDir.name);
        }
      }
    }
  } catch (e) {
    console.warn(`Failed to find dataset in new structure for job ${jobId}: ${e.message}`);
  }

  // Fallback to legacy structure if any
  const standardDatasets = join(CRAWLER_STORAGE_PATH, 'datasets');
  if (datasetName) {
    const specificDatasetPath = join(standardDatasets, datasetName);
    if (existsSync(specificDatasetPath)) {
      return specificDatasetPath;
    }
  } else if (existsSync(join(standardDatasets, jobId))) {
    return join(standardDatasets, jobId);
  }

  return null;
}

/**
 * Discover the three dataset subdirectories (main/error/nfr) for a job.
 * Returns { mainDir, errorDir, nfrDir, domain } — any dir may be null if absent.
 * Does NOT require Redis — the domain is recovered from the directory names.
 */
async function listDatasetDirs(jobId) {
  const datasetsRoot = join(CRAWLER_STORAGE_PATH, jobId, 'storage', 'datasets');
  if (!existsSync(datasetsRoot)) {
    return { mainDir: null, errorDir: null, nfrDir: null, domain: null };
  }
  const entries = await readdir(datasetsRoot, { withFileTypes: true });
  let mainName = null, errorName = null, nfrName = null;
  for (const e of entries) {
    if (!e.isDirectory()) continue;
    if (e.name.startsWith('error-')) errorName = e.name;
    else if (e.name.startsWith('nfr-')) nfrName = e.name;
    else if (!mainName) mainName = e.name;
  }
  const domain = mainName || errorName?.slice('error-'.length) || nfrName?.slice('nfr-'.length) || null;
  return {
    mainDir:  mainName  ? join(datasetsRoot, mainName)  : null,
    errorDir: errorName ? join(datasetsRoot, errorName) : null,
    nfrDir:   nfrName   ? join(datasetsRoot, nfrName)   : null,
    domain,
  };
}

/** Count valid JSON files in a directory (malformed files excluded). */
async function countValidJsonFiles(dir) {
  if (!dir || !existsSync(dir)) return 0;
  const files = await readdir(dir);
  let count = 0;
  for (const f of files) {
    if (!f.endsWith('.json')) continue;
    try {
      const content = await readFile(join(dir, f), 'utf-8');
      JSON.parse(content);
      count++;
    } catch {
      // malformed — skip silently, matches existing scanDataset() behavior
    }
  }
  return count;
}

app.get('/api/jobs/:id/dataset/counts', async (req, res) => {
  const { id } = req.params;
  try {
    const { mainDir, errorDir, nfrDir } = await listDatasetDirs(id);
    const [success, error, nfr] = await Promise.all([
      countValidJsonFiles(mainDir),
      countValidJsonFiles(errorDir),
      countValidJsonFiles(nfrDir),
    ]);
    res.json({ success, error, nfr });
  } catch (err) {
    console.error(`Error counting datasets for job ${id}:`, err);
    res.status(500).json({ error: 'Failed to count datasets' });
  }
});

/** Derive a human-readable error string from an error-dataset entry. */
function deriveErrorMessage(entry) {
  if (Array.isArray(entry.errorMessages) && entry.errorMessages.length > 0) {
    return String(entry.errorMessages[0]);
  }
  if (entry.statusCode !== undefined) {
    const text = entry.statusText ? ` ${entry.statusText}` : '';
    return `HTTP ${entry.statusCode}${text}`;
  }
  return 'Unknown error';
}

app.get('/api/jobs/:id/dataset/urls', async (req, res) => {
  const { id } = req.params;
  const category = String(req.query.category || '');
  if (!['success', 'error', 'nfr'].includes(category)) {
    return res.status(400).json({ error: 'Invalid category. Must be one of: success, error, nfr' });
  }
  const page = Math.max(1, parseInt(req.query.page) || 1);
  const limit = Math.min(200, Math.max(1, parseInt(req.query.limit) || 50));
  const search = String(req.query.search || '').toLowerCase();

  try {
    const dirs = await listDatasetDirs(id);
    const dir = category === 'success' ? dirs.mainDir
              : category === 'error'   ? dirs.errorDir
              :                          dirs.nfrDir;

    if (!dir || !existsSync(dir)) {
      return res.json({ category, total: 0, page, totalPages: 0, items: [] });
    }

    const filenames = (await readdir(dir)).filter(n => n.endsWith('.json'));

    // Single pass: read every file, skip malformed, apply optional search, then paginate.
    // Gives an accurate `total` (malformed files excluded) regardless of search.
    const valid = [];
    for (const name of filenames) {
      try {
        const raw = await readFile(join(dir, name), 'utf-8');
        const data = JSON.parse(raw);
        if (!data.url) continue;
        if (search && !data.url.toLowerCase().includes(search)) continue;
        valid.push(category === 'error'
          ? { url: data.url, error: deriveErrorMessage(data) }
          : { url: data.url });
      } catch {
        console.warn(`[dataset/urls] skipped malformed file ${join(dir, name)}`);
      }
    }
    const total = valid.length;
    const totalPages = Math.ceil(total / limit);
    const startIdx = (page - 1) * limit;
    const items = valid.slice(startIdx, startIdx + limit);
    res.json({ category, total, page, totalPages, items });
  } catch (err) {
    console.error(`Error listing dataset URLs for job ${id}:`, err);
    res.status(500).json({ error: 'Failed to list dataset URLs' });
  }
});

app.get('/api/jobs/:id/dataset/analyze', async (req, res) => {
  const { id } = req.params;
  try {
    // Get job data to find domain
    const client = await ensureRedisConnected();
    const jobData = JSON.parse(await client.get(`${CRAWL_JOB_PREFIX}${id}`) || '{}');

    if (!jobData || !jobData.domain) {
      return res.status(404).json({ error: 'Job not found or domain missing' });
    }

    const domain = jobData.domain;

    // Find both datasets
    const mainDatasetDir = await findDatasetDir(id); // Main dataset ({domain})
    const nfrDatasetDir = await findDatasetDir(id, `nfr-${domain}`); // Non-French dataset

    const urlMap = new Map(); // URL -> { count, datasets: ['main'|'nfr'] }
    let totalItems = 0;
    let mainItems = 0;
    let nfrItems = 0;
    let duplicateItems = 0;
    const duplicatesExample = [];

    // Helper function to scan a dataset
    const scanDataset = async (dir, label) => {
      if (!dir || !existsSync(dir)) return 0;

      const files = await readdir(dir);
      let count = 0;

      for (const file of files) {
        if (file.endsWith('.json')) {
          try {
            const content = await readFile(join(dir, file), 'utf-8');
            const data = JSON.parse(content);
            if (data.url) {
              totalItems++;
              count++;

              const existing = urlMap.get(data.url);
              if (existing) {
                existing.count++;
                existing.datasets.push(label);
                duplicateItems++;
                if (duplicatesExample.length < 5 && !duplicatesExample.includes(data.url)) {
                  duplicatesExample.push(data.url);
                }
              } else {
                urlMap.set(data.url, { count: 1, datasets: [label] });
              }
            }
          } catch (e) {/* ignore malformed */ }
        }
      }
      return count;
    };

    // Scan both datasets
    mainItems = await scanDataset(mainDatasetDir, 'main');
    nfrItems = await scanDataset(nfrDatasetDir, 'nfr');

    res.json({
      path: mainDatasetDir || 'N/A',
      nfrPath: nfrDatasetDir || 'N/A',
      totalItems,
      mainItems,
      nfrItems,
      uniqueUrls: urlMap.size,
      duplicateCount: duplicateItems,
      duplicatesExample
    });
  } catch (error) {
    console.error(`Error analyzing dataset for job ${id}:`, error);
    res.status(500).json({ error: 'Failed to analyze dataset' });
  }
});

app.post('/api/jobs/:id/dataset/deduplicate',
  auditMiddleware('dataset_deduplicate', { captureParams: ['id'] }),
  async (req, res) => {
  const { id } = req.params;
  try {
    // Get job data to find domain
    const client = await ensureRedisConnected();
    const jobData = JSON.parse(await client.get(`${CRAWL_JOB_PREFIX}${id}`) || '{}');

    if (!jobData || !jobData.domain) {
      return res.status(404).json({ error: 'Job not found or domain missing' });
    }

    const domain = jobData.domain;

    // Find both datasets
    const mainDatasetDir = await findDatasetDir(id);
    const nfrDatasetDir = await findDatasetDir(id, `nfr-${domain}`);

    let totalRemovedCount = 0;
    let mainRemovedCount = 0;
    let nfrRemovedCount = 0;

    // Helper function to deduplicate a dataset
    const deduplicateDataset = async (dir) => {
      if (!dir || !existsSync(dir)) return 0;

      const files = await readdir(dir);
      const urlFilesMap = new Map(); // URL -> [{file, path, mtime}]

      for (const file of files) {
        if (file.endsWith('.json')) {
          const filePath = join(dir, file);
          try {
            const content = await readFile(filePath, 'utf-8');
            const data = JSON.parse(content);
            if (data.url) {
              const stats = await stat(filePath);
              const entry = { file, path: filePath, mtime: stats.mtimeMs };

              if (!urlFilesMap.has(data.url)) {
                urlFilesMap.set(data.url, []);
              }
              urlFilesMap.get(data.url).push(entry);
            }
          } catch (e) { }
        }
      }

      // Purge duplicates (keep newest)
      let removedCount = 0;
      for (const [url, fileEntries] of urlFilesMap.entries()) {
        if (fileEntries.length > 1) {
          // Sort by mtime descending (newest first)
          fileEntries.sort((a, b) => b.mtime - a.mtime);

          // Keep the first one (newest), remove the rest
          const toRemove = fileEntries.slice(1);
          for (const item of toRemove) {
            await unlink(item.path);
            removedCount++;
          }
        }
      }

      return removedCount;
    };

    // Deduplicate both datasets
    mainRemovedCount = await deduplicateDataset(mainDatasetDir);
    nfrRemovedCount = await deduplicateDataset(nfrDatasetDir);
    totalRemovedCount = mainRemovedCount + nfrRemovedCount;

    res.json({
      removedCount: totalRemovedCount,
      mainRemovedCount,
      nfrRemovedCount
    });

  } catch (error) {
    console.error('Error deduplicating dataset:', error);
    res.status(500).json({ error: 'Deduplication failed' });
  }
});

app.post('/api/jobs/:id/request-queues/clean-patterns',
  auditMiddleware('queue_clean_patterns', { captureParams: ['id'] }),
  async (req, res) => {

  const { id } = req.params;
  try {
    const baseDir = await findRequestQueuesDir(id);
    if (!baseDir) {
      return res.status(404).json({ error: 'Request queues directory not found' });
    }

    // Flatten all files from all domains into a single array for batch processing
    const entries = await readdir(baseDir, { withFileTypes: true });
    let allFiles = [];
    for (const entry of entries) {
      if (entry.isDirectory()) {
        const domainDir = join(baseDir, entry.name);
        const domainFiles = await readdir(domainDir);
        for (const file of domainFiles) {
          if (file.endsWith('.json')) {
            allFiles.push({
              path: join(domainDir, file),
              name: file,
              domain: entry.name
            });
          }
        }
      }
    }

    let scannedCount = 0;
    let deletedCount = 0;
    const BATCH_SIZE = 50; // Process 50 files in parallel

    // Process in batches
    for (let i = 0; i < allFiles.length; i += BATCH_SIZE) {
      const batch = allFiles.slice(i, i + BATCH_SIZE);

      const results = await Promise.all(batch.map(async (fileObj) => {
        try {
          const content = await readFile(fileObj.path, 'utf-8');
          const data = JSON.parse(content);

          if (data.url) {
            for (const pattern of excludePatterns) {
              if (matchesPattern(data.url, pattern)) {
                await unlink(fileObj.path);
                console.log(`[Clean] Deleting pattern match: ${data.url} (Pattern: ${pattern})`);
                return true; // Deleted
              }
            }
          }
          return false; // Not deleted
        } catch (err) {
          console.error(`Error processing file ${fileObj.name} for cleaning:`, err);
          return false;
        }
      }));

      scannedCount += batch.length;
      deletedCount += results.filter(Boolean).length;
    }

    res.json({ scanned: scannedCount, deleted: deletedCount });
  } catch (error) {
    console.error(`Error cleaning request queues for job ${id}:`, error);
    res.status(500).json({ error: 'Failed to clean request queues' });
  }
});

app.get('/api/capacity', authenticateToken, async (req, res) => {
  try {
    const client = await ensureRedisConnected();
    const runningRaw = await client.get(CRAWL_RUNNING_COUNT_KEY);
    const maxRaw = await client.get(CRAWL_MAX_GLOBAL_KEY);

    const running = parseInt(runningRaw, 10) || 0;
    const max = parseInt(maxRaw, 10) || 0;

    res.json({
      running_jobs: running,
      max_global_jobs: max,
      is_full: max > 0 && running >= max
    });
  } catch (error) {
    console.error('Error fetching capacity:', error);
    res.status(500).json({ error: 'Failed to fetch capacity' });
  }
});

// Active alerts evaluated NOW from current state (jobs + capacity + replicas + callbacks).
// Phase 3 thresholds = env vars (see src/lib/alerts.js DEFAULT_THRESHOLDS).
app.get('/api/alerts', authenticateToken, async (req, res) => {
  try {
    const client = await ensureRedisConnected();

    // Gather inputs in parallel
    const [jobs, capacityRaw, callbacksRaw, replicasHistory] = await Promise.all([
      loadAllJobs(client),
      readCapacityHistory(client, 60 * 60 * 1000), // last 1h
      client.lLen(FAILED_CALLBACKS_KEY).catch(() => 0),
      readAllReplicasHistory(client, 60 * 60 * 1000),
    ]);

    // Map replica points to {ts, cpu} only (alerts engine only needs cpu)
    const replicasForAlerts = {};
    for (const [id, points] of Object.entries(replicasHistory)) {
      replicasForAlerts[id] = points.map(p => ({ ts: p.ts, cpu: p.cpu }));
    }

    const alerts = evaluateAlerts({
      jobs,
      capacityPoints: capacityRaw,
      replicasHistory: replicasForAlerts,
      failedCallbackCount: callbacksRaw,
    });

    res.json({
      generated_at: new Date().toISOString(),
      thresholds: DEFAULT_THRESHOLDS,
      count: alerts.length,
      alerts,
    });
  } catch (error) {
    console.error('Error evaluating alerts:', error);
    res.status(500).json({ error: error.message || 'Failed to evaluate alerts' });
  }
});

// Aggregated list of domains over a window (default 7d).
app.get('/api/domains', authenticateToken, async (req, res) => {
  try {
    const windowKey = req.query.window || '7d';
    const windowMs = parseDomainWindow(windowKey);
    const client = await ensureRedisConnected();
    const jobs = await loadAllJobs(client);
    const domains = aggregateDomains(jobs, Date.now(), windowMs);
    res.json({ window: windowKey, count: domains.length, domains });
  } catch (error) {
    console.error('Error fetching domains:', error);
    res.status(400).json({ error: error.message || 'Failed to fetch domains' });
  }
});

// Per-domain detail: jobs in the window + run chain via previous_crawl_id.
app.get('/api/domains/:domain', authenticateToken, async (req, res) => {
  try {
    const windowKey = req.query.window || '7d';
    const windowMs = parseDomainWindow(windowKey);
    const client = await ensureRedisConnected();
    const jobs = await loadAllJobs(client);
    const detail = jobsForDomain(jobs, req.params.domain, windowMs);
    res.json({
      domain: req.params.domain,
      window: windowKey,
      total_jobs: detail.jobs.length,
      jobs: detail.jobs,
      chain: detail.chain,
    });
  } catch (error) {
    console.error('Error fetching domain detail:', error);
    res.status(400).json({ error: error.message || 'Failed to fetch domain detail' });
  }
});

// Stacked timeline of jobs by start_time bucket. Used by Overview to plot
// success/failure/running per minute (or coarser) on a sliding window.
// Accepts either ?window=1h|6h|24h|7d OR ?from=ISO&to=ISO for a custom range.
// Custom range gets auto-granularity (1min–6h depending on span width).
app.get('/api/timeline', authenticateToken, async (req, res) => {
  try {
    const { window: windowKey, from, to } = req.query;
    const client = await ensureRedisConnected();
    const result = await computeTimeline(client, windowKey || '6h', {
      loadJobs: loadAllJobs,
      from: from || undefined,
      to: to || undefined,
    });
    res.json(result);
  } catch (error) {
    console.error('Error computing timeline:', error);
    res.status(400).json({ error: error.message || 'Failed to compute timeline' });
  }
});

// Per-replica CPU/RAM history (single replica or batch for all known)
app.get('/api/replicas/history', authenticateToken, async (req, res) => {
  try {
    const windowStr = req.query.window || '1h';
    const windowMs = parseReplicaWindow(windowStr);
    const client = await ensureRedisConnected();
    const data = await readAllReplicasHistory(client, windowMs);
    res.json({ window: windowStr, replicas: data });
  } catch (error) {
    console.error('Error fetching all replicas history:', error);
    res.status(400).json({ error: error.message || 'Failed to fetch replica history' });
  }
});

app.get('/api/replicas/:replicaId/history', authenticateToken, async (req, res) => {
  try {
    const windowStr = req.query.window || '1h';
    const windowMs = parseReplicaWindow(windowStr);
    const client = await ensureRedisConnected();
    const points = await readReplicaHistory(client, req.params.replicaId, windowMs);
    res.json({ replicaId: req.params.replicaId, window: windowStr, count: points.length, points });
  } catch (error) {
    console.error('Error fetching replica history:', error);
    res.status(400).json({ error: error.message || 'Failed to fetch replica history' });
  }
});

app.get('/api/capacity/history', authenticateToken, async (req, res) => {
  try {
    const windowStr = req.query.window || '1h';
    const windowMs = parseCapacityWindow(windowStr);
    const client = await ensureRedisConnected();
    const points = await readCapacityHistory(client, windowMs);
    res.json({ window: windowStr, count: points.length, points });
  } catch (error) {
    console.error('Error fetching capacity history:', error);
    res.status(400).json({ error: error.message || 'Failed to fetch capacity history' });
  }
});

app.get('/api/callbacks', authenticateToken, async (req, res) => {
  try {
    const client = await ensureRedisConnected();
    const callbacks = await client.lRange(FAILED_CALLBACKS_KEY, 0, -1);
    const parsed = callbacks.map(c => {
      try { return JSON.parse(c); }
      catch { return { raw: c }; }
    });
    res.json({ count: parsed.length, items: parsed });
  } catch (error) {
    console.error('Error fetching pending callbacks:', error);
    res.status(500).json({ error: 'Failed to fetch callbacks' });
  }
});

// Replay a single failed callback by index (HTTP GET to its url + params).
// On success, LREM the entry. On failure, increment manual_retry_attempts.
app.post('/api/callbacks/:index/retry', authenticateToken,
  auditMiddleware('callback_retry', { captureParams: ['index'] }),
  async (req, res) => {
    const index = parseInt(req.params.index, 10);
    if (!Number.isInteger(index) || index < 0) {
      return res.status(400).json({ error: 'Invalid index' });
    }
    try {
      const client = await ensureRedisConnected();
      const original = await client.lIndex(FAILED_CALLBACKS_KEY, index);
      if (original === null) return res.status(404).json({ error: 'Entry not found' });

      let entry;
      try { entry = JSON.parse(original); }
      catch { return res.status(400).json({ error: 'Stored entry is not valid JSON' }); }

      const result = await replayCallback(entry);

      if (result.ok) {
        // Remove first occurrence matching the original payload
        const removed = await client.lRem(FAILED_CALLBACKS_KEY, 1, original);
        return res.json({
          success: true,
          status: result.status,
          error: null,
          removed: removed > 0,
          manual_retry_attempts: (entry.manual_retry_attempts || 0) + 1,
        });
      } else {
        // Persist the failure attempt back at the same index
        const updated = {
          ...entry,
          manual_retry_attempts: (entry.manual_retry_attempts || 0) + 1,
          last_manual_retry_error: result.error,
          last_manual_retry_at: new Date().toISOString(),
        };
        await client.lSet(FAILED_CALLBACKS_KEY, index, JSON.stringify(updated));
        return res.status(502).json({
          success: false,
          status: result.status,
          error: result.error,
          manual_retry_attempts: updated.manual_retry_attempts,
        });
      }
    } catch (error) {
      console.error('Error retrying callback:', error);
      res.status(500).json({ error: 'Failed to retry callback' });
    }
  }
);

// Delete a single failed callback entry by index.
app.delete('/api/callbacks/:index', authenticateToken,
  auditMiddleware('callback_delete', { captureParams: ['index'] }),
  async (req, res) => {
    const index = parseInt(req.params.index, 10);
    if (!Number.isInteger(index) || index < 0) {
      return res.status(400).json({ error: 'Invalid index' });
    }
    try {
      const client = await ensureRedisConnected();
      const original = await client.lIndex(FAILED_CALLBACKS_KEY, index);
      if (original === null) return res.status(404).json({ error: 'Entry not found' });
      const removed = await client.lRem(FAILED_CALLBACKS_KEY, 1, original);
      res.json({ deleted: removed > 0 });
    } catch (error) {
      console.error('Error deleting callback:', error);
      res.status(500).json({ error: 'Failed to delete callback' });
    }
  }
);

// Clear the entire failed-callbacks list.
app.post('/api/callbacks/clear', authenticateToken,
  auditMiddleware('callback_clear_all'),
  async (req, res) => {
    try {
      const client = await ensureRedisConnected();
      const cleared = await client.lLen(FAILED_CALLBACKS_KEY);
      await client.del(FAILED_CALLBACKS_KEY);
      res.json({ cleared });
    } catch (error) {
      console.error('Error clearing callbacks:', error);
      res.status(500).json({ error: 'Failed to clear callbacks' });
    }
  }
);

// Helper used by /api/system/stats: load all jobs in the same shape /api/jobs returns.
async function loadAllJobs(client) {
  const jobKeys = await client.keys(`${CRAWL_JOB_PREFIX}*`);
  if (jobKeys.length === 0) return [];
  const raw = await client.mGet(jobKeys);
  return raw
    .map(s => { try { return s ? JSON.parse(s) : null; } catch { return null; } })
    .filter(Boolean)
    // Skip malformed entries without a crawl_id (same hardening as /api/jobs).
    // Also expose .id for downstream aggregators that read job.id.
    .filter(job => job && typeof job.crawl_id === 'string' && job.crawl_id.length > 0)
    .map(job => ({ ...job, id: job.crawl_id }));
}

// Aggregated stats over a time window (1h | 24h | 7d). Used by the dashboard
// for KPI cards and tendances.
app.get('/api/system/stats', authenticateToken, async (req, res) => {
  try {
    const windowStr = req.query.window || '24h';
    const windowMs = parseStatsWindow(windowStr);
    const client = await ensureRedisConnected();
    const stats = await computeSystemStats(client, windowMs, { loadJobs: loadAllJobs });
    res.json({ window: windowStr, ...stats, generated_at: new Date().toISOString() });
  } catch (error) {
    console.error('Error computing system stats:', error);
    res.status(400).json({ error: error.message || 'Failed to compute stats' });
  }
});

// System health detail (authenticated) — for dashboard "system" view.
// Note: /health (below) remains unauthenticated for k8s/LB probes.
app.get('/api/system/health', authenticateToken, async (req, res) => {
  const startedAt = Date.now();
  const checks = {};

  // Redis ping (with a small timeout via Promise.race)
  try {
    const client = await ensureRedisConnected();
    const pingPromise = client.ping();
    const timeoutPromise = new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 1500));
    await Promise.race([pingPromise, timeoutPromise]);
    checks.redis = { status: 'ok' };
  } catch (err) {
    checks.redis = { status: 'down', error: err.message };
  }

  // Storage path readability
  try {
    const st = await stat(CRAWLER_STORAGE_PATH);
    checks.storage = { status: st.isDirectory() ? 'ok' : 'down', path: CRAWLER_STORAGE_PATH };
  } catch (err) {
    checks.storage = { status: 'down', path: CRAWLER_STORAGE_PATH, error: err.message };
  }

  // WebSocket clients count
  checks.ws_clients = clients.size;

  // Process info
  const overall = checks.redis.status === 'ok' && checks.storage.status === 'ok' ? 'ok' : 'degraded';
  res.json({
    status: overall,
    checks,
    process: {
      uptime_seconds: Math.floor(process.uptime()),
      node_version: process.version,
      pid: process.pid,
    },
    response_time_ms: Date.now() - startedAt,
  });
});

app.get('/api/audit', authenticateToken, async (req, res) => {
  try {
    const { from, to, action, user, limit, offset } = req.query;
    const result = await readAuditEntries({
      from: from || undefined,
      to: to || undefined,
      action: action || undefined,
      user: user || undefined,
      limit: limit !== undefined ? Number(limit) : undefined,
      offset: offset !== undefined ? Number(offset) : undefined,
    });
    res.json(result);
  } catch (error) {
    console.error('Error reading audit log:', error);
    res.status(400).json({ error: error.message || 'Failed to read audit log' });
  }
});

app.get('/health', (req, res) => res.json({ status: 'ok' }));

async function setupRedisListener() {
  const subscriber = createClient({ url: REDIS_URL });
  subscriber.on('error', err => console.error('Redis Subscriber Error:', err));
  try {
    await subscriber.connect();
    console.log('Connected to Redis for Pub/Sub subscription.');
    await subscriber.subscribe(CRAWL_UPDATES_CHANNEL, (message) => {
      console.log(`Received update: ${message}`);
      try {
        const updateData = JSON.parse(message);
        broadcast({ type: 'job_update', crawl_id: updateData.crawl_id });
      } catch (e) {
        console.error('Failed to parse update message:', e);
      }
    });

    await subscriber.subscribe('crawler:heartbeat', async (message) => {
      try {
        const heartbeat = JSON.parse(message);
        broadcast({ type: 'replica_heartbeat', data: heartbeat });
        // Persist into per-replica AND per-job time series.
        // Uses the persistent client (not the subscriber) since SUBSCRIBE clients
        // cannot run other commands. Fire-and-forget — never blocks broadcast.
        ensureRedisConnected()
          .then(c => Promise.all([
            persistHeartbeat(c, heartbeat),
            persistJobPerf(c, heartbeat),
          ]))
          .catch(err => console.error('[heartbeatPersist] error:', err.message));
      } catch (e) {
        console.error('Failed to parse heartbeat:', e);
      }
    });
  } catch (err) {
    console.error('Failed to connect to Redis. Retrying in 5s.', err);
    setTimeout(setupRedisListener, 5000);
  }
}

async function start() {
  await ensureRedisConnected();
  console.log('Connected to Redis (persistent client).');
  server.listen(PORT, '0.0.0.0', () => {
    console.log(`Crawler Monitor Backend running on port ${PORT}`);
    setupRedisListener();
    // Audit log: prune old files at boot, then once a day
    rotateOldLogs().then(r => {
      if (r.deleted) console.log(`[audit] pruned ${r.deleted} old log files`);
    }).catch(err => console.error('[audit] initial rotation failed:', err.message));
    setInterval(() => {
      rotateOldLogs().catch(err => console.error('[audit] rotation failed:', err.message));
    }, 24 * 60 * 60 * 1000);

    // Capacity history snapshot: every 60s into Redis sorted set (capped at 24h)
    const takeCapacitySnapshot = async () => {
      try {
        const client = await ensureRedisConnected();
        await snapshotCapacity(client, CRAWL_RUNNING_COUNT_KEY, CRAWL_MAX_GLOBAL_KEY);
      } catch (err) {
        console.error('[capacity] snapshot failed:', err.message);
      }
    };
    takeCapacitySnapshot();
    setInterval(takeCapacitySnapshot, SNAPSHOT_INTERVAL_MS);
  });
}

if (process.env.NODE_ENV !== 'test') {
  start().catch(err => {
    console.error('Failed to start server:', err);
    process.exit(1);
  });
}

export { app };
