import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import { createClient } from 'redis';
import { WebSocketServer } from 'ws';
import { createServer } from 'http';
import { readFile, readdir, writeFile, stat } from 'fs/promises';
import { join, normalize } from 'path';
import { existsSync } from 'fs';
import helmet from 'helmet';
import rateLimit from 'express-rate-limit';

import jwt from 'jsonwebtoken';

const PORT = process.env.PORT || 3001;
const REDIS_URL = process.env.REDIS_URL;
const CRAWLER_STORAGE_PATH = process.env.CRAWLER_STORAGE_PATH || '/app/storage';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin'; // Default password
const JWT_SECRET = process.env.JWT_SECRET || 'your-secret-key'; // Change in production

const CRAWL_UPDATES_CHANNEL = 'crawl_updates';
const CRAWL_JOB_PREFIX = 'crawl_job:';

if (!REDIS_URL) {
  console.error("FATAL ERROR: REDIS_URL environment variable is not set.");
  process.exit(1);
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

    // 3. Extraire les warnings (REGEX CORRIGÉ)
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
      hasStats: !!stats // Indicateur pour le frontend
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
  const redisClient = createClient({ url: REDIS_URL });
  try {
    await redisClient.connect();
    const jobKeys = await redisClient.keys(`${CRAWL_JOB_PREFIX}*`);
    if (jobKeys.length === 0) return res.json([]);

    const jobsData = await redisClient.mGet(jobKeys);
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
  } finally {
    if (redisClient.isOpen) await redisClient.quit();
  }
});

app.get('/api/jobs/:id/details', async (req, res) => {
  const { id } = req.params;
  const redisClient = createClient({ url: REDIS_URL });
  try {
    await redisClient.connect();

    // 1. Récupérer les infos de base du job depuis Redis
    const jobDataString = await redisClient.get(`${CRAWL_JOB_PREFIX}${id}`);
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
    const content = await readFile(logPath, 'utf-8');
    console.log(`Log file read successfully, size: ${content.length} bytes`);

    const parsedData = parseLogFile(content);

    // 4. Fusionner les données de Redis et du log
    const fullDetails = {
      ...jobData,
      id: jobData.crawl_id,
      ...parsedData
    };

    res.json(fullDetails);

  } catch (error) {
    console.error(`Error fetching details for job ${id}:`, error);
    if (error.code === 'ENOENT') {
      res.status(404).json({
        error: 'Log file not found',
        id: id,
        hasStats: false
      });
    } else {
      res.status(500).json({
        error: 'Failed to fetch job details',
        message: error.message
      });
    }
  } finally {
    if (redisClient.isOpen) await redisClient.quit();
  }
});

// Helper to find the request_urls directory
async function findRequestUrlsDir(jobId) {
  // Check possible paths
  const paths = [
    join(CRAWLER_STORAGE_PATH, jobId, 'storage', 'request_urls'),
    join(CRAWLER_STORAGE_PATH, jobId, 'request_urls')
  ];

  for (const p of paths) {
    if (existsSync(p)) return p;
  }
  return null;
}

app.get('/api/jobs/:id/request-urls', async (req, res) => {
  const { id } = req.params;
  try {
    const baseDir = await findRequestUrlsDir(id);
    if (!baseDir) {
      return res.json([]); // No directory found, return empty list
    }

    const entries = await readdir(baseDir, { withFileTypes: true });
    const files = [];

    // Iterate over domain directories
    for (const entry of entries) {
      if (entry.isDirectory()) {
        const domainDir = join(baseDir, entry.name);
        const domainFiles = await readdir(domainDir);
        for (const file of domainFiles) {
          if (file.endsWith('.json')) {
            files.push({
              name: file,
              domain: entry.name,
              path: join(entry.name, file) // Relative path for API usage
            });
          }
        }
      }
    }

    res.json(files);
  } catch (error) {
    console.error(`Error listing request urls for job ${id}:`, error);
    res.status(500).json({ error: 'Failed to list request urls' });
  }
});

app.get('/api/jobs/:id/request-urls/:domain/:filename', async (req, res) => {
  const { id, domain, filename } = req.params;
  try {
    const baseDir = await findRequestUrlsDir(id);
    if (!baseDir) {
      return res.status(404).json({ error: 'Request URLs directory not found' });
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
    console.error(`Error reading request url file ${filename}:`, error);
    res.status(500).json({ error: 'Failed to read file' });
  }
});

app.post('/api/jobs/:id/request-urls/:domain/:filename', async (req, res) => {
  const { id, domain, filename } = req.params;
  const content = req.body;

  try {
    const baseDir = await findRequestUrlsDir(id);
    if (!baseDir) {
      return res.status(404).json({ error: 'Request URLs directory not found' });
    }

    const filePath = normalize(join(baseDir, domain, filename));

    // Security check
    if (!filePath.startsWith(baseDir)) {
      return res.status(403).json({ error: 'Access denied' });
    }

    await writeFile(filePath, JSON.stringify(content, null, 2), 'utf-8');
    res.json({ success: true });
  } catch (error) {
    console.error(`Error saving request url file ${filename}:`, error);
    res.status(500).json({ error: 'Failed to save file' });
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
        broadcast({ type: 'file_changed', path: updateData.crawl_id });
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

server.listen(PORT, '0.0.0.0', () => {
  console.log(`Crawler Monitor Backend running on port ${PORT}`);
  setupRedisListener();
});