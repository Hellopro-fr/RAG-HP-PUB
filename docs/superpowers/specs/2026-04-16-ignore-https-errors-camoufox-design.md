# Design: Add `ignoreHTTPSErrors` to Crawler Browser Contexts

**Date:** 2026-04-16
**Service:** `crawler-service`
**Status:** Proposed

## Problem

Crawls are failing on sites with invalid, expired, self-signed, or mismatched HTTPS certificates. The crawler currently passes `--ignore-certificate-errors` as a CLI flag, which works only for Chromium. In the Camoufox/Firefox path, this flag was silently rejected as unrecognized (we just removed it in commit `07df9d2d`). As a result, the Firefox-based Camoufox path has no HTTPS cert bypass — any site with a cert issue fails during navigation.

## Evidence

- `api-detection-langue-fr` uses `browser.new_context(ignore_https_errors=True)` with Camoufox/Firefox successfully ([scraper.py:302](apps-microservices/api-detection-langue-fr/app/services/scraper.py#L302)).
- Playwright's `ignoreHTTPSErrors` is a browser CONTEXT option supported across Chromium, Firefox, and WebKit.
- Crawlee creates persistent browser contexts via `browserType.launchPersistentContext(userDataDir, launchOptions)` — the second parameter accepts Playwright context options.
- Crawlee's type `PlaywrightLaunchContext.launchOptions` is defined as `LaunchOptions & Parameters<BrowserType['launchPersistentContext']>[1]` — explicitly accepts context options.
- Crawlee itself uses this pattern internally for MITM proxy handling (browser-crawler.js:407).

## Solution

Inject `ignoreHTTPSErrors: true` into the `launchOptions` for both Camoufox and Chromium paths in `crawler-service/crawler/src/functions.ts`.

## Changes

### 1. Camoufox path — add to `launchOptions` directly

[functions.ts:486-497](apps-microservices/crawler-service/crawler/src/functions.ts#L486-L497):

```typescript
// Before
...(camoufoxEnabled && camoufoxOpts ? {
    launchContext: {
        launcher: firefox,
        launchOptions: {
            ...camoufoxOpts,
        },
    },
} : {}),

// After
...(camoufoxEnabled && camoufoxOpts ? {
    launchContext: {
        launcher: firefox,
        launchOptions: {
            ...camoufoxOpts,
            ignoreHTTPSErrors: true,
        },
    },
} : {}),
```

### 2. Chromium fallback path — add to `preLaunchHooks`

[functions.ts:518-524](apps-microservices/crawler-service/crawler/src/functions.ts#L518-L524):

```typescript
// Before
preLaunchHooks: [
    (_pageId, launchContext) => {
        launchContext.launchOptions ??= {};
        launchContext.launchOptions.args ??= [];
        launchContext.launchOptions.args.push('--ignore-certificate-errors');
    },
],

// After
preLaunchHooks: [
    (_pageId, launchContext) => {
        launchContext.launchOptions ??= {};
        launchContext.launchOptions.ignoreHTTPSErrors = true;
        launchContext.launchOptions.args ??= [];
        launchContext.launchOptions.args.push('--ignore-certificate-errors');
    },
],
```

## Why both paths

- **Camoufox path:** Only fix. Firefox doesn't accept `--ignore-certificate-errors` CLI flag; `ignoreHTTPSErrors` context option is the correct mechanism.
- **Chromium fallback path:** Belt-and-suspenders. The CLI flag already works, but the context option provides a second layer of defense and matches Crawlee's internal convention (see browser-crawler.js:407).

## Edge Cases

| Scenario | Behavior |
|---|---|
| Valid HTTPS cert | No change — cert validated normally |
| Expired cert | Page loads instead of failing |
| Self-signed cert | Page loads instead of failing |
| Hostname mismatch | Page loads instead of failing |
| HTTP (no cert) | No change — not applicable |
| Redirects through invalid certs | Redirect chain completes instead of breaking midway |

## Security Consideration

Ignoring HTTPS errors means the crawler will load pages with broken trust chains, which could include phishing/fraudulent sites. This is acceptable for this service because:

1. The crawler is a **data collection tool for a RAG pipeline**, not a user-facing browser — it's not vulnerable to phishing harm.
2. The target domain is tightly controlled via `same-domain` strategy + external domain check ([routes.ts:712-716](apps-microservices/crawler-service/crawler/src/routes.ts#L712-L716)) — the crawler can't be tricked into visiting arbitrary fraudulent hostnames.
3. The detection API (`api-detection-langue-fr`) uses the same setting for the same reasons, and serves as the architectural precedent.

## Files to Modify

| File | Action | Description |
|---|---|---|
| `crawler-service/crawler/src/functions.ts` | UPDATE | Add `ignoreHTTPSErrors: true` to Camoufox `launchOptions` and Chromium `preLaunchHooks` |

## Non-goals

- Not changing `api-detection-langue-fr` — already correct.
- Not removing the `--ignore-certificate-errors` CLI flag from Chromium path — it works there and provides defense in depth.
- Not exposing this as a per-crawl config option — always-on is the right default for this service.

## Testing Strategy

- TypeScript compilation check: `cd apps-microservices/crawler-service/crawler && npx tsc --noEmit`
- Build check: `cd apps-microservices/crawler-service/crawler && npm run build`
- Manual verification (optional): Trigger a crawl on a domain known to have cert issues; confirm pages load instead of failing with `ERR_CERT_*` errors.

## Rollback

Single-commit revert. No data migrations, no schema changes, no coordination with other services.
