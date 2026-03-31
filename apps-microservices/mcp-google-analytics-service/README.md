# MCP Google Analytics Service

MCP server exposing Google Analytics 4 data as MCP tools over SSE and streamable HTTP.

## Prerequisites

- Docker
- A Google Cloud project
- A Google Analytics 4 property

## Setup

### 1. Enable Google APIs

Go to [Google Cloud Console > APIs & Services](https://console.cloud.google.com/apis/library) and enable:

- **Google Analytics Admin API**
- **Google Analytics Data API**

Or via CLI:

```bash
gcloud services enable analyticsadmin.googleapis.com --project=YOUR_PROJECT_ID
gcloud services enable analyticsdata.googleapis.com --project=YOUR_PROJECT_ID
```

### 2. Create a Service Account

```bash
gcloud iam service-accounts create ga-mcp-reader \
  --display-name="GA MCP Reader" \
  --project=YOUR_PROJECT_ID
```

### 3. Download the JSON Key

```bash
mkdir -p secrets
gcloud iam service-accounts keys create ./secrets/gcp-analytics-credentials.json \
  --iam-account=ga-mcp-reader@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

### 4. Grant Read-Only Access in Google Analytics

1. Go to [analytics.google.com](https://analytics.google.com)
2. Click **Admin** (gear icon, bottom left)
3. Under your GA4 property, click **Property access management**
4. Click **+** > **Add users**
5. Enter the service account email: `ga-mcp-reader@YOUR_PROJECT_ID.iam.gserviceaccount.com`
6. Select role: **Viewer**
7. Click **Add**

> To grant access to all properties at once, use **Account access management** instead of Property access management.

### 5. Configure Environment Variables

Add to your `.env` file:

```env
GOOGLE_ANALYTICS_PROJECT_ID=your-gcp-project-id
GOOGLE_ANALYTICS_CREDENTIALS_PATH=./secrets/gcp-analytics-credentials.json
```

### 6. Build and Run

```bash
docker compose --profile mcp build mcp-google-analytics-service
docker compose --profile mcp up mcp-google-analytics-service
```

### 7. Verify

```bash
# List available tools
curl -s -X POST http://localhost:8583/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# Test with your GA data (requires valid credentials)
curl -s -X POST http://localhost:8583/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_account_summaries","arguments":{}}}'
```

## Available Tools

| Tool | Description |
|---|---|
| `get_account_summaries` | Lists GA accounts and properties accessible by the service account |
| `get_property_details` | Returns details about a specific GA4 property |
| `list_google_ads_links` | Lists Google Ads links for a property |
| `list_property_annotations` | Lists annotations on a property |
| `get_custom_dimensions_and_metrics` | Lists custom dimensions and metrics for a property |
| `run_report` | Runs a standard GA4 report (dimensions, metrics, date ranges) |
| `run_realtime_report` | Runs a realtime GA4 report |

## Register with MCP Gateway (optional)

```bash
curl -X POST http://localhost:8581/api/v1/servers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Google Analytics",
    "url": "http://mcp-google-analytics-service:8583",
    "tags": ["analytics", "google"],
    "tool_prefix": "ga"
  }'
```

Tools will then be accessible through the gateway as `ga_get_account_summaries`, `ga_run_report`, etc.

## Endpoints

| Endpoint | Transport | Description |
|---|---|---|
| `GET /sse` | SSE | Streaming transport |
| `POST /mcp` | Streamable HTTP | Stateless transport |

## Port

`8583` (MCP port sequence: gateway=8581, recherche=8582, analytics=8583)
