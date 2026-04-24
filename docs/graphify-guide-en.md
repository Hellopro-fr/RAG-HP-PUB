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
# 1. Install graphify CLI
pip install graphifyy

# 2. Install git hooks (auto-rebuild on commits/branch switches, backbone-scoped, zero LLM cost)
graphify hook install
```

Verify:

```bash
graphify hook status
# Expected:
#   post-commit: installed
#   post-checkout: installed
```

The hooks in this repo have a **scope filter**: they rebuild only when the commit/branch-diff touches `libs/`, `protos/`, `tools/`, `model-optimizer/`, or `docs/`. Commits inside `apps-microservices/` trigger no rebuild (avoids scope drift into the 90+ service tree).

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

Three triggers, in order of preference:

1. **Git commit touching backbone** → automatic, free, ~5-15s (AST only, no LLM).
2. **Doc or CLAUDE.md change** → run `/graphify --update` manually. LLM tokens charged only for changed files (cache hits otherwise).
3. **Full rebuild** → `/graphify .` from scratch. Avoid unless structure changed dramatically.

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
| Hook not firing after commit | `graphify hook status`; reinstall if missing |
| Rebuild blocked by pre-commit hook | Hook writes to `graphify-out/` — already gitignored for locals; backbone files committed once |
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
