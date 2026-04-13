# DLQ Manager UX Improvements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 5 UX improvements to the DLQ Manager Service: conditional archive buttons, rule match viewer, rule timestamps, search query fix + clickable error filter, and dynamic service name list.

**Architecture:** Backend-first for features requiring new endpoints/logic (tasks 1-3), then frontend integration (tasks 4-7). Each task produces a committable unit. All paths are relative to `apps-microservices/dlq-manager-service/`.

**Tech Stack:** Python 3.10 / FastAPI (backend), Next.js 16 / React 19 / TypeScript (frontend), Elasticsearch 9.x

**Spec:** `docs/superpowers/specs/2026-04-11-dlq-manager-ux-improvements-design.md`

---

### Task 1: Backend — Fix `_build_query` search routing for quoted field:value patterns

**Goal:** When the user searches `error_reason:'some value with: colons'`, route to a `match_phrase` query instead of `query_string` to avoid Elasticsearch parser misinterpretation.

**Files:**
- Modify: `backend/app/es_client.py:349-366` (`_build_query` method)

**Acceptance Criteria:**
- [ ] Search term `error_reason:'Exception("Erreur: OSError")'` uses `match_phrase` on `error_reason`, not `query_string`
- [ ] Unquoted terms like `service_name:my-service` still go through `query_string` (no behavior change)
- [ ] General search terms without field prefix still get wildcard wrapping

**Verify:** Manual test via `curl` against the running backend, or unit test if pytest is set up.

**Steps:**

- [ ] **Step 1: Add `re` import and field:value detection in `_build_query`**

In `backend/app/es_client.py`, add `import re` at the top (line 1 area), then replace the search_term block in `_build_query` (lines 353-366):

```python
import re

# Inside _build_query, replace the search_term handling block:
        if search_term:
            # Detect quoted field:value pattern like error_reason:'...' or error_reason:"..."
            field_value_match = re.match(r'^(\w+):[\'"](.+)[\'"]$', search_term, re.DOTALL)
            if field_value_match:
                field_name = field_value_match.group(1)
                field_value = field_value_match.group(2)
                query["bool"]["must"].append({
                    "match_phrase": {
                        field_name: field_value
                    }
                })
            elif any(char in search_term for char in [':', '*', '?']):
                # Advanced query_string syntax (unquoted field:value, wildcards, etc.)
                query["bool"]["must"].append({
                    "query_string": {
                        "query": search_term,
                        "fields": ["error_reason", "original_payload.*", "service_name"],
                        "lenient": True
                    }
                })
            else:
                # Simple search term — wrap with wildcards
                query["bool"]["must"].append({
                    "query_string": {
                        "query": f"*{search_term}*",
                        "fields": ["error_reason", "original_payload.*", "service_name"],
                        "lenient": True
                    }
                })
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/es_client.py
git commit -m "fix(dlq-manager): route quoted field:value search to match_phrase query"
```

---

### Task 2: Backend — Add `error_reason` filter + `get_service_names` endpoint + rule timestamps

**Goal:** Three backend additions: (a) support `error_reason` in filter queries, (b) new `/api/services` endpoint returning service names for current filters, (c) add `last_evaluated_at` and `last_archived_at` fields to auto-archive rules.

**Files:**
- Modify: `backend/app/es_client.py` — `_build_query` (error_reason filter), new `get_service_names` method, `ensure_rules_index` (mapping), `create_rule` (init), `apply_auto_archive_rule` (timestamps)
- Modify: `backend/app/api.py` — new `/api/services` endpoint
- Modify: `backend/app/models.py` — new `ServiceNamesRequest` model
- Modify: `backend/main.py` — update `background_rule_processor` to pass timing updates

**Acceptance Criteria:**
- [ ] `_build_query` handles `filters.error_reason` as a `match_phrase` query
- [ ] `POST /api/services` returns `{ services: [{ key, doc_count }] }` respecting status + date filters
- [ ] Rules index mapping includes `last_evaluated_at` and `last_archived_at` date fields
- [ ] `apply_auto_archive_rule` updates `last_evaluated_at` every call, `last_archived_at` only when archiving > 0
- [ ] New rules are created with both timestamp fields set to `null`

**Verify:** `curl -X POST http://localhost:8585/api/services -H 'Content-Type: application/json' -d '{"filters":{"status":["Archived"]}}'` returns services with archived messages.

**Steps:**

- [ ] **Step 1: Add `error_reason` filter handling in `_build_query`**

In `backend/app/es_client.py`, inside `_build_query` after the `service_names` block (after line 379), add:

```python
            error_reason = filters.get("error_reason")
            if error_reason and isinstance(error_reason, str):
                query["bool"]["must"].append({
                    "match_phrase": {"error_reason": error_reason}
                })
```

- [ ] **Step 2: Add `get_service_names` method to `ElasticsearchClient`**

In `backend/app/es_client.py`, add this method after `get_dashboard_stats` (after line 347):

```python
    async def get_service_names(self, filters: Dict = None) -> List[Dict[str, Any]]:
        """Returns service name buckets respecting the full filter context (status + date range)."""
        query = self._build_query(filters or {}, "")
        body = {
            "size": 0,
            "query": query,
            "aggs": {
                "by_service": {"terms": {"field": "service_name", "size": 100}}
            }
        }
        response = await self.client.search(index=ELASTIC_INDEX_NAME, body=body)
        return response['aggregations']['by_service']['buckets']
```

- [ ] **Step 3: Add `ServiceNamesRequest` model**

In `backend/app/models.py`, add at the end:

```python
class ServiceNamesRequest(BaseModel):
    filters: Optional[Dict[str, Any]] = None
```

- [ ] **Step 4: Add `/api/services` endpoint**

In `backend/app/api.py`, add the import for `ServiceNamesRequest` in the imports line (line 12), then add the endpoint after the dashboard-stats endpoint (after line 139):

```python
@router.post("/services")
async def get_service_names(request: ServiceNamesRequest, es_client: ElasticsearchClient = Depends(get_es_client)):
    """Returns the list of service names matching the given filters (status, date range)."""
    buckets = await es_client.get_service_names(filters=request.filters)
    return {"services": buckets}
```

- [ ] **Step 5: Update rules index mapping with timestamp fields**

In `backend/app/es_client.py`, in `ensure_rules_index` (line 49 area), add two fields inside the `"properties"` dict after `"execution_count"`:

```python
                                "execution_count": {"type": "integer"},
                                "last_evaluated_at": {"type": "date"},
                                "last_archived_at": {"type": "date"}
```

- [ ] **Step 6: Initialize timestamps to `None` in `create_rule`**

In `backend/app/es_client.py`, in `create_rule` (line 89 area), add after `rule_data['execution_count'] = 0`:

```python
        rule_data['last_evaluated_at'] = None
        rule_data['last_archived_at'] = None
```

- [ ] **Step 7: Update `apply_auto_archive_rule` to set timestamps**

In `backend/app/es_client.py`, in `apply_auto_archive_rule`, replace the return block (lines 147-150) with:

```python
            # Update rule timestamps after execution
            if rule_id:
                now_iso = datetime.now(timezone.utc).isoformat()
                update_body = {"last_evaluated_at": now_iso}
                if total_archived > 0:
                    update_body["last_archived_at"] = now_iso
                try:
                    await self.client.update(
                        index=RULES_INDEX_NAME,
                        id=rule_id,
                        body={"doc": update_body}
                    )
                except Exception as e:
                    print(f"Error updating rule timestamps for {rule_id}: {e}")

            return total_archived
        except Exception as e:
            print(f"Error applying auto-archive rule {rule.get('name')}: {e}")
            return total_archived
```

- [ ] **Step 8: Update `background_rule_processor` to always call `apply_auto_archive_rule`**

The current `main.py` already calls `apply_auto_archive_rule` for every active rule each cycle (line 28), and the timestamp update happens inside that method. No structural change needed to `main.py` — the timestamps are set inside `apply_auto_archive_rule` regardless of whether messages were archived.

- [ ] **Step 9: Commit**

```bash
git add backend/app/es_client.py backend/app/api.py backend/app/models.py
git commit -m "feat(dlq-manager): add error_reason filter, services endpoint, and rule timestamps"
```

---

### Task 3: Frontend — Add `apiGetServiceNames` and update `AutoArchiveRule` interface

**Goal:** Add the new API function for dynamic service names and update the rule type with timestamp fields.

**Files:**
- Modify: `frontend/lib/api.ts`

**Acceptance Criteria:**
- [ ] `apiGetServiceNames` function exists and calls `POST /api/services`
- [ ] `AutoArchiveRule` interface includes `last_evaluated_at` and `last_archived_at`

**Verify:** TypeScript compilation succeeds (`pnpm build` in `frontend/`).

**Steps:**

- [ ] **Step 1: Add `apiGetServiceNames` function**

In `frontend/lib/api.ts`, add after `apiGetDashboardStats` (after line 97):

```typescript
export const apiGetServiceNames = (filters?: Record<string, any>) => {
    return api.post<{ services: ServiceBucket[] }>('/services', { filters: filters || {} });
};
```

- [ ] **Step 2: Update `AutoArchiveRule` interface**

In `frontend/lib/api.ts`, update the `AutoArchiveRule` interface (lines 71-80) to add the two timestamp fields:

```typescript
export interface AutoArchiveRule {
    _id?: string;
    name: string;
    description?: string;
    search_term?: string;
    filters?: Record<string, any>;
    is_active: boolean;
    created_at?: string;
    execution_count?: number;
    last_evaluated_at?: string;
    last_archived_at?: string;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(dlq-manager): add apiGetServiceNames and rule timestamp fields to API types"
```

---

### Task 4: Frontend — Hide archive buttons on archived-only views

**Goal:** Conditionally hide "Archive Selected" and "Archive All Matching" buttons when the status filter exclusively contains archived statuses.

**Files:**
- Modify: `frontend/components/dlq/SearchPage.tsx`

**Acceptance Criteria:**
- [ ] Status filter `["Archived"]` → archive buttons hidden, requeue buttons visible
- [ ] Status filter `["Auto-Archived"]` → archive buttons hidden
- [ ] Status filter `["Archived", "Auto-Archived"]` → archive buttons hidden
- [ ] Status filter `["New", "Archived"]` → archive buttons visible
- [ ] Status filter `[]` (empty / all) → archive buttons visible

**Verify:** Visual check in browser — toggle status filter and observe button visibility.

**Steps:**

- [ ] **Step 1: Add `isArchivedOnlyView` derived state**

In `frontend/components/dlq/SearchPage.tsx`, add after the `loadingAction` state declaration (after line 75):

```typescript
  const ARCHIVED_STATUSES = ['Archived', 'Auto-Archived'];
  const isArchivedOnlyView = filters.status.length > 0 && filters.status.every(s => ARCHIVED_STATUSES.includes(s));
```

- [ ] **Step 2: Conditionally hide "Archive Selected" button**

In `SearchPage.tsx`, wrap the "Archive Selected" button (lines 481-489) with the condition. Replace:

```typescript
              <Button 
                onClick={() => handleBulkAction('archive')} 
                style={{ backgroundColor: "var(--gris-primary)", color: "white" }} 
                className="hover:opacity-90 w-full sm:w-auto"
                disabled={!!loadingAction}
              >
                {loadingAction === 'archive-selected' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Archive Selected
              </Button>
```

With:

```typescript
              {!isArchivedOnlyView && (
                <Button 
                  onClick={() => handleBulkAction('archive')} 
                  style={{ backgroundColor: "var(--gris-primary)", color: "white" }} 
                  className="hover:opacity-90 w-full sm:w-auto"
                  disabled={!!loadingAction}
                >
                  {loadingAction === 'archive-selected' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Archive Selected
                </Button>
              )}
```

- [ ] **Step 3: Conditionally hide "Archive All Matching" button**

In `SearchPage.tsx`, wrap the "Archive All Matching" button (lines 502-510) similarly. Replace:

```typescript
              <Button
                onClick={handleArchiveByFilter}
                style={{ backgroundColor: "var(--gris-primary)", color: "white" }}
                disabled={totalResults === 0 || !!loadingAction}
                className="hover:opacity-90 disabled:opacity-50 w-full sm:w-auto"
              >
                {loadingAction === 'archive-all' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Archive All Matching
              </Button>
```

With:

```typescript
              {!isArchivedOnlyView && (
                <Button
                  onClick={handleArchiveByFilter}
                  style={{ backgroundColor: "var(--gris-primary)", color: "white" }}
                  disabled={totalResults === 0 || !!loadingAction}
                  className="hover:opacity-90 disabled:opacity-50 w-full sm:w-auto"
                >
                  {loadingAction === 'archive-all' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Archive All Matching
                </Button>
              )}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/components/dlq/SearchPage.tsx
git commit -m "feat(dlq-manager): hide archive buttons when viewing archived-only messages"
```

---

### Task 5: Frontend — Dynamic service name list based on current filters

**Goal:** Replace the one-time dashboard stats call for service names with the new `/api/services` endpoint, re-fetching when status or date filters change.

**Files:**
- Modify: `frontend/components/dlq/SearchPage.tsx`

**Acceptance Criteria:**
- [ ] Service name dropdown updates when status filter changes
- [ ] Service name dropdown updates when date filters change
- [ ] Service name dropdown does NOT re-fetch when service_names filter changes (no circular dependency)
- [ ] Debounced at 300ms to avoid rapid-fire API calls
- [ ] Stale service selections are cleaned when list refreshes

**Verify:** Visual check — change status to "Archived", observe service list updates to show services with archived messages.

**Steps:**

- [ ] **Step 1: Add `apiGetServiceNames` to imports**

In `frontend/components/dlq/SearchPage.tsx`, update the import from `@/lib/api` (line 11) to include `apiGetServiceNames`:

```typescript
import { apiGetDashboardStats, apiGetServiceNames, apiSearchMessages, apiBulkRequeue, apiBulkArchive, apiRequeueByFilter, apiArchiveByFilter, apiGetTaskStatus, apiGetUniqueErrors, Message, UniqueErrorBucket } from "@/lib/api";
```

- [ ] **Step 2: Replace the service name fetch `useEffect`**

Replace the existing `useEffect` that calls `apiGetDashboardStats` for service names (lines 89-109) with:

```typescript
  // Fetch service names dynamically based on current status + date filters
  useEffect(() => {
    const debounceTimer = setTimeout(() => {
      const serviceFilters: Record<string, any> = {};
      if (filters.status.length > 0) {
        serviceFilters.status = filters.status;
      }
      if (filters.date_start instanceof Date) {
        serviceFilters.date_start = filters.date_start.toISOString();
      }
      if (filters.date_end instanceof Date) {
        serviceFilters.date_end = filters.date_end.toISOString();
      }

      apiGetServiceNames(serviceFilters).then(response => {
        const options = response.data.services.map(bucket => ({
          value: bucket.key,
          label: bucket.key,
        }));
        setServiceOptions(options);

        // Purge stale service_names that no longer exist in current options
        const validKeys = new Set(options.map((o: { value: string }) => o.value));
        setFilters((prev: Filters) => {
          const cleaned = prev.service_names.filter((s: string) => validKeys.has(s));
          if (cleaned.length !== prev.service_names.length) {
            return { ...prev, service_names: cleaned };
          }
          return prev;
        });
      }).catch(err => {
        console.error("Failed to fetch service names for filters", err);
      });
    }, 300);

    return () => clearTimeout(debounceTimer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(filters.status), filters.date_start?.getTime(), filters.date_end?.getTime()]);
```

- [ ] **Step 3: Commit**

```bash
git add frontend/components/dlq/SearchPage.tsx
git commit -m "feat(dlq-manager): dynamic service name list based on current status/date filters"
```

---

### Task 6: Frontend — Clickable error filter from Unique Errors modal

**Goal:** Add `error_reason` as a filter, make Unique Errors modal rows clickable to populate it, show a clearable chip.

**Files:**
- Modify: `frontend/components/dlq/SearchPage.tsx` — add `error_reason` to filters state, clearable chip, pass callback to modal
- Modify: `frontend/components/dlq/UniqueErrorsModal.tsx` — make rows clickable

**Acceptance Criteria:**
- [ ] Clicking an error row in the Unique Errors modal sets the `error_reason` filter and closes the modal
- [ ] The selected error is visible as a clearable chip/badge near the search input
- [ ] Clearing the chip removes the `error_reason` filter and triggers a new search
- [ ] The `error_reason` filter is sent to the backend in the `filters` payload

**Verify:** Open Unique Errors modal → click a row → modal closes, chip appears, search results show only that error.

**Steps:**

- [ ] **Step 1: Add `error_reason` to `Filters` interface and state**

In `frontend/components/dlq/SearchPage.tsx`, update the `Filters` interface (lines 18-23):

```typescript
interface Filters {
    service_names: string[];
    status: string[];
    date_start?: Date;
    date_end?: Date;
    error_reason?: string;
}
```

- [ ] **Step 2: Include `error_reason` in `getActiveFiltersPayload`**

In `frontend/components/dlq/SearchPage.tsx`, update `getActiveFiltersPayload` (lines 112-125). Add handling for `error_reason` after the array check. Replace the function:

```typescript
  const getActiveFiltersPayload = useCallback(() => {
    const activeFilters: Record<string, any> = {};
    (Object.keys(filters) as Array<keyof Filters>).forEach(key => {
      const value = filters[key];
      if (key === 'date_start' || key === 'date_end') {
        if (value instanceof Date) {
          activeFilters[key] = value.toISOString();
        }
      } else if (key === 'error_reason') {
        if (value && typeof value === 'string') {
          activeFilters[key] = value;
        }
      } else if (Array.isArray(value) && value.length > 0) {
        activeFilters[key] = value;
      }
    });
    return activeFilters;
  }, [filters]);
```

- [ ] **Step 3: Add callback handler for error selection**

In `frontend/components/dlq/SearchPage.tsx`, add a handler after `handleViewUniqueErrors` (after line 312):

```typescript
  const handleSelectError = (serviceName: string, errorReason: string) => {
    setFilters(prev => ({
      ...prev,
      service_names: [serviceName],
      error_reason: errorReason,
    }));
    setShowUniqueErrors(false);
    // Search will trigger via the useEffect on filters change
  };
```

- [ ] **Step 4: Add clearable chip for active error filter**

In `frontend/components/dlq/SearchPage.tsx`, add a chip display after the search input's closing `</div>` (after line 377, before the Service Names label):

```typescript
            {filters.error_reason && (
              <div className="md:col-span-2 flex items-center gap-2">
                <span className="text-sm text-gris-primary">Active Error Filter:</span>
                <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium bg-bleu-light text-bleu-primary border border-bleu-primary/20 max-w-full">
                  <span className="truncate">{filters.error_reason}</span>
                  <button
                    type="button"
                    onClick={() => setFilters(prev => ({ ...prev, error_reason: undefined }))}
                    className="ml-1 hover:text-rouge-primary transition-colors shrink-0"
                    aria-label="Clear error filter"
                  >
                    ×
                  </button>
                </span>
              </div>
            )}
```

- [ ] **Step 5: Pass `onSelectError` callback to `UniqueErrorsModal`**

In `frontend/components/dlq/SearchPage.tsx`, update the `UniqueErrorsModal` rendering (lines 563-570):

```typescript
      {showUniqueErrors && (
        <UniqueErrorsModal
          buckets={uniqueErrorBuckets}
          totalUnique={uniqueErrorTotal}
          loading={loadingUniqueErrors}
          onClose={() => setShowUniqueErrors(false)}
          onSelectError={handleSelectError}
        />
      )}
```

- [ ] **Step 6: Make `UniqueErrorsModal` rows clickable**

In `frontend/components/dlq/UniqueErrorsModal.tsx`, update the interface (lines 10-15):

```typescript
interface UniqueErrorsModalProps {
  buckets: UniqueErrorBucket[];
  totalUnique: number;
  loading: boolean;
  onClose: () => void;
  onSelectError?: (serviceName: string, errorReason: string) => void;
}
```

Update the component signature (line 19):

```typescript
export default function UniqueErrorsModal({ buckets, totalUnique, loading, onClose, onSelectError }: UniqueErrorsModalProps) {
```

Update the table row (line 152) to be clickable:

```typescript
                    <tr
                      key={`${bucket.service_name}-${bucket.error_reason}`}
                      className={`border-b border-gris-blanc transition-colors ${onSelectError ? 'hover:bg-bleu-light cursor-pointer' : 'hover:bg-clair-4'}`}
                      onClick={() => onSelectError?.(bucket.service_name, bucket.error_reason)}
                      title={onSelectError ? "Click to filter by this error" : undefined}
                    >
```

- [ ] **Step 7: Commit**

```bash
git add frontend/components/dlq/SearchPage.tsx frontend/components/dlq/UniqueErrorsModal.tsx
git commit -m "feat(dlq-manager): clickable error filter from Unique Errors modal with clearable chip"
```

---

### Task 7: Frontend — "View Matches" button + rule timestamps on Rules page

**Goal:** Add a "View Matches" eye icon per rule that navigates to Search with the rule's criteria pre-filled, and display `last_evaluated_at` / `last_archived_at` columns.

**Files:**
- Modify: `frontend/components/dlq/RulesPage.tsx` — add button, timestamp columns, callback prop
- Modify: `frontend/components/dlq/SearchPage.tsx` — accept injected criteria from rules
- Modify: `frontend/app/page.tsx` — wire cross-page state

**Acceptance Criteria:**
- [ ] "View Matches" button per rule navigates to Search with rule's `search_term`, `filters`, and status `["Auto-Archived"]`
- [ ] "Last Checked" column shows `last_evaluated_at` as relative time or "Never"
- [ ] "Last Archived" column shows `last_archived_at` as relative time or "Never"
- [ ] Times older than 24h show absolute date

**Verify:** Click "View Matches" on a rule → Search page opens with pre-filled filters. Rules table shows timestamp columns.

**Steps:**

- [ ] **Step 1: Update `page.tsx` to manage cross-page state**

Replace the entire `frontend/app/page.tsx`:

```typescript
"use client"

import * as React from "react";
import { useState } from "react"
import Sidebar from "@/components/dlq/Sidebar"
import Dashboard from "@/components/dlq/Dashboard"
import SearchPage from "@/components/dlq/SearchPage"
import RulesPage from "@/components/dlq/RulesPage"
import { SidebarProvider, SidebarInset, SidebarTrigger } from "@/components/ui/sidebar"
import { AutoArchiveRule } from "@/lib/api"

type Page = "dashboard" | "search" | "rules"

export interface RuleCriteria {
  search_term?: string;
  filters?: Record<string, any>;
}

export default function App() {
  const[currentPage, setCurrentPage] = useState<Page>("dashboard")
  const [injectedRuleCriteria, setInjectedRuleCriteria] = useState<RuleCriteria | null>(null);

  const getPageTitle = () => {
    switch (currentPage) {
      case "dashboard": return "Dashboard";
      case "search": return "Search & Re-queue";
      case "rules": return "Auto-Archive Rules";
    }
  }

  const handleViewRuleMatches = (rule: AutoArchiveRule) => {
    setInjectedRuleCriteria({
      search_term: rule.search_term,
      filters: rule.filters,
    });
    setCurrentPage("search");
  };

  const handleClearInjectedCriteria = () => {
    setInjectedRuleCriteria(null);
  };

  return (
    <SidebarProvider>
      <Sidebar currentPage={currentPage} onPageChange={setCurrentPage} />
      <SidebarInset className="flex flex-col h-screen overflow-hidden bg-white-light w-full min-w-0">
        <header className="h-16 shrink-0 border-b border-gris-blanc bg-white-primary flex items-center px-4 md:px-8 gap-4">
          <SidebarTrigger />
          <h1 className="text-xl font-semibold text-noir-primary truncate">
            {getPageTitle()}
          </h1>
        </header>
        <main className="flex-1 overflow-auto">
            {currentPage === "dashboard" && <Dashboard />}
            {currentPage === "search" && (
              <SearchPage
                injectedCriteria={injectedRuleCriteria}
                onClearInjectedCriteria={handleClearInjectedCriteria}
              />
            )}
            {currentPage === "rules" && (
              <RulesPage onViewRuleMatches={handleViewRuleMatches} />
            )}
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
```

- [ ] **Step 2: Add injected criteria handling to `SearchPage`**

In `frontend/components/dlq/SearchPage.tsx`, update the component signature and add a `useEffect` to apply injected criteria.

Update the export line (line 61):

```typescript
interface SearchPageProps {
  injectedCriteria?: RuleCriteria | null;
  onClearInjectedCriteria?: () => void;
}

export default function SearchPage({ injectedCriteria, onClearInjectedCriteria }: SearchPageProps = {}) {
```

Add the import at the top of the file:

```typescript
import { RuleCriteria } from "@/app/page"
```

Add a `useEffect` to apply injected criteria, after the polling cleanup effect (after line 87):

```typescript
  // Apply injected criteria from Rules page "View Matches" button
  useEffect(() => {
    if (injectedCriteria) {
      const newFilters: Filters = {
        service_names: injectedCriteria.filters?.service_names || [],
        status: ['Auto-Archived'],
        date_start: injectedCriteria.filters?.date_start ? new Date(injectedCriteria.filters.date_start) : undefined,
        date_end: injectedCriteria.filters?.date_end ? new Date(injectedCriteria.filters.date_end) : undefined,
        error_reason: undefined,
      };
      setFilters(newFilters);
      setSearchTerm(injectedCriteria.search_term || "");
      setCurrentPage(1);
      onClearInjectedCriteria?.();
    }
  }, [injectedCriteria]);
```

- [ ] **Step 3: Add relative time helper and timestamp columns to `RulesPage`**

In `frontend/components/dlq/RulesPage.tsx`, update imports (line 5) to include `AutoArchiveRule`:

```typescript
import { apiGetRules, apiToggleRule, apiDeleteRule, AutoArchiveRule } from "@/lib/api"
```

Add the `Eye` icon import (line 8):

```typescript
import { Trash2, AlertCircle, Eye } from "lucide-react"
```

Update the component signature (line 10):

```typescript
interface RulesPageProps {
  onViewRuleMatches?: (rule: AutoArchiveRule) => void;
}

export default function RulesPage({ onViewRuleMatches }: RulesPageProps) {
```

Add a relative time helper function inside the component (after line 13, before `fetchRules`):

```typescript
    const formatRelativeTime = (isoString?: string | null): string => {
        if (!isoString) return "Never";
        const date = new Date(isoString);
        const now = new Date();
        const diffMs = now.getTime() - date.getTime();
        const diffSec = Math.floor(diffMs / 1000);

        if (diffSec < 60) return `${diffSec}s ago`;
        const diffMin = Math.floor(diffSec / 60);
        if (diffMin < 60) return `${diffMin}m ago`;
        const diffHr = Math.floor(diffMin / 60);
        if (diffHr < 24) return `${diffHr}h ago`;

        // Older than 24h: show absolute date
        return date.toLocaleString();
    };
```

- [ ] **Step 4: Update the table header and rows**

In `RulesPage.tsx`, update the `<thead>` (lines 74-80) to add the new columns:

```typescript
                        <thead>
                            <tr className="border-b border-gris-blanc bg-clair-4">
                                <th className="px-6 py-4 text-left text-sm font-semibold text-noir-primary">Rule Name & Description</th>
                                <th className="px-6 py-4 text-left text-sm font-semibold text-noir-primary">Target Conditions</th>
                                <th className="px-6 py-4 text-center text-sm font-semibold text-noir-primary">Executions</th>
                                <th className="px-6 py-4 text-center text-sm font-semibold text-noir-primary">Last Checked</th>
                                <th className="px-6 py-4 text-center text-sm font-semibold text-noir-primary">Last Archived</th>
                                <th className="px-6 py-4 text-center text-sm font-semibold text-noir-primary">Active</th>
                                <th className="px-6 py-4 text-center text-sm font-semibold text-noir-primary">Actions</th>
                            </tr>
                        </thead>
```

In the `<tbody>`, after the Executions `<td>` (after line 98), add two new cells:

```typescript
                                    <td className="px-6 py-4 text-center text-xs text-gris-primary whitespace-nowrap" title={rule.last_evaluated_at || "Never"}>
                                        {formatRelativeTime(rule.last_evaluated_at)}
                                    </td>
                                    <td className="px-6 py-4 text-center text-xs text-gris-primary whitespace-nowrap" title={rule.last_archived_at || "Never"}>
                                        {formatRelativeTime(rule.last_archived_at)}
                                    </td>
```

Update the Actions cell (lines 106-115) to include the "View Matches" button:

```typescript
                                    <td className="px-6 py-4 text-center">
                                        <div className="flex items-center justify-center gap-1">
                                            {onViewRuleMatches && (
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onClick={() => onViewRuleMatches(rule)}
                                                    className="text-bleu-primary hover:bg-bleu-light hover:text-bleu-primary"
                                                    aria-label={`View messages matched by rule ${rule.name}`}
                                                    title="View matched messages"
                                                >
                                                    <Eye className="w-4 h-4" />
                                                </Button>
                                            )}
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                onClick={() => rule._id && handleDelete(rule._id)}
                                                className="text-rouge-primary hover:bg-rouge-light hover:text-rouge-primary"
                                                aria-label={`Delete rule ${rule.name}`}
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </Button>
                                        </div>
                                    </td>
```

- [ ] **Step 5: Update min-width on table for new columns**

In `RulesPage.tsx`, update the table's `min-w` class (line 72):

```typescript
                    <table className="w-full min-w-[1100px]">
```

- [ ] **Step 6: Commit**

```bash
git add frontend/app/page.tsx frontend/components/dlq/SearchPage.tsx frontend/components/dlq/RulesPage.tsx
git commit -m "feat(dlq-manager): add View Matches button and rule timestamp columns"
```

---

## Task Dependency Summary

```
Task 1 (backend: search fix)  ─── no deps ───┐
Task 2 (backend: filters/services/timestamps) ┤
Task 3 (frontend: API types)  ─── after T2 ───┤
Task 4 (frontend: hide archive buttons) ── no deps ──┤
Task 5 (frontend: dynamic services) ── after T2, T3 ─┤
Task 6 (frontend: clickable errors) ── after T1, T2, T3 ─┤
Task 7 (frontend: rules page) ── after T2, T3, T6 ───┘
```

Tasks 1 and 2 can run in parallel. Task 3 depends on Task 2. Tasks 4-7 are frontend and depend on the backend tasks being done first (except Task 4 which is fully independent).
