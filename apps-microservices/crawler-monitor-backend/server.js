import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import { createClient } from 'redis';
import { WebSocketServer } from 'ws';
import { createServer } from 'http';
import { readFile } from 'fs/promises';
import { join } from 'path';

const PORT = process.env.PORT || 3001;
const REDIS_URL = process.env.REDIS_URL;
const CRAWLER_STORAGE_PATH = process.env.CRAWLER_STORAGE_PATH || '/app/storage';

const CRAWL_UPDATES_CHANNEL = 'crawl_updates';
const CRAWL_JOB_PREFIX = 'crawl_job:';

if (!REDIS_URL) {
  console.error("FATAL ERROR: REDIS_URL environment variable is not set.");
  process.exit(1);
}

const app = express();
const server = createServer(app);
const wss = new WebSocketServer({ server });
app.use(cors());

const clients = new Set();
wss.on('connection', ws => {
  clients.add(ws);
  ws.on('close', () => clients.delete(ws));
});

function parseLogFile(content) {
  try {
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
  } catch (err) {
    console.error('Failed to connect to Redis. Retrying in 5s.', err);
    setTimeout(setupRedisListener, 5000);
  }
}

server.listen(PORT, '0.0.0.0', () => {
  console.log(`Crawler Monitor Backend running on port ${PORT}`);
  setupRedisListener();
});