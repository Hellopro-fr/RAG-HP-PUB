# crawler-monitor-backend

Express.js backend providing REST API and WebSocket for the crawler monitoring dashboard.

## Tech Stack

- **Framework:** Express.js 4 (ESM)
- **Runtime:** Node.js 20
- **WebSocket:** ws
- **Auth:** JWT (jsonwebtoken)
- **Security:** Helmet, express-rate-limit
- **State:** Redis (reads crawler job data)
- **Config:** dotenv

## Commands

| Action | Command |
|--------|---------|
| Start | `npm start` (node server.js) |

## Docker

- Base: `node:20-alpine`
- Port: **3001**
- Production deps only (`npm install --omit=dev`)

## Folder Structure

```
server.js              # Single-file Express app
tests/
  server.test.js       # Test stubs (node:test, placeholder)
package.json
Dockerfile
```

## API Endpoints

- `POST /api/login` -- Password-based JWT login
- `GET /api/jobs` -- List all crawler jobs from Redis (auth required)
- `GET /api/jobs/:id/details` -- Full job details (Redis + log parsing)
- `GET /api/jobs/:id/request-queues` -- Paginated queue file listing with search
- `GET /api/jobs/:id/request-queues/:domain/:filename` -- Read single queue file
- `POST /api/jobs/:id/request-queues/:domain/:filename` -- Update queue file
- `GET /api/jobs/:id/request-queues/analyze` -- Queue health analysis (valid vs blocked URLs)
- `POST /api/jobs/:id/request-queues/clean-patterns` -- Remove pattern-matched URLs
- `POST /api/jobs/:id/request-queues/repair` -- Remove URLs with domain mismatch
- `POST /api/jobs/:id/request-queues/drop` -- Drop entire request queue
- `GET /api/jobs/:id/dataset/analyze` -- Dataset duplicate analysis
- `POST /api/jobs/:id/dataset/deduplicate` -- Remove duplicates (keeps newest)
- `GET /api/capacity` -- Global crawler capacity (running/max slots)
- `GET /api/callbacks` -- Failed webhook callbacks count and details
- `GET /health` -- Health check
- WebSocket at `/` -- Real-time updates via Redis pub/sub (`crawl_updates`, `crawler:heartbeat`)

## Conventions

- Single-file architecture (`server.js`)
- ESM modules (`"type": "module"`)
- JWT auth on all `/api/jobs` routes
- WebSocket requires token in query string (`?token=...`)
- Rate limit: 100 requests per 15 minutes per IP
- Reads crawler storage from `CRAWLER_STORAGE_PATH` env var
- Subscribes to Redis channel `crawl_updates` for real-time broadcasts

## Environment Variables

- `REDIS_URL` (required — fatal if missing)
- `CRAWLER_STORAGE_PATH` (default: `/app/storage`)
- `ADMIN_PASSWORD` (required — fatal if missing)
- `JWT_SECRET` (required — fatal if missing)
- `PORT` (default: `3001`)

## Dependencies

- **Redis** for reading crawler job state
- **crawler-service** or **crawler-service-python** (writes job data to Redis)
- **crawler-monitor-frontend** (Vite SPA, consumes this API)
