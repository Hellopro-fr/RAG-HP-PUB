# ignoreHTTPSErrors in Camoufox/Chromium Contexts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `ignoreHTTPSErrors: true` to the Playwright browser context for both Camoufox/Firefox and Chromium fallback paths in `crawler-service`, so crawls no longer fail on sites with invalid/expired/self-signed HTTPS certificates.

**Architecture:** Inject `ignoreHTTPSErrors: true` into `launchContext.launchOptions` — which Crawlee passes directly to `browserType.launchPersistentContext(userDataDir, launchOptions)`. The second parameter of that call accepts Playwright context options, so the flag takes effect at context creation. No new files, no refactoring — two small inline additions in one file.

**Tech Stack:** Node.js 22, TypeScript, Crawlee 3.0.0, Playwright 1.56.1, Camoufox 0.9.3

**Spec:** `docs/superpowers/specs/2026-04-16-ignore-https-errors-camoufox-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `apps-microservices/crawler-service/crawler/src/functions.ts` | MODIFY | Add `ignoreHTTPSErrors: true` to Camoufox `launchOptions` (line 489-494) and Chromium `preLaunchHooks` (line 518-524) |

Single file, two small changes, one commit. No test file is created — this is a TypeScript config change with no unit-testable logic; verification is via compilation + build.

---

### Task 1: Add `ignoreHTTPSErrors: true` to both launch paths

**Goal:** Bypass HTTPS certificate errors at the browser context level for both Camoufox/Firefox and Chromium fallback, so invalid-cert sites no longer fail to load.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/functions.ts:486-497` (Camoufox path)
- Modify: `apps-microservices/crawler-service/crawler/src/functions.ts:518-524` (Chromium fallback path)

**Acceptance Criteria:**
- [ ] Camoufox path's `launchOptions` object contains `ignoreHTTPSErrors: true`
- [ ] Chromium path's `preLaunchHooks` sets `launchContext.launchOptions.ignoreHTTPSErrors = true`
- [ ] TypeScript compilation succeeds with no new errors
- [ ] Build (`npm run build`) succeeds
- [ ] Changes committed with a descriptive bilingual message

**Verify:** `cd apps-microservices/crawler-service/crawler && npx tsc --noEmit && npm run build` → exit code 0, no errors

**Steps:**

- [ ] **Step 1: Read the current Camoufox launch block**

Run: Read `apps-microservices/crawler-service/crawler/src/functions.ts` lines 485-500.

Confirm the current state matches:

```typescript
        ...(camoufoxEnabled && camoufoxOpts ? {
            launchContext: {
                launcher: firefox,
                launchOptions: {
                    ...camoufoxOpts,
                },
            },
        } : {}),
```

If the state differs (e.g., someone already added `ignoreHTTPSErrors`), skip the next edit for Camoufox and proceed to the Chromium path edit.

- [ ] **Step 2: Edit the Camoufox `launchOptions`**

Use the Edit tool to change the Camoufox block:

**Find (old_string):**
```typescript
            launchContext: {
                launcher: firefox,
                launchOptions: {
                    ...camoufoxOpts,
                },
            },
```

**Replace with (new_string):**
```typescript
            launchContext: {
                launcher: firefox,
                launchOptions: {
                    ...camoufoxOpts,
                    ignoreHTTPSErrors: true,
                },
            },
```

- [ ] **Step 3: Read the current Chromium fallback `preLaunchHooks`**

Run: Read `apps-microservices/crawler-service/crawler/src/functions.ts` lines 514-525.

Confirm the current state matches:

```typescript
            preLaunchHooks: [
                (_pageId, launchContext) => {
                    launchContext.launchOptions ??= {};
                    launchContext.launchOptions.args ??= [];
                    launchContext.launchOptions.args.push('--ignore-certificate-errors');
                },
            ],
```

- [ ] **Step 4: Edit the Chromium fallback `preLaunchHooks`**

Use the Edit tool to change the Chromium block:

**Find (old_string):**
```typescript
            preLaunchHooks: [
                (_pageId, launchContext) => {
                    launchContext.launchOptions ??= {};
                    launchContext.launchOptions.args ??= [];
                    launchContext.launchOptions.args.push('--ignore-certificate-errors');
                },
            ],
```

**Replace with (new_string):**
```typescript
            preLaunchHooks: [
                (_pageId, launchContext) => {
                    launchContext.launchOptions ??= {};
                    launchContext.launchOptions.ignoreHTTPSErrors = true;
                    launchContext.launchOptions.args ??= [];
                    launchContext.launchOptions.args.push('--ignore-certificate-errors');
                },
            ],
```

- [ ] **Step 5: Verify TypeScript compilation**

Run:
```bash
cd apps-microservices/crawler-service/crawler && npx tsc --noEmit
```

Expected: no output (exit code 0). No new errors.

If TypeScript reports an error like `Property 'ignoreHTTPSErrors' does not exist on type 'LaunchOptions'`, the Crawlee type inference is treating `launchOptions` as pure `LaunchOptions` rather than the intersection with `launchPersistentContext` options. In that case, cast as shown:

```typescript
(launchContext.launchOptions as any).ignoreHTTPSErrors = true;
```

For the Camoufox path, use a type assertion on the object literal:

```typescript
launchOptions: {
    ...camoufoxOpts,
    ignoreHTTPSErrors: true,
} as any,
```

Re-run `npx tsc --noEmit` until it passes.

- [ ] **Step 6: Verify build**

Run:
```bash
cd apps-microservices/crawler-service/crawler && npm run build
```

Expected: build completes, produces `dist/main.js` and related files, exit code 0.

- [ ] **Step 7: Commit**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB
git add apps-microservices/crawler-service/crawler/src/functions.ts
git commit -m "fix(crawler): add ignoreHTTPSErrors to Camoufox and Chromium contexts

Bypasses invalid/expired/self-signed HTTPS certificate errors at the
Playwright browser context level. Crawlee passes launchOptions directly
to browserType.launchPersistentContext(), which accepts ignoreHTTPSErrors
as a context option. Applied to both Camoufox/Firefox path (direct
launchOptions) and Chromium fallback (preLaunchHooks).

---

fix(crawler): ajouter ignoreHTTPSErrors aux contextes Camoufox et Chromium

Contourne les erreurs de certificat HTTPS invalide/expiré/auto-signé
au niveau du contexte navigateur Playwright. Crawlee transmet
launchOptions directement à browserType.launchPersistentContext(),
qui accepte ignoreHTTPSErrors comme option de contexte. Appliqué au
chemin Camoufox/Firefox (launchOptions direct) et au fallback Chromium
(preLaunchHooks)."
```

**Optional manual verification (post-merge):**

If a crawl on a site with known cert issues was previously failing, re-run it and confirm the page now loads.

---

## Self-Review

**1. Spec coverage:**
- Spec requirement: Camoufox path gets `ignoreHTTPSErrors: true` → Task 1, Step 2 ✓
- Spec requirement: Chromium fallback gets `ignoreHTTPSErrors: true` → Task 1, Step 4 ✓
- Spec requirement: TS compile check → Task 1, Step 5 ✓
- Spec requirement: Build check → Task 1, Step 6 ✓
- Spec requirement: Single-commit revertability → Task 1, Step 7 (one commit) ✓
- Spec edge cases (expired, self-signed, hostname mismatch) — all handled by the same setting, no separate tasks needed
- Spec "Non-goals" (no changes to api-detection-langue-fr, no per-crawl config) — respected, plan touches only the one file

**2. Placeholder scan:** No TBDs, TODOs, or vague instructions. All code blocks show exact before/after. Commit message is complete, bilingual, and ready to use.

**3. Type consistency:** `ignoreHTTPSErrors` spelled consistently throughout. Camoufox block uses it as an object property; Chromium block uses it as a property assignment. Both match Playwright's official naming.

All clean.
