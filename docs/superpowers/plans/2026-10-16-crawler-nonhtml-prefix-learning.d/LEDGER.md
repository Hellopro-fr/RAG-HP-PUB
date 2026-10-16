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
Session C (2026-10-16): launched IN worktree; guard ARMED (sed with $D variable refused) ⇒ literal paths only; features/poc = e57409aed (0 new). implementer-common scratchpad repointed to session C.
Task 7: dispatched (BASE 74604c4, general-purpose sonnet/medium); P1 carried (needle .onHtml(request.url) at T07:107,:193; mutation fail count re-measured)
Task 7: implementer DONE_WITH_CONCERNS commit 13209ed (194/0, i/lf, wiring 9/9, suite 615/615, mutation fail 2); review dispatched (opus/high) ⇒ task-7-review.md
Task 7: concern — first full npm test 600/597/3 (DedupManager.monitor, DedupManager, ProgressMonitor), rerun 606/606 ⇒ timing flake under load; controller re-run queued
Task 7: concern — guard refused env -u NONHTML_PREFIX_MODE + redirection; plain npm test with variable verified unset
Task 8: dispatched in parallel with T7 review (BASE 13209ed, sonnet/medium); Ruling: 3 admin.py edits applied by extraction script, not Edit — skill §1 three pairs = extracted — cost if wrong: none beyond numstat 6/2 catch
Ruling: T09 Step 8 [contrôleur] real replay deferred to registry phase 2 — kind=pdf exists only after T8 is deployed on the VM, and export = admin API calls with key on the VM — cost if wrong: K not measured inside the plan (already a hors-plan phase per index § Phases)
Task 7: ⚠️ resolved: full suite 615/615 fail 0 by controller re-run at 13209ed (under T8 load); mutation fail 2 per implementer report (names match brief); env -u equivalence — no .env* sets NONHTML_PREFIX_MODE (reviewer)
Task 7: minor (deferred): blankComments blanks only full-line // comments, docstring claims more (test:25-32)
Task 7: minor (deferred): bare-key regex catches only the comma form (test:124-128)
Task 7: minor (deferred): 500/600-char windows prove proximity not containment (tight today)
Task 7: open point — DedupManager.monitor/DedupManager/ProgressMonitor failed once on first full run before T7 test existed, green on 2 reruns — Ruling: pre-existing timing flake at BASE, recorded not fixed; blocks none
Task 7: complete (commits feb9bd9..13209ed, review clean, review file 6892B)
Task 8: implementer DONE_WITH_CONCERNS commit 4f521b8 (admin.py 6/2 i/lf, trio 20 passed = 12+8); review dispatched (opus/high) ⇒ task-8-review.md
Task 8: minor (deferred): Step 2 red run skipped (one script wrote test + edits together)
Task 8: concern — service suite (-x) stopped at tests/test_archive_mock_e2e.py::test_daemon_logic TimeoutExpired (bash daemon 5 s), file untouched by branch; controller full run without -x queued
Task 9: dispatched in parallel with T8 review (BASE 4f521b8, sonnet/medium); Step 8 skipped per ruling
Ruling: T10 doc gets one added paragraph after the shadow-logs table (<workspace>/task-10-addition.md: counts = occurrences, not URLs) — carries T3/T5/T6 minors; addition only, 0 deletions kept — cost if wrong: one paragraph to reword
Task 10: dry run apply-section-edits 1 pair count=1 (+100 lines), target CRLF
Session C plan (CONTEXTE 210k at T9 dispatch): finish T8-T10 here (~15k), cut BEFORE final review; session D = final review + fix wave + finishing
Task 8: open point — service pytest (no -x) 458 passed 1 failed: test_archive_mock_e2e.py::test_daemon_logic TimeoutExpired; test file and tools/ untouched since e57409aed — Ruling: pre-existing at BASE (Windows bash daemon timing), recorded not fixed; blocks none
Task 8: ⚠️ resolved: full service suite by controller = 458 passed, 1 failed (pre-existing daemon timeout, open point above)
Task 8: minor (deferred): 25 pytest warnings pre-existing (admin.py:322 utcfromtimestamp, crawler.py:24 utcnow, pytest-asyncio loop scope)
Task 8: minor (deferred): _dataset_dir docstring (admin.py:233-235) omits pdf-; comment admin.py:229 ~108 chars > 88 — fixing breaks plan numstat 6/2 ⇒ final review
Task 8: complete (commits 13209ed..4f521b8, review clean, review file 5665B)
Task 9: implementer DONE commit 9ebe363 (344/0, red ERR_MODULE_NOT_FOUND seen, 10/10, suite 625/625, usage exit 2); review dispatched (opus/high) ⇒ task-9-review.md
Task 10: P2 controller commit (ledger + .tasks.json T7,T8 completed) then dispatch (sonnet/medium) in parallel with T9 review; ledger appends held in <scratchpad>/ledger-pending.txt until T10 commits
Task 10: implementer DONE_WITH_CONCERNS commit 3092221 (CLAUDE.md +100/-0, i/lf w/crlf, TS 625/625, trio 20 passed); Steps 6-7 [contrôleur] pending
Task 10: concern — apply-section-edits.py mis-paired T10 pair (new_string marker line lacks ':'), --write reverted by checkout; implementer inserted section + addition by own byte script (scratchpad t10_add.py, brief lines 66-158) ⇒ T10 reviewer must diff inserted text vs brief block
Task 10: deviation — functions.ts previous-dataset reader cited :1293 moved to :1310 (fixed in inserted text); brief check NONHTML_PREFIX_MODE count >=5 gives 4 on verbatim text (brief miscount)
Task 9: review dispatched before cut; result in task-9-review.md (NOT YET READ by controller)
Session C cut 2026-10-16 (CONTEXTE 243k IMMINENTE) after T10 implementer. Session D: read task-9-review.md ⇒ complete/fix T9; T10 review (BASE 8c535b8, HEAD 3092221); T10 Step 7 graphify; final review; finishing (merge = stop 3). T10 Step 6 registry line written in session C.
Task 9: review READ (7367B): spec ✅, 1 Important [plan] — replay learns from download-skip rows (functions.ts:623-637 writes pdf dataset, onNonHtml only at routes.ts:387) and T8 export lacks content_type ⇒ learned/avoided overstated; fix = addition (export content_type) ⇒ session D: rule (addition = controller ruling) then fix round 1; 3 Minor [plan]: dataset url = post-redirect vs request.url; html_blocked/released ignore exemption; parse_error rows dropped uncounted
Session D (2026-10-16 ~12:30): launched IN worktree; guard partly armed (`cd <WT> && git log` accepted, awk program refused); features/poc = e57409aed (0 new). implementer-common scratchpad repointed to session D.
Ruling: T9 Important #1 fixed by addition — admin.py serves content_type (key always present, None if absent); replay: field present & null/"" ⇒ decide-only (no recordNonHtml), absent ⇒ unchanged; CLAUDE.md +1 paragraph — spec: production learns only at content-type guard (routes.ts onNonHtml) — cost if wrong: one more fix round; not stop 6 (no plan-imposed assertion changed, absent-field behaviour kept)
Task 9: minor (deferred): dataset url = post-redirect (request.loadedUrl) vs C1 identity request.url
Task 9: minor (deferred): html_blocked/released follow shadow semantics (recordHtml even when blocked; MAJ exemption ignored)
Task 9: minor (deferred): parse_error/unparseable rows dropped without a count
Task 9: fix round 1 dispatched (BASE 3092221, sonnet/medium, brief task-9-fix1-brief.md) ‖ Task 10 review dispatched (opus/high, package review-8c535b8e2..30922211e.diff)
Task 10: ⚠️ resolved: inserted text = brief 66-158 + addition except :1293→:1310 (verified); NONHTML_PREFIX_MODE = 4 in brief block (plan miscount); "BO does not persist" = spec line 75; "before per-page link dedup" = T5 review (ledger T5 minor)
Task 10: minor (deferred): CLAUDE.md:1087 "endpoint table above" — row is at :1174, below
Task 10: minor (deferred): CLAUDE.md:1032 persist events omit `released` (onHtml persists, nonHtmlPrefixGate.ts:88-89)
Task 10: open point — probe exhaustion confirms the key in decide/recordProbeFailure without persisting it; no end-of-crawl write in main.ts ⇒ key lost for next update crawl unless a later event writes the sidecar (contradicts CLAUDE.md:1046) — Ruling: carried to final review as specific question, not T10 fix loop (code of T1-T6) — cost if wrong: confirmed keys re-learned each crawl
Task 10: complete (commits 8c535b8..3092221, review clean, review file 6195B)
Task 9: fix round 1 implementer DONE_WITH_CONCERNS commit a8ece3e (numstat CLAUDE.md 2/0, admin.py 1/0, replay.ts 15/2, tests +30/+12; red 3 TS + 1 py seen; npm test 628/628, tsc 0, pytest trio 21 passed)
Ruling: ExportRecord.learnable optional (absent ⇒ true) instead of required — required breaks tsc on existing fixtures that may not be edited — cost if wrong: none (ReplayRow.learnable required)
Task 9: open point — first full npm test 624 with 3 whole-file failures (UpdateChecker.checkedSet.separation, pushedSet, redirectRepeat), alone 7/7, rerun 628/628 — Ruling: load flake (re-review ran concurrently), same class as T7 open point; blocks none
Ruling: T10 Step 7 graphify deferred to after merge on features/poc — planner rc=1: crawler-service (15 code, 1 doc, LLM pass) + docs (15 docs, LLM pass); context at 215k cannot hold the passes, and the graph is tracked on the integration branch — cost if wrong: graph stale until session E runs it
Task 9: fix round 1/5 (1 addressed, 0 open; commits 3092221..a8ece3e; re-review file task-9-rereview-1.md)
Task 9: minor (deferred): main-kind export now also carries content_type (harmless: html rows forced learnable)
Task 9: complete (commits 4f521b8..a8ece3e, review clean after fix round 1, review file 7367B)
Session D cut planned after T9 re-review + .tasks.json sync (CONTEXTE 215k at T9 re-review dispatch; final review + wave + finishing ≈45-55k > 240k). Session E prompt: memory/r23_reprise_sessionE.md
