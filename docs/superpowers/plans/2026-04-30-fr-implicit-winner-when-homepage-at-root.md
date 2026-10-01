# FR Implicit Winner When Homepage Is at Root — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop excluding the canonical FR content tree (`/fr/`) when the homepage is at site root and the detection API returns a FR-shaped alternative URL.

**Architecture:** Add an "implicit winner" branch to `DetectionLangueClient.computeExcludedRegionalPaths`. When `winnerPrefix` and `seedPrefix` are both `null`, scan `alternative_urls` for the first FR-shaped match (priority-ordered by `region_priority`), treat its prefix as the implicit winner, and exclude only the other alternates. Falls back to current behavior when either prefix is non-null or when no FR-shaped alt exists.

**Tech Stack:** TypeScript, Node.js 22, free-standing tsx test scripts (no Jest/Vitest).

**Spec:** `docs/superpowers/specs/2026-04-30-fr-implicit-winner-when-homepage-at-root-design.md` (commit `b497ac2c`)

---

## File Structure

| File | Responsibility |
|------|----------------|
| `apps-microservices/crawler-service/crawler/src/class/DetectionLangueClient.ts` | Implements the implicit-winner logic inside `computeExcludedRegionalPaths`. |
| `apps-microservices/crawler-service/crawler/src/tests/test_DetectionLangueClient.ts` | Adds 7 new test cases (A–G in the spec) covering the new branch and regression coverage of the existing branch. |

Both files already exist. No new files. No callers change.

---

### Task 1: Implement implicit-winner branch in `computeExcludedRegionalPaths`

**Goal:** When `winnerPrefix` and `seedPrefix` are both null, find the FR-shaped alt with the lowest `region_priority` (treating undefined as worst), treat it as the implicit winner, and exclude only the other alternates.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/class/DetectionLangueClient.ts:270-293`
- Test: `apps-microservices/crawler-service/crawler/src/tests/test_DetectionLangueClient.ts` (append cases A–G to the existing `computeExcludedRegionalPaths` block; do not delete any existing case)

**Acceptance Criteria:**
- [ ] All 9 existing `computeExcludedRegionalPaths` cases still pass.
- [ ] Case A (multimattp): `winnerPrefix=null`, `seedPrefix=null`, `alts=[/fr]` → `excluded=[]`.
- [ ] Case B: `winnerPrefix=null`, `seedPrefix=null`, `alts=[/fr, /de, /en]` → `excluded=[/de, /en]`.
- [ ] Case C: `winnerPrefix=null`, `seedPrefix=null`, alts include `/fr-FR` (priority 0), `/fr` (priority 1), `/fr-CA` (priority 2) → implicit winner `/fr-FR`; `excluded=[/fr, /fr-CA]`.
- [ ] Case D: `winnerPrefix=null`, `seedPrefix=null`, `alts=[/fr, /fr-CA]` (no priority data) → first FR wins; `excluded=[/fr-CA]`.
- [ ] Case E: `winnerPrefix=null`, `seedPrefix=null`, `alts=[/de, /en]` (no FR alt) → no implicit winner; `excluded=[/de, /en]`.
- [ ] Case F (regression): `winnerPrefix=/fr-FR`, `seedPrefix=null`, `alts=[/fr, /de]` → `excluded=[/fr, /de]` (existing behavior).
- [ ] Case G: `winnerPrefix=null`, `seedPrefix=null`, `alts=[]` → `excluded=[]`.
- [ ] `npm run build` clean.

**Verify:** `cd apps-microservices/crawler-service/crawler && npm run build && npx tsx src/tests/test_DetectionLangueClient.ts`

**Steps:**

- [ ] **Step 1: Read the existing implementation and tests**

Read:
- `apps-microservices/crawler-service/crawler/src/class/DetectionLangueClient.ts:270-293` (`computeExcludedRegionalPaths`)
- `apps-microservices/crawler-service/crawler/src/class/DetectionLangueClient.ts:251-254` (`isLocalePathPrefix`)
- `apps-microservices/crawler-service/crawler/src/class/DetectionLangueClient.ts:205-215` (`extractPathPrefix`)
- `apps-microservices/crawler-service/crawler/src/tests/test_DetectionLangueClient.ts` (full file — note the existing 9-case block for `computeExcludedRegionalPaths` and the assertion helper style used)

Confirm exact line numbers — they may have drifted.

- [ ] **Step 2: Write failing tests for cases A–G**

Append a new block to the existing `computeExcludedRegionalPaths` test section in `test_DetectionLangueClient.ts`. Use the same assertion-helper pattern already present in the file. Each case must call the production method directly:

```typescript
// --- Implicit winner when homepage is at root (cases A–G from spec) ---

// Case A: multimattp.com — single FR alt, no winner/seed prefixes
{
    const result = DetectionLangueClient.computeExcludedRegionalPaths(
        [{ url: "https://www.multimattp.com/fr/", method: "hreflang", reliability: "high", validated: true }],
        null,
        null,
    );
    assertEqual(result.excluded, [], "Case A: implicit winner /fr not excluded");
    assertEqual(result.rejected, [], "Case A: no rejections");
}

// Case B: multi-locale, FR present
{
    const result = DetectionLangueClient.computeExcludedRegionalPaths(
        [
            { url: "https://example.com/fr/", method: "hreflang", reliability: "high", validated: true },
            { url: "https://example.com/de/", method: "hreflang", reliability: "high", validated: true },
            { url: "https://example.com/en/", method: "hreflang", reliability: "high", validated: true },
        ],
        null,
        null,
    );
    assertEqual(result.excluded, ["/de", "/en"], "Case B: /fr implicit winner; /de and /en excluded");
}

// Case C: priority-based selection picks /fr-FR over /fr and /fr-CA
{
    const result = DetectionLangueClient.computeExcludedRegionalPaths(
        [
            { url: "https://example.com/fr/", method: "hreflang", reliability: "high", validated: true, region_priority: 1 },
            { url: "https://example.com/fr-FR/", method: "hreflang", reliability: "high", validated: true, region_priority: 0 },
            { url: "https://example.com/fr-CA/", method: "hreflang", reliability: "high", validated: true, region_priority: 2 },
        ],
        null,
        null,
    );
    assertEqual(result.excluded, ["/fr", "/fr-CA"], "Case C: /fr-FR (priority 0) wins; /fr and /fr-CA excluded");
}

// Case D: no priority data, first FR alt wins
{
    const result = DetectionLangueClient.computeExcludedRegionalPaths(
        [
            { url: "https://example.com/fr/", method: "hreflang", reliability: "high", validated: true },
            { url: "https://example.com/fr-CA/", method: "hreflang", reliability: "high", validated: true },
        ],
        null,
        null,
    );
    assertEqual(result.excluded, ["/fr-CA"], "Case D: first FR alt /fr wins; /fr-CA excluded");
}

// Case E: no FR alt — fallback to current behavior
{
    const result = DetectionLangueClient.computeExcludedRegionalPaths(
        [
            { url: "https://example.com/de/", method: "hreflang", reliability: "high", validated: true },
            { url: "https://example.com/en/", method: "hreflang", reliability: "high", validated: true },
        ],
        null,
        null,
    );
    assertEqual(result.excluded, ["/de", "/en"], "Case E: no FR alt; both /de and /en excluded");
}

// Case F: winnerPrefix non-null — regression of existing behavior
{
    const result = DetectionLangueClient.computeExcludedRegionalPaths(
        [
            { url: "https://example.com/fr/", method: "hreflang", reliability: "high", validated: true },
            { url: "https://example.com/de/", method: "hreflang", reliability: "high", validated: true },
        ],
        "/fr-FR",
        null,
    );
    assertEqual(result.excluded, ["/fr", "/de"], "Case F: implicit winner branch does not fire; /fr excluded as non-winning alt");
}

// Case G: empty alts
{
    const result = DetectionLangueClient.computeExcludedRegionalPaths(
        [],
        null,
        null,
    );
    assertEqual(result.excluded, [], "Case G: empty alts produces empty excluded");
    assertEqual(result.rejected, [], "Case G: empty alts produces no rejections");
}
```

If the existing file uses a different assertion helper signature (e.g., `assertDeepEqual`, custom `expect`), match it. Read the file before writing.

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd apps-microservices/crawler-service/crawler && npx tsx src/tests/test_DetectionLangueClient.ts`

Expected: cases A, B, C, D fail (current behavior excludes the FR alt). Cases E, F, G already pass under current behavior.

- [ ] **Step 4: Implement the implicit-winner branch in `computeExcludedRegionalPaths`**

Replace the body of `computeExcludedRegionalPaths` in `DetectionLangueClient.ts` (currently lines ~270–293):

```typescript
static computeExcludedRegionalPaths(
    alternativeUrls: AlternativeUrl[],
    winnerPrefix: string | null,
    seedPrefix: string | null,
): { excluded: string[]; rejected: { prefix: string; sourceUrl: string }[] } {
    const excluded: string[] = [];
    const rejected: { prefix: string; sourceUrl: string }[] = [];

    // When the homepage is at the site root, the canonical FR content tree
    // (e.g., /fr/) is exposed via hreflang as an alternative URL. Treating it
    // as a non-winning alternate (and therefore excluding it) drops every
    // /fr/* link from the crawl. Detect this case by picking the FR-shaped
    // alt with the lowest region_priority as the implicit winner.
    let implicitWinnerPrefix: string | null = null;
    if (winnerPrefix === null && seedPrefix === null) {
        const FR_PREFIX_PATTERN = /^\/fr([-_][a-z]{2,4})?\/?$/i;
        const candidates: { prefix: string; priority: number }[] = [];
        for (const alt of alternativeUrls) {
            const altPrefix = DetectionLangueClient.extractPathPrefix(alt.url);
            if (!altPrefix) continue;
            if (!FR_PREFIX_PATTERN.test(altPrefix)) continue;
            // undefined region_priority sorts last (treated as worst)
            const priority = alt.region_priority ?? Number.MAX_SAFE_INTEGER;
            candidates.push({ prefix: altPrefix, priority });
        }
        if (candidates.length > 0) {
            // Stable sort: lowest priority first, ties keep original order.
            candidates.sort((a, b) => a.priority - b.priority);
            implicitWinnerPrefix = candidates[0].prefix;
        }
    }

    for (const alt of alternativeUrls) {
        const altPrefix = DetectionLangueClient.extractPathPrefix(alt.url);
        if (
            !altPrefix ||
            altPrefix === winnerPrefix ||
            altPrefix === seedPrefix ||
            altPrefix === implicitWinnerPrefix
        ) {
            continue;
        }
        if (!DetectionLangueClient.isLocalePathPrefix(altPrefix)) {
            rejected.push({ prefix: altPrefix, sourceUrl: alt.url });
            continue;
        }
        if (!excluded.includes(altPrefix)) {
            excluded.push(altPrefix);
        }
    }

    return { excluded, rejected };
}
```

Update the JSDoc immediately above the method to add a paragraph explaining the implicit-winner branch:

```typescript
/**
 * ... (existing JSDoc preserved) ...
 *
 * **Implicit winner branch:** when both `winnerPrefix` and `seedPrefix` are
 * null (homepage at site root), the FR-shaped alt with the lowest
 * `region_priority` (undefined treated as worst) is treated as an implicit
 * winner and skipped. This prevents excluding the canonical /fr/ content
 * tree when the site exposes it via hreflang on a root-served homepage.
 * Other-locale alts (e.g., /de, /en) are still excluded.
 */
```

- [ ] **Step 5: Run tests to verify all pass**

Run: `cd apps-microservices/crawler-service/crawler && npx tsx src/tests/test_DetectionLangueClient.ts`

Expected: every test in every block passes (8 + 10 + 24 + 9 + 7 = 58 cases). The summary line for `computeExcludedRegionalPaths` should report `9 + 7 = 16 passed, 0 failed` (or similar — depending on how the file aggregates).

- [ ] **Step 6: Verify build is clean**

Run: `cd apps-microservices/crawler-service/crawler && npm run build`

Expected: tsc exits 0, no errors, no warnings.

- [ ] **Step 7: Commit**

Stage the 2 modified files only (no `git add -A` / `git add .`).

```bash
git add apps-microservices/crawler-service/crawler/src/class/DetectionLangueClient.ts apps-microservices/crawler-service/crawler/src/tests/test_DetectionLangueClient.ts
git commit -m "$(cat <<'EOF'
fix(crawler): pick FR alt as implicit winner when homepage is at root

Closes a crawl gap where the homepage at site root caused the canonical
FR content tree (/fr/) to be classified as a non-winning regional
alternate and excluded at enqueue time. Detected on multimattp.com:
every internal link was dropped because /fr was added to
excludedRegionalPaths.

When both winnerPrefix and seedPrefix are null, computeExcludedRegionalPaths
now picks the FR-shaped alt with the lowest region_priority (undefined
treated as worst) and treats its prefix as an implicit winner. Other-locale
alts (e.g., /de, /en) are still excluded normally. Behavior is unchanged
when either winnerPrefix or seedPrefix is non-null.

Spec: docs/superpowers/specs/2026-04-30-fr-implicit-winner-when-homepage-at-root-design.md

---

fix(crawler): choisir l'alt FR comme vainqueur implicite quand l'accueil est à la racine

Corrige une lacune de crawl : la page d'accueil à la racine du site
provoquait la classification de l'arbre FR canonique (/fr/) comme
alternative régionale non-gagnante, exclue au moment de l'enfilage.
Détecté sur multimattp.com : tous les liens internes étaient supprimés
car /fr était ajouté à excludedRegionalPaths.

Quand winnerPrefix et seedPrefix sont nuls, computeExcludedRegionalPaths
sélectionne désormais l'alt de forme FR avec la priorité région la plus
basse (priorité indéfinie = pire) et traite son préfixe comme vainqueur
implicite. Les alts d'autres locales (/de, /en, etc.) restent exclues
normalement. Comportement inchangé quand l'un des deux préfixes est
non-nul.

Spec : docs/superpowers/specs/2026-04-30-fr-implicit-winner-when-homepage-at-root-design.md
EOF
)"
```

---

## Self-review checklist

- [x] Spec requirement "implicit winner when winnerPrefix=null AND seedPrefix=null" → Task 1 Step 4.
- [x] Spec requirement "FR-shaped match with priority ordering" → Task 1 Step 4 (`FR_PREFIX_PATTERN` + sort).
- [x] Spec requirement "fall back to current behavior when no FR alt" → Task 1 Step 4 (candidates.length === 0 branch leaves `implicitWinnerPrefix` null).
- [x] Spec requirement "fall back to current behavior when winnerPrefix or seedPrefix non-null" → Task 1 Step 4 (the `if (winnerPrefix === null && seedPrefix === null)` guard).
- [x] All 7 test matrix cases (A–G) covered as separate test blocks → Task 1 Step 2.
- [x] No placeholder text. Every step has the actual code or command.
- [x] Type consistency: `AlternativeUrl` schema (with `region_priority?: number`) matches the interface at `DetectionLangueClient.ts:4-10`.
- [x] No callers of `computeExcludedRegionalPaths` need to change — `routes.ts` callsite is unchanged because the signature is preserved.
