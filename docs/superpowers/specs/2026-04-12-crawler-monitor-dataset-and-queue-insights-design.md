# Crawler Monitor — Dataset URL Browser & Queue Insights

- **Date:** 2026-04-12
- **Status:** Approved — ready for implementation plan
- **Scope:** `apps-microservices/crawler-monitor-backend`, `apps-microservices/crawler-monitor-frontend`

## 1. Summary

Extend the Crawler Monitor dashboard with URL-level visibility into crawler outputs and queue state:

1. A **3-category URL browser** for each job's dataset: successful URLs, error URLs (with their error message), and non-French URLs. URLs are paginated with search.
2. A **handled-vs-pending filter** in the Queue Explorer, with live counts.
3. A **syntax-highlighted, pretty-printed JSON viewer** for queue files (replaces the current plain `<textarea>`).

No changes are required on `crawler-service` — the dataset directories already exist on disk in the expected layout.

## 2. Motivation

Today the monitor surfaces aggregate statistics (success/error/duration) and a duplicate analyzer, but operators cannot:

- Inspect which specific URLs failed and why, without shelling into the container.
- Distinguish treated URLs from still-queued URLs in a large request queue.
- Read queue file JSON without manually prettifying it.

This feature closes those gaps with minimal backend surface area and a UI that extends the existing two modals rather than adding new entry points.

## 3. Scope

### In scope

- New `GET /api/jobs/:id/dataset/counts` endpoint.
- New `GET /api/jobs/:id/dataset/urls?category&page&limit&search` endpoint.
- Extension of existing `GET /api/jobs/:id/request-queues` with `status` query param and `counts` response field.
- `DatasetAnalyzer` modal refactored into 4 tabs: Succès / Erreurs / Non-FR / Doublons.
- Shared `UrlListBrowser` React component (paginated list + search) used by the 3 URL tabs.
- `RequestQueueEditor` gains a counts bar, a `Tous / Traités / En attente` segmented toggle, and per-row status glyphs.
- Queue file JSON view replaced with `react-simple-code-editor` + `prismjs` (JSON grammar), pretty-printed on load.

### Out of scope (deferred — may be follow-ups)

- Drill-down modal showing the full raw dataset entry from an error row.
- Re-queueing failed URLs back to the crawler from the Erreurs tab.
- Deleting URLs from a dataset via the UI.
- CSV export per category.
- Frontend unit tests (the repo has only stub tests today; introducing a testing framework is a separate initiative).

## 4. Architecture & File Map

### Backend — `apps-microservices/crawler-monitor-backend/server.js`

- Extend `findDatasetDir(jobId, datasetName)` to support the `error-{domain}` prefix (currently only handles main + `nfr-{domain}`).
- Add endpoint: `GET /api/jobs/:id/dataset/counts`.
- Add endpoint: `GET /api/jobs/:id/dataset/urls`.
- Extend endpoint: `GET /api/jobs/:id/request-queues` (new `status` query param, new `counts` field in response).

### Frontend — `apps-microservices/crawler-monitor-frontend/src/App.jsx`

- New component: `UrlListBrowser` (paginated list + debounced search; reused by 3 tabs).
- New component: `DuplicatesTab` (extracted from current `DatasetAnalyzer` body — no behavior change).
- Refactor: `DatasetAnalyzer` becomes a tabbed container (`Succès` / `Erreurs` / `Non-FR` / `Doublons`).
- Modify: `RequestQueueEditor` — counts bar, status toggle, row status glyphs, `react-simple-code-editor` replacing the textarea.

### Frontend dependencies — `apps-microservices/crawler-monitor-frontend/package.json`

Add:
- `react-simple-code-editor` (~3 KB gzipped)
- `prismjs` (~10 KB gzipped, JSON grammar only)

### Crawler service

No changes. Dataset files remain at `CRAWLER_STORAGE_PATH/{jobId}/storage/datasets/`:
- `{domain}/` — successful crawl entries.
- `error-{domain}/` — error entries (contain `errorMessages`, `statusCode`, etc.).
- `nfr-{domain}/` — non-French filtered entries.

## 5. Backend Design

### 5.1 `GET /api/jobs/:id/dataset/counts`

**Purpose:** return the total URL count in each of the 3 categories. Called once when the `Analyser Dataset` modal opens to populate tab badges.

**Response:**
```json
{ "success": 5000, "error": 1234, "nfr": 300 }
```

**Semantics:**
- Counts are the number of JSON files in each dataset directory.
- Missing directory → `0` (not an error).
- Errors scanning a specific directory are logged and that category falls back to `0`.

### 5.2 `GET /api/jobs/:id/dataset/urls`

**Query params:**

| Param | Required | Values | Default |
|-------|----------|--------|---------|
| `category` | yes | `success` \| `error` \| `nfr` | — |
| `page` | no | integer ≥ 1 | 1 |
| `limit` | no | 1–200 | 50 |
| `search` | no | substring, case-insensitive on `url` field | — |

**Response:**
```json
{
  "category": "error",
  "total": 1234,
  "page": 1,
  "totalPages": 25,
  "items": [
    { "url": "https://example.com/a", "error": "HTTP 500 Server Error" },
    { "url": "https://example.com/b", "error": "HTTP 404 Not Found" }
  ]
}
```

**Row shape:**
- `success` and `nfr` categories → `{ url }`
- `error` category → `{ url, error }`
  - `error` is read from `entry.errorMessages[0]` if present.
  - Fallback: `"HTTP <statusCode> <statusText>"` if `statusCode` is set.
  - Fallback: `"Unknown error"` otherwise.

**Implementation notes:**
- Two-pass on disk: `readdir` to enumerate filenames, then `readFile` only for the page slice (unless `search` is set).
- Without `search`: `total` = file count from `readdir` (minus malformed files discovered on the page read); only the requested page slice is parsed.
- With `search`: full scan required — every file is read so we can match `url` against `search` before paginating. `total` reflects matched files.
- Malformed JSON files are logged (`console.warn`) and skipped; they do not count toward `total`.
- The response is bounded (max `limit` = 200) to prevent large payloads.

**Error responses:**
- Unknown `category`: `400 { "error": "Invalid category. Must be one of: success, error, nfr" }`
- Job storage directory missing: `404 { "error": "Job storage not found" }`
- `page < 1` or non-integer: coerced to `1` silently.
- `limit > 200`: capped at `200` silently.

### 5.3 Extension to `GET /api/jobs/:id/request-queues`

**New query param:**
- `status`: `all` (default) | `pending` | `handled`.

**Response (changes marked `NEW`):**
```json
{
  "files": [ ... ],
  "total": 336,
  "counts": {           // NEW
    "total": 523,
    "pending": 336,
    "handled": 187
  }
}
```

**Semantics:**
- `files` and `total` respect the combined `search` + `status` filters. Callers not sending `status` (default = `all`) see identical behavior to today.
- `counts` is always unfiltered — it reflects totals across the whole queue regardless of `status` or `search`. This drives the counts bar in the UI, which must stay constant when the user toggles filters.
- A queue file is considered **handled** iff its JSON has a non-null, non-empty `handledAt` field — same rule already used by `isHandled` elsewhere in `server.js`.

**Backward compatibility:** callers not sending `status` keep the same behavior, plus the new `counts` field they can ignore.

## 6. Frontend Design

### 6.1 `DatasetAnalyzer` tabbed modal

```
┌─ Analyse Dataset ─────────────────────────────────────── [x] ┐
│  [Succès (5,000)] [Erreurs (1,234)] [Non-FR (300)] [Doublons]│
│  ───────────                                                 │
│  ┌─ Search URL… ──────────────────────────────────────────┐  │
│  │ https://example.com/a                                  │  │
│  │ https://example.com/b                                  │  │
│  │ … 48 more                                              │  │
│  └────────────────────────────────────────────────────────┘  │
│    [← Prev]  Page 1 / 100  [Next →]                          │
└──────────────────────────────────────────────────────────────┘
```

- **State** at the `DatasetAnalyzer` level:
  - `activeTab: 'success' | 'error' | 'nfr' | 'duplicates'` (default `'success'`).
  - `counts: { success, error, nfr } | null`, `loadingCounts: boolean`.
- **On mount:** `GET /dataset/counts` → populate tab badges.
- **Tab body rendering:**
  - `success` / `error` / `nfr` → `<UrlListBrowser category={activeTab} />`
  - `duplicates` → `<DuplicatesTab />` (existing duplicate-analysis UI, extracted unchanged).
- **Tab switch:** unmounts previous tab, mounts new one. State does not persist across switches — acceptable for the initial version.

### 6.2 `UrlListBrowser` (new shared component)

- **Props:** `jobId`, `category: 'success' | 'error' | 'nfr'`, `authFetch`.
- **Internal state:** `items`, `page` (1), `totalPages`, `total`, `searchTerm`, `loading`, `error`.
- **Behavior:**
  - On mount and on `page` / `searchTerm` change, calls `GET /api/jobs/:jobId/dataset/urls?category=X&page=N&search=Y`.
  - Debounces search input at 300 ms; search changes reset `page` to 1.
  - Uses the existing pagination UX (Prev / Page X / Y / Next) already established in `RequestQueueEditor`.
- **Row layout:**
  - `success` / `nfr`: one line — `url` (clickable, opens in new tab with `target="_blank" rel="noopener"`).
  - `error`: two lines — `url` on top, `error` below in `text-red-400 text-xs`.
- **States:**
  - Empty: _"Aucune URL dans cette catégorie."_
  - Error: red banner with a retry button that re-fires the last fetch.
  - Loading: centered spinner in the tab body.

### 6.3 `RequestQueueEditor` — filter + counts + status glyphs

```
┌─ Explorer Queue ──────────────────────────────────────── [x] ┐
│  (LEFT PANEL)                                                │
│  ┌─ Counts bar ─────────────────────────────────────────┐    │
│  │  Total 523  |  ✓ Traités 187  |  ○ En attente 336    │    │
│  └──────────────────────────────────────────────────────┘    │
│  [Tous] [✓ Traités] [○ En attente]       ← segmented toggle  │
│  [Search URL…]                                               │
│  ○ https://example.com/foo   GET  retry:0                    │
│  ✓ https://example.com/bar   GET  retry:2                    │
│  [← Prev]  Page 1 / 7  [Next →]                              │
│  [Analyser] [Nettoyer] [Tout Supprimer]                      │
└──────────────────────────────────────────────────────────────┘
```

- **New state:**
  - `statusFilter: 'all' | 'pending' | 'handled'` (default `'all'`).
  - `counts: { total, pending, handled } | null`.
- **Fetch URL:** `GET /request-queues?...&status=${statusFilter}`.
- **On every fetch response:** update `counts` from the response's new `counts` field.
- **Status glyph** on each row, driven by the file's `handledAt`:
  - `○` (gray) — pending.
  - `✓` (green) — handled.
- **Segmented toggle** — three pills; active pill highlighted blue; changing it resets `page` to 1.
- **Counts bar** — sticky below modal header; re-renders on every list refresh (stays fresh after clean-patterns, drop-queue, or save).

### 6.4 JSON viewer in `RequestQueueEditor`

Replace the right-panel `<textarea>` with `react-simple-code-editor` + `prismjs`:

```jsx
import Editor from 'react-simple-code-editor';
import Prism from 'prismjs';
import 'prismjs/components/prism-json';

<Editor
  value={content}
  onValueChange={setContent}
  highlight={code => Prism.highlight(code, Prism.languages.json, 'json')}
  padding={12}
  textareaClassName="font-mono text-sm"
  preClassName="font-mono text-sm"
  className="bg-gray-900 border border-gray-700 rounded min-h-[400px]"
/>
```

**Pretty-print on load** in `fetchFile()`:
```js
try {
  setContent(JSON.stringify(JSON.parse(raw), null, 2));
} catch {
  setContent(raw); // malformed JSON — leave untouched so user can fix it
}
```

**Token colors** (dark bg, Tailwind-aligned):

| Token | Class |
|-------|-------|
| Property (keys) | `text-cyan-400` |
| String | `text-green-400` |
| Number | `text-orange-400` |
| Boolean / null | `text-purple-400` |
| Punctuation | `text-gray-500` |

Delivered as a small `<style>` block scoped under a wrapper class to avoid leaking globally.

**Format** button behavior unchanged: runs `JSON.stringify(JSON.parse(content), null, 2)`. Useful after manual edits or pasted minified JSON.

**Save** behavior unchanged: validates JSON client-side, then POSTs the raw string; backend validates again.

## 7. Error Handling

### Backend

| Condition | Response |
|-----------|----------|
| Dataset directory missing | Empty results (`total: 0, items: []`) — not an error |
| Malformed JSON file | Logged (`console.warn`), skipped, not counted |
| Unknown `category` | `400 { error: "Invalid category..." }` |
| Invalid `page` / `limit` | Coerced silently to valid values |
| Job storage not found | `404 { error: "Job storage not found" }` |

### Frontend

| Condition | UX |
|-----------|----|
| Network / 5xx | Red banner in tab/list body + `[Réessayer]` button that re-fires last fetch |
| 401 Unauthorized | Triggers existing `handleLogout()`; user returns to login |
| Prism fails on weird content | Prism is permissive; non-highlightable regions render as plain text |
| Pretty-print fails on load (malformed JSON) | `catch` block keeps raw content visible so the user can fix it |

## 8. Testing Plan

### Backend — `apps-microservices/crawler-monitor-backend/tests/server.test.js`

Fixtures: create a temporary `CRAWLER_STORAGE_PATH` containing a synthetic job with the 3 datasets and a queue directory. Tests use `node:test` (already available).

| # | Test | Assertion |
|---|------|-----------|
| 1 | `dataset/counts returns accurate counts` | Returns `{success, error, nfr}` matching fixture file counts |
| 2 | `dataset/counts returns 0 for missing category` | `error: 0` when `error-{domain}` directory absent |
| 3 | `dataset/urls paginates correctly` | `page=2&limit=10` returns items 11–20; `totalPages` correct |
| 4 | `dataset/urls search is case-insensitive` | `search=EXAMPLE` matches `https://example.com/...` |
| 5 | `dataset/urls returns {url, error} for error category` | Error rows include `error` derived from `errorMessages[0]` |
| 6 | `dataset/urls returns 400 on invalid category` | Rejects `category=foo` |
| 7 | `dataset/urls skips malformed JSON files` | One bad file in fixture → request succeeds, bad file excluded from results |
| 8 | `request-queues status=pending excludes handled` | Only files without `handledAt` in results |
| 9 | `request-queues status=handled excludes pending` | Only files with non-null `handledAt` in results |
| 10 | `request-queues always returns counts` | `counts: {total, pending, handled}` matches fixture totals, independent of `status` value |

### Frontend — manual QA checklist (no framework yet)

- [ ] Open `Analyser Dataset` on a job with many URLs — all 3 tabs show correct counts.
- [ ] Search `example` in the Erreurs tab → list filters; `Page X / Y` updates.
- [ ] Click a URL → opens in new tab.
- [ ] Switch between tabs → each shows its own list independently.
- [ ] Open `Explorer Queue` → counts bar displays Total / Traités / En attente.
- [ ] Toggle `[Traités]` / `[En attente]` → list shrinks appropriately; counts stay constant.
- [ ] Click a queue file → JSON opens pretty-printed and syntax-highlighted.
- [ ] Edit & save → backend accepts; file reloads with new content still highlighted.
- [ ] Drop Queue → counts go to 0; filter toggle remains functional.

## 9. Acceptance Criteria

- Users can open `Analyser Dataset` and see 4 tabs: Succès, Erreurs, Non-FR, Doublons, with counts visible on each tab label.
- Each of the 3 URL tabs supports server-side pagination (50 per page default, max 200) and URL substring search.
- The Erreurs tab shows the error message beneath each URL.
- `Explorer Queue` shows Total / Traités / En attente counts at the top, and a `[Tous] [Traités] [En attente]` toggle that filters the list.
- Row-level status glyph (`○` / `✓`) is visible on every queue row.
- Queue JSON opens pretty-printed and syntax-highlighted; editing and saving works as before.
- Backend tests (10 listed above) pass.
- No regressions in existing modals (duplicate analysis, clean-patterns, drop-queue, queue save).

## 10. Open Questions / Future Work

- **Drill-down** from an error row to the full raw dataset entry (modal with the entire JSON). Easy follow-up, but not required for this feature.
- **CSV export** per category. If operators routinely export URL lists for external tools, add a `Télécharger CSV` button per tab.
- **Re-queue a failed URL** from the Erreurs tab. Requires coordination with `crawler-service` (a write path that edits the request queue); not addressed here.
- **Delete URLs from a dataset** via UI. Destructive, explicitly out of scope.
- **Preserving tab/filter state** across modal reopens. Currently reset on unmount. Can be lifted to a higher state if operators ask for it.
