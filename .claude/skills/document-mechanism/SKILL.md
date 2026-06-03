---
name: document-mechanism
description: >-
  Use when the user wants a deep, accurate technical document explaining how a code
  mechanism / feature / scope ACTUALLY works — algorithms, data flow, control flow, and
  exact constants/weights/thresholds/regex/blacklists/SQL — or a comparative between two
  scopes. Triggers on "document how X works", "write a reference on X", "explain the
  algorithm in detail", "documente le fonctionnement de X", "comparatif entre X et Y",
  "fais-moi un doc sur ce scope", or asking to capture a feature's mechanism to a file
  so it can be reused as context in a later session. It fans out parallel deep-reader
  subagents (Workflow tool) that read the real code, then synthesizes a structured
  Markdown reference under docs/superpowers/references/. Prefer this over /explain (a
  single file) and over /understand (which absorbs but produces no written deliverable)
  whenever the user wants an exhaustive WRITTEN doc grounded in the actual code — even if
  they don't say the word "skill" or "document".
---

# Document Mechanism

Produce a precise, written technical reference for how a code scope actually works — by reading the real implementation in depth (not just the spec/README) and synthesizing it into a Markdown doc. This skill exists because a recurring, valuable task in this project is: *take a feature/algorithm/scope, understand it exhaustively, and leave behind a self-contained doc* (for onboarding, for a fresh session's context, or to compare two implementations).

The discipline that makes the output trustworthy: **describe what the code does, not what the spec/README claims**, capture **exact** details (line numbers, function signatures, constant values, regex, thresholds, blacklist contents), and **flag every place the code diverges from its documented intent**. Vague docs are worse than none — they get trusted and mislead.

## When to use vs. siblings

- **This skill** — the user wants a *written* reference explaining a mechanism in depth, possibly comparative. Output is a `.md` file.
- `/explain` — a single file or code block deep-dive, in-conversation, no file written. Use that instead for one small thing.
- `/understand` — absorb several files to *discuss* them; no written deliverable. If the user then says "write it to a file", that's this skill.
- `audit-feature` — judge *whether* something is implemented/correct vs a plan. This skill documents *how* it works, regardless of correctness.

## Inputs (parse from the user's args)

- **scope** (required): one or more files, a directory, or a named feature. If a feature name, locate the files first (Step 1).
- **`--compare-to <path/scope>`** (optional): a second scope to contrast against. Enables comparative mode.
- **`--fr` / `--en`** (optional): output language. Default: match the language of the user's request. Code identifiers, SQL columns, function names always stay verbatim.
- **`--output <path>`** (optional): destination. Default `docs/superpowers/references/<YYYY-MM-DD>-<slug>.md` (use today's date from the environment context — never call a clock).

## Process

### Step 1 — Scope & inventory (inline, fast)

Before any heavy fan-out, discover the work-list yourself with `Glob`/`Grep`/`Read`:
- Resolve a named feature to its actual files. List the directory tree of the scope.
- Read entry-point/orchestrator files briefly to learn the call chain (apply the "trace full execution chain" rule — AJAX → background script → function → cron; a mechanism is often reached indirectly).
- Decide the **reader clusters**: each cluster is a coherent slice one subagent can read deeply (e.g. "extraction helpers", "scoring algorithm", "fetch/download path", "the FP equivalent file"). Aim for 3–8 clusters. For comparative mode, add the scope-B clusters plus a contract/diff angle.

Read the spec/README too, but only to *cross-check* — the doc reflects the code.

### Step 2 — Fan out deep readers (Workflow tool)

Author one Workflow that runs the clusters as **parallel** deep-readers in a single phase, each returning a structured object. Use a schema so every reader captures the same exact-detail fields. The slash-command invocation is your opt-in to use the Workflow tool.

Reader prompt must demand: read the *actual* implementation, do NOT modify code, and capture EXACT values — function signatures, `file:line` ranges, regex patterns, constant names AND their literal values/contents (weights, thresholds, blacklists, enum maps), JSON keys, SQL tables/columns. Tell readers to note any deviation from the spec/README they can see.

A schema that has served well:

```js
const SCHEMA = {
  type: 'object',
  required: ['area', 'summary', 'steps'],
  properties: {
    area: { type: 'string' },
    summary: { type: 'string' },
    steps: { type: 'array', items: { type: 'object', required: ['name','what'], properties: {
      name: {type:'string'}, file:{type:'string'}, lines:{type:'string'},
      what:{type:'string'}, codeDetail:{type:'string'} } } },
    constants: { type: 'array', items: { type: 'object', required: ['name','value'], properties: {
      name:{type:'string'}, value:{type:'string'}, file:{type:'string'}, purpose:{type:'string'} } } },
    functions: { type: 'array', items: { type: 'object', required: ['name','role'], properties: {
      name:{type:'string'}, signature:{type:'string'}, file:{type:'string'}, role:{type:'string'} } } },
    externalCalls: { type: 'array', items: { type: 'string' } },
    dbTables: { type: 'array', items: { type: 'object', required:['table','ops'], properties: {
      table:{type:'string'}, ops:{type:'string'} } } },
    edgeCases: { type: 'array', items: { type: 'string' } },
    knownDeviations: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' },
  },
}
```

Skeleton (adapt cluster list + focus per task):

```js
export const meta = { name: 'doc-<slug>', description: '<one line>', phases: [{ title: 'Read' }] }
const SCHEMA = { /* as above */ }
const clusters = [ { id, label, files:[...abs paths], focus: '<exact, pointed instructions>' }, /* ... */ ]
const intro = 'READ-ONLY deep code read for a technical doc. Do NOT modify code. Read the ACTUAL implementation (not just the spec). Capture EXACT details: function names, line ranges, regex, constant values/contents, weights, thresholds, JSON keys, SQL columns.\n\n'
const results = await parallel(clusters.map(c => () =>
  agent(intro + '## Area: ' + c.label + '\n\n## Files\n' + c.files.map(f=>'- '+f).join('\n') + '\n\n## Focus\n' + c.focus,
        { label: 'read:'+c.id, phase: 'Read', schema: SCHEMA })))
return results.filter(Boolean)
```

Notes that matter:
- Use **absolute** paths; readers may need files in other workspace roots.
- `parallel()` is correct here (single read stage, all results synthesized together). Don't add a barrier you don't need.
- The workflow result is large. Parse it from the output file (`(Get-Content -Raw <file> | ConvertFrom-Json).result` in PowerShell, or `python -m json.tool`) into a digest before writing — don't try to hold the raw JSON in your head. Use `PYTHONIOENCODING=utf-8` if printing non-ASCII.

### Step 3 — Synthesize the document

You (the main thread) write the doc in the target language from the readers' structured findings. Do not paste raw agent JSON. The doc must be self-contained — a fresh session should understand the mechanism from this file alone.

ALWAYS open with this header block, then choose body sections that fit the scope:

```markdown
# <Titre> — <scope>
**Date :** <today>
**Type :** Référence technique (lecture seule ; décrit ce qui est réellement codé)
**Périmètre :** <scope + fichiers clés>
**Sources :** <code files read> · spec/README (cross-check only)
> ⚠️ Déviations spec↔code signalées en §<…>.
```

Body, adapted to the scope (drop sections that don't apply):
1. **Vue d'ensemble / flow** — an ASCII control-flow or data-flow diagram of the mechanism.
2. **Mécanisme détaillé**, step by step, each step citing `file:line` and the exact logic. For an algorithm: tables of constants/weights/thresholds with their literal values; the decision logic; the exact branch conditions.
3. **Comparative section** (if `--compare-to`): side-by-side tables on the axes that differ (identification, decision, dedup, fetch/storage, …). Call out what is shared vs divergent.
4. **Déviations & pièges connus** — every spec-vs-code gap and real bug the readers found, with `file:line`.
5. **Annexe** — inventory of key functions / constants for quick lookup.

Style: precise over pretty. Exact numbers, real blacklist contents, true thresholds. Prefer tables for constant/weight maps. Keep identifiers verbatim regardless of doc language.

### Step 4 — Report & offer commit

State the output path and a 4–6 bullet summary of what the doc covers (mention the count of deviations/bugs found). Do NOT commit unless asked — surface that the doc is uncommitted and offer to commit it (this project commits docs separately; follow the project's commit-language rule before committing).

## Quality bar

- Every non-obvious claim is traceable to `file:line`.
- Constants/weights/thresholds/blacklists are quoted with their **literal** values, not paraphrased.
- The doc states where code and spec/README disagree — silence there is the failure mode that makes a doc actively harmful.
- Comparative tables contrast real behavior, not intentions.

## When NOT to fan out

If the scope is a single small file or a handful of tightly-related functions, skip the Workflow — read them inline and write the doc directly. The fan-out earns its cost only when the scope spans many files / two codebases / a long algorithm where parallel deep reads beat one sequential pass.
