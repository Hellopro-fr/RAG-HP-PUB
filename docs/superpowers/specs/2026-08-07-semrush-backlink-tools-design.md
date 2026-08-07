# Semrush backlink tools — design

**Date:** 2026-08-07
**Service:** `apps-microservices/mcp-semrush-service`
**Status:** Approved, ready for implementation planning

## Problem

`mcp-semrush-service` exposes 16 MCP tools, of which only 2 cover backlinks: `backlinks`
(individual inbound links) and `backlinks_domains` (referring domains). Semrush's v3
Analytics API offers 11 backlink report types. The 9 unimplemented reports block four
workflows the team wants:

1. Monitoring hellopro.fr's own link health
2. Competitive backlink analysis
3. Link prospecting and outreach
4. Anchor text and link-quality auditing

The two existing tools also have gaps documented in
[`BACKLINKS.md`](../../../apps-microservices/mcp-semrush-service/BACKLINKS.md): no
`nofollow` column (so link quality is unknowable), no pagination, no filtering, and no
validation of `display_limit` before it reaches a report billed at 40 API units per row.

## Scope

**In scope:** 7 new backlink tools, a shared table-driven factory, a `display_limit` cap,
`buildQS` array support, `ERROR`-body detection, and unit tests.

**Out of scope, with reasons:**

- `backlinks_comparison` — substantially overlaps `backlinks_matrix`, which already answers
  the competitive question ("who links to them but not me").
- `backlinks_refips` — niche. Only useful for detecting link farms sharing an IP block.
  Add later if penalty-risk auditing becomes a real workflow.
- Parsing CSV responses into JSON — all 16 existing tools return Semrush payloads verbatim.
  Breaking that for 7 tools would make the service inconsistent.
- `display_filter` and `display_offset` — deferred. They expand the schema of every tool
  and neither is required by the four workflows above. Tracked as follow-up.

## Architecture

### Three report shapes

Research during design revealed the reports are not uniform. A single factory signature
cannot cover them.

| Shape | Reports | Parameters |
|---|---|---|
| `standard` | `backlinks`, `backlinks_refdomains`, `backlinks_anchors`, `backlinks_pages`, `backlinks_competitors`, `backlinks_geo`, `backlinks_tld` | `target`, `target_type`, `display_limit` (clamped) |
| `summary` | `backlinks_overview` | `target`, `target_type` only |
| `multi` | `backlinks_matrix` | `targets[]`, `target_types[]` |

`backlinks_overview` is billed **per request** (40 units flat) and returns a single summary
row, so `display_limit` and `display_sort` are meaningless for it.

`backlinks_matrix` takes repeated array parameters — `targets[]=a.com&targets[]=b.com` —
not the singular `target`. This matters structurally: `buildQS` iterates
`Object.entries(params)`, and a plain JavaScript object cannot hold two `targets[]` keys.
`buildQS` must gain array support before `matrix` can work at all.

### Declarative report table

Replaces nine hand-written tool blocks. Adding a tenth report later becomes a table entry.

```js
const MAX_DISPLAY_LIMIT = 100;   // 100 rows x 40 units = 4,000 unit ceiling per call

const BACKLINK_REPORTS = [
  { name: 'backlinks_overview', type: 'backlinks_overview', shape: 'summary',
    columns: 'ascore,total,domains_num,urls_num,ips_num,ipclassc_num,follows_num,' +
             'nofollows_num,sponsored_num,ugc_num,texts_num,images_num,forms_num,frames_num' },

  { name: 'backlinks', type: 'backlinks', shape: 'standard',
    columns: 'page_ascore,source_url,target_url,anchor,nofollow,' +
             'external_num,internal_num,first_seen,last_seen' },

  { name: 'backlinks_domains', type: 'backlinks_refdomains', shape: 'standard',
    columns: 'domain_ascore,domain,backlinks_num,ip,country,first_seen,last_seen' },

  { name: 'backlinks_anchors', type: 'backlinks_anchors', shape: 'standard',
    columns: 'anchor,domains_num,backlinks_num,first_seen,last_seen' },

  { name: 'backlinks_pages', type: 'backlinks_pages', shape: 'standard',
    columns: 'source_url,source_title,response_code,backlinks_num,domains_num,' +
             'last_seen,external_num,internal_num' },

  { name: 'backlinks_competitors', type: 'backlinks_competitors', shape: 'standard',
    columns: 'score,neighbour,similarity,common_refdomains,domains_num,backlinks_num' },

  { name: 'backlinks_geo', type: 'backlinks_geo', shape: 'standard',
    columns: 'country,domains_num,backlinks_num' },

  { name: 'backlinks_tld', type: 'backlinks_tld', shape: 'standard',
    columns: 'zone,domains_num,backlinks_num' },

  { name: 'backlinks_matrix', type: 'backlinks_matrix', shape: 'multi',
    columns: 'domain,domain_ascore,domain_score,matches_num,backlinks_num' },
];
```

All column lists are taken verbatim from the
[Semrush v3 Analytics Backlinks reference](https://developer.semrush.com/api/v3/analytics/backlinks/).
The only deviation is `backlinks`, where `nofollow` is added to the existing column set to
close the link-quality gap.

### Tool descriptions

Each table entry carries a `description` used as the MCP tool description. Descriptions
must state what the report returns and, for `backlinks_overview`, that it is the cheapest
backlink call — this steers an LLM toward checking the summary before drilling into
per-row reports.

### Factory

`makeBacklinkTool(spec)` returns a tool object matching the shape of the existing 16 tools
(`name`, `description`, `inputSchema`, `run`). It switches on `spec.shape` to build the
correct `inputSchema` and query parameters, and is the single place where clamping and
error detection live.

```js
TOOLS.push(...BACKLINK_REPORTS.map(makeBacklinkTool));
```

The two existing backlink tools are removed from the hand-written `TOOLS` array and moved
into the table, so they inherit the clamp and error detection automatically.

## Changes to existing code

### 1. `buildQS` gains array support

Currently:

```js
.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
```

An array value must expand to repeated key/value pairs (`targets=a&targets=b`) rather than
being stringified to `a,b`. This is backward compatible: no current caller passes an array,
so all 16 existing tools are unaffected. A regression test pins that.

### 2. `display_limit` clamp

`Math.min(display_limit, MAX_DISPLAY_LIMIT)` applied in the factory wherever a shape
exposes `display_limit`. That is confirmed for `standard`. The `summary` shape does not
expose it at all.

For `multi` (`backlinks_matrix`), the Semrush reference does not state whether
`display_limit` is supported. Implementation must confirm this against a live call before
deciding: if supported, expose it and clamp it like `standard`; if not, omit it from the
schema. Do not assume either way — a `display_limit` silently ignored by Semrush would make
the cost guard look effective when it is not.

Clamping is **silent** — the call succeeds and returns up to 100 rows.

Rationale: these tools are called by an LLM, which may generate a large `display_limit`
without understanding the cost. A silent clamp degrades gracefully; an error would fail the
agent's task. The accepted trade-off is that a legitimate large audit is truncated without
warning. The cap is a module constant, so raising it is a one-line change.

For reference, at 40 units per row: 10 rows = 400 units, 100 rows = 4,000 units, and
Semrush's own default of 10,000 rows would be 400,000 units.

### 3. `ERROR`-body detection

The Semrush Analytics API returns `200 OK` with a plain-text body such as
`ERROR 50 :: NOTHING FOUND` on failure. `httpGet` only rejects on non-2xx status, so these
currently pass through as successful MCP results with no `isError` flag — indistinguishable
from real data at the protocol level.

The factory adds:

```js
if (/^ERROR\s+\d+\s+::/.test(text.trim())) {
  return { content: [{ type: 'text', text }], isError: true };
}
```

**This changes behavior of the two existing tools.** Once `backlinks` and
`backlinks_domains` move into the table, they begin flagging errors they currently swallow.
This is intended — it is a bug fix — but any consumer keying off `isError` will observe the
change. Non-2xx responses continue to be handled by the existing reject path in `httpGet`
and the catch at the `tools/call` handler.

## Data flow

Unchanged from the existing tools:

```
MCP client -> mcp-proxy :8588 -> server.js (stdio JSON-RPC)
  -> tools/call -> makeBacklinkTool.run(args)
  -> clamp display_limit -> buildQS -> httpGet
  -> https://api.semrush.com/analytics/v1/ -> CSV (semicolon-separated)
  -> ERROR-body check
  -> { content: [{ type: 'text', text: <raw CSV> }] }
```

Responses remain raw CSV. No parsing.

## Testing

Two constraints:

1. `.claude/settings.json` runs a `tdd-gate.sh` PreToolUse hook that blocks production code
   edits when no corresponding test file exists. Tests are a precondition for editing
   `server.js`, not an afterthought.
2. `package.json` declares no dependencies and `server.js` deliberately uses none. Node 20's
   built-in `node:test` and `node:assert` satisfy this with no new dependency and no change
   to the Dockerfile.

No test makes a live Semrush call — each would cost 40 units. `httpGet` is injected or
stubbed so URL construction can be asserted offline.

| Test | Asserts |
|---|---|
| `buildQS` arrays | `{targets:['a','b']}` produces `targets=a&targets=b` |
| `buildQS` regression | Scalar values and the empty/null filter behave exactly as before |
| Clamp — above cap | `display_limit: 5000` sends `100` |
| Clamp — below cap | `display_limit: 25` sends `25` |
| Clamp — default | Omitted `display_limit` sends the per-tool default |
| Schema per shape | `summary` schema has no `display_limit`; `multi` accepts `targets`; `standard` requires `target` |
| URL construction | Each report sends the correct `type=` and `export_columns=` |
| Error detection | `ERROR 50 :: NOTHING FOUND` yields `isError: true` |
| Error false-positive | A CSV row beginning with ordinary data yields no `isError` |
| Tool count | `tools/list` returns 23 tools |

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| `SEMRUSH_API_KEY` lacks Business-plan backlink entitlement | All 9 backlink tools return `ERROR 130 :: API DISABLED` | Verify with one live `backlinks_overview` call (40 units) before implementation. Not yet done — requires spending API units. |
| Tool count grows 16 → 23 | Every MCP client loads 23 schemas per call, inflating context on every gateway request | Accepted. Keeping descriptions terse limits the cost. Revisit if the gateway's total tool count becomes a problem. |
| Refactoring the 2 working tools | Could regress `backlinks` / `backlinks_domains` | Tests assert their exact `type=` and `export_columns=` values, including the new `nofollow` column |
| Silent clamping hides truncation | A large legitimate audit returns 100 rows with no warning | Documented in `BACKLINKS.md`; cap is a single constant |

## Documentation updates

- `apps-microservices/mcp-semrush-service/BACKLINKS.md` — document the 7 new tools, the
  three report shapes, the clamp and its cap, and the new error-detection behavior. Move the
  resolved items out of "Known gaps".
- `apps-microservices/mcp-semrush-service/CLAUDE.md` — update the tool count from 16 to 23
  and list the new backlink tools.

## Success criteria

1. `tools/list` returns 23 tools; the 9 backlink tools are generated from `BACKLINK_REPORTS`.
2. `backlinks` returns a `nofollow` column.
3. `backlinks_matrix` accepts multiple targets and produces repeated `targets` parameters.
4. `display_limit` above 100 is clamped to 100 on every applicable tool.
5. A Semrush `ERROR` body yields `isError: true`.
6. All unit tests pass under `node --test`.
7. The 14 non-backlink tools are byte-for-byte unchanged in behavior.

## References

- [Semrush v3 Analytics — Backlinks](https://developer.semrush.com/api/v3/analytics/backlinks/)
- [Semrush Analytics API overview](https://developer.semrush.com/api/v3/analytics/basic-docs/)
- [`BACKLINKS.md`](../../../apps-microservices/mcp-semrush-service/BACKLINKS.md)
