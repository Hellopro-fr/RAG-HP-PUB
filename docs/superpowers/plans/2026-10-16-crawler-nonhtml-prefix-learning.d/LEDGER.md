# SDD ledger — plan: docs/superpowers/plans/2026-10-16-crawler-nonhtml-prefix-learning.md
Workspace (briefs, reports, reviews, gitignored): <WT>/.superpowers/sdd/2026-10-16-crawler-nonhtml-prefix-learning/
Base jugée: features/poc = e57409aed (re-mesuré 2026-10-16 session A : 0 commit neuf). Plan HEAD 802f90a1a.
Session A form: launched in main checkout, EnterWorktree path ⇒ guard armed; git = plain single commands from <WT>; heredoc/compound Bash refused ⇒ ledger appends via Write/Edit.
Ruling: ledger kept here (.d/LEDGER.md, untracked) per user prompt, not in SDD workspace — survives workspace deletion — cost if wrong: one untracked file in git status.
Ruling: .tasks.json sync deferred to one controller commit at end of each session — tracked file, never left dirty across dispatch — cost if wrong: stale statuses until that commit.
Preflight: <workspace>/preflight.md (scratch run of all tasks: tsc 0 err, npm test 625 = 509+49+29+19+9+10, 1 fail = finding P1). Anchors F1-F22 match HEAD; no existing assertion modified; [contrôleur] steps T09:442, T10:251, T10:261.
Ruling P1: T07 search string "onHtml(request.url)" also matches inside onNonHtml (T07.md:107,:193) — use ".onHtml(request.url)" at both; T07 implementer re-measures proof-mutation fail count (T07.md:270 "≥2") and reports — cost if wrong: one T07 fix round.
Ruling P2: clean-tree checks T07.md:30,:278, T10.md:247 trip on LEDGER.md/.tasks.json — controller commits both (own commit) right before T07 and T10 dispatch — cost if wrong: Step 1 STOP.
Ruling P3: T06.md:137 numstat expected "17 0" (preflight measured; b3 block 12 lines) — carried in T06 dispatch — cost if wrong: one STOP.
Ruling P4: T04.md:241 "≈61" lines is 49 measured; only 0 deletions binding — carried in T04 dispatch.
Ruling P5: test-summary oracle = `grep "^ℹ"` on a saved suite output, not `tail -12` (stack trace hides ℹ lines on failure) — in implementer-common.
Ruling P6: guard-refused forms (T01:30,:46, T09:407; blocks T06:28-35,131-135,141-144,168-173, T07:47-49) — implementer rewrites per preflight §6, lists deviation; `cd <CR> && env -u NONHTML_PREFIX_MODE …` measured ACCEPTED by guard.
Ruling P7: T01.md:37 cmp against <MAIN> skipped — node_modules present in <CR> (302 entries), Step 0 reinstall not needed.
Task 1: dispatched (BASE 802f90a, general-purpose sonnet/medium)
Task 1: minor (deferred): red-first run (Step 2) and 509 baseline (Step 0.3) skipped by implementer
Task 1: minor (deferred): NONHTML_PREFIX_DEFAULTS exported mutable, kept by reference in state (freeze = addition)
Task 1: minor (deferred): probe slot held by a URL never fetched blocks key for the crawl — already accepted frontier in index C5 "Décision du contrat"; final review to confirm
Task 1: complete (commits 802f90a..feef934, review clean, review file 6128B) — controller re-run: tsc rc 0, npm test 558/558 fail 0. Controller cost T1 measured ≈7k; setup ≈90k.
Task 2: minor (deferred): parser accepts prefix keys without "/" (corrupt key loads as confirmed, written back forever) — check = addition
Task 2: minor (deferred): isolated URLs from previous crawl blocked without probation, rewritten each crawl until isolatedMax evicts — spec design choice ⇒ report to user at final
Task 2: ⚠️ resolved: rename-fails test on Linux — target is a directory ⇒ rename(2) EISDIR on Linux as EPERM on win32; test asserts only the warn prefix ⇒ portable
Task 2: ⚠️ carried to T4: currentSidecarPath and resolvePreviousSidecarPath must get the same `domain` string (C8 uses one variable)
Task 2: complete (commits feef934..a72dcd6, review clean, review file 5670B) — implementer: red first seen, 587/587, tsc clean
Task 3: dispatched (BASE a72dcd6, general-purpose sonnet/medium)
Task 3: minor (deferred): shadow mode logs ≥2 "would block" per URL (enqueue+prenav+retries), probe re-logged per retry — T10 doc / shadow reading must count distinct URLs, not lines
Task 3: minor (deferred): no gate test for loadedIsolated block with null key ("[null]" in log)
Task 3: minor (deferred): Step 6 anchor pre-count skipped — numstat 3/0, i/lf hold
Task 3: complete (commits a72dcd6..af2f775, review clean, review file 4816B) — controller re-run: tsc rc 0, npm test 606/606 fail 0
Session A cut after T3 (context ≈220k; T4 + fix round would pass ~240k). Measured: setup ≈90k (baseline system ≈100k not counted in the 25k estimate), per task ≈5-7k when all delegated. Session B: T4-T10 + final review + finishing; expect cut after ~T7 if setup again ≈90k — re-measure.
Session B setup artifacts (reuse, do not rebuild): <workspace>/implementer-common.md, reviewer-filled.md, preflight.md. Next BASE = af2f775 (+ controller commit of ledger/tasks.json, read `git -C <WT> log --oneline -1`).
Session B (2026-10-16 11:29): launched IN worktree; guard NOT armed (`cd <WT> && git log` accepted); features/poc = e57409aed (0 new). implementer-common scratchpad repointed to session B.
Ruling: multi-pair Edit sections applied by <workspace>/apply-section-edits.py (extracted, count==1 dry run, CRLF-aware) — skill §1 "text carried to the byte" — cost if wrong: none beyond script bug caught by dry run/numstat.
Task 4: dispatched (BASE 0421e00, general-purpose sonnet/medium); dry run 9 pairs count=1, +49
Task 4: implementer DONE commit 2a4feb5 (49/0, i/lf, 606/606, tsc 0); review dispatched (opus/high) ⇒ <workspace>/task-4-review.md — NOT YET READ by controller
Task 5: dispatched in parallel with T4 review (BASE 2a4feb5, sonnet/medium; dry run 3 pairs count=1, +13) ⇒ <workspace>/task-5-report.md. If T4 needs a fix round, run it AFTER T5 commits (shared index).
Task 6: brief extracted <workspace>/task-6-brief.md; dry run 2 pairs count=1, +17 (= P3 "17 0").
Session B cut 2026-10-16 (usage limit) after T5 dispatch — resumed same session.
Task 4: minor (deferred): readStat("filtered_nonhtml") runs in off mode (plan-prescribed, never published)
Task 4: ⚠️ resolved: b2 probe then b3 prenav on same seed — decide() step 4 "probeUrl === n ⇒ probe" (00-index C1) returns probe without admitted++; seedUrl = enqueued url/uniqueKey ⇒ same n
Task 4: complete (commits 0421e00..2a4feb5, review clean, review file 5862B)
Task 5: implementer DONE commit 2f67b50 (13/0, 606/606, tsc 0); review dispatched (opus/high) ⇒ task-5-review.md
Task 6: dispatched in parallel with T5 review (BASE 2f67b50, sonnet/medium) ⇒ task-6-report.md
Task 5: minor (deferred): b1 runs per link occurrence before knownUrlsOnPage dedup ⇒ filtered_nonhtml at b1 counts page×link (b2/b3 per request); shadow `would block` lines = occurrences — Ruling: placement plan-imposed (stop 6 if moved), carry "unit = occurrences" into T10 doc dispatch — cost if wrong: misread shadow counts
Task 5: ⚠️ resolved: site + dataset exemption at b1 = gate Set filled by T4 (addExempt(site) C8, addExempt(consolidatedUrl) F10), T4 review verified C8 line for line
Task 5: complete (commits 2a4feb5..2f67b50, review clean, review file 5210B)
Task 6: implementer DONE commit e8cff65 (17/0 P3, i/crlf, bare-LF 0, 606/606, tsc 0); review dispatched (opus/high) ⇒ task-6-review.md
Task 6: minor (deferred): probe admitted at b1/b2 then dropped by an earlier prenav hook (facet cap, filter-on-seen) exits via STALE_VARIANT_SKIP_MARKER branch before onProbeFailure ⇒ slot held, prefix blocked for the crawl — inside C5 accepted frontier; moving the call = plan change ⇒ final review / user
Task 6: minor (deferred): shadow logs `would block` at enqueue AND prenav for one URL (same as T3 minor) ⇒ T10 doc: count distinct URLs
Task 6: ⚠️ resolved: b2 probe then b3 — reviewer confirmed request.url === seedUrl (main.ts:1662, crawlee request.js:215), decide step 4 no admitted++ (nonHtmlPrefix.ts:226)
Task 6: complete (commits 2f67b50..e8cff65, review clean, review file 7376B)
Session B cut after T6 (CONTEXTE 225k + T7 ≈12k + handoff > 240k). Session C: P2 commit already done (see git log) ⇒ dispatch T7 (BASE = HEAD), then T8-T10 + final review. T10 dispatch carries: shadow counts = occurrences (T3, T5, T6 minors). Measured session B: setup ≈25k over socle, ≈5-7k per task, parallel review(N) ‖ implement(N+1) worked (disjoint files).
