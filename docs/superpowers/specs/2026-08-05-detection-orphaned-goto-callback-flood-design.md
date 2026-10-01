# Design — orphaned goto-callback flood (Case-6 alternative confirmation)

**Date:** 2026-08-05
**Status:** Approved (design), pending implementation plan
**Service:** `apps-microservices/api-detection-langue-fr` (Python 3.10, Camoufox/Firefox via Playwright). RAG-HP-PUB `features/poc`.
**Deploy:** `git push` + **Docker rebuild on VM**. No BO, no migration, no new env var, no compose change.

## Problem

Production floods its log with a **different** unretrieved-future than the teardown one fixed in `d7ea1f63`:

```
asyncio - ERROR - Future exception was never retrieved
future: <Future finished exception=TargetClosedError('Target page, context or browser has been closed
  Call log:
  - navigating to "https://www.brabantia.com/fr/accessoires-de-cuisine/ustensiles-de-cuisine/", waiting until "domcontentloaded"
')>
```

Two diagnostic tells distinguish it from the teardown flood:
- **No Python traceback frames** — just the `Future` repr. The signature of a Future whose exception was set *externally*, with no coroutine stack behind it.
- **A navigation call log** embedded in the message, on **deep `/fr/` and `/fr-fr/` paths** — hreflang-alternative shapes, not homepages.

### Mechanism (verified against Playwright source)

It is a **pending `page.goto` protocol callback**. `Connection.cleanup()` is the only place that sets an exception on those:

```python
for callback in self._callbacks.values():
    # To prevent 'Future exception was never retrieved' we ignore all callbacks that are no_reply.
    if callback.no_reply:            continue
    if callback.future.cancelled():  continue
    callback.future.set_exception(self._closed_error)   # ← ours lands here, unread
```

Playwright deliberately suppresses two sibling cases and **misses the third**: a callback that is *pending but not cancelled*. Ours is pending because `asyncio.wait` — used inside Playwright's `_inner_send` — leaves the futures it awaited pending rather than cancelled when the outer task is cancelled. So: cancel a scrape mid-navigation, then close the browser, and every in-flight goto callback gets an exception nobody can read.

**Verified byte-identical at v1.62.0** (fetched from the tag): the two guards are unchanged from 1.48 through the latest release. Upstream [playwright-python#2163](https://github.com/microsoft/playwright-python/issues/2163) — "Future exception was not retrieved when page load is aborted midway" — is this exact scenario, still open.

### Root cause — the belt is shorter than what it wraps

`domain_fr.py:1446-1448`, the Case-6 alternative-confirmation loop:

```python
alt_content_result = await asyncio.wait_for(
    fetch_html(alt_candidate.url), timeout=120
)
```

`fetch_html` is **the whole retry cascade**, not a single scrape: `HTTP_MAX_RETRIES = 3` attempts (`redirect_tracker.py:218`) plus the URL-variant phase. Per attempt the bounds are `BROWSER_LAUNCH_TIMEOUT_S = 45`, nav `min(timeout, 30)` and `TEARDOWN_TIMEOUT_S = 10` — so **three attempts alone are ~255 s**, before variants.

A 120 s belt around a ~255 s+ operation **cannot outlast it**. The cancellation is not an exceptional wedge-breaker; it is the *normal* outcome for any alternative that does not answer on the first attempt. That is precisely why the flood appears on alternative URLs and not on homepages.

Second-order cost, same cause: one alternative can legitimately consume 255 s+ of the 300 s per-item budget, so a domain with several alternatives gets cancelled at the *batch* level instead — reproducing the same orphaned callbacks one layer up.

**A note on what this is not.** The sibling alternative path at `domain_fr.py:649-651` (`asyncio.gather` over candidates) uses the lighter `_validate_single_url`, not the cascade. The expensive call is specific to the Case-6 confirmation loop.

### Ruled out — upgrading does not fix this

Researched because the pin comment invited it, and the answer is the unhelpful one. Recorded so nobody re-runs it:

| fact | value |
|---|---|
| `daijro/camoufox` PR #625 (the pin's stated blocker) | **merged 2026-06-04** |
| latest Camoufox browser release | `v152.0.4-beta.28`, 2026-07-19 (postdates the merge) |
| Camoufox PyPI package | **0.5.4**, declaring **`playwright<1.61`** |
| Playwright releases | 1.59.0 (2026-04-29), 1.60.0 (2026-05-18), 1.61.0 (2026-06-29), 1.62.0 (2026-07-31) |
| `Connection.cleanup()` at v1.62.0 | **byte-identical to 1.48** — still only two guards |

So the `playwright==1.58.0` pin *can* now move, but only to **1.60.x** (Camoufox caps it below 1.61), and it is a coupled upgrade — Playwright **plus** the camoufox wrapper 0.4.11 → 0.5.4 **plus** the browser build. **None of it touches this flood.** The pin is a separate chantier with its own risk budget; folding it in here would be mistaking motion for progress.

Also assessed and dismissed: `jo-inc/camofox-browser` (8,323 stars) and `redf0x1/camofox-browser` (341 stars) are **not forks** of Camoufox (`fork: false`) — they are servers/REST wrappers *consuming* it, so by construction they cannot fix a Juggler/`pageError` compatibility issue. Not candidates. (Noted for the record: the name search returned 30 similarly-named repos, many zero-star and undescribed, including one described as *"Mirror of jo-inc/camofox-browser (full history)"*. No evidence of anything malicious, but any future consideration of them needs real provenance work before running their binaries.)

## Design

Two changes. The first stops the orphaned callbacks being *created*; the second quiets the residual.

### 1. Case-6 confirms an alternative with a single probe — `domain_fr.py`

An alternative is a **confirmation probe**, not a primary target. If a declared FR page does not answer on one attempt, "unconfirmed" is the correct verdict — retries and http/https+www permutations exist for the URL the caller actually asked about, and Case 6 already has a fallback path when confirmation fails.

```python
                    alt_content_result = await asyncio.wait_for(
                        scrape_html(alt_candidate.url, proxy=settings.APIFY_PROXY),
                        timeout=120,
                    )
```

Verified details that make this a two-line change rather than a refactor:
- **Return type is compatible.** `scrape_html` returns `Optional[ScrapeResult]` and `fetch_html` returns the same `ScrapeResult`; the loop already reads `.html` and `.final_url` and already treats a falsy result as fetch-failed (`:1449-1452`), which is what `scrape_html` returns on a missing/invalid proxy (`scraper.py:390-397`). So the no-proxy guard `fetch_html` provided is preserved by the existing branch.
- **No `build_proxy_url` needed.** `settings.APIFY_PROXY` is already the full URL — `config.py:57-64` rewrites the password-only env var into `http://auto:{password}@proxy.apify.com:8000`. `build_proxy_url(base, session_id=None, country='FR')` only rewrites the userinfo, and `redirect_tracker` calls it with `country=None`, so the effective production proxy for `fetch_html` is plain `auto`. Passing `settings.APIFY_PROXY` directly is therefore behaviour-equivalent **and** matches the existing precedent in this same file at `domain_fr.py:414` and `:484`.
- **`scrape_html` must be imported.** `domain_fr.py:18` imports `RedirectTracker, fetch_html` from `redirect_tracker` and the module has **no** top-level import from `app.services.scraper`. `fetch_html` stays imported — it is still used elsewhere in the file.

Inner worst case drops from ~255 s+ to ~85 s on the plain path (≤45 s launch + ≤30 s nav + ≤10 s teardown), so the 120 s belt becomes a genuine safety net and stops firing on the normal path. That ~85 s figure undercounts, though: it omits the ≤5 s `networkidle` bonus wait, the up-to-3 `page.content()` retries, and — on a challenge-protected alternative — the ≤45 s Cloudflare/DataDome polling loop (`scraper.py:471-531`); teardown itself is ≤3×`TEARDOWN_TIMEOUT_S` = 30 s (`unroute_all` + `context.close` + `browser.close`, each independently bounded), not 10 s. So while the typical alternative resolves well under the belt, a challenge-protected one can still approach the 120 s belt on a single probe — which is exactly why the loop exception handler (change 2) is the correct backstop regardless of this timing arithmetic, not merely insurance for a case the numbers said couldn't happen.

**Accepted loss:** an alternative that would have succeeded only on retry #2/#3, or only via a www/http variant, is now recorded unconfirmed. Judged correct for a probe — and note that with the belt firing at 120 s today, most of those retries were being *cancelled mid-flight anyway*, so the rescue was already largely theoretical.

### 2. A narrow loop exception handler — `main.py`

The residual cannot be eliminated: the 300 s per-item batch `wait_for` can still cancel a scrape mid-navigation, and that future is unreachable by construction — the frame that would retrieve it is gone.

Install the service's **first** `set_exception_handler` (there is none anywhere today, verified by grep over `app/` and `main.py`) in the existing lifespan, matching only this shape and delegating everything else to the default handler:

```python
def _handle_loop_exception(loop, context):
    exc = context.get("exception")
    # A pending page.goto protocol callback, orphaned when its awaiting frame
    # was cancelled and the browser then closed. Connection.cleanup() sets the
    # exception on it; nobody can retrieve it. Playwright suppresses the two
    # sibling cases (no_reply, already-cancelled) and misses this one —
    # upstream playwright-python#2163, unchanged through v1.62.0.
    if isinstance(exc, TargetClosedError) and context.get("future") is not None \
            and context.get("task") is None:
        ORPHANED_PROTOCOL_FUTURES.inc()
        logger.debug(f"orphaned Playwright callback drained: {exc!r}")
        return
    loop.default_exception_handler(context)
```

It is **narrow on three axes** — exception type, a `future` present, and no owning `task` — and it **counts** what it silences (`ORPHANED_PROTOCOL_FUTURES`, a Prometheus counter next to the existing metrics) so the noise becomes a number rather than disappearing. A `TargetClosedError` raised on a live awaited path still has an owning task and still reaches the default handler.

## Behaviour change

| Situation | Before | After |
|---|---|---|
| Case-6 alternative answers on attempt 1 | confirmed | unchanged |
| Case-6 alternative needs retry 2/3 or a variant | usually cancelled at 120 s mid-`goto` → flood | recorded unconfirmed, no flood |
| Case-6 alternative genuinely wedged | cancelled at 120 s, flood | cancelled at 120 s, drained + counted |
| Item cancelled at the 300 s batch ceiling | flood | drained + counted |
| `TargetClosedError` on a live awaited call | ERROR (correct) | unchanged — still ERROR |
| Domain with several alternatives | up to 255 s each, item often cancelled | up to ~85 s each |

## Out of scope

- **Lifting `playwright==1.58.0`.** Now possible to 1.60.x but irrelevant to this bug, and a coupled three-part upgrade. Its own chantier.
- **The camoufox wrapper upgrade** (0.4.11 → 0.5.4) — same chantier as the pin.
- **Closing the page before the browser** so goto callbacks resolve through `dispatch()` (which pops them out of `_callbacks`). A genuine ordering fix, but it rests on internals read at 1.48 while prod runs 1.58 — verify against the real version before attempting.
- **A wall-clock deadline threaded into `fetch_html`.** Parked for the third time; change 1 removes this bug's dependence on it.
- **Reporting upstream.** Worth doing on #2163 with our reproduction, but it does not fix today.

## Verification

Unit tests (`tests/test_alt_probe_and_orphan_handler.py`), no network:

1. Case-6 confirmation calls `scrape_html` **exactly once** per alternative (monkeypatch it with a counter) and never calls `fetch_html` — the regression guard against the cascade creeping back.
2. `scrape_html` returning `None` → the alternative is recorded fetch-failed and the loop continues to the next candidate (existing behaviour preserved).
3. `scrape_html` raising a nav timeout → same, loop continues, no propagation.
4. The handler drains a `TargetClosedError` on a `Future` with no task: install it, assert the counter incremented and `default_exception_handler` was **not** called.
5. The handler **delegates** a `TargetClosedError` that has an owning `task`, and delegates a non-`TargetClosedError` — both must reach `default_exception_handler`. This is the guard against it becoming a blanket suppressor.

Baseline: `python -m pytest tests/ --ignore=tests/test_api.py -q` → **`7 failed, 304 passed`**, the 7 pre-existing in `tests/test_domain_fr.py`.

**Post-deploy:** `Future exception was never retrieved` should disappear from the log; `detection_orphaned_protocol_futures_total` should be non-zero but small and flat rather than growing per batch. If it grows fast, change 1 did not reduce creation as expected and the 300 s ceiling is the dominant source.
