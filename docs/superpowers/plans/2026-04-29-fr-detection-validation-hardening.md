# FR Detection Validation Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop non-French pages from entering the main dataset on French TLDs, and stop content paths from being mistakenly excluded as regional language variants.

**Architecture:** Three independent fixes across `api-detection-langue-fr` (Python) and `crawler-service` (TypeScript). The API tightens its acceptance of hreflang/data-lang declarations on same-host paths; the crawler adds a defensive prefix validator and removes a URL fallback that overrides clean HTML rejections.

**Tech Stack:** Python 3.10 + FastAPI + BeautifulSoup4 (API); Node.js 22 + TypeScript + Crawlee + axios (crawler).

**Spec:** `docs/superpowers/specs/2026-04-29-fr-detection-validation-hardening-design.md`

---

## File Structure

| File | Change |
|---|---|
| `apps-microservices/api-detection-langue-fr/app/core/domain_fr.py` | Add `_is_valid_language_alternative` static method; gate hreflang and data-lang/data-gt-lang detection |
| `apps-microservices/api-detection-langue-fr/tests/test_domain_fr.py` | Unit tests for `_is_valid_language_alternative`; integration test for malformed hreflang |
| `apps-microservices/crawler-service/crawler/src/class/DetectionLangueClient.ts` | Add `isFrenchRegionalPathPrefix` static method |
| `apps-microservices/crawler-service/crawler/src/tests/test_DetectionLangueClient.ts` | Unit tests for `isFrenchRegionalPathPrefix` |
| `apps-microservices/crawler-service/crawler/src/routes.ts` | Apply prefix shape gate in regional exclusion block (Change 3); drop URL fallback after clean HTML rejection (Change 1) |
| `apps-microservices/crawler-service/crawler/src/tests/test_routes.ts` | Stub note update only — no logic change |

---

## Task 1: API — `_is_valid_language_alternative` helper + hreflang/data-lang gates

**Goal:** API rejects hreflang/data-lang declarations whose target URL is a same-host non-language-shaped path (e.g., `/nos-realisations`), preventing false-positive entries in `alternative_urls`.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/core/domain_fr.py:324-330` (insert helper after `_check_base_domain`)
- Modify: `apps-microservices/api-detection-langue-fr/app/core/domain_fr.py:678-685` (apply gate to hreflang)
- Modify: `apps-microservices/api-detection-langue-fr/app/core/domain_fr.py:687-697` (apply gate to data-lang/data-gt-lang)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_domain_fr.py` (append new test class)

**Acceptance Criteria:**
- [ ] `_is_valid_language_alternative` returns True for cross-host targets
- [ ] `_is_valid_language_alternative` returns True for same-host targets with first path segment matching `^(fr|fr-[a-z]{2}|fr_[a-z]{2}|french|francais|français|france)$`
- [ ] `_is_valid_language_alternative` returns False for same-host targets with non-language first path segment (e.g., `/nos-realisations`, `/products`, `/de`)
- [ ] `_is_valid_language_alternative` returns False for same-host root URLs (`/`)
- [ ] `_is_valid_language_alternative` returns False for malformed URLs
- [ ] HTML containing `<link rel="alternate" hreflang="fr-FR" href="/nos-realisations">` produces empty `alternative_urls`
- [ ] HTML containing `<link rel="alternate" hreflang="fr-FR" href="/fr-FR/products">` still produces a populated `alternative_urls`
- [ ] Existing tests still pass

**Verify:** `cd apps-microservices/api-detection-langue-fr && pytest tests/test_domain_fr.py -v`

**Steps:**

- [ ] **Step 1: Write failing unit tests for `_is_valid_language_alternative`**

Append to `apps-microservices/api-detection-langue-fr/tests/test_domain_fr.py`:

```python
class TestIsValidLanguageAlternative:
    """Tests for DomainFR._is_valid_language_alternative — gates hreflang/data-lang acceptance."""

    def test_cross_host_trusted(self):
        """Cross-host targets (different hostname) are accepted unconditionally."""
        assert DomainFR._is_valid_language_alternative(
            "example.com", "https://example.fr/products"
        ) is True
        assert DomainFR._is_valid_language_alternative(
            "example.com", "https://fr.example.com/products"
        ) is True

    def test_same_host_language_path_accepted(self):
        """Same-host targets with language-shaped first segment are accepted."""
        cases = [
            ("example.com", "https://example.com/fr/products"),
            ("example.com", "https://example.com/fr-BE/products"),
            ("example.com", "https://example.com/fr-be/products"),
            ("example.com", "https://example.com/fr_CA/products"),
            ("example.com", "https://example.com/french/products"),
            ("example.com", "https://example.com/francais/products"),
            ("example.com", "https://example.com/français/products"),
            ("example.com", "https://example.com/france/products"),
        ]
        for host, url in cases:
            assert DomainFR._is_valid_language_alternative(host, url) is True, f"Expected True for ({host}, {url})"

    def test_same_host_non_language_path_rejected(self):
        """Same-host targets with content-section paths are rejected."""
        cases = [
            ("example.com", "https://example.com/nos-realisations"),
            ("example.com", "https://example.com/l-entreprise"),
            ("example.com", "https://example.com/nos-actualites"),
            ("example.com", "https://example.com/products"),
            ("example.com", "https://example.com/de/products"),
            ("example.com", "https://example.com/en/about"),
        ]
        for host, url in cases:
            assert DomainFR._is_valid_language_alternative(host, url) is False, f"Expected False for ({host}, {url})"

    def test_root_url_rejected(self):
        """Same-host root URL has no path segments — rejected."""
        assert DomainFR._is_valid_language_alternative(
            "example.com", "https://example.com/"
        ) is False
        assert DomainFR._is_valid_language_alternative(
            "example.com", "https://example.com"
        ) is False

    def test_malformed_url_rejected(self):
        """Non-URL strings are rejected gracefully."""
        assert DomainFR._is_valid_language_alternative(
            "example.com", "not-a-url"
        ) is False
        assert DomainFR._is_valid_language_alternative("example.com", "") is False


class TestHreflangValidation:
    """Integration: malformed hreflang declarations on content paths must not pollute alternative_urls."""

    @pytest.mark.asyncio
    async def test_hreflang_to_content_path_rejected(self):
        """A site with hreflang='fr-FR' pointing to a non-language path should yield empty alternatives."""
        html = """
        <html lang="fr-FR">
          <head>
            <link rel="alternate" hreflang="fr-FR" href="/nos-realisations">
            <link rel="alternate" hreflang="fr-FR" href="/l-entreprise">
            <link rel="alternate" hreflang="fr-FR" href="/nos-actualites">
          </head>
          <body><p>Bonjour le monde</p></body>
        </html>
        """
        detector = DomainFR("https://www.example.com")
        alternatives = await detector.detect_alternative_languages(html)
        # All three hrefs are same-host content paths — none should be returned
        assert all("nos-realisations" not in alt.url for alt in alternatives)
        assert all("l-entreprise" not in alt.url for alt in alternatives)
        assert all("nos-actualites" not in alt.url for alt in alternatives)

    @pytest.mark.asyncio
    async def test_hreflang_to_language_path_accepted(self):
        """A site with hreflang='fr-FR' pointing to /fr-FR/ should yield that alternative."""
        html = """
        <html lang="en-US">
          <head>
            <link rel="alternate" hreflang="fr-FR" href="https://www.example.com/fr-FR/">
          </head>
          <body><p>Hello world</p></body>
        </html>
        """
        detector = DomainFR("https://www.example.com")
        alternatives = await detector.detect_alternative_languages(html)
        # Note: this test does not validate via HTTP — hreflang is trusted (high reliability)
        # so it should appear directly without _validate_alternative_urls
        assert any("/fr-FR" in alt.url for alt in alternatives)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps-microservices/api-detection-langue-fr && pytest tests/test_domain_fr.py::TestIsValidLanguageAlternative tests/test_domain_fr.py::TestHreflangValidation -v`

Expected: All `TestIsValidLanguageAlternative` tests FAIL with `AttributeError: type object 'DomainFR' has no attribute '_is_valid_language_alternative'`. `TestHreflangValidation::test_hreflang_to_content_path_rejected` FAILS because content paths still appear in alternatives.

- [ ] **Step 3: Add the `_is_valid_language_alternative` static method**

In `apps-microservices/api-detection-langue-fr/app/core/domain_fr.py`, after the `_check_base_domain` method (around line 330), insert:

```python
    @staticmethod
    def _is_valid_language_alternative(homepage_host: str, target_url: str) -> bool:
        """
        Validate that an hreflang/data-lang target URL looks like a language alternative.

        Cross-host targets (different hostname than homepage) are trusted unconditionally —
        webmasters legitimately declare external French sites via hreflang.

        Same-host targets must have a language-shaped first path segment, e.g.:
          /fr, /fr-be, /fr_ca, /french, /francais, /français, /france
        Anything else (e.g. /nos-realisations, /l-entreprise) is rejected as a webmaster
        error or non-language declaration.

        Args:
            homepage_host: Lowercased hostname of the page being analyzed.
            target_url: Absolute URL declared as an alternative.

        Returns:
            True if the target should be accepted as a French alternative candidate.
        """
        try:
            parsed = urlparse(target_url)
            target_host = (parsed.hostname or '').lower()
            if target_host and target_host != homepage_host:
                return True
            segments = [s for s in parsed.path.split('/') if s]
            if not segments:
                return False
            first = segments[0].lower()
            return bool(re.match(
                r'^(fr|fr-[a-z]{2}|fr_[a-z]{2}|french|francais|français|france)$',
                first
            ))
        except Exception:
            return False
```

- [ ] **Step 4: Apply gate to hreflang detection block**

In `apps-microservices/api-detection-langue-fr/app/core/domain_fr.py:678-685`, change:

```python
            for regex in [re.compile(r'^fr', re.IGNORECASE), re.compile(r'fr', re.IGNORECASE)]:
                for link in soup.find_all(attrs={'hreflang': regex}):
                    href = link.get('href')
                    hreflang_val = link.get('hreflang', '')
                    if href and href != '#':
                        resolved = self.resolve_url(self.homepage, href)
                        if resolved and not self._is_self_url(resolved):
                            _add_trusted(resolved, 'hreflang', hreflang_value=hreflang_val)
```

To:

```python
            for regex in [re.compile(r'^fr', re.IGNORECASE), re.compile(r'fr', re.IGNORECASE)]:
                for link in soup.find_all(attrs={'hreflang': regex}):
                    href = link.get('href')
                    hreflang_val = link.get('hreflang', '')
                    if href and href != '#':
                        resolved = self.resolve_url(self.homepage, href)
                        if resolved and not self._is_self_url(resolved):
                            if not self._is_valid_language_alternative(homepage_host, resolved):
                                continue  # Skip same-host non-language-shaped paths
                            _add_trusted(resolved, 'hreflang', hreflang_value=hreflang_val)
```

- [ ] **Step 5: Apply gate to data-lang/data-gt-lang detection block**

In `apps-microservices/api-detection-langue-fr/app/core/domain_fr.py:687-697`, change:

```python
            for attr_name in ['data-lang', 'data-gt-lang']:
                method_name = attr_name.replace('-', '_')
                for regex in [re.compile(r'^fr', re.IGNORECASE), re.compile(r'fr', re.IGNORECASE)]:
                    for elem in soup.find_all(attrs={attr_name: regex}):
                        href = elem.get('href')
                        lang_val = elem.get(attr_name, '')
                        if href and href != '#':
                            resolved = _resolve_and_check(href)
                            if resolved:
                                _queue_candidate(resolved, href, method_name, hreflang_value=lang_val)
```

To:

```python
            for attr_name in ['data-lang', 'data-gt-lang']:
                method_name = attr_name.replace('-', '_')
                for regex in [re.compile(r'^fr', re.IGNORECASE), re.compile(r'fr', re.IGNORECASE)]:
                    for elem in soup.find_all(attrs={attr_name: regex}):
                        href = elem.get('href')
                        lang_val = elem.get(attr_name, '')
                        if href and href != '#':
                            resolved = _resolve_and_check(href)
                            if resolved:
                                if not self._is_valid_language_alternative(homepage_host, resolved):
                                    continue
                                _queue_candidate(resolved, href, method_name, hreflang_value=lang_val)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd apps-microservices/api-detection-langue-fr && pytest tests/test_domain_fr.py -v`

Expected: All tests PASS, including the new `TestIsValidLanguageAlternative` and `TestHreflangValidation` classes, plus all pre-existing tests.

- [ ] **Step 7: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/core/domain_fr.py \
        apps-microservices/api-detection-langue-fr/tests/test_domain_fr.py
git commit -m "fix(api-detection-langue-fr): validate hreflang/data-lang target URLs

Same-host hreflang/data-lang declarations whose target path is not
language-shaped (e.g., /nos-realisations) are now rejected as webmaster
errors. Cross-host declarations remain trusted.

Fixes the jaunin.com case where content-section paths were polluting
alternative_urls and causing the crawler to exclude entire content
sections from the crawl.

Spec: docs/superpowers/specs/2026-04-29-fr-detection-validation-hardening-design.md"
```

---

## Task 2: Crawler — `isFrenchRegionalPathPrefix` helper

**Goal:** Add a static helper on `DetectionLangueClient` that returns true only for path prefixes shaped like a French regional variant (`/fr`, `/fr-XX`, `/fr_XX`, `/french`, `/francais`, `/français`, `/france`).

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/class/DetectionLangueClient.ts:233` (append new static method after `isExcludedRegionalPath`)
- Test: `apps-microservices/crawler-service/crawler/src/tests/test_DetectionLangueClient.ts` (append new test function + invocation in main)

**Acceptance Criteria:**
- [ ] `isFrenchRegionalPathPrefix("/fr")` → true
- [ ] `isFrenchRegionalPathPrefix("/fr-BE")` → true
- [ ] `isFrenchRegionalPathPrefix("/fr_CA")` → true
- [ ] `isFrenchRegionalPathPrefix("/french")` → true
- [ ] `isFrenchRegionalPathPrefix("/francais")` → true
- [ ] `isFrenchRegionalPathPrefix("/français")` → true
- [ ] `isFrenchRegionalPathPrefix("/france")` → true
- [ ] `isFrenchRegionalPathPrefix("/nos-realisations")` → false
- [ ] `isFrenchRegionalPathPrefix("/de")` → false
- [ ] `isFrenchRegionalPathPrefix("/products")` → false
- [ ] `isFrenchRegionalPathPrefix("fr")` → false (no leading slash)
- [ ] `isFrenchRegionalPathPrefix("")` → false
- [ ] `isFrenchRegionalPathPrefix("/")` → false (empty after slash)

**Verify:** `cd apps-microservices/crawler-service/crawler && npx tsx src/tests/test_DetectionLangueClient.ts`

**Steps:**

- [ ] **Step 1: Write failing test for `isFrenchRegionalPathPrefix`**

In `apps-microservices/crawler-service/crawler/src/tests/test_DetectionLangueClient.ts`, append before the main invocation block (or before any final `process.exit` at end of file):

```typescript
// --- isFrenchRegionalPathPrefix tests ---

function testIsFrenchRegionalPathPrefix() {
    const cases: [string, boolean, string][] = [
        // Accepted shapes
        ["/fr", true, "generic /fr"],
        ["/fr-BE", true, "regional /fr-BE"],
        ["/fr-be", true, "regional /fr-be (lowercase)"],
        ["/fr_CA", true, "regional /fr_CA underscore"],
        ["/french", true, "/french keyword"],
        ["/francais", true, "/francais keyword"],
        ["/français", true, "/français keyword (accented)"],
        ["/france", true, "/france keyword"],
        // Rejected shapes
        ["/nos-realisations", false, "content path"],
        ["/l-entreprise", false, "content path with hyphen"],
        ["/products", false, "regular section"],
        ["/de", false, "non-FR language"],
        ["/en", false, "non-FR language"],
        ["/fr-BEL", false, "/fr-BEL three-letter region (invalid)"],
        ["/frX", false, "extra char after fr"],
        // Edge cases
        ["fr", false, "missing leading slash"],
        ["", false, "empty string"],
        ["/", false, "root only"],
    ];

    let passed = 0;
    let failed = 0;

    for (const [prefix, expected, label] of cases) {
        const result = DetectionLangueClient.isFrenchRegionalPathPrefix(prefix);
        if (result === expected) {
            passed++;
        } else {
            console.error(`FAIL [${label}]: isFrenchRegionalPathPrefix("${prefix}") = ${result}, expected ${expected}`);
            failed++;
        }
    }

    console.log(`\nisFrenchRegionalPathPrefix: ${passed} passed, ${failed} failed`);
    if (failed > 0) process.exit(1);
}
```

Then add `testIsFrenchRegionalPathPrefix();` to the main invocation block (where the other test functions are called).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/crawler-service/crawler && npx tsx src/tests/test_DetectionLangueClient.ts`

Expected: TypeScript compilation error or runtime error: `DetectionLangueClient.isFrenchRegionalPathPrefix is not a function`.

- [ ] **Step 3: Add the `isFrenchRegionalPathPrefix` static method**

In `apps-microservices/crawler-service/crawler/src/class/DetectionLangueClient.ts`, after the `isExcludedRegionalPath` method (after line 233, inside the `DetectionLangueClient` class, before the closing `}`), insert:

```typescript
    /**
     * Returns true if path prefix looks like a French regional variant.
     * Accepted shapes: /fr, /fr-XX, /fr_XX, /french, /francais, /français, /france
     * Used to validate that prefixes added to excludedRegionalPaths are actual
     * language regions, not content sections (e.g. /nos-realisations).
     */
    static isFrenchRegionalPathPrefix(prefix: string): boolean {
        if (!prefix || !prefix.startsWith("/")) return false;
        const segment = prefix.slice(1).toLowerCase();
        return /^(fr|fr-[a-z]{2}|fr_[a-z]{2}|french|francais|français|france)$/.test(segment);
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps-microservices/crawler-service/crawler && npx tsx src/tests/test_DetectionLangueClient.ts`

Expected: All test functions report 0 failed, including `isFrenchRegionalPathPrefix: 18 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/class/DetectionLangueClient.ts \
        apps-microservices/crawler-service/crawler/src/tests/test_DetectionLangueClient.ts
git commit -m "feat(crawler): add isFrenchRegionalPathPrefix helper

Validates that a path prefix matches a French regional shape
(/fr, /fr-XX, /fr_XX, /french, /francais, /français, /france).

Used by routes.ts regional exclusion to gate alt URL prefixes from the
detection API before adding them to excludedRegionalPaths — prevents
non-language paths (e.g. /nos-realisations) from being mistakenly
excluded as language regions.

Spec: docs/superpowers/specs/2026-04-29-fr-detection-validation-hardening-design.md"
```

---

## Task 3: Crawler — apply prefix shape gate in regional exclusion

**Goal:** Crawler only adds an alt URL's path prefix to `context.excludedRegionalPaths` when the prefix passes `isFrenchRegionalPathPrefix`. Belt-and-braces against API regression.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/routes.ts:418-440` (regional exclusion block in homepage detect ok branch)

**Acceptance Criteria:**
- [ ] Alt URL prefixes that don't match `isFrenchRegionalPathPrefix` are excluded from `context.excludedRegionalPaths`
- [ ] Alt URL prefixes matching the French regional shape continue to populate `context.excludedRegionalPaths` as before
- [ ] Existing crawler tests still pass
- [ ] TypeScript build succeeds (`npm run build`)

**Verify:** `cd apps-microservices/crawler-service/crawler && npm run build && npx tsx src/tests/test_DetectionLangueClient.ts && npx tsx src/tests/test_routes.ts`

**Steps:**

- [ ] **Step 1: Modify the regional exclusion loop in `routes.ts`**

In `apps-microservices/crawler-service/crawler/src/routes.ts:423-431`, change:

```typescript
                                const excluded: string[] = [];
                                for (const alt of detectResult.alternative_urls) {
                                    const altPrefix = DetectionLangueClient.extractPathPrefix(alt.url);
                                    if (altPrefix && altPrefix !== winnerPrefix && altPrefix !== seedPrefix) {
                                        if (!excluded.includes(altPrefix)) {
                                            excluded.push(altPrefix);
                                        }
                                    }
                                }
```

To:

```typescript
                                const excluded: string[] = [];
                                for (const alt of detectResult.alternative_urls) {
                                    const altPrefix = DetectionLangueClient.extractPathPrefix(alt.url);
                                    if (altPrefix
                                        && altPrefix !== winnerPrefix
                                        && altPrefix !== seedPrefix
                                        && DetectionLangueClient.isFrenchRegionalPathPrefix(altPrefix)) {
                                        if (!excluded.includes(altPrefix)) {
                                            excluded.push(altPrefix);
                                        }
                                    }
                                }
```

- [ ] **Step 2: Verify TypeScript build succeeds**

Run: `cd apps-microservices/crawler-service/crawler && npm run build`

Expected: build succeeds with no errors.

- [ ] **Step 3: Run all crawler tests**

Run: `cd apps-microservices/crawler-service/crawler && npx tsx src/tests/test_DetectionLangueClient.ts && npx tsx src/tests/test_routes.ts && npx tsx src/tests/test_context.ts`

Expected: all tests report 0 failed.

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/routes.ts
git commit -m "fix(crawler): gate excludedRegionalPaths with prefix shape validator

Apply isFrenchRegionalPathPrefix validation to every alt URL prefix
returned by the detection API before adding it to
context.excludedRegionalPaths. Prevents content-section paths (e.g.
/nos-realisations from a malformed hreflang) from being mistakenly
treated as French regional variants and blocking entire sections of
the site.

Defense in depth: complements the API-side fix that rejects malformed
hreflang declarations at source.

Spec: docs/superpowers/specs/2026-04-29-fr-detection-validation-hardening-design.md"
```

---

## Task 4: Crawler — drop URL fallback after clean HTML rejection

**Goal:** When the API cleanly rejects a page via forced HTML detect (`Check_nok_forced`), trust the verdict. Stop running `checkUrl()` URL-only fallback that lets pages pass on the basis of TLD alone.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/routes.ts:571-581` (internal page detect result handling)

**Acceptance Criteria:**
- [ ] When `detectResult.ok === false` after forced HTML detect, `isEnqueuingLinks` stays `false`
- [ ] No `checkUrl()` call after a clean rejection
- [ ] When `detectResult.ok === true`, `isEnqueuingLinks` is set to `true` (unchanged)
- [ ] API technical errors caught by `try/catch` keep `isEnqueuingLinks` `false` (unchanged)
- [ ] TypeScript build succeeds
- [ ] Existing crawler tests still pass

**Verify:** `cd apps-microservices/crawler-service/crawler && npm run build && npx tsx src/tests/test_DetectionLangueClient.ts && npx tsx src/tests/test_routes.ts`

**Steps:**

- [ ] **Step 1: Modify internal page validation in `routes.ts`**

In `apps-microservices/crawler-service/crawler/src/routes.ts:571-581`, change:

```typescript
                        if (detectResult.ok) {
                            isEnqueuingLinks = true;
                        } else if (!needsNlp) {
                            // Fallback: URL-only check (no method match required).
                            // The stored method describes how the *homepage* was detected,
                            // not which URL patterns are valid for internal pages.
                            const checkUrlResult = await detectionClient.checkUrl(url);
                            if (checkUrlResult.ok) {
                                isEnqueuingLinks = true;
                            }
                        }
```

To:

```typescript
                        if (detectResult.ok) {
                            isEnqueuingLinks = true;
                        }
                        // No URL fallback after a clean rejection. The forced HTML detect
                        // already analyzed the lang attribute; URL TLD/path signals cannot
                        // override that verdict. API technical failures are handled by the
                        // surrounding try/catch (line ~582).
```

- [ ] **Step 2: Verify TypeScript build succeeds**

Run: `cd apps-microservices/crawler-service/crawler && npm run build`

Expected: build succeeds with no errors. Note that the `checkUrlResult` and `needsNlp`-only-branch references disappear from this block; ensure no other references rely on those.

- [ ] **Step 3: Run all crawler tests**

Run: `cd apps-microservices/crawler-service/crawler && npx tsx src/tests/test_DetectionLangueClient.ts && npx tsx src/tests/test_routes.ts && npx tsx src/tests/test_context.ts && npx tsx src/tests/test_functions.ts`

Expected: all tests report 0 failed.

- [ ] **Step 4: Manual verification (recommended)**

If a development environment is available, run a small crawl against `aera-sa.fr` and verify:
- A URL like `https://www.aera-sa.fr/de/2022/12/16/all4pack-2022/` does NOT appear in the main `dataset.json`.
- The same URL appears in the `nfr-aera-sa.fr` non-French dataset (or is filtered earlier without entering either).

This step is optional but recommended; if a dev crawl env is unavailable, rely on the unit-level coverage from Tasks 1-3 and rollout monitoring.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/routes.ts
git commit -m "fix(crawler): drop URL fallback after clean HTML rejection

When forced HTML detect rejects a page (e.g. <html lang=\"de-DE\"> on a
.fr TLD), stop running checkUrl() to second-guess the verdict. The HTML
lang attribute is stronger evidence than the URL TLD; letting the URL
fallback override produced false positives in the main dataset.

Fixes aera-sa.fr where German pages on .fr TLD were entering the main
dataset because direct_match (TLD .fr) overrode forced_method rejection.

API technical failures are still handled by the surrounding try/catch
— this only removes the soft fallback after a clean rejection.

Spec: docs/superpowers/specs/2026-04-29-fr-detection-validation-hardening-design.md"
```

---

## Verification After All Tasks

Run end-to-end test suite:

- [ ] API tests: `cd apps-microservices/api-detection-langue-fr && pytest tests/ -v`
- [ ] Crawler unit tests: `cd apps-microservices/crawler-service/crawler && for f in src/tests/test_*.ts; do echo "=== $f ==="; npx tsx "$f"; done`
- [ ] Crawler build: `cd apps-microservices/crawler-service/crawler && npm run build`

Expected: all green.

## Rollout

Per spec: deploy API change (Task 1) first, then crawler changes (Tasks 2, 3, 4) in the same release. No feature flag needed — all three are bug-corrective and low-risk.
