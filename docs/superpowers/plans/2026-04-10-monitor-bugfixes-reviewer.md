# Monitor Bugfixes & Reviewer Improvement Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two user-reported bugs (blank page after login, incorrect resource metrics) and improve the code reviewer agent to catch these categories of issues in the future.

**Architecture:** Task 1 adds three review dimensions to the code-reviewer agent definition. Task 2 fixes a React Rules of Hooks violation by moving a `useCallback` above a conditional early return. Task 3 replaces process-level metrics with container-level cgroup readings in the crawler's heartbeat publisher.

**Tech Stack:** React 19, Node.js/TypeScript (Crawlee), Linux cgroups v2/v1

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `.claude/agents/code-reviewer.md` | Modify | Add 3 new review dimensions |
| `apps-microservices/crawler-monitor-frontend/src/App.jsx` | Modify | Fix hooks violation |
| `apps-microservices/crawler-service/crawler/src/main.ts` | Modify | Container-level metrics in heartbeat |

---

## Task 1: Improve Code Reviewer Agent

**Files:**
- Modify: `.claude/agents/code-reviewer.md`

**Why:** The reviewer missed two categories of bugs: React runtime rules (hooks called conditionally) and data semantics (process-level vs container-level metrics). Adding explicit review dimensions prevents these gaps.

- [ ] **Step 1: Add three new review passes**

In `.claude/agents/code-reviewer.md`, find the internal multi-pass scan list (passes 1-4). Add three new passes:

```markdown
5. **Pass 5:** Framework runtime correctness (React hooks rules, effect dependency arrays, stale closures)
6. **Pass 6:** End-to-end data semantics (trace values from source → intermediary → display, verify units/meaning match at each step)
7. **Pass 7:** User flow walkthrough (login → main view → detail view → actions — check state transitions and error paths)
```

- [ ] **Step 2: Add the detailed dimension descriptions**

After the existing dimension 7 (Impact Awareness) in the "Your Task" section, add:

```markdown
8. **Framework Runtime Correctness** — For React code:
   - Are all hooks (`useState`, `useEffect`, `useCallback`, `useMemo`, `useRef`) called unconditionally? No hooks after early returns.
   - Are `useEffect` dependency arrays complete? Flag stale closures where a handler references state that isn't in the deps (common with WebSocket/interval handlers).
   - Are event handler references stable or causing unnecessary re-subscriptions?
   For Express/Node.js:
   - Are async error paths handled (unhandled rejections in middleware)?
   - Are shared resources (DB connections, file handles) properly managed?
9. **End-to-End Data Semantics** — For each value displayed to a user:
   - Trace the value from its **source** (sensor, API, database) through any **intermediary** (backend, transform, cache) to the **display** (frontend component).
   - Verify the **meaning** matches at each step: is "CPU" the process CPU or system/container CPU? Is "RAM" the process RSS or total container memory?
   - Flag unit mismatches (bytes vs KB, fraction vs percentage, seconds vs milliseconds).
10. **User Flow Walkthrough** — Walk the critical user-facing flows:
    - For each state transition (null → value, empty → loaded, unauthenticated → authenticated), verify the UI handles it without blank screens, crashes, or stale data.
    - Pay special attention to the first render after a state change (e.g., login sets token → what renders immediately before data loads?).
```

- [ ] **Step 3: Update the internal pass count in the self-check**

Find the self-check instruction that says "Internally, scan the code in multiple passes before producing output:" and update the pass list to include 5, 6, 7.

- [ ] **Step 4: Commit**

```bash
git add .claude/agents/code-reviewer.md
git commit -m "feat(code-reviewer): add framework correctness, data semantics, and user flow dimensions"
```

---

## Task 2: Fix Blank Page After Login (React Hooks Violation)

**Files:**
- Modify: `apps-microservices/crawler-monitor-frontend/src/App.jsx`

**Why:** `fetchJobDetails` is defined with `useCallback` AFTER a conditional `return <LoginPage />` (line 1429-1433). When `token` changes from null to a value, the hook count changes between renders, violating React's Rules of Hooks. React crashes silently → blank page. Manual refresh works because `token` is read from localStorage at init (truthy from start).

- [ ] **Step 1: Read the current App component to identify the exact code block to move**

The current structure (simplified):

```
App = () => {
  // ... all useState, useRef, useMemo declarations ...
  // ... filteredJobs, paginatedJobs, globalStats ...
  // ... handleLogin, handleLogout, authFetch ...
  // ... useEffect (token → fetchJobs) ...
  // ... useEffect (selectedJob → ref sync) ...
  // ... useEffect (WebSocket) ...
  // ... useEffect (replica cleanup) ...
  // ... fetchJobs (useCallback) ...
  // ... fetchCapacity (useCallback) ...
  // ... fetchCallbacks (useCallback) ...

  if (!token) return <LoginPage />;     ← EARLY RETURN (line 1429)

  const fetchJobDetails = useCallback(  ← HOOK AFTER RETURN (line 1433)
    ...
  }, [selectedJob, showRaw]);

  return ( <main dashboard JSX> );
}
```

The fix: move `fetchJobDetails` ABOVE the `if (!token)` early return, alongside the other `useCallback` definitions.

- [ ] **Step 2: Move fetchJobDetails above the early return**

Cut the entire `fetchJobDetails` block (from `const fetchJobDetails = useCallback(` through its closing `}, [selectedJob, showRaw]);`) and paste it BEFORE the `if (!token)` check.

The new order should be:

```javascript
  // ... fetchCallbacks (useCallback) ...

  const fetchJobDetails = useCallback(async (id) => {
    if (jobCache.current[id] && selectedJob?.id === id && !showRaw) {
      return;
    }

    setShowRaw(false);
    setLoadingDetails(true);

    try {
      const response = await authFetch(`${API_URL}/jobs/${id}/details`);
      if (!response.ok) throw new Error(`HTTP error ${response.status}`);
      const data = await response.json();

      jobCache.current[id] = data;
      setSelectedJob(data);
    } catch (error) {
      console.error('Error fetching job details:', error);
      setSelectedJob({ id, error: error.message });
    } finally {
      setLoadingDetails(false);
    }
  }, [selectedJob, showRaw]);

  if (!token) {
    return <LoginPage onLogin={handleLogin} />;
  }

  return (
    <div className="min-h-screen bg-gray-900 ...">
```

- [ ] **Step 3: Verify the fix**

Test flow:
1. Clear localStorage (`localStorage.removeItem('authToken')`) in browser devtools
2. Refresh — should see LoginPage
3. Enter password and submit
4. Dashboard should appear immediately (no blank page, no manual refresh needed)

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/crawler-monitor-frontend/src/App.jsx
git commit -m "fix(crawler-monitor-frontend): move fetchJobDetails above conditional return

useCallback was called after an early return, violating React's Rules of
Hooks. When token changed from null to a value, the hook count changed
between renders, causing a silent crash (blank page after login)."
```

---

## Task 3: Fix Incorrect Resource Metrics in Heartbeat

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts`

**Why:** The heartbeat sends `process.memoryUsage().rss` (Node.js process only, ~150-300 MB) and `process.cpuUsage()` (Node.js process only). But the container also runs Playwright/Camoufox browser processes consuming 500 MB-2 GB RAM and most of the CPU. The dashboard shows misleadingly low values. The cgroup infrastructure for reading container-level metrics already exists in the same file (lines 168-196, used for the startup memory check) — it just needs to be reused in the heartbeat.

### Overview of changes

Replace the heartbeat's process-level metrics with container-level cgroup readings:
- **RAM**: Read `/sys/fs/cgroup/memory.current` (v2) or `/sys/fs/cgroup/memory/memory.usage_in_bytes` (v1) — measures ALL processes in the container
- **CPU**: Read `/sys/fs/cgroup/cpu.stat` (v2, `usage_usec` field) or `/sys/fs/cgroup/cpuacct/cpuacct.usage` (v1) — measures ALL CPU time in the container

- [ ] **Step 1: Add a helper function to read container memory**

In `main.ts`, BEFORE the heartbeat `setInterval` (before line 394), add a helper function:

```typescript
    // Helper to read container-level memory usage from cgroups
    const getContainerMemoryUsage = async (): Promise<number> => {
        try {
            // cgroups v2
            const v2 = await fsPromises.readFile('/sys/fs/cgroup/memory.current', 'utf-8').catch(() => null);
            if (v2) return parseInt(v2.trim());

            // cgroups v1
            const v1 = await fsPromises.readFile('/sys/fs/cgroup/memory/memory.usage_in_bytes', 'utf-8').catch(() => null);
            if (v1) return parseInt(v1.trim());
        } catch (e) { /* fallback below */ }

        // Fallback: Node.js process RSS (inaccurate but better than 0)
        return process.memoryUsage().rss;
    };
```

- [ ] **Step 2: Add a helper function to read container CPU usage**

After the memory helper, add a CPU helper. Container CPU comes from cgroups as a cumulative counter (microseconds or nanoseconds). To get a percentage, we compute the delta between two reads.

```typescript
    // Helper to read container-level CPU usage from cgroups
    // Returns cumulative CPU microseconds used by the entire container
    const getContainerCpuUsec = async (): Promise<number | null> => {
        try {
            // cgroups v2: cpu.stat has "usage_usec <value>" line
            const v2 = await fsPromises.readFile('/sys/fs/cgroup/cpu.stat', 'utf-8').catch(() => null);
            if (v2) {
                const match = v2.match(/usage_usec\s+(\d+)/);
                if (match) return parseInt(match[1]);
            }

            // cgroups v1: cpuacct.usage is in nanoseconds
            const v1 = await fsPromises.readFile('/sys/fs/cgroup/cpuacct/cpuacct.usage', 'utf-8').catch(() => null);
            if (v1) return parseInt(v1.trim()) / 1000; // Convert ns to us
        } catch (e) { /* fallback below */ }

        return null; // No cgroup CPU available
    };

    let lastContainerCpuUsec = await getContainerCpuUsec();
    let lastContainerCpuTime = Date.now();
```

- [ ] **Step 3: Replace the heartbeat interval body**

Replace the `setInterval` body (lines 394-426) to use container-level metrics:

```typescript
    setInterval(async () => {
        try {
            // Container-level CPU from cgroups
            let cpuPercent: number;
            const currentContainerCpuUsec = await getContainerCpuUsec();
            const currentTime = Date.now();

            if (currentContainerCpuUsec !== null && lastContainerCpuUsec !== null) {
                const deltaCpuUsec = currentContainerCpuUsec - lastContainerCpuUsec;
                const deltaWallUsec = (currentTime - lastContainerCpuTime) * 1000;
                cpuPercent = (deltaCpuUsec / deltaWallUsec) / numCpus;
                lastContainerCpuUsec = currentContainerCpuUsec;
                lastContainerCpuTime = currentTime;
            } else {
                // Fallback to process-level CPU
                const currentCpuUsage = process.cpuUsage(lastCpuUsage);
                const elapsedTime = (currentTime - lastTime) * 1000;
                cpuPercent = ((currentCpuUsage.user + currentCpuUsage.system) / elapsedTime) / numCpus;
                lastCpuUsage = process.cpuUsage();
                lastTime = currentTime;
            }

            // Container-level RAM from cgroups
            const containerRam = await getContainerMemoryUsage();
            const topProcesses = await getTopProcesses();

            const heartbeat = {
                type: 'heartbeat',
                replicaId: hostname,
                jobId: id,
                domain: domain,
                cpu: Math.min(Math.max(cpuPercent, 0), 1), // Clamp 0-1
                ram: containerRam,
                totalRam: totalMem,
                topProcesses: topProcesses,
                timestamp: Date.now(),
                status: 'running'
            };
            await redisClient.publish('crawler:heartbeat', JSON.stringify(heartbeat));
        } catch (e) {
            console.error('Failed to send heartbeat:', e);
        }
    }, 2000);
```

- [ ] **Step 4: Remove now-unused variables (if applicable)**

After the replacement, check if `lastCpuUsage` and `lastTime` are still needed. They are — they're used in the fallback branch when cgroup CPU isn't available. Keep them.

Also keep `const memoryUsage = process.memoryUsage();` only if used elsewhere. Since we replaced it with `getContainerMemoryUsage()`, remove the line `const memoryUsage = process.memoryUsage();` from inside the interval.

- [ ] **Step 5: Verify by building the TypeScript**

Run: `cd apps-microservices/crawler-service/crawler && npm run build`

Expected: No TypeScript compilation errors.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/main.ts
git commit -m "fix(crawler-service): use container-level metrics in heartbeat

Replace process.memoryUsage().rss (Node.js only) with cgroup memory.current
(entire container). Replace process.cpuUsage() with cgroup cpu.stat
(entire container). Browser processes are now included in the dashboard
metrics, giving operators accurate resource visibility."
```

---

## Summary

| Task | Category | File | Description |
|------|----------|------|-------------|
| 1 | Reviewer | `.claude/agents/code-reviewer.md` | Add framework correctness, data semantics, user flow dimensions |
| 2 | Bug fix | `App.jsx` | Move `fetchJobDetails` above conditional return (hooks violation) |
| 3 | Bug fix | `crawler/src/main.ts` | Container-level cgroup metrics in heartbeat |

**Execution order:** Tasks are independent — any order works. Task 2 is the quickest (1 move). Task 1 is documentation. Task 3 requires TypeScript compilation to verify.
