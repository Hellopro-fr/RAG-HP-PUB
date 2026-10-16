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
