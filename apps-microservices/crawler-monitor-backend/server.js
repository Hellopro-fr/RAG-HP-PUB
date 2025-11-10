import express from 'express';
import cors from 'cors';
import { createClient } from 'redis';
import { WebSocketServer } from 'ws';
import { createServer } from 'http';

const PORT = process.env.PORT || 3001;
const REDIS_URL = process.env.REDIS_URL;
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
      .map(job => ({ ...job, id: job.crawl_id, lastModified: job.start_time }));

    jobs.sort((a, b) => new Date(b.start_time) - new Date(a.start_time));
    res.json(jobs);
  } catch (error) {
    console.error('Error fetching initial jobs from Redis:', error);
    res.status(500).json({ error: 'Failed to fetch jobs' });
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
      const updateData = JSON.parse(message);
      broadcast({ type: 'file_changed', path: updateData.crawl_id });
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
