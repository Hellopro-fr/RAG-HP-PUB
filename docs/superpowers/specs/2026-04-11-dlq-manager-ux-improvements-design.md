# DLQ Manager Service — UX Improvements Design

**Date:** 2026-04-11
**Service:** `apps-microservices/dlq-manager-service`
**Scope:** 5 targeted improvements to the DLQ Manager web UI and backend

---

## Overview

Five improvements to the DLQ Manager Service addressing usability bugs and missing features:

1. Hide archive buttons on archived-only views
2. "View Matches" button on auto-archive rules
3. Rule timing fields (`last_evaluated_at` + `last_archived_at`)
4. Fix search query escaping + clickable error filter
5. Dynamic service name list based on current filters

---

## 1. Hide Archive Buttons on Archived-Only Views

**Problem:** "Archive Selected" and "Archive All Matching" buttons are always visible, even when viewing already-archived messages. This is confusing and could lead to no-op bulk operations.

**Solution:** Frontend-only change in `SearchPage.tsx`.

**Logic:**

```
ARCHIVED_STATUSES = ["Archived", "Auto-Archived"]
isArchivedOnlyView = status filter is non-empty
                     AND every selected status is in ARCHIVED_STATUSES
```

- When `isArchivedOnlyView` is `true`: hide both archive buttons.
- When the status filter is empty (all statuses) or includes any non-archived status ("New", "Re-queued", etc.): buttons stay visible.
- Requeue buttons remain visible in all views (requeuing an archived message is valid).
- The `MessageDetailModal` already has no archive button — no changes needed there.

**Files modified:**
- `frontend/components/dlq/SearchPage.tsx`

---

## 2. "View Matches" Button on Auto-Archive Rules

**Problem:** No way to see which messages a rule archived. Users cannot verify if a rule accidentally archived messages that shouldn't have been.

**Solution:** Add a "View Matches" button per rule on the Rules page. Clicking it navigates to the Search page with the rule's criteria pre-filled.

**Mechanism:**

1. `RulesPage` receives an `onViewRuleMatches(rule)` callback prop from the parent (`page.tsx`).
2. Clicking the button calls this callback with the rule's `search_term` and `filters`.
3. The parent sets `currentPage` to `"search"` and passes the rule's criteria as initial state.
4. `SearchPage` detects the injected criteria, populates:
   - Status filter: `["Auto-Archived"]`
   - Search term: rule's `search_term`
   - Service names: rule's `filters.service_names` (if present)
   - Date range: rule's `filters.date_start` / `filters.date_end` (if present)
5. Triggers a search automatically.

**UI:** Eye icon button in the Actions column of the rules table (alongside delete).

**Edge case:** If a rule has no `search_term` and no `filters`, clicking "View Matches" navigates to Search with only status set to "Auto-Archived" — showing all auto-archived messages.

**Files modified:**
- `frontend/components/dlq/RulesPage.tsx` — add button + callback prop
- `frontend/components/dlq/SearchPage.tsx` — accept and apply injected criteria
- `frontend/app/page.tsx` — wire the callback, manage cross-page state

---

## 3. Rule Timing Fields: `last_evaluated_at` + `last_archived_at`

**Problem:** Rules only show `execution_count`. Users cannot tell when a rule was last checked or when it last did real work.

**Solution:** Add two timestamp fields to rule documents.

| Field | Updated when | Purpose |
|-------|-------------|---------|
| `last_evaluated_at` | Every background cycle (every 60s), regardless of results | "Is the system running?" |
| `last_archived_at` | Only when the rule archives >= 1 message | "When did it last do real work?" |

**Backend changes:**

1. **Index mapping** (`ensure_rules_index` in `es_client.py`): Add `last_evaluated_at` (date) and `last_archived_at` (date) to the `dlq_auto_archive_rules` mapping.

2. **`apply_auto_archive_rule`** in `es_client.py`: After execution:
   - Always update `last_evaluated_at` to current timestamp.
   - If `total_archived > 0`, also update `last_archived_at`.

3. **`create_rule`** in `es_client.py`: Initialize both fields to `null`.

**Frontend changes:**

1. **`AutoArchiveRule` interface** in `api.ts`: Add `last_evaluated_at?: string` and `last_archived_at?: string`.

2. **`RulesPage.tsx`**: Add two columns:
   - "Last Checked" — `last_evaluated_at` as relative time (e.g., "32s ago"), or "Never" if null.
   - "Last Archived" — `last_archived_at` similarly, or "Never" if null.
   - Times older than 24h show absolute date instead of relative.

**Migration:** Existing rules get `null` for both fields. UI handles gracefully. No reindexing needed.

**Files modified:**
- `backend/app/es_client.py` — mapping, `apply_auto_archive_rule`, `create_rule`
- `frontend/lib/api.ts` — interface update
- `frontend/components/dlq/RulesPage.tsx` — new columns

---

## 4. Fix Search Query Escaping + Clickable Error Filter

**Problem:** Searching `error_reason:'Exception("...OSError: [E050]...")'` returns wrong results because Elasticsearch's `query_string` parser misinterprets colons inside the value as field separators.

**Solution (two parts):**

### Part A — Fix field:value search routing

**Current behavior:** If the search term contains `:`, `*`, or `?`, it's passed as-is to `query_string`. This breaks when values contain colons.

**Fix:** In `_build_query`, detect `field:value` patterns where the value contains characters that break `query_string` parsing. Specifically:
- Regex: `^(\w+):['"](.+)['"]$` — matches field-scoped searches where the value is explicitly quoted (e.g., `error_reason:'...'`).
- When matched, extract field name and value, then use `match_phrase` query on that field instead of `query_string`. This bypasses the parser entirely.
- Unquoted field:value patterns (e.g., `service_name:my-service`) continue through the existing `query_string` path since they work correctly today.

General search (no field prefix) continues to use `query_string` with the existing wildcard wrapping logic.

### Part B — Clickable error filter from Unique Errors modal

**Current behavior:** The "View Unique Errors" modal shows a read-only list of (service_name, error_reason) pairs.

**New behavior:**
1. Add `error_reason` as a new filter field in `SearchPage.tsx` filters state.
2. Add `error_reason` handling in `_build_query`: when `filters.error_reason` is present, use a `match_phrase` query on the `error_reason` field (exact match, no `query_string` parsing).
3. In the Unique Errors modal, each row becomes clickable. Clicking populates:
   - `filters.service_names` with the row's service name.
   - `filters.error_reason` with the row's error reason.
4. The modal closes and search triggers automatically.
5. The active error filter is shown as a clearable chip/badge near the search input.

**Files modified:**
- `backend/app/es_client.py` — `_build_query` (field:value detection + `error_reason` filter handling)
- `backend/app/models.py` — add `error_reason` to `SearchRequest.filters` if needed
- `frontend/components/dlq/SearchPage.tsx` — `error_reason` filter state, clickable Unique Errors modal, clearable chip
- `frontend/lib/api.ts` — include `error_reason` in filter params

---

## 5. Dynamic Service Name List Based on Current Filters

**Problem:** The service name dropdown is populated once on mount from `get_dashboard_stats()`, which is hardcoded to "New" messages only. Changing the status filter to "Archived" still shows services that have "New" messages, not services with archived messages.

**Solution:** New backend endpoint + frontend re-fetch logic.

**Backend changes:**

1. **New method `get_service_names(filters)`** in `es_client.py`:
   - Runs a `size: 0` aggregation with `terms` on `service_name` (size: 100).
   - Applies the full filter context (status + date range) using `_build_query`.
   - Returns list of service name buckets.
   - Separate from `get_dashboard_stats` to avoid coupling (dashboard intentionally scoped to "New" for KPIs).

2. **New endpoint `POST /api/services`** in `api.py`:
   - Accepts `filters` (status, date_start, date_end).
   - Returns `{ services: [{ key: string, doc_count: number }] }`.

**Frontend changes:**

1. **New API function** `apiGetServiceNames(filters)` in `api.ts`.

2. **Replace initial fetch** in `SearchPage.tsx`: Instead of calling `apiGetDashboardStats()` on mount for service names, call `apiGetServiceNames()` with current filters.

3. **Re-fetch on filter change:** `useEffect` with dependencies on `filters.status`, `filters.date_start`, `filters.date_end`. When any change, re-fetch service names.

4. **Debounce:** 300ms debounce on re-fetch to avoid rapid-fire calls when multiple filters change.

5. **Preserve selection:** When service list refreshes, keep selected services that still exist. Remove stale ones (existing logic).

**Circular dependency prevention:** Service name filter changes do NOT trigger a service list re-fetch. Only status and date range changes do.

**Files modified:**
- `backend/app/es_client.py` — new `get_service_names` method
- `backend/app/api.py` — new `POST /api/services` endpoint
- `backend/app/models.py` — request model for services endpoint (if needed)
- `frontend/lib/api.ts` — new `apiGetServiceNames` function
- `frontend/components/dlq/SearchPage.tsx` — re-fetch logic with debounce

---

## Files Impact Summary

| File | Changes |
|------|---------|
| `backend/app/es_client.py` | `_build_query` (field:value routing, error_reason filter), `get_service_names` (new), `apply_auto_archive_rule` (timestamps), `ensure_rules_index` (mapping), `create_rule` (init fields) |
| `backend/app/api.py` | `POST /api/services` (new endpoint) |
| `backend/app/models.py` | `error_reason` in filters, services request model |
| `frontend/lib/api.ts` | `AutoArchiveRule` interface (timestamps), `apiGetServiceNames` (new), `error_reason` in filters |
| `frontend/components/dlq/SearchPage.tsx` | Archive button hiding, injected criteria from rules, error_reason filter + chip, dynamic service list re-fetch |
| `frontend/components/dlq/RulesPage.tsx` | "View Matches" button, timestamp columns |
| `frontend/app/page.tsx` | Cross-page state wiring for rule → search navigation |

---

## Out of Scope

- Changes to the Dashboard page aggregations (remains scoped to "New" messages).
- Changes to the `tools/dlq_archiver.py` or `tools/dlq_requeuer.py` scripts.
- Auto-archive rule editing (rules remain create/toggle/delete only).
- Message payload editing or requeue logic changes.
