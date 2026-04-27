# graphify — Team Guide (English)

A persistent knowledge graph of this monorepo, built from code (AST) + docs (LLM). Survives sessions. Queryable from any Claude Code session. Already integrated — no action required to benefit passively.

> **Rollout status (2026-04-24): passive only.** The infrastructure is committed but both CI workflows (auto-rebuild and coverage-check) are set to `workflow_dispatch` only. They do not fire on anyone's PR or push. Nothing about your normal git workflow changes until the team is briefed and the workflows are activated (one-line YAML edit — see the "Activating the CI workflows" section below).

---

## What you get today

**One unified graph** at `graphify-out/`, committed on `features/poc`:

- 1700 nodes, ~3150 edges, 86 communities
- Covers: `libs/`, `protos/`, `tools/`, `model-optimizer/`, `docs/`, and `apps-microservices/crawler-service/`
- 10 explicit cross-service links from crawler-service concepts to backbone concepts (e.g. `crawler_capacity_counter --uses--> cache_service.py`, `crawler_archiving_gcs_fallback --shares_data_with--> tools_upload_daemon`) — these are what answer questions like "how does the crawler use Redis" in a single query.

The graph directory contains:

- `graph.html` — interactive visualization, open in any browser
- `graph.json` — raw graph data (consumed by the CLI + MCP)
- `GRAPH_REPORT.md` — audit report with god nodes, surprises, suggested questions
- `labels.json` — community names (tracked; preserved across rebuilds)
- `memory/` — saved Q&A from past queries (auto-promoted to graph nodes on next semantic update)

Local-only (gitignored): `cache/`, `manifest.json`, `cost.json`, `.needs_update`.

## Why use it

| Problem | Graph solves it by |
|---------|-------------------|
| "How does X reach Y across files?" | `graphify path "X" "Y"` — shortest dependency path with confidence tags |
| "What's the blast radius of changing `Configuration`?" | `graphify explain "Configuration"` — lists all consumers with source locations |
| "Who uses this library function?" | Traverses `calls` / `uses` / `references` edges instead of greping 90 service dirs |
| New to a codebase section | `GRAPH_REPORT.md` shows top-10 god nodes + community structure in 5 minutes |
| Token cost of raw scan | Graph compresses 59x vs reading corpus text |

**Honesty tag on every edge**:
- `EXTRACTED` — found directly in source (import statement, method call via AST)
- `INFERRED` — LLM reasoned from context (docs, shared data patterns)
- `AMBIGUOUS` — flagged for verification

## One-time setup (per developer)

```bash
# 1. Install graphify CLI
pip install graphifyy

# 2. Install the scoped post-commit hook (autonomous updates, no LLM cost for code changes)
bash scripts/install-graphify-hook.sh
```

Verify:

```bash
graphify --version                # prints a version
ls .git/hooks/post-commit         # hook present after install
```

### Scoped hook vs. upstream hook

The upstream `graphify hook install` command ships a post-commit hook that calls `_rebuild_code(Path("."))` — it rescans the entire working directory on every commit. In this 2129-file monorepo that pulls `apps-microservices/` into the graph, explodes `graph.json` by ~20x, and silently drifts the graph scope every time someone commits. **Do not run `graphify hook install`.**

`scripts/install-graphify-hook.sh` installs two hooks (`post-commit` + `post-merge`) that delegate to `scripts/graphify_rebuild_scoped.py`. `post-commit` fires after your own commits; `post-merge` fires after `git pull` / `git merge` that absorb other teammates' work, so you do not need to remember to rebuild manually after pulling. Both share the same scoped-rebuild body:

1. Derives the scope from `graphify-out/graph.json` — every node's `source_file` attribute is collected into an in-scope path set. `graph.json` is tracked, so every teammate gets the correct scope right after `git pull`. `manifest.json` is intentionally gitignored (mtime-based, invalid post-clone per upstream convention) and is only used as a fallback.
2. Intersects the commit's changed files with that scope. Anything outside scope is silently skipped; no rebuild.
3. For in-scope code files: re-runs AST extraction on the changed files only, merges in place, preserves semantic + cross-link edges untouched. Zero LLM cost.
4. For in-scope doc / config files: touches `graphify-out/.needs_update` and prints a reminder to run `/graphify --update` from a Claude Code session (semantic re-extraction needs the LLM).
5. Regenerates `graph.json`, `graph.html`, `GRAPH_REPORT.md` and reuses community names from `graphify-out/labels.json`.

That's the autonomous path: commit normally, the backbone + any graphed service stays fresh with no thought. If the hook fails for any reason the commit still succeeds — the hook is side-effect-only.

## Automatic integration with Claude Code

Already wired:

- **Root `CLAUDE.md`** has a `## graphify` section directing Claude to consult `GRAPH_REPORT.md` before architecture questions.
- **`.claude/settings.json`** has a `PreToolUse` hook on `Glob|Grep` that injects a reminder to check the graph before raw search.

No action needed. Every session starts graph-aware.

## Detecting a pending `/graphify --update`

The local hooks (`post-commit`, `post-merge`) and the CI auto-rebuild path can both refresh code AST without LLM. They cannot refresh doc / CLAUDE.md nodes — that requires a semantic pass via `/graphify --update`. When a doc change in scope is detected, the rebuild script touches `graphify-out/.needs_update` (gitignored, local only) as a "pending" flag.

Three ways to notice it:

1. **Automatic in Claude Code sessions.** A `SessionStart` hook in `.claude/settings.json` reads the flag and injects a reminder into Claude's context at the start of every session opened in this repo. If the flag is set, your next prompt's response will mention the pending update.
2. **Manual one-line check from a shell.** Use the helper script:

    ```bash
    bash scripts/graphify-status.sh
    # Outputs one of:
    #   [graphify] fresh — graph.json is up to date relative to in-scope files.
    #   [graphify] AST drift — at least one in-scope code file is newer than graph.json. ...
    #   [graphify] PENDING — semantic re-extraction needed. Run /graphify --update from a Claude Code session.
    #   [graphify] no graph in this repo (graphify-out/graph.json missing)
    ```

    Add `--quiet` for exit-code-only mode (0 fresh, 1 pending, 2 missing graph) — convenient for status-line scripts or pre-push hooks.

3. **Direct file inspection.** `test -f graphify-out/.needs_update` works fine when you do not want any helper. The upstream CLI offers `graphify check-update .` if you have graphify installed; it does the same thing with a fancier message.

The flag is cleared automatically the next time `/graphify --update` runs successfully and the rebuild script sees no doc files to refresh.

## Pulling updates from the repository

The usual case is `git pull` with your own unpushed graphify commits ahead of `origin/features/poc` and teammates' commits on the remote. Two rules keep the graph intact.

### 1. Prefer `--rebase` over merge

Your local graph commits replay on top of teammates' work. History stays linear, CI produces no extra merge-commit noise, and `graph.json` conflicts — if any — surface once at the top of the rebase instead of once per intermediate step. Make it the default for this repo:

```bash
git config pull.rebase true           # per-repo
# or globally:
git config --global pull.rebase true
```

A plain `git pull` without rebase still works; it just creates a merge commit and the post-merge hook will rebuild AST for the merged diff. Either strategy is safe, rebase is cleaner.

### 2. Never hand-merge `graph.json`

`graph.json` is a ~2 MB NetworkX serialization. Conflict markers leave invalid JSON and everything breaks. Same for `graph.html`, `GRAPH_REPORT.md`, and `labels.json` — they are all either auto-generated or mechanically maintained, so the right answer to a conflict is to regenerate, not hand-merge.

Recovery recipe when git reports a conflict on any `graphify-out/*` file:

```bash
# Accept the remote side wholesale (or --ours if you prefer yours)
git checkout --theirs graphify-out/graph.json graphify-out/graph.html \
                      graphify-out/GRAPH_REPORT.md graphify-out/labels.json
git add graphify-out/graph.json graphify-out/graph.html \
        graphify-out/GRAPH_REPORT.md graphify-out/labels.json

# Close the merge / rebase step
git rebase --continue       # if rebasing
# OR
git commit                  # if merging

# Regenerate locally to be consistent with the merged code
python scripts/graphify_rebuild_scoped.py $(git diff --name-only ORIG_HEAD HEAD)
```

Community labels survive because `labels.json` is the remote's version — teammates keep their label edits too.

### 3. Post-merge hook absorbs routine pulls

If the installed post-merge hook fires cleanly (teammate's commits did not touch `graphify-out/*` files), you do nothing — the hook silently re-extracts AST for their changed code files and writes the updated `graph.json`. Push includes the rebuild as part of your next commit.

If the hook did nothing (their changes were outside the graph scope), nothing to do.

## Querying the graph manually

Four slash commands inside any Claude Code session:

```bash
/graphify query "How does the DLQ archiver reach Elasticsearch?"
/graphify query "What calls get_embedding?" --dfs
/graphify path "DLQArchiver" "get_elasticsearch_client"
/graphify explain "Configuration"
```

Modes:
- BFS (default) — broad context, "what's connected to X"
- DFS (`--dfs`) — trace a specific A→B chain
- `--budget 1500` — cap answer tokens

Answers are persisted to `graphify-out/memory/` and promoted to graph nodes on next `--update`. The graph learns from your queries.

## Services currently in the graph

The single source of truth is `graphify-out/services-policy.yml` (tracked, machine-readable, read by the coverage-check CI workflow). The tables below are the human-facing summary; keep them in sync with the YAML when you add a service.

### Graphed (2)

| Service | Added | Why |
|---------|-------|-----|
| `apps-microservices/crawler-service` | 2026-04-24 | Node.js + Python, complex state machine, recent bug-fix cluster (OOM relaunch, leader election, archive staging). |
| `apps-microservices/graph-rag-api-recherche-rust-service` | 2026-04-24 | Rust (Actix-web / tonic). Core retrieval. Unique stack; cross-links to libs/rust-common-utils gRPC clients and to Python LLM providers. |

### Not graphed (89)

Grouped by reason. See `graphify-out/services-policy.yml` for the full list with per-service details.

| Reason code | Meaning | Count |
|-------------|---------|------:|
| `too_small` | < 10 files and no rich CLAUDE.md. Raw grep is enough. | 11 |
| `frontend` | Next.js / React frontend, separate toolchain. | 5 |
| `debug_variant` | Debug or test variant of another service. | 1 |
| `template_scaffold` | Template used to scaffold new services, not a live service. | 1 |
| `templated_wrapper` | FastAPI / processor wrapper following a common pattern; graph one reference and skip siblings. | 63 |
| `candidate_deferred` | Large / unique service that would be worth graphing, not prioritised yet. Promote when a cross-service query surfaces the need. | 8 |

Before running `/graphify <path> --update`, confirm the service is not already in one of those lists:

```bash
python scripts/graphify_check_service.py apps-microservices/<name>
```

The script reads the policy and prints a verdict. It returns non-zero only when the path is missing from the policy entirely — that is the signal to classify it.

## Extending — add a service to the unified graph

We chose to grow a **single unified graph** instead of one standalone graph per service. Cross-service queries (e.g. "how does `<service>` use Redis?") require one graph where the service's concepts and `libs/common-utils` concepts live in the same namespace, linked by cross-edges. Separate per-service graphs cannot answer cross-service questions without manual stitching.

### Checklist (do all four steps in a single commit)

1. **Update the policy.** Move the service from `not_graphed:` (or add it) to `graphed:` in `graphify-out/services-policy.yml`. Include `added_at` and a one-line rationale.

2. **Merge the service into the graph.** From the repo root:

    ```bash
    /graphify apps-microservices/<service> --update
    ```

    The skill's `--update` path:
    1. Reads the root graph's scope (from `graph.json`), notices the service files aren't in it.
    2. Re-detects the service subdirectory (37-file crawler-service took ~1 min end-to-end).
    3. Dispatches one semantic subagent for its docs (`CLAUDE.md`, `README.md`, `requirements.txt`). Few LLM tokens — expect under $0.10 per service.
    4. Merges new nodes / edges into `graphify-out/graph.json` and adds the files to the manifest.

    Remember to apply the two known gotchas after the subagent finishes (invented cross-link IDs + community relabelling — both recipes in the "Gotchas when merging a service" section).

3. **Update the CI rebuild workflow.** Add the new service's path glob to the `paths:` filter in `.github/workflows/graphify-auto-rebuild.yml`. Forgetting this step is silent: the service is in `graph.json` but its commits will no longer trigger CI rebuilds, so the graph slowly goes stale whenever someone edits that service on `main` / `features/poc`.

4. **Update this guide's "Graphed" table and the reason-count table** under "Not graphed". Mirror the French guide.

### What if a dev creates a new service and forgets to classify it?

They cannot merge it. The CI workflow `.github/workflows/graphify-coverage-check.yml` scans `apps-microservices/*` on every PR that touches that tree or the policy file, and fails the build if any directory is missing from `graphify-out/services-policy.yml`. The PR stays red until the dev picks one of two paths:

- **Graph it** → follow the four-step checklist above (policy + `/graphify --update` + workflow paths + guide tables).
- **Skip it** → add an entry to `not_graphed:` with a reason code (`too_small`, `frontend`, `debug_variant`, `template_scaffold`, `templated_wrapper`, or `candidate_deferred`) and optional `details`.

Either path unblocks the PR. Coverage-check then passes on re-run.

If a dev is unsure, the conservative default is `candidate_deferred` with a short `details` explaining "pending review". The service is skipped from the graph but flagged for later reconsideration.

After the merge, any new concepts in the service's `CLAUDE.md` that reference backbone modules are extracted as cross-links automatically (same mechanism that produced the 10 existing crawler → libs/tools edges).

If the service's CLAUDE.md is sparse, cross-links will be sparse too — invest in writing the CLAUDE.md first, then graph.

**When to add a service:**

- ≥ 20 files
- Active development / frequent questions
- Non-trivial internal state (race conditions, leader election, orchestration, domain logic)

**When to skip:**

- Templated FastAPI wrapper (read one service as template, skip the rest)
- < 10 files (raw grep is fine)
- Deprecated / dead service

### Gotchas when merging a service (read before adding one)

Both services merged so far (`crawler-service`, `graph-rag-api-recherche-rust-service`) hit the same two snags. Plan for them up front.

**1. Invented cross-link target IDs.** The semantic subagent invents short, intuitive IDs for backbone concepts (e.g. `cache_service_redisclient`, `embedding.rs`, `libs_common_utils`) instead of using the actual node IDs (e.g. `cache_service_py`, `libs_rust_common_utils_src_grpc_clients_embedding_rs`, `common_utils_lib`). Invented IDs produce dangling cross-link edges that quietly fail queries.

Workaround — grep the existing graph for each concept the subagent tried to cross-link, build a remap dict, rewrite the edges before merging:

```python
import json
sem = json.loads(open('.graphify_<svc>_semantic.json').read())
REMAP = {
    'cache_service_redisclient': 'cache_service_py',
    'embedding.rs': 'libs_rust_common_utils_src_grpc_clients_embedding_rs',
    'libs_common_utils': 'common_utils_lib',
    # ...
}
for e in sem['edges']:
    if e['source'] in REMAP: e['source'] = REMAP[e['source']]
    if e['target'] in REMAP: e['target'] = REMAP[e['target']]
```

Keep a running remap list in this document (the `labels.json` update story will let us amortise this over time). Pre-seed the subagent prompt with a list of known backbone node IDs to reduce invention — the prompt we used for `graph-rag-api-recherche-rust-service` lists them explicitly and cut invention rate from 10/10 to 6/16.

**2. Community re-clustering shuffles labels.** Each merge re-runs clustering. Community `c0` may become `c4`, `c7` may become `c1`, etc. The labels in `graphify-out/labels.json` are keyed by community ID — after a merge they point to the *new* community at that ID, which is probably a different topic.

Workaround — after every merge, regenerate the sample per community and re-label:

```bash
# dump first 4 node labels per community for cross-check
python -c "import json, os; d=json.loads(open('graphify-out/graph.json').read()); \
  from collections import defaultdict; c=defaultdict(list); \
  [c[n.get('community')].append(n['label']) for n in d['nodes'] if n.get('community') is not None]; \
  [print(f'c{k} ({len(v)}): {v[:4]}') for k,v in sorted(c.items(), key=lambda x:-len(x[1]))[:30]]"
```

Compare to `labels.json`, rewrite where wrong, commit the label update with the graph update.

Long term, labels should be derived from community content (top-N node labels) rather than human-assigned, so they survive re-clustering for free. Not worth the engineering investment until we hit this a few more times.

## Updating the graph

Four triggers, in order of coverage:

1. **Any backbone push to `main` or `features/poc`** → **automatic** via the CI workflow at `.github/workflows/graphify-auto-rebuild.yml`. Only these two branches trigger CI — they are the deployed integration branches; other feature branches rely on the local hook so we do not burn CI minutes on exploratory work. GitHub Actions runs the scoped rebuild on an ephemeral runner (graphify installed there, not here) and commits the updated `graph.json` / `graph.html` / `GRAPH_REPORT.md` back to the same branch with `[skip graphify]` in the message to break the loop. Covers the "consume-only server" case — a server agent that commits code but has no graphify install relies entirely on CI for graph freshness. Runtime ~1 min per rebuild. Free on public repos; a few hundred minutes per month on private.
2. **Code-only changes in scope, locally** → **automatic** via the scoped post-commit hook (if installed with `bash scripts/install-graphify-hook.sh`). Zero LLM cost. Runs in ~5-15s after commit. Redundant with CI but useful so your local `graph.json` is fresh for queries before the next push.
3. **Doc / CLAUDE.md changes in scope** → the local hook (and CI) can only refresh AST; semantic re-extraction needs the LLM. CI / hook touch `graphify-out/.needs_update` and log a reminder. You then run `/graphify --update` from a Claude Code session when convenient. Cost is proportional to what you edited thanks to the semantic cache.
4. **Full rebuild** → `/graphify .` from scratch. Avoid unless the graph is corrupted or the scope changed drastically — re-extracts every file.

**Do NOT run `graphify update .` as a CLI command** in this repo. The upstream CLI invokes `_rebuild_code` which rescans the whole directory (no manifest). In this monorepo that pulls in `apps-microservices/` and explodes the graph. The scoped hook and the slash command are the supported paths. If you need an on-demand AST rebuild without committing, call the script directly:

```bash
python scripts/graphify_rebuild_scoped.py path/to/file1.py path/to/file2.ts
```

Arguments are the changed files — it respects the graph's scope and does nothing for out-of-scope paths.

Cumulative token cost per run is tracked in `graphify-out/cost.json` (gitignored, local-only).

## Limitations you should know

1. **Edge direction may be flipped**. The graph is undirected. An edge `Configuration --uses--> MilvusCrud` often means the inverse (CRUD uses Configuration). Interpret bidirectionally.
2. **Test docstrings inflate god nodes**. Example: `CrawlerManager` has 93 edges; some come from `test_*.py` docstrings being extracted as nodes. Ignore test-prefixed neighbors when eyeballing god nodes.
3. **INFERRED edges need verification** for critical decisions. Run `graphify explain <node>` and grep to confirm before refactoring a shared component.
4. **Small corpora don't benefit from compression** (< 50k words). Graph value is structural clarity, not tokens.
5. **Cache misses on clone** — `cache/` is gitignored. First run after `git clone` re-extracts everything. Subsequent runs are instant.

## Files layout reference

```
graphify-out/                                  # unified graph (backbone + graphed services)
├── graph.html                                 # interactive viz
├── graph.json                                 # raw data (MCP/CLI input)
├── GRAPH_REPORT.md                            # audit report
├── labels.json                                # community names (tracked)
├── memory/                                    # saved Q&A (tracked, promoted to nodes on update)
├── cache/                                     # local extraction cache (gitignored)
├── manifest.json                              # mtime-based index (gitignored)
├── cost.json                                  # token log (gitignored)
└── .needs_update                              # flag written by hook on doc changes (gitignored)

scripts/
├── graphify_rebuild_scoped.py                 # scoped AST rebuild (scope derived from graph.json)
├── test_graphify_rebuild_scoped.py            # unit tests for the above
├── graphify_check_service.py                  # classifier / coverage scanner (reads services-policy.yml)
├── test_graphify_check_service.py             # unit tests for the classifier
├── graphify-post-commit.sh                    # post-commit hook body
├── graphify-post-merge.sh                     # post-merge hook body (fires after git pull / git merge)
├── graphify-status.sh                         # one-line "is the graph fresh / pending / drifting?" check
└── install-graphify-hook.sh                   # installer (copies both hooks to .git/hooks/)

.github/workflows/
└── graphify-auto-rebuild.yml                  # CI autonomous rebuild on push
```

## Who rebuilds the graph, when

Three independent paths keep the graph fresh. They are idempotent and safe to run together.

| Trigger | Where it runs | What it refreshes | Cost |
|---------|---------------|-------------------|------|
| `git push` to `main` or `features/poc` touching in-scope files | GitHub Actions runner | Code AST + regenerated HTML / report, commits back to same branch | ~1 min CI per push, free tier |
| `git commit` on a machine with the scoped hook installed | Your local machine | Same as CI, but instant and locally visible before push | ~5-15 s |
| `/graphify --update` from a Claude Code session | Your local machine | Semantic (LLM) re-extraction for changed docs / CLAUDE.md files | LLM tokens proportional to edited docs |

"Consume-only" participants — typically a server agent that edits code but has no graphify install — rely on **CI** alone. They commit, push, pull; the graph is maintained without them ever running graphify. Local dev machines benefit from all three paths and are never the bottleneck.

## Optional: MCP server for live agent queries

Expose `graph.json` as an MCP stdio server so other agents can query without text:

```bash
python -m graphify.serve graphify-out/graph.json
```

Configure in Claude Desktop `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "graphify-backbone": {
      "command": "python",
      "args": ["-m", "graphify.serve", "/absolute/path/to/graphify-out/graph.json"]
    }
  }
}
```

Exposes tools: `query_graph`, `get_node`, `get_neighbors`, `get_community`, `god_nodes`, `graph_stats`, `shortest_path`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `graphify: command not found` | `pip install graphifyy` |
| Ran `graphify update .` and graph exploded (10k+ nodes) | You hit the unscoped-rebuild trap. `git checkout -- graphify-out/` to restore. Use `/graphify --update` from a Claude Code session, or `python scripts/graphify_rebuild_scoped.py <files>` directly. |
| Teammate ran `graphify hook install` by mistake | `graphify hook uninstall` then reinstall ours: `bash scripts/install-graphify-hook.sh`. `git checkout -- graphify-out/` if the graph was polluted. |
| Post-commit hook fired but did nothing | Either no changed files are in the graph scope (expected for `apps-microservices/` commits on non-graphed services), or graphify isn't installed on your Python. Run `python -c "import graphify"` to check. |
| Hook output mentions `.needs_update` | A doc/CLAUDE.md in scope changed. Semantic re-extraction needs the LLM; run `/graphify --update` in a Claude Code session at your convenience. |
| Added a new service but its nodes aren't in the graph | You ran `/graphify <service-path>` but not `--update`. Use the update flag so it merges into the root graph instead of creating a standalone one. |
| Merge / rebase conflict on `graphify-out/graph.json` | Do not hand-merge. See § "Pulling updates from the repository" for the accept-theirs + regenerate recipe. Touching the raw JSON corrupts it. |
| Merge conflict on `graphify-out/labels.json` | Same recipe. Accept one side, re-run the rebuild script, which uses whichever `labels.json` was kept. |
| Pulled from remote but graph did not refresh | The post-merge hook only fires if the installer has been run. Run `bash scripts/install-graphify-hook.sh` once per clone — installs both post-commit and post-merge. |
| Vertical scrolling broken in PowerShell 5.1 | Use Windows Terminal, or uninstall `graspologic`: `pip uninstall graspologic` |
| Graph shows wrong direction | Inherent to undirected graph; interpret edge bidirectionally or rebuild with `--directed` flag |
| Want to skip extracting a file | Create `.graphifyignore` in repo root (same syntax as `.gitignore`) |

## When NOT to use graphify

- Quick one-off bug fix in a file you know
- Non-architectural questions ("how does Python list comprehension work?")
- Tiny scripts (< 10 files) where grep is sufficient

## Activating the CI workflows

The two GitHub Actions workflows — `.github/workflows/graphify-auto-rebuild.yml` (auto-rebuild on backbone pushes) and `.github/workflows/graphify-coverage-check.yml` (blocks PRs with unclassified services) — ship in `workflow_dispatch` mode. They are visible in the Actions tab and can be run manually, but they do not trigger on push or pull_request events.

This staging is deliberate. Until the team is briefed, we do not want:

- Teammate PRs failing because they added a service the policy has not covered yet.
- Bot commits ("chore(graphify): auto-rebuild") appearing on `main` / `features/poc` with no explanation.

Activation is a one-edit change per file — top of the `on:` block:

```yaml
# Before (shipped state):
on:
  workflow_dispatch:
  # --- ACTIVATE BY UNCOMMENTING BELOW AFTER THE TEAM BRIEFING ---
  # push:
  #   branches: [main, features/poc]
  #   ...

# After (post-brief):
on:
  workflow_dispatch:
  push:
    branches: [main, features/poc]
    ...
```

Do this for both workflow files in a single commit, push, confirm that the next backbone commit triggers a build. Then you can also drop the `workflow_dispatch:` entry if you prefer a push-only trigger — it is harmless either way.

Recommended ordering:

1. Briefing session (or async Slack note with a link to this guide).
2. Anyone who opts in runs `pip install graphifyy` and `bash scripts/install-graphify-hook.sh`.
3. Once 2-3 days have passed with no pushback, edit both workflows to uncomment the real triggers. Push. From that moment CI takes over.
4. If a teammate's PR then fails coverage-check, the failure message tells them exactly what to update in `services-policy.yml`.

Nothing in the rest of this guide assumes the workflows are live — all the local paths (scoped hook, `/graphify --update`, `python scripts/graphify_rebuild_scoped.py`) work regardless.

## Further reading

- Upstream docs: https://github.com/safishamsi/graphify
- Root `CLAUDE.md` `## graphify` section — condensed rules for AI assistants
- `GRAPH_REPORT.md` in each graph directory — current state of that graph
