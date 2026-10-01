# Backlinks — `mcp-semrush-service`

Reference for the nine backlink tools exposed by this MCP server: `backlinks`,
`backlinks_domains`, `backlinks_overview`, `backlinks_anchors`, `backlinks_pages`,
`backlinks_competitors`, `backlinks_geo`, `backlinks_tld`, and `backlinks_matrix`. All nine
are generated from the `BACKLINK_REPORTS` table in [`server.js`](./server.js) and proxy the
**Semrush v3 Analytics API**.

> **Cost warning.** Backlink reports are billed at **40 API units per returned line** —
> the most expensive reports in this service — except `backlinks_overview`, which is billed
> **40 units per request** regardless of row count. `display_limit` is clamped to
> `MAX_DISPLAY_LIMIT` (100 rows / 4,000 units) before it reaches Semrush. See
> [Cost guard](#cost-guard) before raising it.

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
| `display_limit` | integer | no | `10` | Rows returned. **40 units each.** Clamped to 100 — see [Cost guard](#cost-guard). |

Maps to:

```
GET https://api.semrush.com/analytics/v1/
  ?key=<SEMRUSH_API_KEY>
  &type=backlinks
  &target=<target>
  &target_type=<target_type>
  &export_columns=page_ascore,source_url,target_url,anchor,nofollow,external_num,internal_num,first_seen,last_seen
  &display_limit=<display_limit>
```

Columns returned:

| Column | Meaning |
|---|---|
| `page_ascore` | Authority Score (0–100) of the **source page** carrying the link |
| `source_url` | URL of the page that contains the backlink |
| `target_url` | URL on your site that the backlink points to |
| `anchor` | Anchor text of the link |
| `nofollow` | Whether the link carries `rel="nofollow"` — nofollow links do not pass authority. |
| `external_num` | Count of external links on the source page (link-equity dilution) |
| `internal_num` | Count of internal links on the source page |
| `first_seen` | Date Semrush first crawled this link |
| `last_seen` | Date Semrush last confirmed this link |

### `backlinks_domains` — referring domains

Returns one row per *domain* linking to the target, aggregated. Call this before `backlinks`:
it is the cheaper way to size a backlink profile, since one row covers many individual links.

| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `target` | string | yes | — | Domain to analyze |
| `target_type` | string | no | `root_domain` | One of `root_domain`, `domain`, `url` |
| `display_limit` | integer | no | `10` | Rows returned. **40 units each.** Clamped to 100 — see [Cost guard](#cost-guard). |

Maps to:

```
GET https://api.semrush.com/analytics/v1/
  ?key=<SEMRUSH_API_KEY>
  &type=backlinks_refdomains
  &target=<target>
  &target_type=<target_type>
  &export_columns=domain_ascore,domain,backlinks_num,ip,country,first_seen,last_seen
  &display_limit=<display_limit>
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

> Note: this tool's name (`backlinks_domains`) does not match its Semrush report type
> (`backlinks_refdomains`). The mismatch is deliberate — the name predates this reference
> and was kept as-is when the tool was rebuilt on the `BACKLINK_REPORTS` table, so existing
> callers would not break. Do not "fix" the name to match the type.

### `backlinks_overview` — profile summary

Returns a single row summarizing the target's whole backlink profile: authority score,
total backlinks, referring domains/URLs/IPs, and follow vs. nofollow/sponsored/UGC counts.
Billed **40 units per request** (not per row) — the cheapest backlink call, and the
recommended first call before drilling into any per-row report below.

| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `target` | string | yes | — | Domain, subdomain, or URL |
| `target_type` | string | no | `root_domain` | One of `root_domain`, `domain`, `url` |

There is no `display_limit` parameter — the report always returns one row.

Maps to:

```
GET https://api.semrush.com/analytics/v1/
  ?key=<SEMRUSH_API_KEY>
  &type=backlinks_overview
  &target=<target>
  &target_type=<target_type>
  &export_columns=ascore,total,domains_num,urls_num,ips_num,ipclassc_num,follows_num,nofollows_num,sponsored_num,ugc_num,texts_num,images_num,forms_num,frames_num
```

Columns returned:

| Column | Meaning |
|---|---|
| `ascore` | Authority Score (0–100) of the target |
| `total` | Total backlinks found |
| `domains_num` | Distinct referring domains |
| `urls_num` | Distinct referring URLs |
| `ips_num` | Distinct referring IPs |
| `ipclassc_num` | Distinct referring class-C IP blocks |
| `follows_num` | Links without a nofollow/sponsored/UGC attribute |
| `nofollows_num` | Links with `rel="nofollow"` |
| `sponsored_num` | Links with `rel="sponsored"` |
| `ugc_num` | Links with `rel="ugc"` |
| `texts_num` | Links embedded in plain text/anchor markup |
| `images_num` | Links embedded in `<img>` markup |
| `forms_num` | Links embedded in `<form>` markup |
| `frames_num` | Links embedded in `<frame>`/`<iframe>` markup |

### `backlinks_anchors` — anchor text usage

Returns one row per distinct anchor text used across all backlinks pointing at the target.

| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `target` | string | yes | — | Domain, subdomain, or URL |
| `target_type` | string | no | `root_domain` | One of `root_domain`, `domain`, `url` |
| `display_limit` | integer | no | `10` | Rows returned. **40 units each.** Clamped to 100 — see [Cost guard](#cost-guard). |

Maps to:

```
GET https://api.semrush.com/analytics/v1/
  ?key=<SEMRUSH_API_KEY>
  &type=backlinks_anchors
  &target=<target>
  &target_type=<target_type>
  &export_columns=anchor,domains_num,backlinks_num,first_seen,last_seen
  &display_limit=<display_limit>
```

Columns returned:

| Column | Meaning |
|---|---|
| `anchor` | The anchor text |
| `domains_num` | Distinct referring domains using this anchor text |
| `backlinks_num` | Total backlinks using this anchor text |
| `first_seen` | Date Semrush first saw this anchor text used |
| `last_seen` | Date Semrush last saw this anchor text used |

### `backlinks_pages` — pages receiving backlinks

Returns one row per page on the target, ranked by how many backlinks that page receives.

| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `target` | string | yes | — | Domain, subdomain, or URL |
| `target_type` | string | no | `root_domain` | One of `root_domain`, `domain`, `url` |
| `display_limit` | integer | no | `10` | Rows returned. **40 units each.** Clamped to 100 — see [Cost guard](#cost-guard). |

Maps to:

```
GET https://api.semrush.com/analytics/v1/
  ?key=<SEMRUSH_API_KEY>
  &type=backlinks_pages
  &target=<target>
  &target_type=<target_type>
  &export_columns=source_url,source_title,response_code,backlinks_num,domains_num,last_seen,external_num,internal_num
  &display_limit=<display_limit>
```

Columns returned:

| Column | Meaning |
|---|---|
| `source_url` | URL of the page on the target that receives backlinks |
| `source_title` | Title of that page |
| `response_code` | HTTP status of the linked page (last time Semrush crawled it) |
| `backlinks_num` | Backlinks pointing at this page |
| `domains_num` | Distinct referring domains pointing at this page |
| `last_seen` | Date Semrush last confirmed a link to this page |
| `external_num` | Count of external links on this page |
| `internal_num` | Count of internal links on this page |

### `backlinks_competitors` — similar backlink profiles

Returns one row per domain whose backlink profile resembles the target's, ranked by shared
referring domains. Use it to find competitors you did not already know about.

| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `target` | string | yes | — | Domain, subdomain, or URL |
| `target_type` | string | no | `root_domain` | One of `root_domain`, `domain`, `url` |
| `display_limit` | integer | no | `10` | Rows returned. **40 units each.** Clamped to 100 — see [Cost guard](#cost-guard). |

Maps to:

```
GET https://api.semrush.com/analytics/v1/
  ?key=<SEMRUSH_API_KEY>
  &type=backlinks_competitors
  &target=<target>
  &target_type=<target_type>
  &export_columns=score,neighbour,similarity,common_refdomains,domains_num,backlinks_num
  &display_limit=<display_limit>
```

Columns returned:

| Column | Meaning |
|---|---|
| `score` | Competitor match strength |
| `neighbour` | The competing domain |
| `similarity` | Similarity of the two backlink profiles |
| `common_refdomains` | Referring domains shared with the target |
| `domains_num` | Total referring domains of the competing domain |
| `backlinks_num` | Total backlinks of the competing domain |

### `backlinks_geo` — referring domains by country

Returns one row per country, aggregating referring domains and backlinks by the inferred
country of the referring IP.

| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `target` | string | yes | — | Domain, subdomain, or URL |
| `target_type` | string | no | `root_domain` | One of `root_domain`, `domain`, `url` |
| `display_limit` | integer | no | `10` | Rows returned. **40 units each.** Clamped to 100 — see [Cost guard](#cost-guard). |

Maps to:

```
GET https://api.semrush.com/analytics/v1/
  ?key=<SEMRUSH_API_KEY>
  &type=backlinks_geo
  &target=<target>
  &target_type=<target_type>
  &export_columns=country,domains_num,backlinks_num
  &display_limit=<display_limit>
```

Columns returned:

| Column | Meaning |
|---|---|
| `country` | ISO country code inferred from the referring IP |
| `domains_num` | Distinct referring domains from that country |
| `backlinks_num` | Total backlinks from that country |

### `backlinks_tld` — referring domains by top-level domain

Returns one row per top-level domain (zone), aggregating referring domains and backlinks.

| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `target` | string | yes | — | Domain, subdomain, or URL |
| `target_type` | string | no | `root_domain` | One of `root_domain`, `domain`, `url` |
| `display_limit` | integer | no | `10` | Rows returned. **40 units each.** Clamped to 100 — see [Cost guard](#cost-guard). |

Maps to:

```
GET https://api.semrush.com/analytics/v1/
  ?key=<SEMRUSH_API_KEY>
  &type=backlinks_tld
  &target=<target>
  &target_type=<target_type>
  &export_columns=zone,domains_num,backlinks_num
  &display_limit=<display_limit>
```

Columns returned:

| Column | Meaning |
|---|---|
| `zone` | Top-level domain (e.g. `fr`, `com`) |
| `domains_num` | Distinct referring domains in that zone |
| `backlinks_num` | Total backlinks from that zone |

### `backlinks_matrix` — compare up to five domains

Returns one row per referring domain, showing which of up to five compared domains it links
to. Use it to find domains that link to competitors but not to you. This is the one
`multi`-shaped report: the caller supplies a `targets` array and a single `target_type`
(applied to every entry in `targets`) instead of one `target`/`target_type` pair. On the
wire, that single `target_type` is fanned out into one repeated `target_types=` query
parameter per target — but `target_types` (plural) is only ever a Semrush wire-format
detail, never a parameter the caller sets.

| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `targets` | array of string | yes | — | 2 to 5 domains to compare (e.g. `["hellopro.fr", "competitor.fr"]`) |
| `target_type` | string | no | `root_domain` | Applied to every entry in `targets` |
| `display_limit` | integer | no | `10` | Rows returned. **40 units each.** Clamped to 100 — see [Cost guard](#cost-guard). |

Maps to (repeated `targets=`/`target_types=` pairs, one per compared domain):

```
GET https://api.semrush.com/analytics/v1/
  ?key=<SEMRUSH_API_KEY>
  &type=backlinks_matrix
  &targets=<targets[0]>&targets=<targets[1]>&...
  &target_types=<target_type>&target_types=<target_type>&...
  &export_columns=domain,domain_ascore,domain_score,matches_num,backlinks_num
  &display_limit=<display_limit>
```

Columns returned:

| Column | Meaning |
|---|---|
| `domain` | The referring domain being compared across targets |
| `domain_ascore` | Authority Score (0–100) of that referring domain |
| `domain_score` | Semrush-assigned score for this referring domain — exact definition not confirmed against Semrush's published docs; verify at the [Backlinks API reference](https://developer.semrush.com/api/v3/analytics/backlinks/) before relying on it |
| `matches_num` | Referring domains shared with the compared set — how many of the compared targets this domain links to |
| `backlinks_num` | Total backlinks this domain sends across all compared targets |

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

## Cost guard

All standard- and multi-shaped reports (`backlinks`, `backlinks_domains`,
`backlinks_anchors`, `backlinks_pages`, `backlinks_competitors`, `backlinks_geo`,
`backlinks_tld`, `backlinks_matrix`) bill **40 units per returned line**, so cost is
`display_limit × 40`. `backlinks_overview` is the one exception: it always returns a single
row and bills **40 units per request**, independent of `display_limit` (it has none).

`server.js` enforces a hard ceiling via `MAX_DISPLAY_LIMIT = 100` and `clampDisplayLimit()`.
Two distinct mechanisms are in play, and they must not be conflated:

- **Omitted `display_limit`.** When a caller of this MCP server does not pass
  `display_limit` at all, `clampDisplayLimit()` returns its **fallback of 10** — not
  Semrush's own default, and not `MAX_DISPLAY_LIMIT`. This server always sends an explicit
  `display_limit` to Semrush, so Semrush's documented server-side default of 10,000 rows
  (400,000 units) only applies to a *raw* API call made outside this server, never to one
  that goes through it.
- **Explicitly-requested value above the ceiling.** When a caller passes a `display_limit`
  greater than `MAX_DISPLAY_LIMIT`, `clampDisplayLimit()` silently reduces it to **100**
  before the request is sent. There is no warning or error when this happens; the call
  simply succeeds with fewer rows than requested.

| `display_limit` requested | `display_limit` actually sent | Units consumed |
|---|---|---|
| *(omitted)* | 10 (our fallback) | 400 |
| 10 (default) | 10 | 400 |
| 100 | 100 | 4,000 |
| 1,000 | 100 (clamped) | 4,000 |
| 10,000 | 100 (clamped) | 4,000 |

This clamp (the `clampDisplayLimit()` function and `MAX_DISPLAY_LIMIT` constant in
`server.js`) is the only thing standing between a bare `backlinks(target: "…")` call and
Semrush's much larger default. Do not remove it, and do not raise `MAX_DISPLAY_LIMIT`
without deliberately deciding the new unit ceiling is acceptable.

## Subscription requirements

All nine tools require an **active Semrush Business plan**; the tool descriptions state
this. `SEMRUSH_API_KEY` must belong to an account with API access. A key lacking backlink
entitlement returns an `ERROR` body rather than data — see below.

## Error behavior

The Semrush Analytics API returns **CSV** (`;`-separated) on success. Failures come back as
a plain-text `ERROR <code> :: <MESSAGE>` line — over HTTP 200, so it cannot be caught as an
HTTP error.

`server.js` now detects this case. Each backlink tool's `run()` calls `isSemrushError()` on
the response body (`server.js:62-64`); when it matches, the factory returns
`{ content: [{ type: 'text', text: <body> }], isError: true }` instead of a plain string
(`server.js:566-579`), and `handleLine`'s `tools/call` branch passes that object straight
through to the caller (`server.js:647-648`) rather than re-wrapping it as a bare success.
A Semrush `ERROR …` body is therefore now flagged with `isError: true`, the same as an HTTP
transport failure — any MCP client checking that flag will catch it.

One subtlety remains, for whoever writes the tenth backlink tool: the pass-through at
`server.js:647` only recognizes an object whose `content` field is an array
(`Array.isArray(out.content)`). A tool that returned some other object shape — say
`{ content: "oops" }` — would fail that check, fall into the `else` branch, and be
stringified into the literal text `[object Object]`, silently losing the `isError` flag.
No tool in `BACKLINK_REPORTS` does this today; `makeBacklinkTool` always returns either a
plain string or the well-formed `{ content: [...], isError }` shape. Keep it that way.

Error codes you are most likely to hit here:

| Code | Meaning | Usual cause |
|---|---|---|
| `ERROR 50 :: NOTHING FOUND` | No data matched | Wrong `target`, or a genuinely link-less domain |
| `ERROR 120 :: WRONG KEY - ID PAIR` | Unknown API key | `SEMRUSH_API_KEY` unset or invalid |
| `ERROR 130 :: API DISABLED` | Endpoint not in your plan | No Business plan / no backlink entitlement |
| `ERROR 134 :: API UNITS BALANCE IS ZERO` | Out of units | Account ran out of API units — the display_limit clamp in [Cost guard](#cost-guard) caps a single call at 4,000 units but does not track cumulative balance |

There is no startup check that `SEMRUSH_API_KEY` is non-empty (`server.js:14` defaults it
to `''`), so a missing key surfaces only as `ERROR 120` at call time.

## Known gaps

Deliberately listed so nobody assumes these work:

- **No pagination.** `display_offset` is not exposed, so you can only ever read the first
  `display_limit` rows. Deep profiles are unreachable.
- **No sorting control.** `display_sort` is not exposed. Semrush's defaults apply:
  `page_ascore_desc` for `backlinks`, `backlinks_num_desc` for `backlinks_refdomains`.
- **No filtering.** `display_filter` is not exposed. `backlinks_refdomains` supports
  filtering by `zone`, `country`, `ip`, `newdomain`, `lostdomain`, `category`.
- **No lost/new link tracking.** The `newlink` and `lostlink` columns are not requested,
  so link decay is invisible.

### Columns available but not currently requested

Add to `export_columns` in `server.js` if needed.

`backlinks`: `response_code`, `source_size`, `redirect_url`, `source_title`, `image_url`,
`target_title`, `image_alt`, `form`, `frame`, `image`, `sitewide`, `newlink`,
`lostlink`

`backlinks_refdomains`: `domain_score`, `domain_trust_score`

## Recommended usage pattern

1. Call `backlinks_overview` first — one request, 40 units, tells you whether the target has
   a profile worth investigating at all before spending anything on per-row reports.
2. Call `backlinks_domains` next, with a small `display_limit`, to size and shape the
   profile — one row per domain is far more information per unit than one row per link.
3. Only then call `backlinks` for detail, scoped with `target_type: "url"` where possible.
4. Inspect the response body for a leading `ERROR` before parsing.

## References

- [Backlinks | Semrush API (v3 Analytics)](https://developer.semrush.com/api/v3/analytics/backlinks/)
- [Analytics API overview](https://developer.semrush.com/api/v3/analytics/basic-docs/)
- [API unit balance](https://developer.semrush.com/api/v3/get-started/api-units-balance/)
- [Backlinks Report: Semrush Manual](https://www.semrush.com/kb/501-backlinks-report-manual)
