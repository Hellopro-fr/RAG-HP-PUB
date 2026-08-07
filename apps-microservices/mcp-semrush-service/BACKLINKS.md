# Backlinks — `mcp-semrush-service`

Reference for the two backlink tools exposed by this MCP server: `backlinks` and
`backlinks_domains`. Both are defined in [`server.js`](./server.js) (lines 325–364) and
proxy the **Semrush v3 Analytics API**.

> **Cost warning.** Backlink reports are billed at **40 API units per returned line** —
> the most expensive reports in this service. `display_limit` is forwarded to Semrush
> unvalidated. See [API unit cost](#api-unit-cost) before raising it.

## Why these tools are hand-written

The service README once described this server as a thin `mcp-proxy` wrapper around the
community `semrush-mcp` npm package. That is no longer true, and backlinks are the reason.

`server.js:6` records the defect that forced the rewrite:

```
// Fixes vs semrush-mcp npm package:
//   - backlinks/backlinks_domains: adds required target_type parameter
```

Semrush marks `target_type` as **required** on both backlink report types. The upstream
package omitted it, so every backlink call failed. This server now always sends it,
defaulting to `root_domain`.

## Tools

### `backlinks` — individual inbound links

Returns one row per backlink pointing at the target.

| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `target` | string | yes | — | Domain, subdomain, or URL (e.g. `hellopro.fr`) |
| `target_type` | string | no | `root_domain` | One of `root_domain`, `domain`, `url` |
| `display_limit` | integer | no | `10` | Rows returned. **40 units each.** |

Maps to:

```
GET https://api.semrush.com/analytics/v1/
  ?key=<SEMRUSH_API_KEY>
  &type=backlinks
  &target=<target>
  &target_type=<target_type>
  &display_limit=<display_limit>
  &export_columns=page_ascore,source_url,target_url,anchor,external_num,internal_num,first_seen,last_seen
```

Columns returned:

| Column | Meaning |
|---|---|
| `page_ascore` | Authority Score (0–100) of the **source page** carrying the link |
| `source_url` | URL of the page that contains the backlink |
| `target_url` | URL on your site that the backlink points to |
| `anchor` | Anchor text of the link |
| `external_num` | Count of external links on the source page (link-equity dilution) |
| `internal_num` | Count of internal links on the source page |
| `first_seen` | Date Semrush first crawled this link |
| `last_seen` | Date Semrush last confirmed this link |

### `backlinks_domains` — referring domains

Returns one row per *domain* linking to the target, aggregated. Use this first: it is the
cheaper way to size a backlink profile, since one row covers many individual links.

| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `target` | string | yes | — | Domain to analyze |
| `target_type` | string | no | `root_domain` | One of `root_domain`, `domain`, `url` |
| `display_limit` | integer | no | `10` | Rows returned. **40 units each.** |

Maps to:

```
GET https://api.semrush.com/analytics/v1/
  ?key=<SEMRUSH_API_KEY>
  &type=backlinks_refdomains
  &target=<target>
  &target_type=<target_type>
  &display_limit=<display_limit>
  &export_columns=domain_ascore,domain,backlinks_num,ip,country,first_seen,last_seen
```

Columns returned:

| Column | Meaning |
|---|---|
| `domain_ascore` | Authority Score (0–100) of the **referring domain** |
| `domain` | The referring domain itself |
| `backlinks_num` | How many backlinks this domain sends to the target |
| `ip` | IP address of the referring domain |
| `country` | Country inferred from that IP |
| `first_seen` | Date Semrush first saw a link from this domain |
| `last_seen` | Date Semrush last confirmed a link from this domain |

## Choosing `target_type`

This is the parameter that made the upstream package unusable, and it changes results
substantially. For `hellopro.fr`:

| Value | Scope | Example match |
|---|---|---|
| `root_domain` | The domain **and every subdomain** | `hellopro.fr`, `www.hellopro.fr`, `blog.hellopro.fr` |
| `domain` | That exact host only | `www.hellopro.fr` only |
| `url` | One specific page | `https://www.hellopro.fr/some-page.html` only |

`root_domain` is the default here and is almost always what you want for a site-wide
backlink profile. Switch to `url` for page-level link audits.

## API unit cost

Both reports bill **40 units per returned line**, so cost is
`display_limit × 40` and scales linearly with no ceiling in this service.

| `display_limit` | Units consumed |
|---|---|
| 10 (default) | 400 |
| 100 | 4,000 |
| 1,000 | 40,000 |
| 10,000 (Semrush's own default) | 400,000 |

Note that Semrush's server-side default for `display_limit` is **10,000**. This service
overrides it to **10** — that override is the only thing standing between a bare
`backlinks(target: "…")` call and a 400,000-unit charge. Do not remove it.

`display_limit` accepts up to 1,000,000 on Semrush's side. Nothing in `server.js` clamps
or validates it before forwarding.

## Subscription requirements

Both tools require an **active Semrush Business plan**; the tool descriptions state this.
`SEMRUSH_API_KEY` must belong to an account with API access. A key lacking backlink
entitlement returns an `ERROR` body rather than data — see below.

## Error behavior — read this before trusting a result

The Semrush Analytics API returns **CSV** (`;`-separated) on success. Failures come back as
a plain-text `ERROR <code> :: <MESSAGE>` line.

`server.js` handles the two failure shapes differently:

| Failure shape | Handling in `httpGet` / `tools/call` | Result seen by the caller |
|---|---|---|
| Non-2xx HTTP status | `httpGet` rejects (`server.js:27`), caught at `server.js:501` | `Error: HTTP nnn: …` with **`isError: true`** |
| HTTP 200 with an `ERROR …` body | Treated as success — body passed through verbatim | Plain text content, **no `isError` flag** |

That second row is the trap. When Semrush answers `200 OK` with a body like
`ERROR 50 :: NOTHING FOUND`, the MCP response is indistinguishable from a successful one at
the protocol level. Any consumer — including an LLM reading the tool result — must inspect
the body itself. Do not treat "no `isError`" as "the data is valid."

Error codes you are most likely to hit here:

| Code | Meaning | Usual cause |
|---|---|---|
| `ERROR 50 :: NOTHING FOUND` | No data matched | Wrong `target`, or a genuinely link-less domain |
| `ERROR 120 :: WRONG KEY - ID PAIR` | Unknown API key | `SEMRUSH_API_KEY` unset or invalid |
| `ERROR 130 :: API DISABLED` | Endpoint not in your plan | No Business plan / no backlink entitlement |
| `ERROR 134 :: API UNITS BALANCE IS ZERO` | Out of units | Often follows an unclamped `display_limit` |

There is no startup check that `SEMRUSH_API_KEY` is non-empty (`server.js:14` defaults it
to `''`), so a missing key surfaces only as `ERROR 120` at call time.

## Known gaps

Deliberately listed so nobody assumes these work:

- **No `nofollow` column.** The `backlinks` tool does not request it, so you cannot tell
  whether a link passes authority. This is the single biggest analytical gap — a profile
  that looks strong may be entirely `nofollow`.
- **No pagination.** `display_offset` is not exposed, so you can only ever read the first
  `display_limit` rows. Deep profiles are unreachable.
- **No sorting control.** `display_sort` is not exposed. Semrush's defaults apply:
  `page_ascore_desc` for `backlinks`, `backlinks_num_desc` for `backlinks_refdomains`.
- **No filtering.** `display_filter` is not exposed. `backlinks_refdomains` supports
  filtering by `zone`, `country`, `ip`, `newdomain`, `lostdomain`, `category`.
- **No lost/new link tracking.** The `newlink` and `lostlink` columns are not requested,
  so link decay is invisible.
- **No `display_limit` validation.** See [API unit cost](#api-unit-cost).

### Columns available but not currently requested

Add to `export_columns` in `server.js` if needed.

`backlinks`: `response_code`, `source_size`, `redirect_url`, `source_title`, `image_url`,
`target_title`, `image_alt`, `nofollow`, `form`, `frame`, `image`, `sitewide`, `newlink`,
`lostlink`

`backlinks_refdomains`: `domain_score`, `domain_trust_score`

## Recommended usage pattern

1. Call `backlinks_domains` first with a small `display_limit` to size and shape the
   profile — one row per domain is far more information per unit than one row per link.
2. Only then call `backlinks` for detail, scoped with `target_type: "url"` where possible.
3. Inspect the response body for a leading `ERROR` before parsing.

## References

- [Backlinks | Semrush API (v3 Analytics)](https://developer.semrush.com/api/v3/analytics/backlinks/)
- [Analytics API overview](https://developer.semrush.com/api/v3/analytics/basic-docs/)
- [API unit balance](https://developer.semrush.com/api/v3/get-started/api-units-balance/)
- [Backlinks Report: Semrush Manual](https://www.semrush.com/kb/501-backlinks-report-manual)
