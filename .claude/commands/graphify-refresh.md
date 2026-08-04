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

## Step 3 — Re-label once, at the end

Every merge re-runs clustering and reassigns community IDs, so `labels.json`
ends up pointing at the wrong topics. Re-label **after the last merge**, not
between merges.

Name the ~20 largest communities by hand from their highest-degree members and
dominant source area; derive the rest from content (dominant area + top member)
so they survive the next re-clustering.

Then regenerate `GRAPH_REPORT.md` and commit `graphify-out/` with a message
naming which areas moved and by how many nodes.

## Step 4 — Confirm

```bash
python scripts/graphify_plan_update.py   # must now exit 0
bash scripts/graphify-status.sh          # must print "fresh"
```

Report the node/edge delta and anything the run revealed — dangling cross-links
refused, files that entered the graph for the first time, communities that
changed shape.
