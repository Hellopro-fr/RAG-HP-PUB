# Audit — the `crawler-service` ↔ `api-detection-langue-fr` seam

**Date:** 2026-07-29
**Status:** findings only. Nothing implemented. Parked for a later session.
**Method:** 8 agents — 4 parallel readers (caller side / detection capability surface / crawl-path consumers / contract & wiring), one synthesis per direction, then one adversarial refuter per direction instructed to assume every recommendation was wrong. 16 recommendations produced, **15 survived, 1 killed**. Every `file:line` below was opened by at least two agents (a synthesizer and a refuter); the handful of exceptions are marked.

**Read this before re-auditing.** It exists so the next session can pick an item and go straight to a spec without re-running the audit. It also records what was *dropped and why*, so the same ideas do not get re-proposed.

---

## Ground truth (verified; do not re-derive)

- The crawler calls detection through `crawler/src/class/DetectionLangueClient.ts`. It sends `html_content` for every page in `complete` mode — which **bypasses the detection service's admission control entirely**, because the gate is only taken when a real fetch is needed — and sends `validate_alternatives: false` (`routes.ts:617`), which kills the alt HTTP/browser validation and the Case-6 confirmation loop while still returning parsed hreflang alternatives.
- `DetectionLangueClient.extractPrimaryMethod` (`:170-176`) splits `method` on `+` and returns any HTML method found **anywhere** in the array, falling back to `parts[0]`. `requiresNlpValidation` (`:186-189`) is a closed 3-method HTML whitelist. `routes.ts:628` persists the extracted primary into `{domain}.json`.
- **Nothing under `crawler/src/` reads `confidence`.** Declared at `DetectionLangueClient.ts:23`, zero readers.
- **Nothing under `crawler/src/` reads any detection technical verdict.** `challenge_page`, `fetch_empty_content`, `soft_404`, `redirected_to_home`, `admission_rejected` appear zero times as reads. The only hits are `UpdateChecker`'s own `http_error_{status}` strings (`UpdateChecker.ts:187,192`) and the two-substring gate at `routes.ts:692-693`.
- `DomainFR.check_url(url, track_redirect=False)` returns `{ok: True, method: 'direct_match'}` for **any** `.fr` hostname with zero network work (`domain_fr.py:233-235`). This is the resurrection mechanism behind finding A.
- Detection's challenge classifier runs on **provided** html: `routes.py:175` opens `if not html_was_provided` and **closes at `:336`**, so the classifier at `:370-376` is reachable on the crawler's calls. Same for `error` (`:451-454`, any internal exception returned as HTTP 200) and `fetch_empty_content` (`domain_fr.py:1352-1368`).
- Conversely, `validate_page` (`routes.py:213-336`) and the stub-page hop (`:344-367`) sit **inside** `if not html_was_provided`, so the crawler receives none of `soft_404` / `redirected_to_home` / `http_error`.
- `use_nlp_detection` is dead server-side: assigned at `domain_fr.py:163` and read nowhere else in `app/`. NLP runs unconditionally at `:1251-1272` **and inside** the `forced_method` branch at `:1176-1188`. `mode` gates only the alternatives step (`:1288`) — contradicting the OpenAPI text at `api/routes.py:410` ("simple : URL + attribut lang HTML uniquement (rapide)").
- **Trap:** the TypeScript crawler under Marketplace `BO/admin/.../scrapping_produit_ia/tools/crawler/` is legacy/dead except its `shell.php`. Nothing in this audit touches it.

---

## Findings

Priority is the refuter's defended ordering. `effort` is the original estimate, corrected where the refutation moved it.

### A. Technical failures are laundered into the `not_french` business verdict — `REAL`, effort M, crawler-only

*Found independently from both directions (caller-side hygiene and capability-consumption). The single systemic defect at this seam.*

**Today.** `isEnqueuingLinks` defaults false (`routes.ts:557`) and stays false on: a thrown detect/checkUrl error (`:717-720`, `:768-770`, `:817-819` — each only `log.error`), an unresolved bot challenge (`:739-741`, `:788-790`), and any `ok=false`. All of it converges on one `else` at `routes.ts:1138-1163`, which increments `filtered_nonfr` (`:1142`, with the BO `isError='not_french'` comment at `:1140-1141`), pushes the page into `nfr-{domain}` (`:1158-1161`), and in update mode calls `updateChecker.checkUrl(..., false)` (`:1147-1153`) → `isEligible` false (`UpdateChecker.ts:129-142`) → **`action:'deleted'` + a line in `deleted_urls.jsonl`** (`:267-283`).

Two further wrinkles:
- The `.fr` resurrection: three technical methods reachable on the crawler's own calls (`challenge_page`, `error`, `fetch_empty_content`) contain neither `nlp_not_confirmed` nor `nlp_override`, so the gate at `routes.ts:692-693` lets them through to `checkUrl`, which accepts any `.fr` host (`domain_fr.py:233-235`) and blanks `crawlErrorMessage` (`routes.ts:711-713`).
- An unresolved-challenge page is still sent to detection and `isEnqueuingLinks` is set back to true if that call returns ok (`routes.ts:793-812`, unguarded).

**Why it matters.** The precedent already exists one function up: the HTTP axis was hardened after **incident 1320-402** (63 anti-bot 403s → 59 false deletions) so that only 404/410 may claim a deletion (`UpdateChecker.ts:174-192`, which deliberately ignores `unverified_http_error_*`). That reasoning was never extended to the detection axis — a *larger* outage surface, because it is one shared HTTP dependency rather than per-URL statuses. A detection restart during a MAJ can emit deletion claims against live French fiches.

On non-`.fr`, `routes.ts:686` sets exactly `"Page non détectée en Français"`, and BO's `not_french_signal.php:21-23` trusts that string **unconditionally, before any counter test** — so a detection-side 500 (returned as HTTP 200 + `method='error'`) becomes a permanent business verdict.

**Change.** A `verdictUnavailable` flag beside `isEnqueuingLinks` (`routes.ts:557`), set in the three catches and the two challenge branches; guard the internal-page detect at `:793`; a `static isTechnicalFailureMethod(m)` on `DetectionLangueClient` over the closed set `{challenge_page, error, fetch_empty_content}` called before the `nlpRejected` test at `:692`; then split the terminal branch with `} else if (verdictUnavailable) { log.warning(...) }` before `:1138` — no counter, no `nfr-` write, no `updateChecker` call. Test goes in the existing `DetectionLangueClient.test.ts` (pure, no crawlee import, runs locally under tsx).

**Free side effect.** Honouring the server's `challenge_page` imports detection's maintained 9-family classifier. The crawler's hand-ported copy (`functions.ts:233-320`) is missing `Rescaled_WAF` (`language_detector.py:108-114`), `JS_PoW_bot_check` (`:119-127`) and `Squid_proxy_error` (`:136-146`), and narrows the error-title regex to `(403|401|406|429|503)` (`functions.ts:294-296`) where the service uses `[45]\d{2}` (`language_detector.py:154-157`). Those three families are exactly the ones that reach the laundering path, so the local copy is not shadowing it.

**Corrected framing — do not repeat the original claim.** The synthesis said a WAF-walled `.fr` site gets "crawled end-to-end with the interstitial as every page's content, garbage into the RAG data plane". That is **wrong in kind**. `routerDefaultHandler` (`functions.ts:1867-1893`, `Dataset.open(domain)` at `:1888`) has one callsite, `routes.ts:916`, **inside** `if (isEnqueuingLinks)` (opens `:823`). Internal interstitial pages also get `challenge_page` from detection, so they land in `nfr-{domain}`, never the main dataset. **Only the one resurrected homepage row enters the RAG plane.** The real harms are (1) the full crawl budget burned and the crawl reported SUCCESS, landing BO on `insufficientData`, and (2) the permanent `not_french` stamp on the non-`.fr` / detection-500 path. Lead with (2).

Also: a *thrown* homepage error sets a different message (`routes.ts:719`, "Erreur API de détection…") so it misses BO's string branch — but it still trips `not_french` via the counter branch (`not_french_signal.php:24`), because `filtered_nonfr`=1 and `nb_success_crawled`=0.

### B. `?lang=fr` propagation is dead on session-i18n sites — `REAL`, effort S, crawler-only

*Also found independently from both directions.*

**Today.** `routes.ts:636` gates the language-param capture on `primaryMethod === "pattern_match_query"`. But `extractPrimaryMethod` (`DetectionLangueClient.ts:170-176`) prefers any HTML method found anywhere in the `+`-split, and the decision matrix puts `html_method` ahead of position 0: Case 1 assembles `[url_method, html_method, 'nlp_confirmed']` (`domain_fr.py:1301-1307`), Case 3 does `methods.insert(1, html_method)` (`:1396-1399`). So `pattern_match_query+langHtml+nlp_confirmed` reduces to `langHtml`, the test is false, and `context.languageQueryParam` is never assigned (only written at `routes.ts:637` and `:706`; default null at `context.ts:159`).

The re-injection at `routes.ts:1021-1034` is then a no-op, every discovered link loses the param, the server serves its default language, and the stored `langHtml` forced_method rejects each page (`domain_fr.py:1174` requires the tag value to be `fr`, else `Check_nok_forced` at `:1237-1241`) → straight into branch A. **Net: a full crawl of a genuinely French site yielding near-zero French pages, plus an inflated `filtered_nonfr` and a wrong BO signal.**

The sibling `checkUrl` branch (`routes.ts:705`) is correct only by accident — `/check-url` returns single bare tokens (`domain_fr.py:235,250,266`).

**Change (preferred shape).** Drop the method gate: inside the `detectResult.ok` branch call `DetectionLangueClient.extractLanguageQueryParam(site)` unconditionally and assign when non-null. The helper already self-guards — it returns null unless the seed carries a `lang|locale|language|hl` matching `/^fr/i` (`DetectionLangueClient.ts:201-218`). Two lines. The alternative shape (test `detectResult.method.split("+").includes("pattern_match_query")`) also works and is the one that stays correct as new `+`-composed methods keep appearing.

**Scope note.** The dead guard bites only the intersection — seed carries `?lang=fr` **and** the homepage declares a French `<html lang>`/meta. Without the HTML tag, `parts[0]` wins and propagation works today. That intersection is the common CMS-i18n shape, and when it hits the whole crawl is lost.

**Risk.** Propagation now also fires when the verdict came from the TLD. Injection is additive and only when absent (`:1023`), so the blast radius is one extra query param on internal URLs — which does change dedup keys and the `?`-param surface, relevant if `QM_TIER2_ENABLED` is on.

### C. A homepage detection failure ships a SUCCESS webhook — `REAL`, effort S, both services (Node half can ship alone)

**Today.** The homepage catch (`routes.ts:717-720`) sets only `context.crawlErrorMessage` — no `stopReason`, no `fatalExitCode` (those are set only at `routes.ts:332/344`=7, `:426`=8, `functions.ts:747`=9). The queue drains, so `isError` stays empty (`main.ts:1197`), `gracefulShutdown('COMPLETED', context.fatalExitCode ?? 2)` exits 2 (`main.ts:1763`), and `_classify_exit_code` returns `(None, None)` for 2 (`crawler_manager.py:348-351`) ⇒ status `finished` + **success webhook**. The only trace is a 250-char truncated French free-text `message_erreur_crawling` (`main.ts:1217-1231`, payload `:1267`).

**Change.** Set `context.stopReason = "detectionUnavailable"; context.fatalExitCode = 10;` and call the existing `stopCrawler(...)`. Add the `ERROR_MAP` entry (`main.ts:1126-1140`; `limitQueue` is at `:1139`, so insert at `:1140`). Add `elif exit_code == 10: return ("Service de détection de langue indisponible", "detection_unavailable")` to `_classify_exit_code` (before the 137 branch) and add 10 to the exclusion tuple at `:348`. Update the exit-code + `failure_cause` tables in `crawler-service/CLAUDE.md`.

**Sequencing.** Exit 10 is free (the tuple at `:348` lists 0,2,3,4,5,6,7,8,9,-1,137) and degrades safely into the existing `unknown` branch ⇒ failed + failure webhook, so the Node half can ship alone. **Before flipping, confirm BO treats `detection_unavailable` (or an unknown cause) as retryable rather than terminal** — if BO auto-retires on unknown causes, ship the Python branch and the BO mapping together.

**Correction.** "a 1-page crawl" holds only for initial crawls; in update mode `homepageReady.resolve()` at `routes.ts:1171-1173` sits outside the doublon/detect result, so Phase-2 still seeds the previous crawl's URLs. The success-webhook-on-infrastructure-failure defect is identical.

### D. Update crawls inherit regional exclusions forever — `REAL`, effort M, crawler-only

**Today.** `copyPreviousMethod` (`functions.ts:1371-1400`) `fs.copyFileSync`s the previous `{domain}.json` whole (`:1386`) and preloads `excludedPaths` into `context.excludedRegionalPaths` (`:1396-1399`); called from `main.ts:895` inside `if (crawlMode === 'update')`. `seedPhase2` then **skips the fresh homepage wait entirely** whenever that array is non-empty (`main.ts:1512-1513`). `routes.ts:664-670` only ever assigns a fresh result when it is non-empty — never clears. `manageFrenchDetectionMethod` re-serializes it on every write (`functions.ts:2291-2294`) and reads it back (`:2300-2306`).

Net: the exclusion set is frozen at initial-crawl time, monotonically re-persisted, and **can never shrink or be revalidated** — while detection TTLs its own equivalent domain knowledge at 30d/7d/6h (documented `api-detection-langue-fr/CLAUDE.md:91`; the `domain_fr.py:43-45` citation is corroborated-by-doc, not line-verified). Content loss is live: `routes.ts:1084-1088` blocks any discovered link matching an excluded prefix via `isExcludedRegionalPath` (`DetectionLangueClient.ts:246-256`).

**Change.** Make `copyPreviousMethod` carry the method only: replace the `copyFileSync` with a read-parse-write of `JSON.stringify({ method: content.method })` and delete the `excludedPaths` preload. A same-crawl OOM restart still restores the **current** crawl's set through `manageFrenchDetectionMethod`'s read path (`functions.ts:2304-2306`) — the case the disk preload actually protected.

**Correction (cheaper than advertised).** The stated "update crawls now pay the ≤120s Phase-2 wait" does **not** apply in the doublon case: `homepageReady.resolve()` is deliberately outside the `isDoublon` check (`routes.ts:1171-1173`, comment at `:1168-1170`), so the wait resolves immediately with an empty set — more crawling, nothing lost. The 120s exposure applies only when the homepage is genuinely handled fresh and detection is slow.

**Out of scope, needs its own decision.** The inherited **`method`** has the same staleness problem in the doublon case (a stale HTML forced_method rejects every page → `deleted` in MAJ). Do not fold it into this edit.

### E. `checkUrl` has no 503 / `Retry-After` retry — `REAL`, effort S, crawler-only

`_detectWithRetry` implements the contract faithfully (503 only, `Retry-After` wins over `backoffBase * 2**attempt`, `DetectionLangueClient.ts:117-128`). `checkUrl` (`:146-157`) is a single GET in the same p-limit with a bare catch→throw. The Python reference client routes **both** through one helper (`libs/common-utils/src/common_utils/detection_client.py:42-44, 46-75`, whose docstring is the contract `crawler-service/CLAUDE.md` says the TS client mirrors).

Not cosmetic: a `checkUrl` throw is swallowed by the enclosing catch (`routes.ts:717-720`), leaving `isEnqueuingLinks=false` — so one 503 on `/check-url` sinks the homepage into branch A. Fix = extract a `private async _withRetry<T>(label, fn)` and call it from both. Add a stubbed-503 case to `DetectionLangueClient.test.ts` (it already stubs the axios instance, `:5-16`).

### F. The Apify proxy password is sent on every `html_content` call — `REAL`, effort S, crawler-only

`proxy_url: options?.proxyUrl ?? undefined` (`DetectionLangueClient.ts:109`) is sent on all three call sites (`routes.ts:616, 748, 804`), fed from `routes.ts:236`. That string embeds the credential (`http://auto:${password}@proxy.apify.com:8000`, `functions.ts:62-68`) — which is why the crawler masks it everywhere else it touches it (`maskProxyUrl`, `functions.ts:75-86`, used at `routes.ts:595`).

Server-side the field is **structurally unreachable** on these calls — stronger than the original claim: every `proxy_url` consumer sits under `if not html_was_provided` (`api/routes.py:175→194/197`, `261/266`, stub hop `344-351`), and `proxy_url` is **never passed to `DomainFR` at all** (`api/routes.py:378-384` passes only homepage/forced_method/use_nlp_detection/original_homepage/validate_alternatives). So a live credential crosses a service boundary thousands of times per crawl for nothing, where it can land in any request-body log, APM trace or 422/500 dump on either side.

**Change.** Two lines at the single chokepoint: `proxy_url: htmlContent ? undefined : (options?.proxyUrl ?? undefined)` and `html_content: htmlContent ?? undefined`. The field is declared on the schema (`models/schemas.py:25`), so omitting it is contract-safe.

**Coupling — land F before or with A.** Today `html_content: htmlContent || undefined` (`:105`) coerces an empty extraction to *absent*, flipping the call to a fetching, admission-taking, cache-**writing** path. The `??` fix makes `info_vide` (`domain_fr.py:1153-1158`) reachable, and A's predicate is what stops it being laundered. (The empty case is latent, not live today: `getPageContentWithRetry` either returns a document or throws, `functions.ts:163-220`.)

### G. The four contract knobs are absent from compose (+ NaN-guard them) — `REAL`, effort S, compose

`DETECTION_LANGUE_API_URL` (`docker-compose.yml:1373`) is the **only** `DETECTION_*` entry in a 30+ var block. `DETECTION_MAX_CONCURRENCY`, `_REQUEST_TIMEOUT_S`, `_MAX_RETRIES`, `_BACKOFF_BASE_S`, `DETECTION_BACKPRESSURE_MAX_PENDING`, `REQUEST_HANDLER_TIMEOUT_S`, `CRAWLER_MAX_CONCURRENCY` appear nowhere, so they can only arrive via the shared uncommitted `env_file: .env` (`:1362-1363`; the repo `.env` is 94 bytes, one line, no `DETECTION_*` key). `GET /admin/config` lists env vars only when present in `os.environ` (`admin.py:214-215`), so an operator cannot distinguish "unset, code default" from "someone exported 25 on the host" — while tuning exactly these values is the documented remediation for a detection incident. Same class as the REDIS_URL-missing-from-compose incident.

**Change.** Add `${VAR:-default}` lines next to `:1373`. The four contract knobs + backpressure match the whitelisted `DETECTION_` prefix (`admin.py:190`). If `REQUEST_HANDLER_TIMEOUT_S` / `CRAWLER_MAX_CONCURRENCY` go in the same pass, extend `_ENV_WHITELIST_PREFIXES` (`admin.py:189-194`) — neither matches an existing prefix (`MAX_CONCURRENT` does **not** prefix-match `CRAWLER_MAX_CONCURRENCY`) and `tests/test_admin_config.py:39-69` enforces compose→whitelist parity.

**Bundle the NaN guard here.** `DetectionLangueClient.ts:64-67` does raw `parseInt`/`parseFloat` with no validation, unlike every other crawler knob, which goes through a `Number.isFinite` resolver (`httpStatusPolicy.ts:62-93`, wired `:119-124`; `crawler-service/CLAUDE.md` documents "Both thresholds validate against NaN and non-positive values"). A NaN timeout is falsy to axios ⇒ **no timeout at all**; a NaN `maxRetries` makes `attempt <= NaN` never run and every call throws at `:135`; `pLimit(NaN)` (`:73`) inside the unconditional `new DetectionLangueClient()` (`main.ts:1613`) would crash at startup before any page.

**Correction — the original flagship example was wrong.** `parseInt("18O")` is **18**, not NaN (parseInt stops at the first non-digit). NaN needs an empty string or leading garbage, and `?? "180"` only defaults on undefined/null — so the realistic trigger is an **empty-valued env var**, which is exactly what a bare `- DETECTION_REQUEST_TIMEOUT_S=${DETECTION_REQUEST_TIMEOUT_S}` in compose produces. Hence: ship the guard together with the `${VAR:-default}` declarations, whose form removes the only realistic trigger. On its own the guard defends against a hand-typo only, with zero evidence any of these vars is set anywhere today.

### H. `detect_ms` is 0 on exactly the failing calls — `REAL`, effort M, crawler-only

`_timing.detectEndAt` is assigned only on the line after each successful await (`routes.ts:619, 750, 806`), never in the catches (`:717, 768, 817`). `buildTimingEntry` falls back `detectEndAt = detectStartAt` (`:73-74`) ⇒ `detect_ms: 0`, with the whole 180s wait folded into `post_ms` (`:81-82`). The `finally` at `:1174-1185` records the entry on every path, so the misleading row is definitely written. The same single marker pair also covers up to three calls per page (`:745` and `:799` both assign `detectStartAt`), so only the last survives.

No rollup either: `TimingSummary` (`timing/types.ts:48-72`) carries phases+pool only, `buildSummary` (`aggregator.ts:119-143`) computes nothing from the `detect_ok`/`detect_method` fields already present on every entry, and `timing.jsonl` is deliberately excluded from `/admin/sidecar` as unbounded (`admin.py:336-346`) — while **`timing-summary.json` IS servable** (`:341`).

So during a detection incident the surfaces built after crawl 7033 for exactly this diagnosis show detect healthy and `post_ms` exploding. Fix = set `detectEndAt` in the catches (or try/finally), accumulate rather than overwrite, and add `detect: { ok_pct, failed_count, top_methods }` to `TimingSummary`. No new collection, no new endpoint. Reachable by default (`TIMING_ENABLED=${TIMING_ENABLED:-true}`, `docker-compose.yml:1398`; gate `main.ts:1623`).

### I. Two in-code claims that internal detects are cheap — `REAL`, effort S, docs only

`routes.ts:796-798` says "When stored method is HTML-based, use forced_method for fast validation", and the client defaults `use_nlp_detection ?? true` (`DetectionLangueClient.ts:108`) as if the flag were live. Both are false server-side (see Ground truth). Anyone reasoning about crawl latency from the crawler's code concludes internal detects are cheap and tunes the wrong knob. Reword the comment and drop the cost implication from the Detection Backpressure section of `crawler-service/CLAUDE.md`. **Deliberately do not remove `use_nlp_detection` from the request body** — whether the service honours it or drops it from the contract is the detection side's decision.

### J. Duplicate `/detect` on the no-stored-method path — `REAL_BUT_MISPRIORITIZED`, effort S, crawler-only

Real: `routes.ts:746-749` detects; on `autoCheck.ok` line `:757` assigns `methodOrError` a string, so the `instanceof Error` test at `:773` is false and `:800-805` issues a **second** `detect` on the same URL and content. Outcome is deterministically identical (the forced branch at `domain_fr.py:1172-1174` compares against the same `detect_from_html_tags` token the first call produced, and `mode:'simple'` means alternatives are never fetched, `:1288`).

**Both urgency claims were inverted — do not ship the original framing.** (a) "every internal page for the rest of the crawl" is false: the first successful auto-detect memoises `context.frenchDetectionMethod` (`functions.ts:2273-2280`), so later pages read it from memory and take the single-detect path. (b) "doubles load exactly when detection is failing" is backwards: when detection fails, `autoCheck` throws → `methodOrError` is still an Error → `:773` skips the second call ⇒ **one** call. The duplicate fires only when detection is **healthy**. Real cost ≈ one duplicate per concurrent handler in flight before the first success (≤ `CRAWLER_MAX_CONCURRENCY`, default 20) **per crawl**, not per page. Bundle it with something else; do not schedule it alone.

### K. `id_lang` / `isolang` stripped from every link — `REAL_BUT_MISPRIORITIZED`, effort S, evidence-gated

`ALWAYS_REMOVE_PARAMS` lists `"isolang", "id_lang"` under the comment "PrestaShop (non-routing params only)" (`routes.ts:196`) — the comment is simply **false** for `id_lang`, which is the language router in non-friendly-URL mode. Applied unconditionally to every discovered link (`routes.ts:993`; `functions.ts:2151-2163` confirms the strip fires regardless of `skipQuestionMark`), before the language re-injection, which can only restore `lang|locale|language|hl` (`DetectionLangueClient.ts:206`). Detection cannot rescue it either: `check_url`'s vocabulary is `['lang','locale','language']` (`domain_fr.py:262`), so `pattern_match_query` is unreachable for `id_lang`. No operator workaround: `toKeep` is not passed to that call at all.

**Gate before spending effort.** Prevalence is not measurable from the code — run a BO query over `data_crawling` start URLs for `id_lang` seeds first. If zero, close it as a comment fix.

**Use the surgical fix, not the proposed one.** The suggested `ALWAYS_REMOVE_PARAMS.filter(p => !seed.searchParams.has(p))` has an undersold blast radius: `ref`, `referrer`, `source`, `medium`, `campaign` (`routes.ts:182`) and `PHPSESSID`, `sessionid`, `sid` (`:185-186`) are in the same list, and BO-sourced seeds commonly carry a tracking param — so it would silently stop stripping session/campaign params on every link for that crawl. Prefer: remove `id_lang`/`isolang` from the list (they *are* routing, so the comment becomes true), **or** add `id_lang` to both language vocabularies (`domain_fr.py:262` + `DetectionLangueClient.ts:206`) so the existing propagation machinery carries it.

### L. Page validation is unreachable for the crawler — `REAL_BUT_MISPRIORITIZED`, measurement task first

`validate_page` and the stub hop are inside `if not html_was_provided` (`api/routes.py:213-336`, `:344-367`), so the crawler gets no `soft_404` / `redirected_to_home` / `http_error`. Crawler-side there is **no equivalent at all**: page quality is purely HTTP status (`httpStatusPolicy.ts:14-30`), and a grep for `soft.?404|notFound|thinContent|minContentLength` across `crawler/src` returns nothing. So a French 404 template arrives as HTTP 200, passes the language check, and is stored as a legitimate dataset row (`functions.ts:1888` via `routes.ts:916`).

The html-only half is genuinely self-sufficient: `_detect_soft_404` (`page_validator.py:77-98`) needs only `final_url` for `_URL_404_PATH_RE` plus `html` for the title/H1 regex and `_visible_text_length` — no status code, no network. `validate` itself (`:49-68`) is the only part needing status_code and final_url.

**Corrected scope and sequencing.** Not independently actionable — it hard-depends on A creating the "technical, not a verdict" branch, so schedule it strictly after. Ship **`soft_404` only** (S-to-M), not the full validator: `http_error`/`redirected_to_home` need the crawler to send HTTP status and final URL, i.e. a `DetectionRequest` schema change. And **measure before building**: run `GET /admin/dataset/{crawl_id}` over a few recent crawls, count rows whose title/H1 matches `_NOT_FOUND_RE` with a thin body; if negligible, drop it. Do **not** port the heuristic to TypeScript — the drifted `detectChallengePage` copy is the standing evidence for why a second implementation rots.

---

## Killed by refutation

**Derive regional path exclusions on the `checkUrl`-accepted path — `SPECULATIVE`.** The code fact was right (`context.excludedRegionalPaths` is assigned only inside `if (detectResult.ok)` at `routes.ts:665`, so the filter is inert on that branch), but **the target class cannot reach it**. For a `.fr` host with a non-French root the service returns Case 2a `nlp_override_tld_fr` (`domain_fr.py:1333-1340`, forced immediate by the crawler's own `validate_alternatives:false` at `:1329`), which contains `nlp_override` ⇒ the gate at `routes.ts:692-693` skips `checkUrl` entirely. Same for Case 7 `nlp_not_confirmed`. Of the `ok=false` methods that *do* fall through, all carry empty `alternative_urls` except `fetch_empty_content` — which by construction means a homepage with almost no text, i.e. no links to explode into locale trees. **And it directly contradicts A**, which reclassifies `fetch_empty_content` as technical: implementing A makes this dead code. Ship A; drop this.

## Also considered and deliberately dropped

Recorded so they are not re-proposed. Each was confirmed against the code first.

- **Read `confidence` / act on `nlp_weak_disagree_<lang>`** — confirmed unread, and the service emits synthetic per-case constants (`domain_fr.py:1376-1385, 1432, 1509`) alongside real probabilities (`:1313, 1405, 1495`), so it is not one comparable scale. Acting on it means the caller overriding a verdict detection deliberately returns as `ok=true` — a 9-case-matrix policy decision, not a caller-side fix. Would create false negatives on exactly the French-with-technical-vocabulary sites the langdetect cross-check exists for.
- **Re-seed the crawl from `alternative_urls[0]`** — the alt is already surfaced to the operator in `message_erreur_crawling` (`routes.ts:676-680`) for a manual relaunch. Automating it means seeding a URL that was never fetched (the crawler's own `validate_alternatives:false` makes non-hreflang alts `validated:false/'low'`, and hreflang `validated:true` means only "declared in the markup"), or re-enabling the alt validation deliberately disabled as the residual OOM source. There is also no `addRequests` call anywhere under `crawler/src/` — new machinery. Product decision with fiche-identity and update-baseline blast radius.
- **Gate `computeExcludedRegionalPaths` on `alt.reliability` / `alt.validated`** — both fields are unread for any decision (`DetectionLangueClient.ts:300-363` reads only `url` and `region_priority`). Gating on either would be a no-op or would disable the feature for every non-hreflang site, re-admitting the duplicate locale trees it exists to avoid. `isLocalePathPrefix` (`:274-277`) plus the FR implicit-winner branch (`:308-330`) already bound the damage.
- **Adopt `/detect-batch` or the async job API** — already correct as-is. The verdict gates the *current* page's link enqueue inside a synchronous Crawlee handler, so there is nothing to batch; and the server already exempts 100%-`html_content` batches from its concurrency clamp (`api/routes.py:150-156`). Do not let this be "fixed" by batching — the lever is per-call cost and call count.
- **Re-port the missing challenge families into the crawler's `detectChallengePage`** — the drift is real but porting doubles down on two copies of a 150-line heuristic in two languages. A is the root-cause fix; the local copy then degrades to a pre-filter optimisation.
- **Reuse detection's consent-aware HTML→text cleaning for the dataset** — exposed only through `/detect-debug` + `include_full_content`, which is deliberately capacity-starved (`ADMISSION_DEBUG_SLOTS=2`) and runs its pipeline twice: a diagnosis tool, not a data path. It also truncates at 10000 chars and returns None under 100 — thresholds tuned for language detection, not RAG content. The crawler already has content-extractor `/clean` wired.
- **Expose the redirect chain** — genuinely captured and dropped server-side (`scraper.py:582-588` → `redirect_tracker.py:73-77` → `domain_fr.py:287-300`), but every fetch path is inside `if not html_was_provided`, so there is no chain for the crawler's calls to receive. Would only serve the BO path.
- **Use detection's http/https + www variant cascade against the `domain_dead` exit-9 verdict** — real capability (`redirect_tracker.py:136-182`, "www toggle first — cause #1 of DNS failure on .fr"), but the crawler's dead-host exit is behind `TERMINAL_FAILURE_DETECT_ENABLED`, default **off**, so the cost is not live; and the only way to consume it today is `checkUrl(url, trackRedirect=true)`, which reaches a full Camoufox launch through the shared `BROWSER_SEMAPHORE` with **no admission slot** (`admission.py:42` gates only `/detect-debug`). Recommending it would push an ungated browser launch onto the pool admission exists to protect. A one-line crawler-side HEAD on the toggled host would be lazier — but that is not a detection capability.
- **`info_vide` mishandled** — falsified. It fires only on `if not url or not content` (`domain_fr.py:1150-1156`), and the client coerces an empty string to absent, so a provided-html request always has non-empty content. Unreachable for this caller **today** — but see F, which makes it reachable on purpose.
- **A connect timeout to match the Python contract's `connect=10.0`** — axios exposes no separate connect timeout; it would need a custom `http.Agent` for a case the socket timeout already bounds. `[UNCLEAR]` on exact adapter semantics; low value.
- **Cap or truncate the HTML sent per call** — a caller-side prefix cap changes what the server's NLP and tag extraction see, so it cannot be done safely without the detection side re-validating its thresholds against truncated input. Joint change; the caller cannot verify it alone.
- **A Prometheus surface for the seam** — crawler-service exposes no `/metrics` and `prometheus/prometheus.yml` lists neither service. New infrastructure with one consumer; prod may scrape from config outside this repo. H gets the same answers out of the already-served `timing-summary.json`.
- **A fleet-wide detection concurrency budget** — needs shared state (a Redis token bucket). The correct place to bound it is the server's own admission/clamp. G at least makes the per-process number visible.
- **`nlp_soft_confirmed` as `parts[0]`** (new from the just-merged soft-FR branch) — not in the 3-method HTML whitelist, so `requiresNlpValidation` returns true and internal pages take the full-matrix path with `forcedMethod: undefined`. Correct, if most expensive, handling. No caller change needed. It does get persisted into `{domain}.json`, which is harmless precisely because nothing can match it as a `forced_method`.
- **Stale inherited `forced_method` with no TTL** — same family as D but a distinct decision (what refreshes a domain's method on an update crawl?). Deserves its own spec; second-order to A, which removes the destructive consequence.

---

## Sequencing constraints

1. **A before L.** L needs A's "technical, not a verdict" branch to route verdicts into.
2. **F before or with A.** F makes `info_vide` reachable; A's predicate keeps it from being laundered.
3. **A kills the killed item.** Do not implement both.
4. **G bundles the NaN guard** — the `${VAR:-default}` form removes the guard's only realistic trigger.
5. **C's Python half + BO mapping ship together** if BO auto-retires on unknown failure causes; otherwise the Node half is safe alone.
6. **K is gated on a BO prevalence query**; **L is gated on a dataset count.** Neither is a code task yet.

## Suggested first slice

**A + B in one spec.** Both are `routes.ts`, B is two lines, and they are the two items with demonstrated loss behind them: false MAJ fiche deletions on a detection outage (A) and whole wasted crawls on session-i18n sites (B). Everything else is hygiene, observability, or evidence-gated.

## Provenance

Workflow run `wf_41801b37-dde`. Raw agent returns: that run's `journal.jsonl` under the session's `subagents/workflows/` directory (session-scoped — this document is the durable record). Audited at `features/poc` tip `b4e70966`, i.e. **including** the just-merged soft-FR lexical-corroboration change and **not** including any of the findings above.
