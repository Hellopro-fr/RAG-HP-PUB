# BDD Table Doc-Enrichment Workflow — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a reusable, code-free workflow that documents MCP-exposed MySQL tables — a versioned doc-JSON template, a runbook, and a first table documented end-to-end as a worked example.

**Architecture:** No code change to the three system components (gateway, PHP data-plane, dashboard). The plan produces two repo artifacts (a doc-JSON template + a runbook) and exercises them once against a real table, grounding descriptions via the live read-only `bdd_*` MCP tools + Hellopro code, then applying the doc through the existing dashboard `import-doc` endpoint/format.

**Tech Stack:** JSON (doc-JSON shape consumed by `POST /api/v1/bdd/used/tables/import-doc`), Markdown (runbook), live MCP tools (`bdd_describe_table`, `bdd_sample_data`, `bdd_query_readonly`, `bdd_get_table_doc`), `python -m json.tool` for local JSON validation.

**Spec:** `docs/superpowers/specs/2026-06-05-bdd-doc-enrichment-workflow-design.md`

**Repo / branch:** RAG-HP-PUB, `features/poc`.

---

### Task 1: Reusable doc-JSON template

**Goal:** A versioned, importable-shaped skeleton an operator copies and fills for any table — the single source of the JSON shape both for one table (approach A) and a batch (approach B).

**Files:**
- Create: `docs/superpowers/runbooks/bdd-doc-template.json`

**Acceptance Criteria:**
- [ ] File parses as valid JSON (`python -m json.tool` exits 0).
- [ ] Shape matches the `import-doc` handler contract: top-level `_meta` (optional) + one table block keyed by table name, with `database_id`, `description`, `primary_key`, `default_order_by`, `rows`, `columns` (map of `{type, desc}`), `relations`, `notes`.
- [ ] The placeholder table key is `REPLACE_table_name` (a clearly-non-real name) and `database_id` is one of `1`/`5`/`10`.
- [ ] An inline reminder of the DB mapping (1=edgb2b/BO, 5=hpdata, 10=hellopro_ia) lives in `_meta.usage` (since JSON has no comments).

**Verify:** `python -m json.tool docs/superpowers/runbooks/bdd-doc-template.json` → pretty-prints with exit 0.

**Steps:**

- [ ] **Step 1: Create the template file**

Create `docs/superpowers/runbooks/bdd-doc-template.json` with exactly this content:

```json
{
  "_meta": {
    "description": "Doc globale de la base exposee au MCP (optionnel). Servie par bdd_get_table_doc sans argument.",
    "usage": "GABARIT. Copier ce fichier, renommer la cle 'REPLACE_table_name' avec le nom EXACT de la table, fixer database_id (1=edgb2b/BO, 5=hpdata, 10=hellopro_ia), remplir description + columns (nom EXACT de colonne -> {type, desc}). Les cles commencant par '_' sont ignorees a l'import. Puis: dashboard -> Importer JSON (drag-drop)."
  },
  "REPLACE_table_name": {
    "database_id": 1,
    "description": "Role metier de la table en une-deux phrases. Grain: 1 ligne = quoi.",
    "primary_key": "id",
    "default_order_by": "id DESC",
    "rows": null,
    "columns": {
      "id": { "type": "int", "desc": "Identifiant unique." },
      "REPLACE_colonne": { "type": "varchar(255)", "desc": "Sens metier + unite/format + valeurs enum + FK (table cible) + piege (nullable/soft-delete/TZ)." }
    },
    "relations": [],
    "notes": ""
  }
}
```

- [ ] **Step 2: Validate JSON**

Run: `python -m json.tool docs/superpowers/runbooks/bdd-doc-template.json`
Expected: the file is pretty-printed back, exit code 0 (no `JSONDecodeError`).

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/runbooks/bdd-doc-template.json
git commit -F - <<'MSG'
docs(runbooks): gabarit doc-JSON reutilisable pour l'enrichissement BDD

EN — Add a versioned, import-doc-shaped JSON skeleton operators copy
and fill to document an MCP-exposed table (one table or a batch).

FR — Ajoute un squelette JSON (forme import-doc) versionne, a copier
et remplir pour documenter une table exposee au MCP (a l'unite ou en lot).
MSG
```

---

### Task 2: Runbook

**Goal:** A short operating procedure an operator follows for every table: the ritual, the grounding method, the 7 gotchas, and the two application paths — so the workflow is repeatable without re-reading the spec.

**Files:**
- Create: `docs/superpowers/runbooks/bdd-doc-enrichment.md`

**Acceptance Criteria:**
- [ ] Documents the ritual (approach A = one table, approach B = batch) with the 5 steps.
- [ ] Documents the grounding method (the ordered live-MCP + code procedure) and the live prerequisite (table active in registry, ~60 s config pull).
- [ ] Contains the full 7-gotcha table (G1 database_id match, G2 full field-set replacement, G3 catalog column drop, G4 identifier regex, G5 1 MiB cap, G6 enum/set, G7 doc visibility lag).
- [ ] Documents both application paths (voie 1 drag-drop, voie 2 user-run curl) and the `{inserted, updated, errors}` correction loop.
- [ ] Links to the template (`bdd-doc-template.json`) and the spec.

**Verify:** `grep -c -E "G[1-7]" docs/superpowers/runbooks/bdd-doc-enrichment.md` → `>= 7`; manual read confirms both voies + the ritual present.

**Steps:**

- [ ] **Step 1: Create the runbook**

Create `docs/superpowers/runbooks/bdd-doc-enrichment.md` with this content:

````markdown
# Runbook — Enrichir la doc d'une table BDD (MCP)

> Procedure rejouable. Spec: `../specs/2026-06-05-bdd-doc-enrichment-workflow-design.md`. Gabarit: `bdd-doc-template.json`.
> Aucun changement de code. On edite uniquement la donnee du registre via l'import JSON du dashboard.

## Le ritual

Unite = une table (A). Lot = plusieurs tables dans un seul fichier `{_meta, t1:{...}, t2:{...}}` (B). Meme gabarit.

1. **Creer la table** dans le dashboard (nom + database_id + champs). Optionnel (l'import upsert cree la table) mais recommande: verifie les noms de colonnes + active la table.
2. **Donner le contexte** a Claude: nom de table + database_id (1/5/10) + colonnes ciblees (option) + connaissance metier.
3. **Grounding** par Claude (voir plus bas).
4. **Livraison**: fichier doc-JSON (copie du gabarit, rempli) + apercu FR (tableau colonne -> description) a valider.
5. **Application**: drag-drop dans "Importer JSON" (ou voie 2 curl). Coller le retour `{inserted, updated, errors}`. Colonne droppee (G3) -> corriger le nom -> re-deposer.

## Grounding (ordre, par table)

1. `bdd_describe_table` -> noms + types + cles exacts (evite G3).
2. `bdd_sample_data` -> 5 lignes reelles -> formats, unites, valeurs, colonnes FK-like.
3. `bdd_query_readonly` ad hoc: `SELECT <col>, COUNT(*) ... GROUP BY <col>` (enum + cardinalite), `MIN/MAX` (plages).
4. Grep code Hellopro (`BO/`, `FRONT/`) sur table + colonnes -> sens metier, qui ecrit/lit, jointures.
5. `bdd_get_table_doc` si deja documentee -> ne pas contredire.

**Prerequis live**: les outils ne voient la table que si elle est ACTIVE dans le registre (pull config gateway ~60 s). Creer + activer, attendre ~1 min, puis demander. Sinon repli code + catalogue.

## Langue & ton

Public = le LLM. FR, concis, oriente requete.
- Champ: sens metier + unite/format + valeurs enum + FK (table cible) + piege (nullable/soft-delete/TZ).
- Table: role + grain (1 ligne = quoi) + relations cles + default_order_by utile.

## Gotchas (ce qui fait rater un import)

| # | Piege | Parade |
|---|-------|--------|
| G1 | `database_id` != celui de la table -> ligne dupliquee (upsert keye sur (database_id, table_name)) | Meme DB (1/5/10) que la creation |
| G2 | Update = remplacement TOTAL du jeu de champs (delete + reinsert) | Le JSON liste TOUTES les colonnes a garder; omises = supprimees |
| G3 | Colonne hors catalogue amont -> droppee + signalee ("field X not in upstream catalog (skipped)") | Noms exacts (grounding live); sinon refresh catalogue amont |
| G4 | Identifiant hors `^[a-zA-Z0-9_]{1,128}$` | Verifier avant emission |
| G5 | Corps > 1 MiB | Decouper le lot en plusieurs fichiers |
| G6 | enum/set normalises au mot-cle (type tronque) | Mettre les valeurs reelles dans `desc` |
| G7 | Doc pas visible tout de suite cote agent | PHP re-pull config ~60 s / schema-doc ~300 s; ou declencher `generate_schema_doc_2.php?token=...` |

Transactionnel: echecs par ligne collectes, transaction NON annulee. Reponse: `{inserted, updated, errors[]}`.

## Application

**Voie 1 — drag-drop (defaut)**: dashboard -> onglet BDD -> "Importer JSON" -> glisser le `.json`. Accepte export `{tables:[...]}` ou doc `{_meta, <table>:{...}}`.

**Voie 2 — curl (lance par l'operateur)**: `! curl -X POST {GATEWAY}/api/v1/bdd/used/tables/import-doc -H "<auth admin: cookie gw_session ou Bearer JWT, a confirmer>" -H "Content-Type: application/json" --data-binary @mon-fichier.doc.json`. Le token reste chez l'operateur. Marche en batch.

Dans les deux cas: renvoyer `{inserted, updated, errors}` a Claude pour la boucle de correction.
````

- [ ] **Step 2: Verify gotchas + voies present**

Run: `grep -c -E "G[1-7]" docs/superpowers/runbooks/bdd-doc-enrichment.md`
Expected: a count `>= 7`.
Then read the file and confirm "Voie 1" and "Voie 2" both appear.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/runbooks/bdd-doc-enrichment.md
git commit -F - <<'MSG'
docs(runbooks): runbook d'enrichissement de la doc des tables BDD

EN — Add the repeatable operating procedure (ritual, grounding,
7 gotchas, two application paths) for documenting MCP tables.

FR — Ajoute la procedure rejouable (ritual, grounding, 7 gotchas,
deux voies d'application) pour documenter les tables MCP.
MSG
```

---

### Task 3: First table documented end-to-end (worked example)

**Goal:** Prove the workflow on one real table chosen by the operator — grounded, emitted as a doc-JSON, imported with zero dropped columns, and visible via `bdd_get_table_doc`.

**Files:**
- Create: `docs/superpowers/runbooks/examples/<table_name>.doc.json` (the produced, applied doc-JSON, committed as a reference example)

**Acceptance Criteria:**
- [ ] Operator supplies a real table name + `database_id`; the table is active in the registry (so live tools can reach it).
- [ ] The produced doc-JSON parses (`python -m json.tool`), uses the operator's `database_id`, and lists every real column from `bdd_describe_table` (G2-safe).
- [ ] Import returns `errors: []` (zero dropped columns — G3 clear) with `inserted` or `updated` >= 1.
- [ ] `bdd_get_table_doc` with that table name returns the table description + per-column descriptions.

**Verify:** Operator pastes the import result `{inserted, updated, errors}` showing `errors: []`; then `bdd_get_table_doc <table_name>` shows the populated doc.

**Steps:**

- [ ] **Step 1: Collect the target**

Ask the operator: table name, `database_id` (1/5/10), and any business context. Confirm the table is created + active in the dashboard (else wait ~60 s for the gateway config pull so the live tools can see it).

- [ ] **Step 2: Ground the table (live MCP + code)**

Run, in order:
- `bdd_describe_table` with `{ "table_name": "<table_name>" }` → capture exact column names + types + keys.
- `bdd_sample_data` with `{ "table_name": "<table_name>" }` → infer formats/units/enum values/FK-like ids.
- For each enum-looking column: `bdd_query_readonly` with `{ "sql": "SELECT <col>, COUNT(*) AS n FROM <table_name> GROUP BY <col> ORDER BY n DESC" }` → real enum values + cardinality.
- Grep the Hellopro repo for the table name and key columns to recover business meaning + relations:
  `grep -rIn "<table_name>" C:/Users/randr/Documents/Workspaces/Hellopro/BO C:/Users/randr/Documents/Workspaces/Hellopro/FRONT` (use the Grep tool).

- [ ] **Step 3: Emit the doc-JSON from the template**

Copy `docs/superpowers/runbooks/bdd-doc-template.json` to `docs/superpowers/runbooks/examples/<table_name>.doc.json`. Rename the table key to the real `<table_name>`, set `database_id` to the operator's value, fill `description`/`primary_key`/`default_order_by`, and add EVERY column from Step 2 to `columns` (exact names — G2/G3). Put real enum values in each `desc` (G6). Then validate:
Run: `python -m json.tool docs/superpowers/runbooks/examples/<table_name>.doc.json`
Expected: pretty-prints, exit 0.

Also present an FR preview table (column → description) in chat for the operator to validate before import.

- [ ] **Step 4: Apply + verify**

Operator imports via the dashboard "Importer JSON" (voie 1) or the curl (voie 2), and pastes back `{inserted, updated, errors}`.
Expected: `errors: []` and `inserted`/`updated` >= 1.
If any column is reported dropped (G3): correct the name in the `.doc.json`, re-validate (Step 3), re-import.
Then confirm visibility:
Run: `bdd_get_table_doc` with `{ "table_name": "<table_name>" }`
Expected: returns the table `description` + the per-column descriptions just imported. (If empty, allow up to ~300 s for the PHP schema-doc cache, or trigger `generate_schema_doc_2.php?token=...` — G7.)

- [ ] **Step 5: Commit the example**

```bash
git add docs/superpowers/runbooks/examples/<table_name>.doc.json
git commit -F - <<'MSG'
docs(runbooks): exemple de doc-JSON applique pour <table_name>

EN — First table documented end-to-end as a worked example
(grounded via live bdd_* tools + code, imported with zero dropped columns).

FR — Premiere table documentee de bout en bout en exemple
(grounding via outils bdd_* live + code, import sans colonne droppee).
MSG
```

---

## Notes for the executor

- **No code change** to the gateway, PHP data-plane, or dashboard. Tasks 1–2 add docs; Task 3 adds one example data file + applies registry data.
- Tasks 1 and 2 are independent and can run in either order. Task 3 depends on both (it uses the template and follows the runbook).
- Task 3 is interactive: it needs the operator to pick a real table and to perform the dashboard import. The live `bdd_*` MCP tools require the table to be active in the registry.
- Commits use heredoc (`-F -`) bilingual messages. On Windows, prefer the documented dedicated-msg-file + `git -c commit.encoding=utf-8 commit -F` route if accents get mangled.
