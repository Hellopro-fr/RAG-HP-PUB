# Crawler gallery-render wait (A664) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Before capturing `page.content()`, wait (bounded) for a Magento Fotorama gallery to render its first frame when the page carries the gallery placeholder.

**Architecture:** A small pure module `galleryRenderWait.ts` (env resolver + decision + bounded wait taking a minimal page interface) called from `processPage()` between `waitAndScroll()` and `getPageContentWithRetry()`. All 5 `processPage()` callers (`routes.ts:645,878,943,1444`, `functions.ts:665` @ `58c87cba1`, from `grep -rn 'processPage(' src`) inherit it. Delay is an env var exposed by `/admin/config` and versioned in compose.

**Tech Stack:** TypeScript (Node, Playwright/Camoufox, Crawlee), `node --import tsx --test`; Python pytest for the compose/whitelist parity guard.

**Spec:** `D:/DevHellopro/banc_selecteurs_data/a664/mesure_rendu_galerie_2026-11-23.md` § 7.3 (measurement: V1 = wait for the frame 15 s → 14/15 rendered vs 6/15, p = 0.005, § 7.2).

## Global Constraints

- Placeholder selector `[data-gallery-role=gallery-placeholder]`; rendered selector `.fotorama__stage__frame`, `state: "attached"` (exactly as measured in V1, fiche § 7.3).
- Env var `GALLERY_RENDER_WAIT_MS`: default `15000`; `0` = disabled (no DOM query at all); empty / non-numeric / negative → `15000`.
- The wait never throws: timeout or any error is swallowed (same policy as `waitAndScroll()` `networkidle`, `functions.ts:109-113`), returns a status; one `log.info` line only on timeout.
- Budget (handler `REQUEST_HANDLER_TIMEOUT_S` default 200, `httpStatusPolicy.ts`; navigation has its own 90 s, `functions.ts:561`): only pages with the placeholder pay ≤ 15 s. Pre-existing worst case already 5 + 30 + 180 (detect) = 215 s > 200; this adds ≤ 15 s on placeholder pages only. Not changed here — reported to the user.
- `/admin/config` lists env vars by prefix (`admin.py:191`); add `"GALLERY_"` with a justification comment. `tests/test_admin_config.py::test_compose_env_parity` must stay green.
- EOL: `functions.ts` i/crlf, `admin.py`, `docker-compose.yml`, `CLAUDE.md` i/lf (w/crlf) — edit with the Edit tool, check `git diff --stat` shows only intended lines.

**User decisions (already made):** « Coder l'attente » (2026-11-24 ~12:00 local) — do not re-ask. Merge and deploy are user gates.

---

### Task 1: galleryRenderWait module + processPage wiring + config exposure

**Goal:** `processPage()` waits ≤ `GALLERY_RENDER_WAIT_MS` for `.fotorama__stage__frame` on pages carrying the gallery placeholder.

**Files:**
- Create: `apps-microservices/crawler-service/crawler/src/galleryRenderWait.ts`
- Test: `apps-microservices/crawler-service/crawler/src/galleryRenderWait.test.ts`
- Modify: `apps-microservices/crawler-service/crawler/src/functions.ts` (`processPage`, anchor `await waitAndScroll(page, url, log, maxScrolls, timeoutSecs);` inside `processPage`)
- Modify: `apps-microservices/crawler-service/app/router/admin.py` (`_ENV_WHITELIST_PREFIXES`)
- Modify: `docker-compose.yml` (crawler-service `environment:`), `apps-microservices/crawler-service/CLAUDE.md` (env table § HTTP Status & Navigation Retry Policy)

**Acceptance Criteria:**
- [ ] Tests: resolver (undefined/""/"abc"/"-5" → 15000, "0" → 0, "8000" → 8000); wait: no placeholder → `skipped`, no `waitForSelector` call; placeholder → `waitForSelector('.fotorama__stage__frame', {state:'attached', timeout})` and `rendered`; waitMs 0 → `disabled`, no `evaluate` call; `waitForSelector` rejects → `timeout`, no throw, one log line; `evaluate` rejects → `error`, no throw.
- [ ] Full crawler suite `npm test` green, non-zero test count, run location printed.
- [ ] `pytest tests/test_admin_config.py` green.

**Verify:** `npm test` (from `crawler/`) → `# fail 0` with `# tests N`, N > 0.

**Steps:** TDD — write `galleryRenderWait.test.ts`, run (fails: module missing), write module, run (pass), wire `processPage`, add compose line `- GALLERY_RENDER_WAIT_MS=${GALLERY_RENDER_WAIT_MS:-15000}`, whitelist prefix, CLAUDE.md row, full suites, commit (bilingual EN then FR).

### Task 2: Local bench replay (free)

**Goal:** Replay V1 on the local Camoufox bench through the committed module's code path, 5 witnesses × 3 passes, result in fiche § 8.

**Files:**
- Create: `D:/DevHellopro/banc_selecteurs_data/a664/test_local/` variant `V1c` (imports the decision of `galleryRenderWait.ts` or reproduces its exact call), results appended to `results.jsonl`
- Modify: `D:/DevHellopro/banc_selecteurs_data/a664/mesure_rendu_galerie_2026-11-23.md` (new § 8)

**Acceptance Criteria:**
- [ ] 15 captures V1c, frame rendered count reported against V0b 6/15 and V1 14/15 (same witnesses, fiche § 7.1).
- [ ] One sub-run in the foreground first (1 witness × 1 pass) before the full 15.

**Verify:** count of `fotorama__stage__frame` hits per variant in `results.jsonl` (script line printed in § 8).
