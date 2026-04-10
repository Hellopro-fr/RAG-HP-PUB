# Crawler Monitor Alignment Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align crawler-monitor-backend and crawler-monitor-frontend with the current crawler-service data contracts, fix broken real-time updates, and harden security.

**Architecture:** The monitor-backend (Express.js) reads crawler state from Redis + filesystem and exposes it via REST + WebSocket. The monitor-frontend (React 19 SPA) consumes the backend API. This plan fixes the data contract mismatch between what the crawler-service writes and what the monitor reads/displays, plus security and performance issues.

**Tech Stack:** Node.js 20, Express.js 4 (ESM), Redis 4, WebSocket (ws), React 19, Vite 7, Tailwind CSS 3, Lucide React

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `apps-microservices/crawler-monitor-backend/server.js` | Modify | All backend changes: Redis pool, WebSocket fix, new endpoints, security, search rewrite |
| `apps-microservices/crawler-monitor-frontend/src/App.jsx` | Modify | All frontend changes: status handling, WebSocket handler, capacity bar, callbacks indicator, update mode display |

Both services are single-file architectures. All changes are within these two files.

---

## Task 1: Fail-Fast Security Defaults (C3)

**Files:**
- Modify: `apps-microservices/crawler-monitor-backend/server.js:19-31`

**Why:** `ADMIN_PASSWORD` defaults to `admin` and `JWT_SECRET` to `your-secret-key`. If env vars are missing in production, the service is trivially accessible and JWTs forgeable.

- [ ] **Step 1: Replace default values with mandatory validation**

In `server.js`, replace lines 22-23 and add validation after line 27:

```javascript
// OLD (lines 22-23):
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin'; // Default password
const JWT_SECRET = process.env.JWT_SECRET || 'your-secret-key'; // Change in production

// NEW:
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD;
const JWT_SECRET = process.env.JWT_SECRET;
```

Then extend the existing REDIS_URL validation block (lines 28-31) to also check the new vars:

```javascript
// OLD (lines 28-31):
if (!REDIS_URL) {
  console.error("FATAL ERROR: REDIS_URL environment variable is not set.");
  process.exit(1);
}

// NEW:
const missingVars = [];
if (!REDIS_URL) missingVars.push('REDIS_URL');
if (!ADMIN_PASSWORD) missingVars.push('ADMIN_PASSWORD');
if (!JWT_SECRET) missingVars.push('JWT_SECRET');

if (missingVars.length > 0) {
  console.error(`FATAL ERROR: Missing required environment variables: ${missingVars.join(', ')}`);
  process.exit(1);
}
```

- [ ] **Step 2: Verify the service fails to start without env vars**

Run: `cd apps-microservices/crawler-monitor-backend && node -e "delete process.env.ADMIN_PASSWORD; delete process.env.JWT_SECRET; delete process.env.REDIS_URL;" && node server.js`

Expected: Process exits with `FATAL ERROR: Missing required environment variables: REDIS_URL, ADMIN_PASSWORD, JWT_SECRET`

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/crawler-monitor-backend/server.js
git commit -m "fix(crawler-monitor-backend): require ADMIN_PASSWORD and JWT_SECRET env vars

Remove insecure defaults ('admin' / 'your-secret-key'). Service now fails
fast on startup if any required env var is missing."
```

---

## Task 2: Persistent Redis Client (I5)

**Files:**
- Modify: `apps-microservices/crawler-monitor-backend/server.js`

**Why:** Every API request creates a new Redis client, connects, queries, and disconnects. Under load this causes TCP connection storms. A persistent client eliminates this overhead.

- [ ] **Step 1: Create a persistent Redis client at module level**

After the `CRAWL_JOB_PREFIX` constant (line 26), add:

```javascript
// --- Persistent Redis Client ---
const redisClient = createClient({ url: REDIS_URL });
redisClient.on('error', err => console.error('Redis Client Error:', err));

async function ensureRedisConnected() {
  if (!redisClient.isOpen) {
    await redisClient.connect();
  }
  return redisClient;
}
```

- [ ] **Step 2: Refactor GET /api/jobs to use persistent client**

Replace the `GET /api/jobs` handler (lines 172-197):

```javascript
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
```

- [ ] **Step 3: Refactor GET /api/jobs/:id/details to use persistent client**

Replace lines 199-250, removing the per-request `createClient`:

```javascript
app.get('/api/jobs/:id/details', async (req, res) => {
  const { id } = req.params;
  try {
    const client = await ensureRedisConnected();
    const jobDataString = await client.get(`${CRAWL_JOB_PREFIX}${id}`);
    if (!jobDataString) {
      return res.status(404).json({ error: 'Job not found in Redis' });
    }
    const jobData = JSON.parse(jobDataString);

    const logPath = join(CRAWLER_STORAGE_PATH, id, 'crawler.log');
    let parsedData = { stats: null, errors: [], warnings: [], rawContent: '', hasStats: false };
    try {
      const content = await readFile(logPath, 'utf-8');
      parsedData = parseLogFile(content);
    } catch (e) {
      if (e.code !== 'ENOENT') throw e;
      // Log file not found — return job data without log
    }

    res.json({
      ...jobData,
      id: jobData.crawl_id,
      ...parsedData
    });
  } catch (error) {
    console.error(`Error fetching details for job ${id}:`, error);
    res.status(500).json({ error: 'Failed to fetch job details', message: error.message });
  }
});
```

- [ ] **Step 4: Refactor dataset/analyze to use persistent client**

In the `GET /api/jobs/:id/dataset/analyze` handler (around lines 772-851), replace the per-request Redis block:

```javascript
// OLD (lines 777-780):
    const redisClient = createClient({ url: REDIS_URL });
    await redisClient.connect();
    const jobData = JSON.parse(await redisClient.get(`${CRAWL_JOB_PREFIX}${id}`) || '{}');
    await redisClient.quit();

// NEW:
    const client = await ensureRedisConnected();
    const jobData = JSON.parse(await client.get(`${CRAWL_JOB_PREFIX}${id}`) || '{}');
```

- [ ] **Step 5: Refactor dataset/deduplicate to use persistent client**

In the `POST /api/jobs/:id/dataset/deduplicate` handler (around lines 853-936), same replacement:

```javascript
// OLD (lines 857-860):
    const redisClient = createClient({ url: REDIS_URL });
    await redisClient.connect();
    const jobData = JSON.parse(await redisClient.get(`${CRAWL_JOB_PREFIX}${id}`) || '{}');
    await redisClient.quit();

// NEW:
    const client = await ensureRedisConnected();
    const jobData = JSON.parse(await client.get(`${CRAWL_JOB_PREFIX}${id}`) || '{}');
```

- [ ] **Step 6: Connect persistent client at startup**

Modify the server startup block (lines 1038-1041) to connect the persistent client before listening:

```javascript
// Connect persistent Redis client, then start server
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
```

- [ ] **Step 7: Verify by starting the service**

Run: `cd apps-microservices/crawler-monitor-backend && REDIS_URL=$REDIS_URL ADMIN_PASSWORD=$ADMIN_PASSWORD JWT_SECRET=$JWT_SECRET node server.js`

Expected: `Connected to Redis (persistent client).` then `Crawler Monitor Backend running on port 3001`

- [ ] **Step 8: Commit**

```bash
git add apps-microservices/crawler-monitor-backend/server.js
git commit -m "perf(crawler-monitor-backend): use persistent Redis client

Replace per-request connect/quit pattern with a single persistent Redis
client. Eliminates TCP connection storms under load."
```

---

## Task 3: Fix WebSocket Message Contract (C1)

**Files:**
- Modify: `apps-microservices/crawler-monitor-backend/server.js:1014-1021`
- Modify: `apps-microservices/crawler-monitor-frontend/src/App.jsx:1312-1332`

**Why:** Backend sends `{ type: 'file_changed', path: crawl_id }` but frontend expects `{ type: 'job_update', job: { id } }`. Real-time updates are completely broken — WebSocket messages are silently ignored.

- [ ] **Step 1: Fix backend broadcast format**

In `server.js`, in the `setupRedisListener` function, change the `crawl_updates` handler:

```javascript
// OLD (line 1018):
        broadcast({ type: 'file_changed', path: updateData.crawl_id });

// NEW:
        broadcast({ type: 'job_update', crawl_id: updateData.crawl_id });
```

- [ ] **Step 2: Fix frontend WebSocket handler**

In `App.jsx`, fix the `onmessage` handler (lines 1315-1322):

```javascript
// OLD (lines 1315-1322):
        if (data.type === 'job_update') {
          // Auto-refresh job list
          fetchJobs();

          // Update selected job if needed
          if (selectedJob?.id === data.job.id) {
            fetchJobDetails(data.job.id);
          }
        } else if (data.type === 'replica_heartbeat') {

// NEW:
        if (data.type === 'job_update') {
          fetchJobs();
          if (data.crawl_id && selectedJob?.id === data.crawl_id) {
            fetchJobDetails(data.crawl_id);
          }
        } else if (data.type === 'replica_heartbeat') {
```

- [ ] **Step 3: Verify by checking WebSocket messages in browser devtools**

1. Open the monitor frontend in browser
2. Open DevTools → Network → WS tab
3. Start or stop a crawl job
4. Verify the WebSocket frame shows `{ "type": "job_update", "crawl_id": "..." }`
5. Verify the job list auto-refreshes without manual refresh

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/crawler-monitor-backend/server.js apps-microservices/crawler-monitor-frontend/src/App.jsx
git commit -m "fix(crawler-monitor): fix WebSocket message contract

Backend was sending type:'file_changed' but frontend expected
type:'job_update'. Real-time updates were silently broken.
Align both sides on { type: 'job_update', crawl_id: string }."
```

---

## Task 4: Add All Job Statuses (C2)

**Files:**
- Modify: `apps-microservices/crawler-monitor-frontend/src/App.jsx`

**Why:** The crawler-service writes 6 statuses (running, finished, failed, stopping, archived, restarting_oom). The frontend only handles 4 — `archived` and `restarting_oom` fall to a generic gray "Autre" label. The status filter dropdown only offers 3 options.

- [ ] **Step 1: Add Archive and RotateCcw icons to imports**

In `App.jsx`, update the lucide-react import (lines 2-6):

```javascript
// OLD (lines 2-6):
import {
  Activity, CheckCircle, XCircle, Clock, AlertTriangle, RefreshCw, Code,
  Search, Calendar, Filter, Server, Download, ChevronLeft, ChevronRight,
  AlertCircle, Info, Zap, ExternalLink, TrendingUp, LogOut, AlignLeft, Cpu, Trash2
} from 'lucide-react';

// NEW:
import {
  Activity, CheckCircle, XCircle, Clock, AlertTriangle, RefreshCw, Code,
  Search, Calendar, Filter, Server, Download, ChevronLeft, ChevronRight,
  AlertCircle, Info, Zap, ExternalLink, TrendingUp, LogOut, AlignLeft, Cpu, Trash2,
  Archive, RotateCcw
} from 'lucide-react';
```

- [ ] **Step 2: Add missing status cases in getStatusInfo**

In `App.jsx`, in the `JobCard` component's `getStatusInfo` function (lines 30-38), add cases before the `default`:

```javascript
// OLD (lines 30-38):
  const getStatusInfo = (job) => {
    const status = job.status || 'pending';
    switch (status.toLowerCase()) {
      case 'running': return { color: 'blue', text: 'En cours', icon: RefreshCw, spin: true };
      case 'finished': return { color: 'green', text: 'Succès', icon: CheckCircle };
      case 'failed': return { color: 'red', text: 'Échec', icon: XCircle };
      case 'stopping': return { color: 'yellow', text: 'Arrêt...', icon: AlertTriangle };
      default: return { color: 'gray', text: 'Autre', icon: Clock };
    }
  };

// NEW:
  const getStatusInfo = (job) => {
    const status = job.status || 'pending';
    switch (status.toLowerCase()) {
      case 'running': return { color: 'blue', text: 'En cours', icon: RefreshCw, spin: true };
      case 'finished': return { color: 'green', text: 'Succès', icon: CheckCircle };
      case 'failed': return { color: 'red', text: 'Échec', icon: XCircle };
      case 'stopping': return { color: 'yellow', text: 'Arrêt...', icon: AlertTriangle };
      case 'archived': return { color: 'gray', text: 'Archivé', icon: Archive };
      case 'restarting_oom': return { color: 'orange', text: 'Restart OOM', icon: RotateCcw, spin: true };
      default: return { color: 'gray', text: status, icon: Clock };
    }
  };
```

Note: The default case now shows the raw status string instead of "Autre", so any future new status is visible.

- [ ] **Step 3: Add missing statuses to the filter dropdown**

In `App.jsx`, extend the status filter `<select>` options (lines 1461-1466):

```javascript
// OLD (lines 1461-1466):
                <option value="all">Tous les statuts</option>
                <option value="finished">Succès</option>
                <option value="failed">Échec</option>
                <option value="running">En cours</option>

// NEW:
                <option value="all">Tous les statuts</option>
                <option value="finished">Succès</option>
                <option value="failed">Échec</option>
                <option value="running">En cours</option>
                <option value="stopping">Arrêt...</option>
                <option value="archived">Archivé</option>
                <option value="restarting_oom">Restart OOM</option>
```

- [ ] **Step 4: Add archived and restarting_oom to global stats**

In `App.jsx`, extend the `globalStats` computation (lines 1262-1267):

```javascript
// OLD (lines 1262-1267):
  const globalStats = useMemo(() => {
    const finished = filteredJobs.filter(j => j.status === 'finished').length;
    const failed = filteredJobs.filter(j => j.status === 'failed').length;
    const running = filteredJobs.filter(j => j.status === 'running').length;
    return { finished, failed, running, total: filteredJobs.length };
  }, [filteredJobs]);

// NEW:
  const globalStats = useMemo(() => {
    const finished = filteredJobs.filter(j => j.status === 'finished').length;
    const failed = filteredJobs.filter(j => j.status === 'failed').length;
    const running = filteredJobs.filter(j => j.status === 'running').length;
    const archived = filteredJobs.filter(j => j.status === 'archived').length;
    return { finished, failed, running, archived, total: filteredJobs.length };
  }, [filteredJobs]);
```

- [ ] **Step 5: Add an "Archived" stat card to the dashboard**

In `App.jsx`, after the "En cours" StatCard (line 1431), add:

```javascript
          <StatCard title="En cours" value={globalStats.running} icon={Zap} color="blue" />
          <StatCard title="Archivés" value={globalStats.archived} icon={Archive} color="gray" />
```

This changes the grid from 4 to 5 cards. Update the grid class (line 1427):

```javascript
// OLD:
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">

// NEW:
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
```

- [ ] **Step 6: Verify visually**

1. Open the frontend
2. Check that archived jobs show a gray "Archivé" badge with an Archive icon
3. Check that the filter dropdown has all 6 status options
4. Check that the stat cards row shows 5 cards including "Archivés"

- [ ] **Step 7: Commit**

```bash
git add apps-microservices/crawler-monitor-frontend/src/App.jsx
git commit -m "feat(crawler-monitor-frontend): handle all crawler job statuses

Add archived (gray/Archive icon) and restarting_oom (orange/RotateCcw)
statuses. Add all 6 statuses to filter dropdown. Add Archived stat card.
Default case now shows raw status string instead of 'Autre'."
```

---

## Task 5: Replace Shell Exec with Native FS Search (I6)

**Files:**
- Modify: `apps-microservices/crawler-monitor-backend/server.js:383-412`

**Why:** The request queue search uses `exec(find ... grep ...)` with string interpolation, creating a command injection risk. Replace with pure Node.js file I/O.

- [ ] **Step 1: Rewrite the search branch in GET /api/jobs/:id/request-queues**

Replace the `if (search) { ... }` block (lines 385-412) with native fs search:

```javascript
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
```

- [ ] **Step 2: Remove the sanitizeSearchTerm function**

Delete the `sanitizeSearchTerm` function (lines 364-367) since it is no longer needed:

```javascript
// DELETE (lines 363-367):
// Improved search sanitization
function sanitizeSearchTerm(term) {
  // Remove or escape shell metacharacters
  return term.replace(/[`$();&|<>{}[\]\\!]/g, '\\$&');
}
```

- [ ] **Step 3: Remove unused exec import if no other usage remains**

Check if `execAsync` is still used elsewhere in the file. It is used in:
- Line 608: `await execAsync(\`rm -rf "${domainQueuePath}"\`)` in the drop queue endpoint

Since `execAsync` is still used by the drop endpoint, keep the import. However, also replace the drop endpoint's `rm -rf` with native fs:

```javascript
// OLD (line 608):
      await execAsync(`rm -rf "${domainQueuePath}"`);

// NEW:
      const { rm } = await import('fs/promises');
      await rm(domainQueuePath, { recursive: true, force: true });
```

Wait — `rm` is already available from `fs/promises` but not imported at line 11. Add it to the existing import:

```javascript
// OLD (line 11):
import { readFile, readdir, writeFile, unlink, stat, mkdir } from 'fs/promises';

// NEW:
import { readFile, readdir, writeFile, unlink, stat, mkdir, rm } from 'fs/promises';
```

Then replace the execAsync call:

```javascript
// OLD (line 608):
      await execAsync(`rm -rf "${domainQueuePath}"`);

// NEW:
      await rm(domainQueuePath, { recursive: true, force: true });
```

Now check if `execAsync` is used anywhere else. If not, remove the import (lines 2-4):

```javascript
// DELETE if no longer used (lines 2-4):
import { exec } from 'child_process';
import { promisify } from 'util';
const execAsync = promisify(exec);
```

- [ ] **Step 4: Verify search still works**

1. Open the Request Queue Editor for a running job
2. Type a domain name in the search box
3. Verify results appear (matching URLs containing the search term)
4. Verify no errors in backend console

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-monitor-backend/server.js
git commit -m "fix(crawler-monitor-backend): replace exec() with native fs for search

Eliminate command injection risk in request queue search. Use readdir +
readFile + string matching instead of spawning find/grep child processes.
Also replace rm -rf shell exec with fs.rm()."
```

---

## Task 6: Add Capacity Endpoint and Dashboard (I1)

**Files:**
- Modify: `apps-microservices/crawler-monitor-backend/server.js`
- Modify: `apps-microservices/crawler-monitor-frontend/src/App.jsx`

**Why:** The crawler-service writes `crawl_jobs:running_count` and `crawl_jobs:max_global_crawls` to Redis. The monitor has no visibility into global capacity — operators don't know if the service is at capacity or how many slots remain.

- [ ] **Step 1: Add Redis key constants to backend**

In `server.js`, after `CRAWL_JOB_PREFIX` (line 26), add:

```javascript
const CRAWL_RUNNING_COUNT_KEY = 'crawl_jobs:running_count';
const CRAWL_MAX_GLOBAL_KEY = 'crawl_jobs:max_global_crawls';
const FAILED_CALLBACKS_KEY = 'crawl_jobs:failed_callbacks';
```

(We add `FAILED_CALLBACKS_KEY` here too for Task 7.)

- [ ] **Step 2: Add GET /api/capacity endpoint**

Add before the health endpoint (before the line `app.get('/health', ...)`):

```javascript
app.get('/api/capacity', authenticateToken, async (req, res) => {
  try {
    const client = await ensureRedisConnected();
    const runningRaw = await client.get(CRAWL_RUNNING_COUNT_KEY);
    const maxRaw = await client.get(CRAWL_MAX_GLOBAL_KEY);

    const running = parseInt(runningRaw) || 0;
    const max = parseInt(maxRaw) || 0;

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
```

- [ ] **Step 3: Add capacity state and fetch to frontend**

In `App.jsx`, inside the `App` component, after `const [replicas, setReplicas] = useState({});` (line 1231), add:

```javascript
  const [capacity, setCapacity] = useState(null);
```

Add a `fetchCapacity` function after `fetchJobs` (after line 1376):

```javascript
  const fetchCapacity = useCallback(async () => {
    try {
      const response = await authFetch(`${API_URL}/capacity`);
      const data = await response.json();
      setCapacity(data);
    } catch (error) {
      console.error('Error fetching capacity:', error);
    }
  }, [token]);
```

Call `fetchCapacity` alongside `fetchJobs` in the token effect (line 1294):

```javascript
// OLD (lines 1292-1296):
  useEffect(() => {
    if (token) {
      fetchJobs();
    }
  }, [token]);

// NEW:
  useEffect(() => {
    if (token) {
      fetchJobs();
      fetchCapacity();
    }
  }, [token]);
```

Also refresh capacity on WebSocket job_update (inside the `if (data.type === 'job_update')` block):

```javascript
        if (data.type === 'job_update') {
          fetchJobs();
          fetchCapacity();
          if (data.crawl_id && selectedJob?.id === data.crawl_id) {
            fetchJobDetails(data.crawl_id);
          }
        }
```

- [ ] **Step 4: Add CapacityBar to the dashboard**

In `App.jsx`, after the stat cards grid and before the ReplicaMonitor (between lines 1432 and 1434), add:

```javascript
        {/* Capacity Bar */}
        {capacity && capacity.max_global_jobs > 0 && (
          <div className="bg-gray-800 rounded-lg p-4 shadow-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-semibold text-gray-400">
                Capacité globale
              </span>
              <span className={`text-sm font-bold ${capacity.is_full ? 'text-red-400' : 'text-green-400'}`}>
                {capacity.running_jobs} / {capacity.max_global_jobs} slots
              </span>
            </div>
            <div className="h-3 bg-gray-700 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  capacity.is_full ? 'bg-red-500' : capacity.running_jobs / capacity.max_global_jobs > 0.8 ? 'bg-yellow-500' : 'bg-green-500'
                }`}
                style={{ width: `${Math.min((capacity.running_jobs / capacity.max_global_jobs) * 100, 100)}%` }}
              />
            </div>
          </div>
        )}
```

- [ ] **Step 5: Verify visually**

1. Open the frontend
2. Verify a capacity bar appears between stat cards and replica monitor
3. Verify it shows "X / Y slots" with a colored progress bar
4. Start a crawl — verify the bar updates in real-time via WebSocket

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/crawler-monitor-backend/server.js apps-microservices/crawler-monitor-frontend/src/App.jsx
git commit -m "feat(crawler-monitor): add global capacity visibility

New GET /api/capacity endpoint reads crawl_jobs:running_count and
crawl_jobs:max_global_crawls from Redis. Frontend shows a capacity bar
with color-coded fill (green/yellow/red). Auto-refreshes via WebSocket."
```

---

## Task 7: Add Pending Callbacks Visibility (I2)

**Files:**
- Modify: `apps-microservices/crawler-monitor-backend/server.js`
- Modify: `apps-microservices/crawler-monitor-frontend/src/App.jsx`

**Why:** Failed webhook callbacks are stored in Redis (`crawl_jobs:failed_callbacks`) but invisible in the dashboard. Operators have no way to see or manage them.

- [ ] **Step 1: Add GET /api/callbacks endpoint to backend**

In `server.js`, after the capacity endpoint, add:

```javascript
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
```

- [ ] **Step 2: Add callback count state and fetch to frontend**

In `App.jsx`, after `const [capacity, setCapacity] = useState(null);`, add:

```javascript
  const [failedCallbackCount, setFailedCallbackCount] = useState(0);
```

Add a fetch function after `fetchCapacity`:

```javascript
  const fetchCallbacks = useCallback(async () => {
    try {
      const response = await authFetch(`${API_URL}/callbacks`);
      const data = await response.json();
      setFailedCallbackCount(data.count);
    } catch (error) {
      console.error('Error fetching callbacks:', error);
    }
  }, [token]);
```

Call alongside other fetches in the token effect:

```javascript
  useEffect(() => {
    if (token) {
      fetchJobs();
      fetchCapacity();
      fetchCallbacks();
    }
  }, [token]);
```

And in the WebSocket job_update handler:

```javascript
        if (data.type === 'job_update') {
          fetchJobs();
          fetchCapacity();
          fetchCallbacks();
          // ...
        }
```

- [ ] **Step 3: Add failed callbacks indicator to the header**

In `App.jsx`, in the header (around line 1415), before the refresh button, add:

```javascript
            {failedCallbackCount > 0 && (
              <div className="flex items-center gap-2 px-3 py-1 bg-red-900/50 border border-red-500/30 rounded-lg text-sm">
                <AlertCircle className="w-4 h-4 text-red-400" />
                <span className="text-red-300">{failedCallbackCount} callback{failedCallbackCount > 1 ? 's' : ''} en échec</span>
              </div>
            )}
```

- [ ] **Step 4: Verify visually**

1. If there are failed callbacks in Redis, the header should show a red indicator
2. If there are none, no indicator appears (clean state)

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-monitor-backend/server.js apps-microservices/crawler-monitor-frontend/src/App.jsx
git commit -m "feat(crawler-monitor): surface failed webhook callbacks

New GET /api/callbacks reads crawl_jobs:failed_callbacks from Redis.
Frontend shows a red badge in the header when callbacks have failed,
alerting operators to silent notification failures."
```

---

## Task 8: Surface Update Mode Data (I3)

**Files:**
- Modify: `apps-microservices/crawler-monitor-frontend/src/App.jsx`

**Why:** The crawler-service writes `crawl_mode`, `previous_crawl_id`, and update report data to the Redis job hash. The monitor-backend already returns all job fields. The frontend just doesn't display them.

- [ ] **Step 1: Add crawl mode and metadata to JobDetails header**

In `App.jsx`, in the `JobDetails` component, after `<h2 className="text-2xl font-bold text-white">Job #{job.id}</h2>` (line 896), add metadata display:

```javascript
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-white">Job #{job.id}</h2>
          <div className="flex items-center gap-3 mt-1">
            {job.domain && <span className="text-sm text-gray-400">{job.domain}</span>}
            {job.crawl_mode && (
              <span className={`text-xs px-2 py-0.5 rounded ${
                job.crawl_mode === 'update' ? 'bg-purple-500/20 text-purple-400' : 'bg-blue-500/20 text-blue-400'
              }`}>
                {job.crawl_mode === 'update' ? 'Mode Update' : 'Mode Standard'}
              </span>
            )}
            {job.previous_crawl_id && (
              <span className="text-xs text-gray-500">prev: {job.previous_crawl_id}</span>
            )}
            {job.oom_restart_count > 0 && (
              <span className="text-xs px-2 py-0.5 rounded bg-orange-500/20 text-orange-400">
                {job.oom_restart_count} OOM restart{job.oom_restart_count > 1 ? 's' : ''}
              </span>
            )}
          </div>
        </div>
```

Remove the old `<h2>` line and adjust the flex container to wrap the new content.

The full replacement for lines 895-896:

```javascript
// OLD (lines 895-896):
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-white">Job #{job.id}</h2>

// NEW:
      <div className="flex justify-between items-start">
        <div>
          <h2 className="text-2xl font-bold text-white">Job #{job.id}</h2>
          <div className="flex items-center gap-3 mt-1 flex-wrap">
            {job.domain && <span className="text-sm text-gray-400">{job.domain}</span>}
            {job.crawl_mode && (
              <span className={`text-xs px-2 py-0.5 rounded ${
                job.crawl_mode === 'update' ? 'bg-purple-500/20 text-purple-400' : 'bg-blue-500/20 text-blue-400'
              }`}>
                {job.crawl_mode === 'update' ? 'Mode Update' : 'Mode Standard'}
              </span>
            )}
            {job.previous_crawl_id && (
              <span className="text-xs text-gray-500">prev: {job.previous_crawl_id}</span>
            )}
            {job.oom_restart_count > 0 && (
              <span className="text-xs px-2 py-0.5 rounded bg-orange-500/20 text-orange-400">
                {job.oom_restart_count} OOM restart{job.oom_restart_count > 1 ? 's' : ''}
              </span>
            )}
          </div>
        </div>
```

- [ ] **Step 2: Verify visually**

1. Select a job — the header should show domain, crawl mode badge, and OOM restart count if applicable
2. For update mode jobs, a purple "Mode Update" badge and previous crawl ID should appear

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/crawler-monitor-frontend/src/App.jsx
git commit -m "feat(crawler-monitor-frontend): surface update mode data

Display crawl_mode badge (Standard/Update), previous_crawl_id link, and
OOM restart count in job details header. Data already available from
Redis — just not displayed until now."
```

---

## Task 9: Remove Debug Code (M5)

**Files:**
- Modify: `apps-microservices/crawler-monitor-backend/server.js:773`

**Why:** Debug logging left in production code.

- [ ] **Step 1: Remove the debug log line**

```javascript
// DELETE (line 773):
  console.log('🔍 DATASET ANALYZE ENDPOINT HIT (DEBUG: FS FIX APPLIED)');
```

- [ ] **Step 2: Commit**

```bash
git add apps-microservices/crawler-monitor-backend/server.js
git commit -m "chore(crawler-monitor-backend): remove debug log from dataset endpoint"
```

---

## Task 10 (Optional): Update CLAUDE.md Files

**Files:**
- Modify: `apps-microservices/crawler-monitor-backend/CLAUDE.md`
- Modify: `apps-microservices/crawler-monitor-frontend/CLAUDE.md`

**Why:** The CLAUDE.md files should reflect the new endpoints and capabilities.

- [ ] **Step 1: Update backend CLAUDE.md**

Add to the API Endpoints section:

```markdown
- `GET /api/capacity` -- Global crawler capacity (running/max slots) (auth required)
- `GET /api/callbacks` -- Failed webhook callbacks count and details (auth required)
```

Update the Environment Variables section:

```markdown
- `REDIS_URL` (required — fatal if missing)
- `CRAWLER_STORAGE_PATH` (default: `/app/storage`)
- `ADMIN_PASSWORD` (required — fatal if missing)
- `JWT_SECRET` (required — fatal if missing)
- `PORT` (default: `3001`)
```

- [ ] **Step 2: Update frontend CLAUDE.md**

Add a note about supported statuses:

```markdown
## Job Statuses

The frontend handles all crawler-service statuses:
- `running` (blue, spinning) — Crawl in progress
- `finished` (green) — Crawl completed successfully
- `failed` (red) — Crawl failed
- `stopping` (yellow) — Stop requested, awaiting completion
- `archived` (gray) — Job archived to GCS
- `restarting_oom` (orange, spinning) — OOM restart in progress
```

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/crawler-monitor-backend/CLAUDE.md apps-microservices/crawler-monitor-frontend/CLAUDE.md
git commit -m "docs(crawler-monitor): update CLAUDE.md for new endpoints and statuses"
```

---

## Summary

| Task | Severity | Backend | Frontend | Description |
|------|----------|---------|----------|-------------|
| 1 | Critical | X | | Fail-fast security defaults |
| 2 | Important | X | | Persistent Redis client |
| 3 | Critical | X | X | Fix WebSocket message contract |
| 4 | Critical | | X | Add all job statuses |
| 5 | Important | X | | Replace exec with native fs |
| 6 | Important | X | X | Capacity endpoint + dashboard bar |
| 7 | Important | X | X | Pending callbacks visibility |
| 8 | Important | | X | Surface update mode data |
| 9 | Minor | X | | Remove debug code |
| 10 | Minor | X | X | Update CLAUDE.md files |

**Estimated execution order:** Tasks 1-9 are sequential (each builds on the previous backend state). Task 10 is independent.
