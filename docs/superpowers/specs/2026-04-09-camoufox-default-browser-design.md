# Design: Camoufox as Default Browser

**Date:** 2026-04-09
**Service:** crawler-service (Node.js crawler engine)
**Status:** Approved

## Problem

Sites with advanced anti-bot systems (Cloudflare WAF, PerimeterX, Akamai Bot Manager) block the crawler despite Crawlee's built-in fingerprint rotation. The current fingerprinting approach injects browser properties via JavaScript, which is detectable by sophisticated fingerprinting libraries (CreepJS, FingerprintJS Pro) that inspect `toString()`, prototype chains, and worker thread comparisons.

Blocking manifests as a mix of HTTP 403/429, CAPTCHAs, cloaked content, and connection-level blocks.

## Decision

Switch to **Camoufox** (stealth Firefox with C++ level anti-detection patches) as the **default browser** for all crawls. The existing `camoufox` API flag is repurposed as an **opt-out** (`camoufox: false`) to fall back to the current Playwright multi-browser rotation.

**Dependency:** `camoufox-js` — the official Apify package (v0.9.3, 252K downloads/month, maintained by Apify engineer Jindrich Bar, published via GitHub Actions OIDC). NOT `@hieutran094/camoufox-js` (unauthorized re-publish) or `camoufox` by tocha688 (abandoned fork).

## What Camoufox Provides Over Current Stack

| Feature | Current (Crawlee fingerprinting) | Camoufox |
|---------|----------------------------------|----------|
| `navigator.webdriver` | Detectable (CDP exposes it) | Hidden at C++ level |
| Fingerprint injection | JavaScript injection (detectable) | C++ native — appears native |
| WebGL spoofing | Not available | Vendor, renderer spoofed natively |
| WebRTC IP | Leaks real IP | Spoofed at protocol level |
| AudioContext | Not spoofed | Spoofed natively |
| Screen/viewport | Manual config | Auto-generated from real-world distributions |
| Automation protocol | Visible to page JS | Sandboxed — page JS cannot detect Playwright |
| Cursor movement | Instant/programmatic | Human-like movement (C++ algorithm) |

**Trade-off:** Firefox-only (no Chrome/Safari rotation). Sites that specifically fingerprint SpiderMonkey engine behavior may need the opt-out fallback.

## Design

### Integration Approach

`camoufox-js` provides `launchOptions()` which returns Playwright `firefox.launch()` compatible options. This plugs into Crawlee's `PlaywrightCrawler` via `preLaunchHooks`:

```typescript
import { launchOptions } from 'camoufox-js';

// In preLaunchHooks:
launchContext.launchOptions = {
    ...await launchOptions({ /* camoufox config */ }),
    args: ['--ignore-certificate-errors'],
};
```

The `PlaywrightCrawler` continues to manage browser pool, sessions, retries, and page lifecycle. Only the browser binary changes.

### Flag Behavior

- **Default (`camoufox: true` or omitted):** Camoufox stealth Firefox
- **Opt-out (`camoufox: false`):** Current Playwright multi-browser rotation (Chrome/Firefox/Safari fingerprinting)

The Python schema's `camoufox` field default changes from `False` to `True`.

### Callback Payload

Include `camoufox_used: true/false` in `_callback_payload.json` for observability — same pattern as `robots_txt_bypassed`.

### Docker Changes

Add `npx camoufox-js fetch` to the Dockerfile build stage to bake the Camoufox binary (~200MB) into the image. No runtime download needed.

### Files to Modify

| File | Change |
|------|--------|
| `crawler/package.json` | Add `camoufox-js` dependency |
| `crawler/src/main.ts` | Parse `--camoufox` flag (default `true`), store in context |
| `crawler/src/context.ts` | Add `camoufoxEnabled: boolean` field |
| `crawler/src/functions.ts` | Conditional browser launch: Camoufox vs Playwright rotation |
| `crawler/src/main.ts` | Include `camoufox_used` in callback payload |
| `crawler/Dockerfile` | Add `npx camoufox-js fetch` build step |
| `app/schemas/crawler.py` | Update `camoufox` field default to `True`, update description |

### What Stays Unchanged

- `routes.ts` — page handling, URL filtering, robots.txt checks
- Python orchestrator (`crawler_manager.py`, `router/crawler.py`) — no awareness of browser choice
- Crawlee's request queue, session management, retry logic
- Circuit breaker, archiving, update mode

### Edge Cases

| Case | Behavior |
|------|----------|
| `camoufox: true` (default) | Camoufox Firefox stealth |
| `camoufox: false` (opt-out) | Current Playwright multi-browser rotation |
| Camoufox binary missing | Startup error — caught at Docker build time (`npx camoufox-js fetch`) |
| Site blocks Firefox/SpiderMonkey | Caller opts out with `camoufox: false` to get Chrome/Safari |
| OOM restart | Camoufox flag preserved in job params — relaunch uses same browser |

## Alternatives Considered

### A: Per-request opt-in (keep current default, Camoufox when asked)
- Requires manual decision per site — the user explicitly rejected this due to operational overhead.

### B: Automatic fallback (detect blocking, retry with Camoufox)
- Detecting blocking reliably is hard (CAPTCHAs in HTML, cloaked content, soft blocks).
- Double crawl cost for every blocked page.
- Rejected due to implementation complexity.

### C: Camoufox for everything, no fallback
- Rejected because losing Chrome/Safari rotation entirely removes a recovery option for sites that fingerprint SpiderMonkey.
