---
description: Detect every graph area owed a re-extraction and run them all, in order
---

# /graphify-refresh

One command instead of remembering which services you touched. Plans the work,
runs each scoped `--update`, then re-labels once at the end.

Use this rather than `/graphify --update`. **A bare `--update` has no path, and
the path is the only thing that bounds scope** — it would rescan all 99 services.

## Step 1 — Plan

```bash
python scripts/graphify_plan_update.py
```

The planner derives the graph's scope from `graphify-out/graph.json`, takes the
last commit that touched it as a watermark, and diffs content with git from
there (mtimes over-report badly: a checkout bumps them without changing a byte).

It only lists areas the post-commit hook cannot handle by itself — a changed doc
(semantics need the LLM) or a file the graph has never seen (the hook refreshes
what is in scope, it never admits anything new). Code edits to already-graphed
files are left out on purpose: the hook already re-extracted them for free.

Exit 0 means nothing is owed. Say so and stop — do not run anything.

## Step 2 — Run each command

Run the listed commands **in the order printed**, one at a time. For each area,
follow the merge procedure in `docs/graphify-guide-en.md` § "Gotchas when
merging a service":

- Pre-seed the extraction subagent with real backbone node IDs from the current
  graph, and tell it to keep an edge internal rather than guess an ID. Invented
  IDs create dangling edges that fail queries silently.
- Merge into the existing graph (`G.update`), never rebuild from the extraction
  alone — that would drop every other service.
- When updating the manifest, **merge** into it. `graphify.detect.save_manifest`
  rewrites the whole file from the run's own detect, which on a scoped run would
  shrink it to that one path; a missing entry then reads as new and the next
  update re-extracts the monorepo.

## Step 3 — Label once, at the end

A merge no longer re-clusters the graph: since `37247ad5` (2026-08-07) it goes
through `_preserve_and_place` (`scripts/graphify_rebuild_scoped.py:173`), which
keeps every prior node in its community and only places the new ones. Label
**after the last merge**, not between merges:

1. **Assert 0 drift.** Every node present before the merge must keep its
   community ID — 0.00 % drift is the expected result. Anything else means the
   merge re-clustered: stop and report it.
2. **Name only the NEW communities**, from their content (dominant source area +
   top member).
3. **Audit every community that RECEIVED nodes** this cycle: re-read its label
   against its content and rename it if the label no longer describes it. A
   placed node can land in a community whose label was already wrong.
4. **No hand relabel of the ~20 largest communities** unless step 1 measured a
   drift above 0 — with 0 drift their labels are still correct, and rewriting
   them is the churn the fix removed.

Then regenerate `GRAPH_REPORT.md` and commit `graphify-out/` with a message
naming which areas moved and by how many nodes.

## Step 4 — Confirm

```bash
python scripts/graphify_plan_update.py   # must now exit 0
```

Once the planner exits 0 after the commit, remove `graphify-out/.needs_update`.
It is a gitignored marker set by the hook (`scripts/graphify_rebuild_scoped.py:261`)
on any in-scope doc change, and the scoped merge never clears it — the planner is
the authority on what is owed. Then:

```bash
bash scripts/graphify-status.sh          # must print "fresh"
```

Report the node/edge delta and anything the run revealed — dangling cross-links
refused, files that entered the graph for the first time, communities that
changed shape.
