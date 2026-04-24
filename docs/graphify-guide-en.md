# graphify — Team Guide (English)

A persistent knowledge graph of this monorepo, built from code (AST) + docs (LLM). Survives sessions. Queryable from any Claude Code session. Already integrated — no action required to benefit passively.

## What you get today

Two pre-built graphs, committed to `features/poc`:

| Graph | Scope | Nodes / Edges / Communities | Location |
|-------|-------|-----------------------------|----------|
| **Backbone** | `libs/`, `protos/`, `tools/`, `model-optimizer/`, `docs/` | 1240 / 2120 / 85 | `graphify-out/` |
| **crawler-service** | `apps-microservices/crawler-service/` | 491 / 1056 / 18 | `apps-microservices/crawler-service/graphify-out/` |

Each graph directory contains:

- `graph.html` — interactive visualization, open in any browser
- `graph.json` — raw graph data (consumed by `graphify` CLI + MCP)
- `GRAPH_REPORT.md` — plain-text audit report with god nodes, surprises, suggested questions
- `memory/` — saved Q&A from past queries (auto-promoted to graph nodes on `--update`)

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
pip install graphifyy
```

That's it. Nothing to install in the repo. Verify:

```bash
graphify --version   # should print a version string
which graphify       # should resolve to your pip install path
```

### Why no git hooks?

graphify ships an optional post-commit hook (`graphify hook install`) that auto-rebuilds the graph after every commit. **We do not use it in this monorepo.**

**Reason**: the hook's `_rebuild_code` rescans the entire current working directory. In this 2129-file monorepo, a single backbone commit would extract AST from all 1790 code files (including 90+ services outside the backbone scope), exploding the committed `graph.json` by ~20x and scope-drifting the graph away from its intended boundaries.

**Workaround**: use `/graphify --update` from a Claude Code session instead. That command reads the scoped manifest (`graphify-out/manifest.json`) and re-extracts only the files that changed within the original extraction set — no scope drift, same zero LLM cost for code-only changes. See **Updating the graph** below.

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

## Extending — graph a new service

```bash
cd apps-microservices/<service>
# Install CLAUDE.md in service is recommended for richer concept extraction
/graphify .
```

Output lands in `apps-microservices/<service>/graphify-out/`. Commit it.

**When to graph a service:**

- ≥ 20 files
- Active development / frequent questions
- Complex internal state (race conditions, leader election, orchestration)

**When to skip:**

- Templated FastAPI wrapper (read one service as template, skip the rest)
- < 10 files (raw grep is fine)
- Deprecated / dead service

## Updating the graph

Two triggers, in order of preference:

1. **Any change within backbone scope** → run `/graphify --update` from any Claude Code session. Uses manifest-based incremental detection:
   - Code-only changes: AST re-extract on changed files, **zero LLM cost**, ~5-15s.
   - Doc / CLAUDE.md changes: semantic re-extraction (LLM) on changed docs only. Cache hits for unchanged. Cost proportional to what you edited.
2. **Full rebuild** → `/graphify .` from scratch. Avoid unless structure changed dramatically — re-extracts every file.

**Do NOT run `graphify update .` as a CLI command** in this repo. The CLI invokes `_rebuild_code` which rescans the whole directory (no manifest). In this monorepo that pulls in `apps-microservices/` and explodes the graph. Always use the slash command `/graphify --update` inside a Claude Code session — it goes through the skill which reads the manifest first.

Cumulative token cost for a run is tracked in `graphify-out/cost.json` (gitignored, local-only).

## Limitations you should know

1. **Edge direction may be flipped**. The graph is undirected. An edge `Configuration --uses--> MilvusCrud` often means the inverse (CRUD uses Configuration). Interpret bidirectionally.
2. **Test docstrings inflate god nodes**. Example: `CrawlerManager` has 93 edges; some come from `test_*.py` docstrings being extracted as nodes. Ignore test-prefixed neighbors when eyeballing god nodes.
3. **INFERRED edges need verification** for critical decisions. Run `graphify explain <node>` and grep to confirm before refactoring a shared component.
4. **Small corpora don't benefit from compression** (< 50k words). Graph value is structural clarity, not tokens.
5. **Cache misses on clone** — `cache/` is gitignored. First run after `git clone` re-extracts everything. Subsequent runs are instant.

## Files layout reference

```
graphify-out/                                  # backbone graph
├── graph.html                                 # interactive viz
├── graph.json                                 # raw data (MCP/CLI input)
├── GRAPH_REPORT.md                            # audit report
├── memory/                                    # saved Q&A (tracked)
├── cache/                                     # local extraction cache (gitignored)
├── manifest.json                              # mtime-based index (gitignored)
└── cost.json                                  # token log (gitignored)

apps-microservices/<service>/graphify-out/     # per-service graph
└── (same layout)
```

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
| Ran `graphify update .` and graph exploded (10k+ nodes) | You hit the unscoped-rebuild trap. `git checkout -- graphify-out/` to restore. Use `/graphify --update` from a Claude Code session instead. |
| Team member installed git hooks — graph now full of `apps-microservices/` | `graphify hook uninstall`, `git checkout -- graphify-out/`. Hooks intentionally not used in this repo — see "Why no git hooks?" above. |
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
