# Camoufox as Default Browser — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch the crawler-service from Playwright multi-browser rotation to Camoufox (stealth Firefox) as the default browser, with an opt-out flag to fall back.

**Architecture:** Install `camoufox-js` (official Apify package), parse `--camoufox` CLI flag (default `true`), pass it to `startCrawler()` which conditionally uses Camoufox's `launchOptions()` in the browser pool config. Bake the Camoufox binary into the Docker image at build time.

**Tech Stack:** TypeScript, `camoufox-js` (Apify), Crawlee/Playwright, Docker, Python/FastAPI (schema only)

**Spec:** `docs/superpowers/specs/2026-04-09-camoufox-default-browser-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `crawler/package.json` | MODIFY | Add `camoufox-js` dependency |
| `crawler/src/context.ts` | MODIFY | Add `camoufoxEnabled: boolean` field |
| `crawler/src/main.ts` | MODIFY | Parse `--camoufox` flag, store in context, include in callback payload |
| `crawler/src/functions.ts` | MODIFY | Conditional browser launch: Camoufox vs Playwright rotation |
| `app/schemas/crawler.py` | MODIFY | Change `camoufox` default from `False` to `True`, update description |
| `Dockerfile` | MODIFY | Add `npx camoufox-js fetch` to bake binary into image |
| `CLAUDE.md` | MODIFY | Document Camoufox default browser feature |

---

### Task 1: Install `camoufox-js` dependency

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/package.json`

- [ ] **Step 1: Install the package**

```bash
cd apps-microservices/crawler-service/crawler
npm install camoufox-js
```

This adds `camoufox-js` to `dependencies` in `package.json` and updates `package-lock.json`.

- [ ] **Step 2: Fetch the Camoufox browser binary (for local dev)**

```bash
cd apps-microservices/crawler-service/crawler
npx camoufox-js fetch
```

This downloads the Camoufox Firefox binary locally. Needed for testing — the Docker build will also run this.

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/crawler-service/crawler/package.json apps-microservices/crawler-service/crawler/package-lock.json
git commit -m "feat(crawler-service): add camoufox-js dependency"
```

---

### Task 2: Add `camoufoxEnabled` flag to context

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/context.ts:53`

- [ ] **Step 1: Add the field**

After the existing `robotsTxtBypassed: false` line (line 53), add:

```typescript
    robotsTxtBypassed: false,
    camoufoxEnabled: true,
    crawlErrorMessage: "",
```

- [ ] **Step 2: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/context.ts
git commit -m "feat(crawler-service): add camoufoxEnabled flag to crawler context"
```

---

### Task 3: Parse `--camoufox` flag and store in context

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts:75-76` (flag parsing area)
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts:91-120` (context.config setup)

- [ ] **Step 1: Parse the flag**

After line 75 (the `crawlMode` parsing), add:

```typescript
const crawlMode = getArg('crawlMode', 'npm_config_crawlmode') || 'standard';
const camoufoxEnabled = (getArg('camoufox', 'npm_config_camoufox') || 'true').toLowerCase() !== 'false';
```

The flag defaults to `true`. Only `--camoufox=false` disables it.

- [ ] **Step 2: Store in context**

After the `context.config = { ... }` block (after line 120), add:

```typescript
context.camoufoxEnabled = camoufoxEnabled;
```

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/main.ts
git commit -m "feat(crawler-service): parse --camoufox CLI flag (default true)"
```

---

### Task 4: Conditional browser launch in `startCrawler`

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/functions.ts:1-15` (imports)
- Modify: `apps-microservices/crawler-service/crawler/src/functions.ts:429-441` (function signature)
- Modify: `apps-microservices/crawler-service/crawler/src/functions.ts:470-497` (browserPoolOptions)

This is the core change. The `startCrawler` function gets a new `camoufoxEnabled` parameter that switches between Camoufox and the current Playwright rotation.

- [ ] **Step 1: Add import**

At the top of `functions.ts`, add the `camoufox-js` import alongside existing imports:

```typescript
import { launchOptions as camoufoxLaunchOptions } from 'camoufox-js';
```

- [ ] **Step 2: Add parameter to `startCrawler`**

Add `camoufoxEnabled` as the last parameter in the function signature at line 429:

```typescript
export const startCrawler = async (
    router: RouterHandler<PlaywrightCrawlingContext<Dictionary>>,
    domain: string,
    paramPerCrawl: number,
    paramPerMinute: number,
    apifyProxyPassword?: string,
    breakLimit?: boolean,
    bypassQuestionMark?: boolean,
    bypassDiez?: boolean,
    skipquestionmark?: boolean,
    skipdiez?: boolean,
    containerMemoryMb?: number,
    camoufoxEnabled?: boolean
) => {
```

- [ ] **Step 3: Replace `browserPoolOptions`**

Replace the entire `browserPoolOptions` block (lines 478-497) with conditional logic. The Camoufox path uses `camoufoxLaunchOptions()` in a `preLaunchHooks` callback, while the fallback path keeps the current fingerprinting:

```typescript
        browserPoolOptions: camoufoxEnabled ? {
            // Camoufox mode: stealth Firefox with C++ anti-detection
            retireBrowserAfterPageCount: 25,
            preLaunchHooks: [
                async (_pageId, launchContext) => {
                    const opts = await camoufoxLaunchOptions({});
                    launchContext.launchOptions = {
                        ...opts,
                        args: [
                            ...(opts.args || []),
                            '--ignore-certificate-errors',
                        ],
                    };
                },
            ],
        } : {
            // Fallback mode: Playwright multi-browser rotation with fingerprinting
            fingerprintOptions: {
                fingerprintGeneratorOptions: {
                    browsers: ["firefox", "chrome", "safari"],
                    locales: ["fr-FR"],
                    devices: ["desktop"],
                    operatingSystems: ["windows", "macos", "linux"],
                },
            },
            retireBrowserAfterPageCount: 25,
            preLaunchHooks: [
                (_pageId, launchContext) => {
                    launchContext.launchOptions ??= {};
                    launchContext.launchOptions.args ??= [];
                    launchContext.launchOptions.args.push('--ignore-certificate-errors');
                },
            ],
        },
```

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/functions.ts
git commit -m "feat(crawler-service): conditional Camoufox vs Playwright browser launch"
```

---

### Task 5: Pass `camoufoxEnabled` to `startCrawler` call

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts:1004-1016` (startCrawler call)

- [ ] **Step 1: Add the argument**

Update the `startCrawler` call at line 1004 to pass `camoufoxEnabled`:

```typescript
    const crawler = await startCrawler(
        router,
        domain,
        paramPerCrawl,
        paramPerMinute,
        apifyProxyPassword,
        breakLimit,
        bypassQuestionMark,
        bypassDiez,
        skipquestionmark,
        skipdiez,
        containerMemoryMb,
        camoufoxEnabled
    );
```

- [ ] **Step 2: Add log line**

After the flag parsing (from Task 3), add a log line so it's visible in the crawl output:

```typescript
console.log(`🦊 Browser: ${camoufoxEnabled ? 'Camoufox (stealth Firefox)' : 'Playwright (multi-browser rotation)'}`);
```

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/main.ts
git commit -m "feat(crawler-service): pass camoufoxEnabled to startCrawler and log browser choice"
```

---

### Task 6: Include `camoufox_used` in callback payload

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts:844-853` (payload construction)

- [ ] **Step 1: Add the field to the payload**

In the `payload` object (around line 844), add `camoufox_used` after the existing `robots_txt_bypassed`:

```typescript
    const payload = {
        id_domaine: id,
        success: finalStats?.requestsFinished || 0,
        failed: finalStats?.requestsFailed || 0,
        isFinished: isFinished,
        method: method,
        isError: isError,
        storagePath: storagePath,
        message_erreur_crawling: messageErreurCrawling || null,
        robots_txt_bypassed: context.robotsTxtBypassed,
        camoufox_used: context.camoufoxEnabled
    };
```

- [ ] **Step 2: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/main.ts
git commit -m "feat(crawler-service): include camoufox_used in callback payload"
```

---

### Task 7: Update Python schema default

**Files:**
- Modify: `apps-microservices/crawler-service/app/schemas/crawler.py:86`

- [ ] **Step 1: Change the default and description**

Replace line 86:

```python
    camoufox: Optional[bool] = Field(False, description="Use Camoufox stealth browser.")
```

With:

```python
    camoufox: Optional[bool] = Field(True, description="Use Camoufox stealth browser (default). Set to false to fall back to Playwright multi-browser rotation.")
```

- [ ] **Step 2: Commit**

```bash
git add apps-microservices/crawler-service/app/schemas/crawler.py
git commit -m "feat(crawler-service): change camoufox default to True (opt-out instead of opt-in)"
```

---

### Task 8: Update Dockerfile

**Files:**
- Modify: `apps-microservices/crawler-service/Dockerfile:13-14` (after npm build)

- [ ] **Step 1: Add Camoufox binary fetch to builder stage**

After line 14 (`RUN npm run build`), add:

```dockerfile
# Download Camoufox stealth browser binary (~200MB, baked into image)
RUN npx camoufox-js fetch
```

- [ ] **Step 2: Copy the Camoufox binary in the final stage**

The Camoufox binary is stored in `node_modules/camoufox-js/` (or a `.camoufox` cache dir). Since we already copy `node_modules` from builder at line 46, the binary is included automatically:

```dockerfile
COPY --from=builder /app/crawler/node_modules ./crawler/node_modules
```

Verify this is sufficient by checking where `npx camoufox-js fetch` stores the binary. If it stores outside `node_modules`, add an additional `COPY` line for that path.

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/crawler-service/Dockerfile
git commit -m "feat(crawler-service): bake Camoufox binary into Docker image"
```

---

### Task 9: Update CLAUDE.md

**Files:**
- Modify: `apps-microservices/crawler-service/CLAUDE.md`

- [ ] **Step 1: Add Camoufox section**

After the "robots.txt Blanket Block Bypass" section, add:

```markdown
## Camoufox Default Browser

The crawler uses **Camoufox** (stealth Firefox with C++ anti-detection patches) as the default browser. Unlike Crawlee's built-in fingerprinting (JavaScript injection), Camoufox spoofs `navigator.webdriver`, WebGL, WebRTC, AudioContext, and screen dimensions at the browser engine level — undetectable by JS inspection.

- **Default (`camoufox: true` or omitted):** Camoufox stealth Firefox via `camoufox-js` (official Apify package)
- **Opt-out (`camoufox: false`):** Falls back to Playwright multi-browser rotation (Chrome/Firefox/Safari)
- `camoufox_used: true/false` is included in `_callback_payload.json` for observability
- Dependency: `camoufox-js` — browser binary baked into Docker image at build time
```

- [ ] **Step 2: Commit**

```bash
git add apps-microservices/crawler-service/CLAUDE.md
git commit -m "docs(crawler-service): document Camoufox default browser feature"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|-----------------|------|
| Install `camoufox-js` dependency | Task 1 |
| Add `camoufoxEnabled` to context | Task 2 |
| Parse `--camoufox` flag (default `true`) | Task 3 |
| Conditional browser launch (Camoufox vs Playwright) | Task 4 |
| Pass flag to `startCrawler()` | Task 5 |
| Include `camoufox_used` in callback payload | Task 6 |
| Python schema default `True` | Task 7 |
| Dockerfile: bake binary | Task 8 |
| CLAUDE.md documentation | Task 9 |
| No changes to `routes.ts` | Confirmed — no task touches it |
| No changes to Python orchestrator | Confirmed — only schema touched |
| OOM restart preserves flag | Already handled — flag is in `job_data["params"]` |
