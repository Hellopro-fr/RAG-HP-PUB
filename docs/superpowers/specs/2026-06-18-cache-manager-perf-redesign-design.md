# Design — redis-client-frontend cache-manager perf redesign

- **Date:** 2026-06-18
- **Service:** `apps-microservices/redis-client-frontend`
- **Goal:** Stop the cache manager from eagerly loading the entire shared Redis keyspace on page open / Refresh. Make it a paginated, SCAN-based, consent-gated key browser that never disrupts the fleet's shared Redis.
- **Status:** Approved design (brainstorming). Next: implementation plan.
- **Related:** the SSO + shared-auth-lib specs in this dir (same service).

---

## 1. Context & root cause

`app/page.tsx` (Server Component) `await`s `getCachedData()`, which:
1. `getAllKeys()` — `SCAN COUNT 100` over the **entire shared Redis** (used by the whole fleet).
2. `Promise.all(keys.map(...))` — `GET` + `MEMORY USAGE` + `TTL` for **every** key = **3N–4N commands at once**.
3. Loads every value into memory, sorts, serializes the whole list to the browser.

Consequences on a large shared Redis: `/` hangs (server-side TTFB blocks until the whole keyspace is read), the UI is laggy (all rows rendered), and the command burst **degrades the single-threaded shared Redis for other services** (observed: errors in other services on Refresh — Refresh re-runs the same full load).

**Decisive observation:** the table (`cache-table.tsx`) shows only **Key / Size / Expires / Actions** — the **value is never displayed**. So the `GET` per key (the heaviest, most fleet-disruptive part) fetches data that is immediately discarded (used only to skip null keys). Removing it is pure win.

---

## 2. Decisions (locked in brainstorming)

| # | Decision | Choice |
|---|----------|--------|
| D1 | Scope | **Core perf fix** — paginated SCAN-based key browser, no per-key `GET`, server-side `MATCH`. (Value inspector deferred.) |
| D2 | Fleet-safety infra | **Note-only** — the code fix removes the load; a read-replica is optional future infra. A dedicated DB index is explicitly rejected (different keyspace → manager couldn't see the fleet's cache). |
| D3 | **Consent gate** | The manager does **not** auto-scan on page open. A **"Scan keys"** action behind a `ConfirmDialog` initiates any scan (page open shows a shell only; zero Redis contact until consent). |
| D4 | Total Size stat | **Dropped** — cannot sum without scanning everything (the thing we're removing). Total Keys = `DBSIZE` (O(1)). |
| D5 | Key types | Show **all** keys incl. non-string (Sets/Hashes the crawler writes), with a **Type** column — the old `GET`-based path silently dropped them. |

---

## 3. Architecture / flow

```
Open /  → Server Component renders shell + "Scan keys" button + warning. NO Redis contact.
        → user clicks "Scan keys" → ConfirmDialog ("queries the shared prod Redis, may add
          latency to other services — continue?")
        → confirm → listCacheKeys({cursor:0, match}) server action:
             SCAN 0 MATCH <glob> COUNT 100  → keys[]
             per key: TTL + TYPE + MEMORY USAGE   (page-sized, ~100 → cheap)
             DBSIZE  → total
          → render table (page 1) + Total Keys stat
        → "Load more" → listCacheKeys({cursor:nextCursor, match})  (no re-confirm)
        → search box → debounced listCacheKeys({cursor:0, match:`*term*`})  (no re-confirm)
        → "Refresh" → same ConfirmDialog → listCacheKeys({cursor:0, match})
```

Load = one SCAN page + ~100 metadata reads (no `GET`, no whole-keyspace load). Non-disruptive.

---

## 4. Components

### 4.1 `lib/infrastructure/redis-cache-repository.ts`
- **Add** `scanKeys(cursor: number, match: string, count = 100): Promise<{ keys: string[]; nextCursor: number }>` → `client.scan(cursor, { MATCH: match || "*", COUNT: count })`. Single SCAN step (not the exhaustive loop).
- **Add** `getKeyMeta(key): Promise<{ ttl?: number; type: string; size: number }>` → `TYPE` + `TTL` + `MEMORY USAGE` (with the existing size fallback, but **no `GET`** for value). 
- **Add** `dbSize(): Promise<number>` → `DBSIZE`.
- **Keep** `deleteEntry` (DEL), `clearAll` (FLUSHDB), the singleton client. **Remove** reliance on `getAllKeys` (exhaustive) + `getEntry` from the list path (leave `getEntry` for a future value inspector, or remove if unused).

### 4.2 `app/actions/cache-actions.ts`
- **Add** server action `listCacheKeys({ cursor = 0, match = "" }): Promise<{ entries: KeyMeta[]; nextCursor: number; total: number }>` where `KeyMeta = { key, type, ttl?, size }`. It: `scanKeys` → `Promise.all(getKeyMeta)` for that page → `dbSize` (only when cursor===0) → returns. Validates `match` length (≤512) and coerces cursor to a non-negative int.
- **Keep** `invalidateCacheEntry` (DEL) + `clearAllCache` (FLUSHDB). **Remove** `refreshCacheData` (replaced by re-invoking `listCacheKeys`). Drop the old `getCachedData` (or leave unused/removed).

### 4.3 `app/page.tsx`
- Server Component: read session (email) as today; render the shell (`CacheHeader` + `CacheTable`) with **no data** (no `getCachedData`). Passes `userEmail` only.

### 4.4 `components/cache-table.tsx` (client)
- Holds state: `entries`, `nextCursor`, `total`, `match`, `loading`, `scanned` (has the user scanned yet?).
- **Before first scan:** empty state with a **"Scan keys"** button wrapped in `ConfirmDialog` (reuse `components/confirm-dialog.tsx`) with the shared-Redis warning.
- **After scan:** table with columns **Key / Type / Size / Expires / Actions** (Copy, Delete). Search box → debounced (300ms) `listCacheKeys({cursor:0, match:*term*})` (server-side MATCH; replaces the client substring filter). **"Load more"** button when `nextCursor !== 0` → append next page. 
- Delete (DEL one key) + Copy unchanged. After Delete, re-run the current page (or optimistic remove).

### 4.5 `components/cache-header.tsx` (client)
- **Total Keys** = `total` (`DBSIZE`, shown after first scan; "—" before). **Remove the Total Size card.** Last Refreshed stays (set on each scan). **Refresh** button → `ConfirmDialog` → re-run `listCacheKeys({cursor:0, match})`. Clear All unchanged (still FLUSHDB behind its own confirm).
- Header needs to trigger scans/refresh that update the table → lift the scan state to `page.tsx`-level client wrapper OR co-locate header+table in one client component. **Decision:** introduce a small client wrapper `components/cache-browser.tsx` that owns the scan state and renders header + table; `page.tsx` renders `<CacheBrowser userEmail=... />`. Keeps header/table dumb-ish and state in one place.

### 4.6 `lib/domain/cache-entry.ts`
- Replace/augment: `KeyMeta { key: string; type: string; ttl?: number; size: number }` for the list. (The old `CacheEntry` with `value` can be dropped or retained for a future inspector.)

---

## 5. Error handling
- `listCacheKeys` wraps SCAN/meta in try/catch → returns `{ entries: [], nextCursor: 0, total: 0, error }`; the browser shows an inline error (as today's page did).
- `getKeyMeta`: `MEMORY USAGE` failure → size 0 (no value GET fallback in the list path — keep it cheap); `TTL`/`TYPE` failures → default (`ttl` undefined, `type` "unknown").
- A key deleted between SCAN and meta read → meta returns type "none"/ttl none → still listed harmlessly (or filtered).

---

## 6. Testing
- **Repository** (mock redis client): `scanKeys` returns `{keys, nextCursor}` from a mocked `scan`; `getKeyMeta` composes TYPE/TTL/MEMORY USAGE and does **not** call `get`; `dbSize`.
- **Action** `listCacheKeys` (mock repo): page 1 sets `total` (dbSize called), later pages don't; `match` passed through; error path returns empty + error.
- **Client** `cache-browser`/table: no scan on mount (asserts the action isn't called until confirm); "Scan keys" → confirm → action called; "Load more" uses nextCursor; debounced search issues one MATCH call; Refresh re-confirms. (Vitest + a light React test, or at minimum the pure state logic.)

---

## 7. Out of scope (YAGNI / deferred)
- **Value inspector** (view a key's value on demand, type-aware GET/LRANGE/HGETALL/SMEMBERS) — deferred; Core is a key/metadata browser.
- **Read-replica / DB-index** connection — infra follow-up (D2); documented, not built. Note in CLAUDE.md: point at a replica if the Redis grows large enough to care even about paginated scans.
- **Clear All / FLUSHDB** behavior — unchanged (still the whole-DB nuke behind confirm).
- Table **virtualization** — pagination (page size ~100) keeps the DOM small enough; revisit only if a page is still heavy.

---

## 8. Risks / must-verify
1. **`redis` v4 SCAN cursor type** — `client.scan(cursor, {MATCH, COUNT})` returns `{ cursor: number, keys: string[] }`; cursor is a number, `0` means iteration complete. Verify against the installed `redis@^4.6` (Context7/docs) before finalizing the loop-vs-single-step semantics.
2. **MATCH glob vs substring** — the search box maps to `*term*` (Redis glob). Document that it's glob, not regex; `*`/`?`/`[` in the term are glob metacharacters.
3. **SCAN COUNT is a hint** — a page may return fewer/more than COUNT; rely on `nextCursor !== 0` for "more", never on batch length.
4. **State lift** — moving header+table state into `cache-browser` is the largest structural change; keep the SSO/session bits (userEmail) untouched.
5. Build verified on the VM (same repo-root Docker context as the service).
