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

const PORT = process.env.PORT || 3001;
const REDIS_URL = process.env.REDIS_URL;
const CRAWLER_STORAGE_PATH = process.env.CRAWLER_STORAGE_PATH || '/app/storage';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD;
const JWT_SECRET = process.env.JWT_SECRET;

const CRAWL_UPDATES_CHANNEL = 'crawl_updates';
const CRAWL_JOB_PREFIX = 'crawl_job:';
const CRAWL_RUNNING_COUNT_KEY = 'crawl_jobs:running_count';
const CRAWL_MAX_GLOBAL_KEY = 'crawl_jobs:max_global_crawls';
const FAILED_CALLBACKS_KEY = 'crawl_jobs:failed_callbacks';

const missingVars = [];
if (!REDIS_URL) missingVars.push('REDIS_URL');
if (!ADMIN_PASSWORD) missingVars.push('ADMIN_PASSWORD');
if (!JWT_SECRET) missingVars.push('JWT_SECRET');

if (missingVars.length > 0) {
  console.error(`FATAL ERROR: Missing required environment variables: ${missingVars.join(', ')}`);
  process.exit(1);
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

// Security Middleware
app.use(helmet());
const limiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100, // Limit each IP to 100 requests per windowMs
  standardHeaders: true,
  legacyHeaders: false,
});
app.use(limiter);

app.use(cors());
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

// Login Endpoint
app.post('/api/login', (req, res) => {
  const { password } = req.body;
  if (password === ADMIN_PASSWORD) {
    const token = jwt.sign({ role: 'admin' }, JWT_SECRET, { expiresIn: '24h' });
    res.json({ token });
  } else {
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
      .map(str => str ? JSON.parse(str) : null)
      .filter(Boolean)
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
  const page = parseInt(req.query.page) || 1;
  const limit = parseInt(req.query.limit) || 50;
  const search = (req.query.search || '').toLowerCase();

  try {
    const baseDir = await findRequestQueuesDir(id);
    if (!baseDir) {
      return res.json({ items: [], total: 0, page, limit });
    }

    let matchingFiles = [];

    if (search) {
      // Native FS search — no shell exec, no injection risk
      const entries = await readdir(baseDir, { withFileTypes: true });
      for (const entry of entries) {
        if (entry.isDirectory()) {
          const domainDir = join(baseDir, entry.name);
          const domainFiles = await readdir(domainDir);

          for (const file of domainFiles) {
            if (file.endsWith('.json')) {
              try {
                const filePath = join(domainDir, file);
                const content = await readFile(filePath, 'utf-8');
                if (content.toLowerCase().includes(search)) {
                  matchingFiles.push({
                    name: file,
                    domain: entry.name,
                    fullPath: filePath,
                    relativePath: join(entry.name, file)
                  });
                }
              } catch (e) {
                // Skip unreadable files
              }
            }
          }
        }
      }
    } else {
      // No search, list all files
      const entries = await readdir(baseDir, { withFileTypes: true });
      for (const entry of entries) {
        if (entry.isDirectory()) {
          const domainDir = join(baseDir, entry.name);
          const domainFiles = await readdir(domainDir);

          for (const file of domainFiles) {
            if (file.endsWith('.json')) {
              matchingFiles.push({
                name: file,
                domain: entry.name,
                fullPath: join(domainDir, file),
                relativePath: join(entry.name, file)
              });
            }
          }
        }
      }
    }

    const total = matchingFiles.length;
    const startIndex = (page - 1) * limit;
    const endIndex = startIndex + limit;
    const paginatedFiles = matchingFiles.slice(startIndex, endIndex);

    // Read content ONLY for the current page
    const items = await Promise.all(paginatedFiles.map(async (f) => {
      try {
        const content = await readFile(f.fullPath, 'utf-8');
        const data = JSON.parse(content);
        return {
          name: f.name,
          domain: f.domain,
          path: f.relativePath,
          url: data.url,
          method: data.method,
          retryCount: data.retryCount,
          errorMessages: data.errorMessages
        };
      } catch (err) {
        console.error(`Error reading queue file ${f.name}:`, err);
        return {
          name: f.name,
          domain: f.domain,
          path: f.relativePath,
          url: 'Error reading file',
          method: 'UNKNOWN'
        };
      }
    }));

    res.json({
      items,
      total,
      page,
      limit,
      totalPages: Math.ceil(total / limit)
    });

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

app.post('/api/jobs/:id/request-queues/:domain/:filename', async (req, res) => {
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

app.post('/api/jobs/:id/request-queues/repair', async (req, res) => {
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
app.post('/api/jobs/:id/request-queues/drop', async (req, res) => {
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

                // Check if handled
                if (data.handledAt) {
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

app.post('/api/jobs/:id/dataset/deduplicate', async (req, res) => {
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

app.post('/api/jobs/:id/request-queues/clean-patterns', async (req, res) => {

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

    await subscriber.subscribe('crawler:heartbeat', (message) => {
      try {
        const heartbeat = JSON.parse(message);
        broadcast({ type: 'replica_heartbeat', data: heartbeat });
      } catch (e) {
        console.error('Failed to parse heartbeat:', e);
      }
    });
  } catch (err) {
    console.error('Failed to connect to Redis. Retrying in 5s.', err);
    setTimeout(setupRedisListener, 5000);
  }
}

ensureRedisConnected()
  .then(() => {
    console.log('Connected to Redis (persistent client).');
    server.listen(PORT, '0.0.0.0', () => {
      console.log(`Crawler Monitor Backend running on port ${PORT}`);
      setupRedisListener();
    });
  })
  .catch(err => {
    console.error('Failed to connect to Redis:', err);
    process.exit(1);
  });
