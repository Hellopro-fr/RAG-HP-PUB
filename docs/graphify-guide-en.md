# graphify — Team Guide (English)

A persistent knowledge graph of this monorepo, built from code (AST) + docs (LLM). Survives sessions. Queryable from any Claude Code session. Already integrated — no action required to benefit passively.

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

`scripts/install-graphify-hook.sh` installs a different hook (`scripts/graphify-post-commit.sh`) that delegates to `scripts/graphify_rebuild_scoped.py`. The scoped hook:

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

## Extending — add a service to the unified graph

We chose to grow a **single unified graph** instead of one standalone graph per service. Reasons: cross-service queries (e.g. "how does `<service>` use Redis?") require one graph where the service's concepts and `libs/common-utils` concepts are nodes in the same namespace, linked by cross-edges. Separate per-service graphs cannot answer cross-service questions without manual stitching.

**To add a service** (example: `llm-service`):

```bash
# From the repo root — working directory matters, it picks up graphify-out/
/graphify apps-microservices/llm-service --update
```

The skill's `--update` path:

1. Reads the root graph's scope (from `graph.json`), notices the service files aren't in it.
2. Re-detects the service subdirectory (37-file crawler-service took ~1 min end-to-end).
3. Dispatches one semantic subagent for its docs (`CLAUDE.md`, `README.md`, `requirements.txt`). Few LLM tokens — expect under $0.10 per service.
4. Merges new nodes / edges into `graphify-out/graph.json` and adds the files to the manifest.

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
├── graphify-post-commit.sh                    # post-commit hook body
└── install-graphify-hook.sh                   # installer (copies hook to .git/hooks/)

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
| Vertical scrolling broken in PowerShell 5.1 | Use Windows Terminal, or uninstall `graspologic`: `pip uninstall graspologic` |
| Graph shows wrong direction | Inherent to undirected graph; interpret edge bidirectionally or rebuild with `--directed` flag |
| Want to skip extracting a file | Create `.graphifyignore` in repo root (same syntax as `.gitignore`) |

## When NOT to use graphify

- Quick one-off bug fix in a file you know
- Non-architectural questions ("how does Python list comprehension work?")
- Tiny scripts (< 10 files) where grep is sufficient

## Further reading

- Upstream docs: https://github.com/safishamsi/graphify
- Root `CLAUDE.md` `## graphify` section — condensed rules for AI assistants
- `GRAPH_REPORT.md` in each graph directory — current state of that graph
