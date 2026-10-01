# Orphaned goto-callback flood — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the `Future exception was never retrieved` flood on deep `/fr/` alternative URLs, by removing the cancellation that creates the orphaned `page.goto` callbacks and draining the residual that a higher-level cancel can still produce.

**Architecture:** Two independent changes. `domain_fr.py`'s Case-6 alternative-confirmation loop stops calling the full `fetch_html` retry cascade and uses a single `scrape_html` probe, so the 120 s belt around it stops firing mid-navigation. `main.py` gains the service's first `set_exception_handler`, narrow on three axes and counting what it silences, for the residual the 300 s batch ceiling can still create.

**Tech Stack:** Python 3.10, asyncio, Playwright (Camoufox/Firefox in prod), prometheus_client, pytest + pytest-asyncio.

**User decisions (already made):**
- **Single-attempt probe for alternatives**, chosen over raising the belt or threading a deadline into `fetch_html`: "an alternative is a confirmation probe — retries and http/https+www permutations are for the PRIMARY url".
- **Then the narrow handler** for the residual — approach "D then A".
- **Upgrading Playwright is NOT part of this.** Researched and ruled out: `cleanup()` is byte-identical at v1.62.0, so no upgrade fixes this bug. The pin can move but only to 1.60.x (Camoufox 0.5.4 declares `playwright<1.61`) and it is a coupled three-part upgrade — its own chantier.
- The two `camofox-browser` repos are **not** Camoufox forks but REST wrappers consuming it, so they cannot fix a Juggler issue. Dismissed.

**Spec:** `docs/superpowers/specs/2026-08-05-detection-orphaned-goto-callback-flood-design.md` (`ef802b0d`)

---

## Environment notes (read before running anything)

- Run pytest from `apps-microservices/api-detection-langue-fr` with `$env:PYTHONIOENCODING="utf-8"` set first — French log output crashes this machine's cp1252 stdout. If output is unreadable, redirect to a file and read the file.
- `common_utils` is **already** installed editable from the MAIN checkout. Do **not** reinstall, and never `pip install -e` from inside a worktree. On `ModuleNotFoundError: No module named 'common_utils'`, stop and report NEEDS_CONTEXT.
- Baseline: `python -m pytest tests/ --ignore=tests/test_api.py -q` → **`7 failed, 304 passed`**. The 7 are pre-existing in `tests/test_domain_fr.py` (no local fastText `.bin`, a `ScrapeResult` tuple-unpack drift, a missing `await` in two alternative-language tests). **Not yours — never edit that file.** ~5 minutes; foreground, wait.
- Local Python is **3.12.10**, local Playwright **1.48.0**; prod is Python 3.10 and `playwright==1.58.0`. Nothing in this plan may depend on version-specific internals.

## File structure

| File | Responsibility | Task |
|---|---|---|
| `app/core/domain_fr.py` | Case-6 confirmation uses a single `scrape_html` probe | 1 |
| `app/core/metrics.py` | the counter for silenced orphans | 2 |
| `main.py` | installs the narrow loop exception handler | 2 |
| `tests/test_alt_probe.py` | create — Case-6 probe behaviour | 1 |
| `tests/test_orphan_handler.py` | create — handler match/delegate behaviour | 2 |

Tasks 1 and 2 touch **disjoint files** and may run in parallel.

---

### Task 1: Case-6 confirms an alternative with one probe, not the cascade

**Goal:** The Case-6 alternative-confirmation loop calls `scrape_html` exactly once per alternative instead of the full `fetch_html` retry cascade, so its 120 s belt stops cancelling mid-navigation.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/core/domain_fr.py` (import line `:18`; the Case-6 `wait_for` at `:1446-1448`)
- Modify: `apps-microservices/api-detection-langue-fr/tests/test_case2a_alt_fallthrough.py` (`_stub_fetch` at `:69-73` — see Step 6; **mock fidelity only, no assertion changes**)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_alt_probe.py` (create)

**Acceptance Criteria:**
- [ ] Case-6 confirmation calls `scrape_html` **exactly once** per reliable alternative
- [ ] Case-6 confirmation never calls `fetch_html` for an alternative
- [ ] `fetch_html` remains imported and used by its other call sites in the file (it is not removed)
- [ ] `scrape_html` returning `None` → the alternative is recorded fetch-failed and the loop continues to the next candidate (existing behaviour preserved)
- [ ] `scrape_html` raising → the loop continues, nothing propagates out of `check_page_if_french`
- [ ] The proxy passed is `settings.APIFY_PROXY` (already a full URL after `config.py:57-64`), matching the existing precedent at `domain_fr.py:414`/`:484` — **no** `build_proxy_url` import is added
- [ ] The 120 s `wait_for` bound is unchanged
- [ ] `test_case2a_alt_fallthrough.py`'s `_stub_fetch` patches `scrape_html` instead of `fetch_html`, with **every assertion in that file unchanged** — it currently stubs the call Case 6 no longer makes, so without this the suite would launch a real browser

**Verify:** `python -m pytest tests/test_alt_probe.py tests/test_case2a_alt_fallthrough.py -v` → all pass, then `python -m pytest tests/test_validate_alternatives.py tests/test_domain_cache_admission.py -v` → all pass (untouched alternative-path suites; verified by grep that neither stubs `domain_fr.fetch_html`, so neither should need changing)

**Steps:**

- [ ] **Step 1: Write the failing test**

The fixture shape below is taken verbatim from the existing `tests/test_case2a_alt_fallthrough.py` (read at plan time), which already drives the decision matrix into Case 6: a `.fr` homepage whose NLP says `en` at 0.95 (strongly contradicts) plus a validated hreflang alternative. `region_priority` has a model default, so it is not required on `AlternativeUrl`.

Create `tests/test_alt_probe.py`:

```python
"""Case-6 alternative confirmation uses ONE probe, not the retry cascade.

Why this matters (2026-08-05): the loop wrapped `fetch_html` — the whole
3-attempt cascade, ~85s per attempt — in `asyncio.wait_for(..., timeout=120)`.
A belt shorter than what it wraps cannot outlast it, so the cancellation was
the NORMAL outcome for any alternative that missed on attempt 1. Cancelling
mid-`page.goto` leaves Playwright's protocol callback pending-and-uncancelled;
`Connection.cleanup()` then sets an exception on it that nobody can read —
the `Future exception was never retrieved` flood on deep /fr/ URLs.
"""
from types import SimpleNamespace

import pytest

from app.core import domain_fr as domain_fr_module
from app.core.domain_fr import DomainFR
from app.models.schemas import AlternativeUrl, DetectionMode

HOMEPAGE = "https://www.sumca.fr/"
ALT_URL = "https://www.sumca.fr/fr/"
ALT_URL_2 = "https://www.sumca.fr/fr-fr/"

HOME_HTML = """<html lang="en-US"><body><p>
Perfect bespoke tooling for demanding industrial applications. Micron
tolerances, superb finishing all ready out of the box to be used on your press.
</p></body></html>"""

ALT_HTML_FR = """<html lang="fr"><body><p>
FRENCH_ALT_MARKER Outillage sur mesure pour les applications industrielles
exigeantes. Tolerances au micron et finition soignee pour votre presse.
</p></body></html>"""


def _make_detector():
    return DomainFR(homepage=HOMEPAGE, use_nlp_detection=True,
                    validate_alternatives=True)


def _stub_nlp(detector, monkeypatch):
    """`fr` strong when the FR marker is present, else `en` strong (0.95 > 0.9
    => strongly_contradicts on the English homepage, which reaches Case 6)."""
    def fake_fasttext(text):
        if "FRENCH_ALT_MARKER" in (text or ""):
            return {"lang": "fr", "confidence": 0.95, "method": "stub"}
        return {"lang": "en", "confidence": 0.95, "method": "stub"}

    monkeypatch.setattr(detector.language_detector,
                        "detect_from_text_content_fasttext", fake_fasttext)
    monkeypatch.setattr(detector.language_detector,
                        "detect_from_text_content", fake_fasttext)


def _stub_alternatives(detector, monkeypatch, candidates):
    async def fake_detect_alternative_languages(content):
        return candidates
    monkeypatch.setattr(detector, "detect_alternative_languages",
                        fake_detect_alternative_languages)


def _alt(url=ALT_URL):
    return AlternativeUrl(url=url, method="hreflang", reliability="high",
                          validated=True)


def _result(url, html):
    return SimpleNamespace(html=html, final_url=url, status_code=200,
                           content_type="text/html", headers={})


@pytest.mark.asyncio
async def test_alternative_confirmed_with_single_scrape(monkeypatch):
    scrape_calls = []

    async def fake_scrape(url, timeout=90, proxy=None):
        scrape_calls.append(url)
        return _result(url, ALT_HTML_FR)

    async def fake_fetch(url, proxy=None, *a, **kw):
        raise AssertionError("Case 6 must not use the fetch_html cascade")

    monkeypatch.setattr(domain_fr_module, "scrape_html", fake_scrape)
    monkeypatch.setattr(domain_fr_module, "fetch_html", fake_fetch)

    d = _make_detector()
    _stub_nlp(d, monkeypatch)
    _stub_alternatives(d, monkeypatch, [_alt()])

    res = await d.check_page_if_french(HOME_HTML, DetectionMode.COMPLETE)

    assert res.ok is True
    assert res.url == ALT_URL
    assert scrape_calls == [ALT_URL], f"expected one probe, got {scrape_calls}"


@pytest.mark.asyncio
async def test_probe_returning_none_probes_every_candidate(monkeypatch):
    scrape_calls = []

    async def fake_scrape(url, timeout=90, proxy=None):
        scrape_calls.append(url)
        return None          # what scrape_html returns on a bad/missing proxy

    monkeypatch.setattr(domain_fr_module, "scrape_html", fake_scrape)

    d = _make_detector()
    _stub_nlp(d, monkeypatch)
    _stub_alternatives(d, monkeypatch, [_alt(ALT_URL), _alt(ALT_URL_2)])

    res = await d.check_page_if_french(HOME_HTML, DetectionMode.COMPLETE)

    assert res.ok is False
    assert scrape_calls == [ALT_URL, ALT_URL_2], (
        f"loop must continue past a None result: {scrape_calls}"
    )


@pytest.mark.asyncio
async def test_probe_raising_does_not_propagate(monkeypatch):
    async def fake_scrape(url, timeout=90, proxy=None):
        raise RuntimeError("Timeout 30000ms exceeded.")

    monkeypatch.setattr(domain_fr_module, "scrape_html", fake_scrape)

    d = _make_detector()
    _stub_nlp(d, monkeypatch)
    _stub_alternatives(d, monkeypatch, [_alt()])

    res = await d.check_page_if_french(HOME_HTML, DetectionMode.COMPLETE)

    assert res.ok is False          # returns a verdict, does not raise


@pytest.mark.asyncio
async def test_probe_gets_the_full_proxy_url(monkeypatch):
    """settings.APIFY_PROXY is already a full URL after config.py:57-64 —
    the probe passes it straight through, like domain_fr.py:414/:484 do."""
    seen = {}

    async def fake_scrape(url, timeout=90, proxy=None):
        seen["proxy"] = proxy
        return None

    monkeypatch.setattr(domain_fr_module, "scrape_html", fake_scrape)
    monkeypatch.setattr(domain_fr_module.settings, "APIFY_PROXY",
                        "http://auto:pw@proxy.apify.com:8000")

    d = _make_detector()
    _stub_nlp(d, monkeypatch)
    _stub_alternatives(d, monkeypatch, [_alt()])

    await d.check_page_if_french(HOME_HTML, DetectionMode.COMPLETE)

    assert seen["proxy"] == "http://auto:pw@proxy.apify.com:8000"
```

If `monkeypatch.setattr(domain_fr_module.settings, ...)` fails because `Settings` is frozen (it uses `object.__setattr__` in `model_post_init`, which hints at that), patch the module attribute instead: `monkeypatch.setattr(domain_fr_module, "settings", SimpleNamespace(APIFY_PROXY="http://auto:pw@proxy.apify.com:8000"))` — but only if the real form errors, since a `SimpleNamespace` would hide every other settings read in that call path. Report which form you used.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_alt_probe.py -v`
Expected RED: `AttributeError: <module 'app.core.domain_fr'> has no attribute 'scrape_html'` — monkeypatch refuses to set a name the module does not define. Report the exact message.

- [ ] **Step 3: Add the import**

`app/core/domain_fr.py:18` currently reads:

```python
from app.services.redirect_tracker import RedirectTracker, fetch_html
```

The module has **no** top-level import from `app.services.scraper`. Add one — keep `fetch_html`, which other call sites in this file still use:

```python
from app.services.redirect_tracker import RedirectTracker, fetch_html
from app.services.scraper import scrape_html
```

If a top-level `from app.services.scraper import ...` line already exists by the time you edit, extend it instead of adding a second one.

- [ ] **Step 4: Swap the cascade for the probe**

At `app/core/domain_fr.py:1446-1448`, replace:

```python
                    alt_content_result = await asyncio.wait_for(
                        fetch_html(alt_candidate.url), timeout=120
                    )
```

with:

```python
                    # Une alternative est une SONDE de confirmation, pas une cible
                    # primaire : les reprises et les permutations http/https+www
                    # existent pour l'URL demandée par l'appelant. Envelopper la
                    # cascade complète de fetch_html (3 tentatives × ~85s) dans un
                    # wait_for de 120s garantissait l'annulation en pleine
                    # navigation, ce qui orphelinait le callback protocolaire du
                    # goto et produisait le flood « Future exception was never
                    # retrieved ». settings.APIFY_PROXY est déjà l'URL complète
                    # (config.py:57-64), comme aux appels :414/:484.
                    alt_content_result = await asyncio.wait_for(
                        scrape_html(alt_candidate.url, proxy=settings.APIFY_PROXY),
                        timeout=120,
                    )
```

Leave the `120` bound and every line after it untouched — `:1449-1452` already treats a falsy result as fetch-failed, which is exactly what `scrape_html` returns on a missing/invalid proxy (`scraper.py:390-397`), so `fetch_html`'s no-proxy guard is preserved by the existing branch.

- [ ] **Step 5: Repoint the existing Case-6 stub (mock fidelity — expected, not optional)**

`tests/test_case2a_alt_fallthrough.py:69-73` stubs the call Case 6 no longer makes:

```python
def _stub_fetch(monkeypatch, html):
    async def fake_fetch_html(url, proxy=None, *args, **kwargs):
        return SimpleNamespace(html=html, final_url=url, status_code=200,
                               content_type="text/html", headers={})
    monkeypatch.setattr(domain_fr_module, "fetch_html", fake_fetch_html)
```

Left as-is, its two Case-6 tests (`test_validated_french_alt_is_accepted`, `test_lying_alt_is_rejected`) would fall through to the **real** `scrape_html` and try to launch a browser. Repoint the patch target only:

```python
def _stub_fetch(monkeypatch, html):
    # Case 6 probes an alternative with scrape_html, not the fetch_html cascade
    # (2026-08-05) — the stub follows the call the code actually makes.
    async def fake_scrape_html(url, timeout=90, proxy=None, *args, **kwargs):
        return SimpleNamespace(html=html, final_url=url, status_code=200,
                               content_type="text/html", headers={})
    monkeypatch.setattr(domain_fr_module, "scrape_html", fake_scrape_html)
```

Keep the helper's name and every call site. **Do not touch a single assertion in that file** — if any of its five tests then fails, that is a real behaviour change and you must STOP and report BLOCKED rather than adjusting the expectation.

- [ ] **Step 6: Run the tests + syntax check**

Run: `python -c "import ast; ast.parse(open('app/core/domain_fr.py',encoding='utf-8').read()); print('AST OK')"`
Run: `$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_alt_probe.py tests/test_case2a_alt_fallthrough.py -v` → all pass (4 new + 5 existing).
Run: `$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_validate_alternatives.py tests/test_domain_cache_admission.py -v` → all pass. Verified by grep at plan time that neither stubs `domain_fr.fetch_html`, so neither should need changing; if either fails, STOP and report BLOCKED rather than editing it.

- [ ] **Step 7: Prove the guard bites**

Temporarily revert Step 4 to `fetch_html(alt_candidate.url)` and re-run `test_alternative_confirmed_with_single_scrape` → it MUST fail (the `fake_fetch` stub raises `AssertionError: Case 6 must not use the fetch_html cascade`). Restore the probe exactly and re-run → all pass. Report both outcomes and confirm the restoration is byte-identical.

- [ ] **Step 8: Commit**

Stage exactly:
```
apps-microservices/api-detection-langue-fr/app/core/domain_fr.py
apps-microservices/api-detection-langue-fr/tests/test_alt_probe.py
apps-microservices/api-detection-langue-fr/tests/test_case2a_alt_fallthrough.py
```
Explicit paths only — **never `git add -A`**. Bilingual EN-then-FR Conventional Commit, message written to a temp file with the Write tool and passed via `git commit --file=<path>` (**no bash heredoc** — it trips a force-push blocker hook here). EN subject: `fix(detection): confirm alternatives with one probe, not the retry cascade`

---

### Task 2: A narrow loop exception handler for the residual orphans

**Goal:** An orphaned Playwright protocol callback is drained at debug level and counted, instead of printing an asyncio ERROR block — while a `TargetClosedError` that has an owning task still reaches the default handler.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/core/metrics.py` (add the counter)
- Modify: `apps-microservices/api-detection-langue-fr/main.py` (define + install the handler in the existing lifespan)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_orphan_handler.py` (create)

**Acceptance Criteria:**
- [ ] A context with a `TargetClosedError`, a `future`, and **no** `task` → counter incremented, `default_exception_handler` **not** called
- [ ] A context with a `TargetClosedError` that **has** a `task` → delegated to `default_exception_handler`
- [ ] A context with a non-Playwright exception (e.g. `ValueError`) → delegated
- [ ] A context with a Playwright `Error` that is **not** `TargetClosedError` → delegated
- [ ] A context with **no** exception key → delegated, no crash
- [ ] The handler does **not** import from `playwright._impl` — `TargetClosedError` is not exported by `playwright.async_api` (verified), so matching is by the public base class plus the class name
- [ ] The counter is named `detection_orphaned_protocol_futures_total` and lives in `app/core/metrics.py` beside the existing metrics
- [ ] The handler is installed in `main.py`'s existing lifespan, not at import time

**Verify:** `python -m pytest tests/test_orphan_handler.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `tests/test_orphan_handler.py`:

```python
"""The loop exception handler drains orphaned Playwright protocol callbacks.

A cancelled scrape leaves `page.goto`'s protocol callback pending-and-uncancelled;
`Connection.cleanup()` then sets TargetClosedError on it. Nobody can retrieve it —
the awaiting frame is gone by construction. Playwright suppresses the two sibling
cases (no_reply, already-cancelled) and misses this one (upstream
playwright-python#2163, unchanged through v1.62.0), so we complete the suppression.

The handler must stay NARROW: a TargetClosedError on a live awaited path has an
owning task and must still be reported.
"""
import asyncio

import pytest
from playwright.async_api import Error as PlaywrightError

from main import _handle_loop_exception
from app.core.metrics import ORPHANED_PROTOCOL_FUTURES


class _TargetClosedError(PlaywrightError):
    """Stand-in with the real class NAME — the handler matches on the name
    because playwright.async_api does not export TargetClosedError."""
    pass


_TargetClosedError.__name__ = "TargetClosedError"


class _FakeLoop:
    def __init__(self):
        self.delegated = []

    def default_exception_handler(self, context):
        self.delegated.append(context)


def _count():
    return ORPHANED_PROTOCOL_FUTURES._value.get()


def test_orphaned_future_is_drained_and_counted():
    loop = _FakeLoop()
    before = _count()

    _handle_loop_exception(loop, {
        "message": "Future exception was never retrieved",
        "exception": _TargetClosedError("Target page, context or browser has been closed"),
        "future": asyncio.Future(),
    })

    assert loop.delegated == [], "an orphaned protocol future must not be reported"
    assert _count() == before + 1, "the silenced orphan must be counted"


def test_target_closed_with_owning_task_is_delegated():
    """The guard against becoming a blanket suppressor."""
    loop = _FakeLoop()

    _handle_loop_exception(loop, {
        "message": "Task exception was never retrieved",
        "exception": _TargetClosedError("Target page, context or browser has been closed"),
        "future": asyncio.Future(),
        "task": object(),
    })

    assert len(loop.delegated) == 1, "a TargetClosedError with an owner must be reported"


def test_other_playwright_error_is_delegated():
    loop = _FakeLoop()
    _handle_loop_exception(loop, {
        "exception": PlaywrightError("some other playwright failure"),
        "future": asyncio.Future(),
    })
    assert len(loop.delegated) == 1


def test_non_playwright_exception_is_delegated():
    loop = _FakeLoop()
    _handle_loop_exception(loop, {
        "exception": ValueError("unrelated"),
        "future": asyncio.Future(),
    })
    assert len(loop.delegated) == 1


def test_context_without_exception_is_delegated():
    loop = _FakeLoop()
    _handle_loop_exception(loop, {"message": "something odd happened"})
    assert len(loop.delegated) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_orphan_handler.py -v`
Expected RED: `ImportError` — `cannot import name '_handle_loop_exception' from 'main'` and `cannot import name 'ORPHANED_PROTOCOL_FUTURES'`. Report the exact messages.

- [ ] **Step 3: Add the counter**

In `app/core/metrics.py`, following the file's existing `Counter(...)` style and `detect*` naming:

```python
# Orphaned Playwright protocol callbacks silenced by main.py's loop exception
# handler. A cancelled scrape leaves page.goto's callback pending-and-uncancelled;
# Connection.cleanup() sets TargetClosedError on it and nobody can retrieve it.
# Counted rather than merely suppressed, so the noise stays observable.
ORPHANED_PROTOCOL_FUTURES = Counter(
    "detection_orphaned_protocol_futures_total",
    "Orphaned Playwright protocol callbacks drained by the loop exception handler",
)
```

- [ ] **Step 4: Add the handler and install it**

In `main.py`, at module level near the existing logger setup:

```python
from playwright.async_api import Error as PlaywrightError

from app.core.metrics import ORPHANED_PROTOCOL_FUTURES


def _handle_loop_exception(loop, context) -> None:
    """Drain orphaned Playwright protocol callbacks; report everything else.

    A cancelled scrape (the 300s per-item wait_for, or any caller cancel) leaves
    `page.goto`'s protocol callback pending AND uncancelled, because asyncio.wait
    inside Playwright's _inner_send does not cancel what it awaited. When the
    browser is then closed, Connection.cleanup() sets TargetClosedError on that
    callback — and nobody can retrieve it, since the awaiting frame is gone.
    Playwright already suppresses the two sibling cases (no_reply, and
    already-cancelled) with the comment "To prevent 'Future exception was never
    retrieved'"; this completes that suppression for the third.
    Upstream: playwright-python#2163, unchanged through v1.62.0.

    NARROW on three axes — a Playwright error, named TargetClosedError, with a
    future but NO owning task. A TargetClosedError on a live awaited path has an
    owning task and still reaches the default handler.

    Matched by class NAME on purpose: TargetClosedError is not exported by
    playwright.async_api (only Error is), and importing it from
    playwright._impl._errors would tie us to a private module that the pending
    1.58 -> 1.60 upgrade could move.
    """
    exc = context.get("exception")
    if (
        isinstance(exc, PlaywrightError)
        and type(exc).__name__ == "TargetClosedError"
        and context.get("future") is not None
        and context.get("task") is None
    ):
        ORPHANED_PROTOCOL_FUTURES.inc()
        logger.debug(f"orphaned Playwright protocol callback drained: {exc!r}")
        return
    loop.default_exception_handler(context)
```

Then install it inside the **existing** lifespan's startup section (alongside `init_redis_pool()` / the JobManager setup — read the lifespan before editing and place it with the other startup steps, not at import time):

```python
    asyncio.get_running_loop().set_exception_handler(_handle_loop_exception)
    logging.getLogger(__name__).info("Loop exception handler installed (orphaned Playwright callbacks)")
```

`main.py` already imports `logging` and defines `logger` at `:122`; add `import asyncio` only if it is absent.

- [ ] **Step 5: Run the tests + syntax check**

Run: `python -c "import ast; ast.parse(open('main.py',encoding='utf-8').read()); ast.parse(open('app/core/metrics.py',encoding='utf-8').read()); print('AST OK')"`
Run: `$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_orphan_handler.py tests/test_metrics.py tests/test_main.py -v` → all pass. `tests/test_metrics.py` and `tests/test_main.py` are existing suites and are your regression guard for these two files; if either fails, STOP and report BLOCKED rather than editing them.

- [ ] **Step 6: Prove the narrowness**

Temporarily widen the handler by deleting the `and context.get("task") is None` clause, and re-run `test_target_closed_with_owning_task_is_delegated` → it MUST fail. Restore the clause exactly and re-run → all pass. This is the guard against the handler degrading into a blanket suppressor. Report both outcomes and confirm the restoration is byte-identical.

- [ ] **Step 7: Full-suite regression + commit**

Run: `$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/ --ignore=tests/test_api.py -q`
Expected: `7 failed` and nothing else new; the passed count rises by the tests added across both tasks. ~5 minutes; foreground, wait for it.

Stage exactly:
```
apps-microservices/api-detection-langue-fr/main.py
apps-microservices/api-detection-langue-fr/app/core/metrics.py
apps-microservices/api-detection-langue-fr/tests/test_orphan_handler.py
```
Bilingual EN-then-FR message via the Write tool + `git commit --file=<path>`. EN subject: `fix(detection): drain and count orphaned Playwright protocol callbacks`

---

## Deploy (after both tasks, user-controlled)

`git push origin features/poc` + **Docker rebuild of `api-detection-langue-fr` on the VM**. No BO, no migration, no env var, no compose change.

## Post-deploy verification

- `Future exception was never retrieved` should **disappear** from the container log.
- `detection_orphaned_protocol_futures_total` should be **non-zero but small and flat** — it proves the handler is live and the residual exists. If it climbs fast per batch, Task 1 did not reduce creation as expected and the 300 s ceiling is the dominant source; say so rather than assuming success.
- Case-6 outcomes: alternatives that previously confirmed on retry #2/#3 now report unconfirmed. Watch `/detect-debug` on a known multi-alternative domain to confirm the volume is what the spec's accepted loss predicts.

## Out of scope

- **Lifting `playwright==1.58.0`** (possible to 1.60.x now, irrelevant to this bug, coupled three-part upgrade) and the camoufox wrapper move 0.4.11 → 0.5.4. Own chantier.
- **Closing the page before the browser** so callbacks resolve via `dispatch()` — rests on internals read at 1.48 while prod runs 1.58. Verify against the real version first.
- **A wall-clock deadline threaded into `fetch_html`** — parked for the third time; Task 1 removes this bug's dependence on it.
- **Reporting upstream on playwright-python#2163** — worth doing with our reproduction, but it does not fix today.
