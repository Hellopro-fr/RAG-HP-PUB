#!/usr/bin/env node
'use strict';

// Custom Semrush MCP server — Node.js stdio transport (no external deps)
// Fixes vs semrush-mcp npm package:
//   - backlinks/backlinks_domains: adds required target_type parameter
//   - traffic_summary/traffic_sources: uses correct Trends API base URL
//   - api_units_balance: uses correct balance check URL

const https = require('https');
const http = require('http');
const readline = require('readline');

const API_KEY = process.env.SEMRUSH_API_KEY || '';

// ── HTTP helpers ────────────────────────────────────────────────────────────

function httpGet(urlStr) {
  return new Promise((resolve, reject) => {
    const mod = urlStr.startsWith('https') ? https : http;
    mod.get(urlStr, (res) => {
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => {
        const body = Buffer.concat(chunks).toString();
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(new Error(`HTTP ${res.statusCode}: ${body}`));
        } else {
          resolve(body);
        }
      });
    }).on('error', reject);
  });
}

function buildQS(params) {
  return Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .flatMap(([k, v]) => {
      const key = encodeURIComponent(k);
      return Array.isArray(v)
        ? v.map((item) => `${key}=${encodeURIComponent(String(item))}`)
        : [`${key}=${encodeURIComponent(String(v))}`];
    })
    .join('&');
}

// ── Cost guard ──────────────────────────────────────────────────────────────
// Backlink reports bill 40 Semrush API units per returned row. Clamp silently:
// the call succeeds with fewer rows rather than failing the caller's task.

const MAX_DISPLAY_LIMIT = 100;   // 100 rows x 40 units = 4,000 unit ceiling

function clampDisplayLimit(value, fallback) {
  const n = Number(value);
  if (!Number.isFinite(n) || n < 1) return fallback;
  return Math.min(Math.floor(n), MAX_DISPLAY_LIMIT);
}

// The Semrush Analytics API answers HTTP 200 with a plain-text `ERROR n :: MESSAGE`
// body on failure. Without this check such a body reaches the caller as a success.
function isSemrushError(text) {
  return /^ERROR\s+\d+\s*::/.test(String(text ?? '').trim());
}

// ── Semrush API base URLs ───────────────────────────────────────────────────

const STD    = 'https://api.semrush.com/';                     // Standard analytics
const BACK   = 'https://api.semrush.com/analytics/v1/';        // Backlinks API
// DISABLED: const TRENDS = 'https://api.semrush.com/analytics/ta/api/v3/'; // Trends API (requires Trends API subscription)
const BAL    = 'https://api.semrush.com/management/v1/api-units';          // API units balance

// ── Tool definitions ────────────────────────────────────────────────────────

const TOOLS = [
  // ── Domain analytics ──
  {
    name: 'domain_overview',
    description: 'Overview of a domain\'s organic SEO performance: rank, traffic, keywords, backlinks',
    inputSchema: {
      type: 'object',
      properties: {
        domain:   { type: 'string', description: 'Domain to analyze (e.g. hellopro.fr)' },
        database: { type: 'string', description: 'Country database code (e.g. fr, us, uk). Default: us' },
      },
      required: ['domain'],
    },
    async run({ domain, database = 'us' }) {
      return httpGet(STD + '?' + buildQS({ key: API_KEY, type: 'domain_ranks', domain, database }));
    },
  },

  {
    name: 'domain_organic_keywords',
    description: 'Organic keywords a domain ranks for in search results',
    inputSchema: {
      type: 'object',
      properties: {
        domain:        { type: 'string', description: 'Domain to analyze' },
        database:      { type: 'string', description: 'Country database (default: us)' },
        display_limit: { type: 'integer', description: 'Max number of keywords to return (default: 10)' },
      },
      required: ['domain'],
    },
    async run({ domain, database = 'us', display_limit = 10 }) {
      return httpGet(STD + '?' + buildQS({
        key: API_KEY, type: 'domain_organic', domain, database, display_limit,
        export_columns: 'Ph,Po,Pp,Pd,Nq,Cp,Ur,Tr,Tc,Co,Nr,Td',
      }));
    },
  },

  {
    name: 'domain_paid_keywords',
    description: 'Paid keywords a domain bids on in Google Ads',
    inputSchema: {
      type: 'object',
      properties: {
        domain:        { type: 'string', description: 'Domain to analyze' },
        database:      { type: 'string', description: 'Country database (default: us)' },
        display_limit: { type: 'integer', description: 'Max number of keywords (default: 10)' },
      },
      required: ['domain'],
    },
    async run({ domain, database = 'us', display_limit = 10 }) {
      return httpGet(STD + '?' + buildQS({
        key: API_KEY, type: 'domain_adwords', domain, database, display_limit,
        export_columns: 'Ph,Po,Pp,Pd,Ab,Bm,Ts,Tt,Pt,Np,Ur,Tr,Tc,Co,Nr,Td',
      }));
    },
  },

  {
    name: 'competitors',
    description: 'Organic search competitors of a domain',
    inputSchema: {
      type: 'object',
      properties: {
        domain:        { type: 'string', description: 'Domain to find competitors for' },
        database:      { type: 'string', description: 'Country database (default: us)' },
        display_limit: { type: 'integer', description: 'Number of competitors (default: 10)' },
      },
      required: ['domain'],
    },
    async run({ domain, database = 'us', display_limit = 10 }) {
      return httpGet(STD + '?' + buildQS({
        key: API_KEY, type: 'domain_organic_organic', domain, database, display_limit,
        export_columns: 'Dn,Cr,Np,Or,Ot,Oc,Ad',
      }));
    },
  },

  // ── Keyword analytics ──
  {
    name: 'keyword_overview',
    description: 'Keyword metrics across all databases (global overview: volume, CPC, competition)',
    inputSchema: {
      type: 'object',
      properties: {
        keyword:  { type: 'string', description: 'Keyword to analyze' },
        database: { type: 'string', description: 'Country database (default: us)' },
      },
      required: ['keyword'],
    },
    async run({ keyword, database = 'us' }) {
      return httpGet(STD + '?' + buildQS({ key: API_KEY, type: 'phrase_all', phrase: keyword, database }));
    },
  },

  {
    name: 'keyword_overview_single_db',
    description: 'Detailed keyword metrics for a single country/database',
    inputSchema: {
      type: 'object',
      properties: {
        keyword:  { type: 'string', description: 'Keyword to analyze' },
        database: { type: 'string', description: 'Country database (default: us)' },
      },
      required: ['keyword'],
    },
    async run({ keyword, database = 'us' }) {
      return httpGet(STD + '?' + buildQS({
        key: API_KEY, type: 'phrase_this', phrase: keyword, database,
        export_columns: 'Ph,Nq,Cp,Co,Nr,Td',
      }));
    },
  },

  {
    name: 'batch_keyword_overview',
    description: 'Keyword metrics for multiple keywords at once (max 100 keywords)',
    inputSchema: {
      type: 'object',
      properties: {
        keywords: {
          type: 'array',
          items: { type: 'string' },
          description: 'List of keywords to analyze (max 100)',
        },
        database: { type: 'string', description: 'Country database (default: us)' },
      },
      required: ['keywords'],
    },
    async run({ keywords, database = 'us' }) {
      const phrase = Array.isArray(keywords) ? keywords.join(';') : keywords;
      return httpGet(STD + '?' + buildQS({ key: API_KEY, type: 'phrase_all', phrase, database }));
    },
  },

  {
    name: 'keyword_organic_results',
    description: 'Organic SERP results (top ranking pages) for a keyword',
    inputSchema: {
      type: 'object',
      properties: {
        keyword:       { type: 'string', description: 'Keyword to analyze' },
        database:      { type: 'string', description: 'Country database (default: us)' },
        display_limit: { type: 'integer', description: 'Number of results (default: 10)' },
      },
      required: ['keyword'],
    },
    async run({ keyword, database = 'us', display_limit = 10 }) {
      return httpGet(STD + '?' + buildQS({
        key: API_KEY, type: 'phrase_organic', phrase: keyword, database, display_limit,
        export_columns: 'Dn,Ur,Fk,Fp,Fs,Fg,Nq,Cp,Co,Tr,Tc,Nr,Td',
      }));
    },
  },

  {
    name: 'keyword_paid_results',
    description: 'Paid ad results for a keyword (advertisers and their ads)',
    inputSchema: {
      type: 'object',
      properties: {
        keyword:       { type: 'string', description: 'Keyword to analyze' },
        database:      { type: 'string', description: 'Country database (default: us)' },
        display_limit: { type: 'integer', description: 'Number of results (default: 10)' },
      },
      required: ['keyword'],
    },
    async run({ keyword, database = 'us', display_limit = 10 }) {
      return httpGet(STD + '?' + buildQS({
        key: API_KEY, type: 'phrase_adwords', phrase: keyword, database, display_limit,
        export_columns: 'Dn,Ur,Vu,Nq,Cp,Co,Nr,Td',
      }));
    },
  },

  {
    name: 'keyword_ads_history',
    description: 'Historical Google Ads data for a keyword (who advertised, when, at what position)',
    inputSchema: {
      type: 'object',
      properties: {
        keyword:  { type: 'string', description: 'Keyword to analyze' },
        database: { type: 'string', description: 'Country database (default: us)' },
      },
      required: ['keyword'],
    },
    async run({ keyword, database = 'us' }) {
      return httpGet(STD + '?' + buildQS({
        key: API_KEY, type: 'phrase_adwords_historical', phrase: keyword, database,
        export_columns: 'Dn,Dt,Po,Pco,Ur,Tt,Ds,Vu,Nq,Cp,Tr,Tc,Co,Nr,Td',
      }));
    },
  },

  {
    name: 'related_keywords',
    description: 'Keywords semantically related to a seed keyword',
    inputSchema: {
      type: 'object',
      properties: {
        keyword:       { type: 'string', description: 'Seed keyword' },
        database:      { type: 'string', description: 'Country database (default: us)' },
        display_limit: { type: 'integer', description: 'Number of related keywords (default: 10)' },
      },
      required: ['keyword'],
    },
    async run({ keyword, database = 'us', display_limit = 10 }) {
      return httpGet(STD + '?' + buildQS({
        key: API_KEY, type: 'phrase_related', phrase: keyword, database, display_limit,
        export_columns: 'Ph,Nq,Cp,Co,Nr,Td,Rr',
      }));
    },
  },

  {
    name: 'broad_match_keywords',
    description: 'Broad match keyword variations containing the phrase',
    inputSchema: {
      type: 'object',
      properties: {
        keyword:       { type: 'string', description: 'Keyword to find broad matches for' },
        database:      { type: 'string', description: 'Country database (default: us)' },
        display_limit: { type: 'integer', description: 'Number of results (default: 10)' },
      },
      required: ['keyword'],
    },
    async run({ keyword, database = 'us', display_limit = 10 }) {
      return httpGet(STD + '?' + buildQS({
        key: API_KEY, type: 'phrase_fullsearch', phrase: keyword, database, display_limit,
        export_columns: 'Ph,Nq,Cp,Co,Nr,Td',
      }));
    },
  },

  {
    name: 'phrase_questions',
    description: 'Question-based keywords containing the phrase (who, what, how, why...)',
    inputSchema: {
      type: 'object',
      properties: {
        keyword:       { type: 'string', description: 'Keyword/phrase to find questions for' },
        database:      { type: 'string', description: 'Country database (default: us)' },
        display_limit: { type: 'integer', description: 'Number of question keywords (default: 10)' },
      },
      required: ['keyword'],
    },
    async run({ keyword, database = 'us', display_limit = 10 }) {
      return httpGet(STD + '?' + buildQS({
        key: API_KEY, type: 'phrase_questions', phrase: keyword, database, display_limit,
        export_columns: 'Ph,Nq,Cp,Co,Nr,Td',
      }));
    },
  },

  {
    name: 'keyword_difficulty',
    description: 'Keyword difficulty score (0–100): how hard it is to rank organically for this keyword',
    inputSchema: {
      type: 'object',
      properties: {
        keyword:  { type: 'string', description: 'Keyword to check difficulty for' },
        database: { type: 'string', description: 'Country database (default: us)' },
      },
      required: ['keyword'],
    },
    async run({ keyword, database = 'us' }) {
      return httpGet(STD + '?' + buildQS({
        key: API_KEY, type: 'phrase_kdi', phrase: keyword, database,
        export_columns: 'Ph,Kd',
      }));
    },
  },

  // ── Traffic / Trends ──
  // DISABLED: requires Semrush Trends API subscription (returns ERROR 130 :: API DISABLED)
  // To re-enable: subscribe to Trends API at semrush.com, then uncomment the block below.
  /*
  {
    name: 'traffic_summary', // DISABLED: requires Semrush Trends API subscription
    description: 'Traffic analytics summary: visits, users, pages/visit, bounce rate, avg duration. Requires Semrush Trends API subscription.',
    inputSchema: {
      type: 'object',
      properties: {
        domain:       { type: 'string', description: 'Domain to analyze (e.g. hellopro.fr)' },
        display_date: { type: 'string', description: 'Month to analyze, format YYYY-MM-01 (default: latest available)' },
        country:      { type: 'string', description: 'Country code (e.g. fr, us, gb). Default: us' },
      },
      required: ['domain'],
    },
    async run({ domain, display_date, country = 'us' }) {
      const params = {
        key: API_KEY,
        targets: domain,
        export_columns: 'target,visits,users,pages_per_visit,bounce_rate,avg_visit_duration',
        country,
      };
      if (display_date) params.display_date = display_date;
      return httpGet(TRENDS + 'summary?' + buildQS(params));
    },
  },

  {
    name: 'traffic_sources', // DISABLED: requires Semrush Trends API subscription
    description: 'Traffic sources breakdown (direct, organic, referral, social, paid, email). Requires Semrush Trends API subscription.',
    inputSchema: {
      type: 'object',
      properties: {
        domain:       { type: 'string', description: 'Domain to analyze' },
        display_date: { type: 'string', description: 'Month to analyze, format YYYY-MM-01 (default: latest available)' },
        country:      { type: 'string', description: 'Country code (e.g. fr, us, gb). Default: us' },
      },
      required: ['domain'],
    },
    async run({ domain, display_date, country = 'us' }) {
      const params = {
        key: API_KEY,
        target: domain,
        export_columns: 'source,visits,share',
        country,
      };
      if (display_date) params.display_date = display_date;
      return httpGet(TRENDS + 'sources?' + buildQS(params));
    },
  },
  */

  // DISABLED: api_units_balance — not needed (utility/monitoring tool outside domain/keyword/backlinks scope)
  /*
  {
    name: 'api_units_balance',
    description: 'Check remaining Semrush API units balance',
    inputSchema: {
      type: 'object',
      properties: {},
    },
    async run() {
      return httpGet(BAL + '?' + buildQS({ key: API_KEY }));
    },
  },
  */
];

// ── Backlink reports (table-driven) ─────────────────────────────────────────
// Semrush backlink reports are not uniform. Three parameter shapes exist:
//   standard — target + target_type + display_limit  (billed per row)
//   summary  — target + target_type, single row      (billed per request)
//   multi    — targets[] + target_types[]            (billed per row)
// Columns are verbatim from developer.semrush.com/api/v3/analytics/backlinks/

const BACKLINK_REPORTS = [
  {
    name: 'backlinks_overview',
    type: 'backlinks_overview',
    shape: 'summary',
    description: 'Backlink profile summary for a domain: authority score, total backlinks, referring domains and IPs, and follow vs nofollow counts. Costs 40 units per request rather than per row, making it the cheapest backlink call — use it before drilling into per-row reports. Requires Semrush Business plan.',
    columns: 'ascore,total,domains_num,urls_num,ips_num,ipclassc_num,follows_num,' +
             'nofollows_num,sponsored_num,ugc_num,texts_num,images_num,forms_num,frames_num',
  },
  {
    name: 'backlinks',
    type: 'backlinks',
    shape: 'standard',
    description: 'Individual backlinks pointing at a domain or URL, with source page authority, anchor text and follow status. Requires Semrush Business plan.',
    columns: 'page_ascore,source_url,target_url,anchor,nofollow,' +
             'external_num,internal_num,first_seen,last_seen',
  },
  {
    name: 'backlinks_domains',
    type: 'backlinks_refdomains',
    shape: 'standard',
    description: 'Referring domains linking to a target, with authority score and link counts. Cheaper per unit of insight than the backlinks report — one row covers many links. Requires Semrush Business plan.',
    columns: 'domain_ascore,domain,backlinks_num,ip,country,first_seen,last_seen',
  },
  {
    name: 'backlinks_anchors',
    type: 'backlinks_anchors',
    shape: 'standard',
    description: 'Anchor texts used in backlinks pointing at a domain, with domain and backlink counts. Requires Semrush Business plan.',
    columns: 'anchor,domains_num,backlinks_num,first_seen,last_seen',
  },
  {
    name: 'backlinks_pages',
    type: 'backlinks_pages',
    shape: 'standard',
    description: 'Pages on the target that receive backlinks, ranked by backlink count. Requires Semrush Business plan.',
    columns: 'source_url,source_title,response_code,backlinks_num,domains_num,last_seen,external_num,internal_num',
  },
  {
    name: 'backlinks_competitors',
    type: 'backlinks_competitors',
    shape: 'standard',
    description: 'Domains with a backlink profile similar to the target, with the number of shared referring domains. Requires Semrush Business plan.',
    columns: 'score,neighbour,similarity,common_refdomains,domains_num,backlinks_num',
  },
  {
    name: 'backlinks_geo',
    type: 'backlinks_geo',
    shape: 'standard',
    description: 'Referring domains grouped by country. Requires Semrush Business plan.',
    columns: 'country,domains_num,backlinks_num',
  },
  {
    name: 'backlinks_tld',
    type: 'backlinks_tld',
    shape: 'standard',
    description: 'Referring domains grouped by top-level domain (zone). Requires Semrush Business plan.',
    columns: 'zone,domains_num,backlinks_num',
  },
  // Step 1 finding: display_limit IS documented for backlinks_matrix. Confirmed by
  // fetching https://developer.semrush.com/api/v3/analytics/backlinks/ directly (raw
  // HTML, not just the rendered summary) — the "Comparison by Referring Domains"
  // section lists an optional `display_limit` parameter ("Number of results returned
  // to a request... integer") alongside display_sort/display_offset/display_filter,
  // and its own request example includes `&display_limit=5`. Clamped identically to
  // the `standard` shape.
  {
    name: 'backlinks_matrix',
    type: 'backlinks_matrix',
    shape: 'multi',
    description: 'Compare the backlink profiles of up to five domains by referring-domain overlap. Finds domains that link to competitors but not to you. Requires Semrush Business plan.',
    columns: 'domain,domain_ascore,domain_score,matches_num,backlinks_num',
  },
];

const TARGET_TYPE_DESC = 'Target type: root_domain, domain, or url. Default: root_domain';

function backlinkInputSchema(spec) {
  if (spec.shape === 'multi') {
    return {
      type: 'object',
      properties: {
        targets: {
          type: 'array',
          items: { type: 'string' },
          minItems: 2,
          maxItems: 5,
          description: 'Domains to compare (2 to 5, e.g. ["hellopro.fr", "competitor.fr"])',
        },
        target_type: { type: 'string', description: `${TARGET_TYPE_DESC}. Applied to every target.` },
        display_limit: {
          type: 'integer',
          description: `Rows to return (default 10, max ${MAX_DISPLAY_LIMIT}). Each row costs 40 Semrush API units.`,
        },
      },
      required: ['targets'],
    };
  }

  const properties = {
    target: { type: 'string', description: 'Domain or URL to analyze (e.g. hellopro.fr)' },
    target_type: { type: 'string', description: TARGET_TYPE_DESC },
  };
  // display_limit is the DEFAULT for every shape except summary (billed per request,
  // always one row). Gating on `=== 'standard'` instead fails OPEN on any other shape.
  if (spec.shape !== 'summary') {
    properties.display_limit = {
      type: 'integer',
      description: `Rows to return (default 10, max ${MAX_DISPLAY_LIMIT}). Each row costs 40 Semrush API units.`,
    };
  }
  return { type: 'object', properties, required: ['target'] };
}

function buildBacklinkParams(spec, args = {}) {
  if (spec.shape === 'multi') {
    const { targets = [], target_type = 'root_domain', display_limit } = args;
    const list = Array.isArray(targets) ? targets : [targets];
    return {
      key: API_KEY,
      type: spec.type,
      targets: list,
      target_types: list.map(() => target_type),
      export_columns: spec.columns,
      display_limit: clampDisplayLimit(display_limit, 10),
    };
  }

  const { target, target_type = 'root_domain', display_limit } = args;
  const params = {
    key: API_KEY,
    type: spec.type,
    target,
    target_type,
    export_columns: spec.columns,
  };
  // Clamp is the DEFAULT for every shape except summary (billed per request, always
  // one row). Gating on `=== 'standard'` instead fails OPEN: an unrecognized shape
  // (typo, missing field) would send no display_limit at all, and Semrush applies its
  // own 10,000-row default — 400,000 API units on a single call.
  if (spec.shape !== 'summary') {
    params.display_limit = clampDisplayLimit(display_limit, 10);
  }
  return params;
}

function buildBacklinkUrl(spec, args) {
  return BACK + '?' + buildQS(buildBacklinkParams(spec, args));
}

function makeBacklinkTool(spec) {
  return {
    name: spec.name,
    description: spec.description,
    inputSchema: backlinkInputSchema(spec),
    async run(args) {
      const text = await httpGet(buildBacklinkUrl(spec, args));
      if (isSemrushError(text)) {
        return { content: [{ type: 'text', text: String(text) }], isError: true };
      }
      return text;
    },
  };
}

// Fail fast at startup, not silently at billing time: a BACKLINK_REPORTS entry with a
// misspelled or missing `shape` must not reach buildBacklinkParams/backlinkInputSchema,
// where an unrecognized value would otherwise be treated as "not summary" (safe) only
// because of the inversion above — better to reject it outright and name the entry.
const VALID_BACKLINK_SHAPES = ['summary', 'standard', 'multi'];

function assertValidBacklinkShape(spec) {
  if (!VALID_BACKLINK_SHAPES.includes(spec.shape)) {
    throw new Error(
      `BACKLINK_REPORTS entry "${spec.name}" has invalid shape "${spec.shape}" ` +
      `(must be one of: ${VALID_BACKLINK_SHAPES.join(', ')})`,
    );
  }
}

for (const spec of BACKLINK_REPORTS) {
  assertValidBacklinkShape(spec);
}

TOOLS.push(...BACKLINK_REPORTS.map(makeBacklinkTool));

const toolByName = Object.fromEntries(TOOLS.map((t) => [t.name, t]));

// ── MCP protocol (stdio) ────────────────────────────────────────────────────

function sendMsg(obj) {
  process.stdout.write(JSON.stringify(obj) + '\n');
}

function sendResult(id, result) {
  sendMsg({ jsonrpc: '2.0', id, result });
}

function sendError(id, code, message) {
  sendMsg({ jsonrpc: '2.0', id, error: { code, message } });
}

function handleLine(line) {
  return (async () => {
    line = line.trim();
    if (!line) return;

    let req;
    try {
      req = JSON.parse(line);
    } catch {
      return;
    }

    const { id, method, params = {} } = req;

    // Notifications (no id) — per MCP spec, no response
    if (id === undefined || id === null) return;

    try {
      switch (method) {
        case 'initialize':
          sendResult(id, {
            protocolVersion: '2024-11-05',
            capabilities: { tools: {} },
            serverInfo: { name: 'semrush-mcp', version: '2.0.0' },
          });
          break;

        case 'tools/list':
          sendResult(id, {
            tools: TOOLS.map((t) => ({
              name: t.name,
              description: t.description,
              inputSchema: t.inputSchema,
            })),
          });
          break;

        case 'tools/call': {
          const { name, arguments: args = {} } = params;
          const tool = toolByName[name];
          if (!tool) {
            sendError(id, -32602, `Unknown tool: ${name}`);
            break;
          }
          try {
            const out = await tool.run(args);
            // A tool may return a plain string (the 14 original tools) or a
            // complete MCP result object (the backlink factory, which sets isError).
            if (out && typeof out === 'object' && Array.isArray(out.content)) {
              sendResult(id, out);
            } else {
              sendResult(id, { content: [{ type: 'text', text: String(out) }] });
            }
          } catch (err) {
            sendResult(id, {
              content: [{ type: 'text', text: `Error: ${err.message}` }],
              isError: true,
            });
          }
          break;
        }

        default:
          sendError(id, -32601, `Method not found: ${method}`);
      }
    } catch (err) {
      sendError(id, -32603, `Internal error: ${err.message}`);
    }
  })();
}

function main() {
  const rl = readline.createInterface({ input: process.stdin, terminal: false });
  rl.on('line', handleLine);
}

if (require.main === module) {
  main();
}

module.exports = {
  TOOLS,
  toolByName,
  buildQS,
  BACK,
  handleLine,
  MAX_DISPLAY_LIMIT,
  clampDisplayLimit,
  isSemrushError,
  BACKLINK_REPORTS,
  buildBacklinkParams,
  buildBacklinkUrl,
  makeBacklinkTool,
  assertValidBacklinkShape,
};
