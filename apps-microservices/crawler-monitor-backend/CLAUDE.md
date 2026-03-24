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
package.json
Dockerfile
```

## API Endpoints

- `POST /api/login` -- Password-based JWT login
- `GET /api/jobs` -- List all crawler jobs from Redis (auth required)
- `GET /api/jobs/:id` -- Single job details
- `GET /api/jobs/:id/log` -- Read crawler log file
- `GET /api/jobs/:id/stats` -- Parsed crawler stats
- WebSocket at `/` -- Real-time crawl updates via Redis pub/sub

## Conventions

- Single-file architecture (`server.js`)
- ESM modules (`"type": "module"`)
- JWT auth on all `/api/jobs` routes
- WebSocket requires token in query string (`?token=...`)
- Rate limit: 100 requests per 15 minutes per IP
- Reads crawler storage from `CRAWLER_STORAGE_PATH` env var
- Subscribes to Redis channel `crawl_updates` for real-time broadcasts

## Environment Variables

- `REDIS_URL` (required)
- `CRAWLER_STORAGE_PATH` (default: `/app/storage`)
- `ADMIN_PASSWORD` (default: `admin`)
- `JWT_SECRET` (default: `your-secret-key`)
- `PORT` (default: `3001`)

## Dependencies

- **Redis** for reading crawler job state
- **crawler-service** or **crawler-service-python** (writes job data to Redis)
- **crawler-monitor-frontend** (Vite SPA, consumes this API)
