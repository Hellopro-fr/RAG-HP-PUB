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
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&');
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

  // ── Backlinks (fixed: target_type now always included) ──
  {
    name: 'backlinks',
    description: 'Backlinks for a domain: list of inbound links. Requires Semrush Business plan.',
    inputSchema: {
      type: 'object',
      properties: {
        target:        { type: 'string', description: 'Domain or URL to analyze (e.g. hellopro.fr)' },
        target_type:   { type: 'string', description: 'Target type: root_domain, domain, or url. Default: root_domain' },
        display_limit: { type: 'integer', description: 'Number of backlinks (default: 10)' },
      },
      required: ['target'],
    },
    async run({ target, target_type = 'root_domain', display_limit = 10 }) {
      return httpGet(BACK + '?' + buildQS({
        key: API_KEY, type: 'backlinks', target, target_type, display_limit,
        export_columns: 'page_ascore,source_url,target_url,anchor,external_num,internal_num,first_seen,last_seen',
      }));
    },
  },

  {
    name: 'backlinks_domains',
    description: 'Referring domains (backlink sources) for a domain. Requires Semrush Business plan.',
    inputSchema: {
      type: 'object',
      properties: {
        target:        { type: 'string', description: 'Domain to analyze (e.g. hellopro.fr)' },
        target_type:   { type: 'string', description: 'Target type: root_domain, domain, or url. Default: root_domain' },
        display_limit: { type: 'integer', description: 'Number of referring domains (default: 10)' },
      },
      required: ['target'],
    },
    async run({ target, target_type = 'root_domain', display_limit = 10 }) {
      return httpGet(BACK + '?' + buildQS({
        key: API_KEY, type: 'backlinks_refdomains', target, target_type, display_limit,
        export_columns: 'domain_ascore,domain,backlinks_num,ip,country,first_seen,last_seen',
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

  // ── API balance (fixed: uses correct URL) ──
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
];

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

const rl = readline.createInterface({ input: process.stdin, terminal: false });

rl.on('line', async (line) => {
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
          const text = await tool.run(args);
          sendResult(id, {
            content: [{ type: 'text', text: String(text) }],
          });
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
});
