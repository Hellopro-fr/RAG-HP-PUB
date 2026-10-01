# Backlog — Crawler keeps the French URL api-detection resolved (post-cryolor follow-ups)

- **Date:** 2026-06-05
- **Status:** OPEN — deferred follow-ups (not urgent; the reported bug is already fixed)
- **Origin:** systematic-debugging of `cryolor.com` (crawl id 6894) "detected `/fr` but crawled the English root and lost French".
- **Shipped fix this session (the actual bug):** commit `148f4bd7` on `features/poc` —
  pin the crawler's Camoufox browser to `locale: 'fr-FR'`
  (`apps-microservices/crawler-service/crawler/src/camoufoxLaunchInput.ts`, wired at
  `functions.ts:473`). NOT yet SFTP-deployed (operator controls deploy).

---

## 1. Context (why these follow-ups exist)

`cryolor.com` is a Drupal/Acquia multilingual site: **English = `/` (root), French = `/fr`**
(hreflang on every page: `en→/`, `fr→/fr`). It ships Drupal's **`browser_language_detection`**
module, which runs this JS client-side:

```js
// footer bundle js_7gz5...js
o = (navigator.languages ? navigator.languages[0] : navigator.language).substring(0,2);
e = drupalSettings.browserLanguageDetection.language.substring(0,2);   // page lang
if (o in redirections && e !== o) window.location.href = redirections[o];
```
```json
"browserLanguageDetection":{"language":"fr","default_language":"en",
 "language_redirections":{"en":"https://www.cryolor.com/","fr":"https://www.cryolor.com/fr"}}
```

The redirect is driven entirely by **`navigator.language`**:

| Service | `navigator.language` | on `/fr` | on `/` (root) |
|---|---|---|---|
| api-detection (`scraper.py:328` pins `locale:'fr-FR'`) | `fr` | `o=fr=e` → **stays /fr** | `o=fr≠e=en` → **redirected to /fr** ✅ |
| crawler **before** fix (`functions.ts` launched Camoufox `{headless:true}` only) | `en` (Docker default) | `o=en≠e=fr` → **bounced to /** ❌ | stays / |

So the *same* JS that made api-detection succeed (root → `/fr`) made the crawler fail (`/fr` → root).
The `locale:'fr-FR'` fix aligns the crawler with api-detection's already-working behavior and closes
the whole `browser_language_detection` class.

**These two follow-ups are defense-in-depth** for redirect mechanisms the locale fix does NOT cover
(server-side GeoIP, cookie-based negotiation, JS not keyed on `navigator.language`). They make the
invariant true regardless of *how* the redirect happens.

### The shared invariant
> When api-detection has resolved a French URL for a domain, the crawler must end up crawling that
> French URL — it must never silently re-judge a redirected landing page and lose the French
> designation.

### Confirmed evidence (for a cold-start reader)
- Prod DB `domaine_scrapping_produit_ia` id **6894**: `seed_homepage = https://www.cryolor.com/fr`,
  `message_erreur_crawling = "Page non détectée en Français"`, `statut_dspi = 9`.
- Crawler log: `Processing https://www.cryolor.com/ ( https://www.cryolor.com/fr )` (loadedUrl=root,
  seed=/fr) then `[NOT_FRENCH] Homepage https://www.cryolor.com/ is NOT French and no French
  alternative was found.`
- `/fr` is server-side stable FR (curl: every UA / Accept-Language / http / www / trailing-slash
  variant → 200 `Content-Language: fr`, no 3xx). The redirect is **client-side, locale-driven**.

---

## 2. Follow-up #1 — Crawler must honor the FR URL api-detection resolves (HIGHER LEVERAGE)

### Problem
On the main site the crawler branches on `detectResult.ok` and crawls whatever
`request.loadedUrl` it landed on. It **never navigates to `detectResult.url`**. The only read of
`detectResult.url` is regional-path-exclusion.

`apps-microservices/crawler-service/crawler/src/routes.ts`:
- `:221` `let url = request.loadedUrl;` — everything downstream judges the *landed* URL.
- `:419` `const isMainSite = request.url === site;`
- `:473-477` `detectionClient.detect(url, content, { mode:"complete", validateAlternatives:false })`.
- `:482-531` `ok=true` branch → `isEnqueuingLinks=true`, crawls `loadedUrl` even if
  `detectResult.url` points elsewhere.
- `:511` only use of `detectResult.url`: `extractPathPrefix(detectResult.url || url)` (regional
  exclusion).
- `:532-575` `ok=false` branch → **logs** `alternative_urls[0]` (`[ALTERNATIVE_URL] … found: /fr`,
  `:535-539`) then only `checkUrl(url)` (`:555`). It **never re-seeds** the alternative; if `checkUrl`
  fails → `[NOT_FRENCH]` (`:544-546`) → stop.

**Net:** api-detection can *know* the French URL (its `url` field, or `alternative_urls`) and the
crawler throws that knowledge away — crawling wrong-language content (`ok=true`) or stopping
(`ok=false`).

### Proposed approach
When `isMainSite` AND api-detection resolves a French URL different from `loadedUrl`
— either `ok=true` with `detectResult.url !== loadedUrl`, or `ok=false` with a high-reliability
`validated` entry in `alternative_urls` — **re-seed the crawl to that URL once**, then proceed as the
new main site (skip re-detect on it). Guards:
- **Redirect-loop guard:** never re-seed a URL already visited or that already bounced; cap at **1
  re-seed hop**. (Without this, a `/fr → / → re-seed /fr → /` loop is possible if the locale fix
  isn't deployed or doesn't apply.)
- Decide which field wins when both present (`detectResult.url` vs `alternative_urls[0]`).
- Keep the existing regional-path-exclusion behavior intact.

**Risk:** mid-crawl re-seeding + loop safety is non-trivial → spec-worthy (brainstorm → writing-plans).

### Sub-anomaly to instrument (low priority, runtime-only)
For cryolor, `alternative_urls` came back **empty** even though the crawler forwards the **full** root
HTML (`processPage` returns `page.content()` — `functions.ts:134-191`, confirmed) and that HTML
carries `hreflang fr→/fr`. Static trace shows it *should* surface:
- `detect_alternative_languages` IS called in complete mode — `domain_fr.py:1077-1080`.
- `_is_self_url` compares host **and** path (`domain_fr.py:527-548`) → `/fr` ≠ `/` → not self → kept.
- `_is_valid_language_alternative` accepts a language-shaped `/fr` (`domain_fr.py:365-404`).
- hreflang alts are added by `_add_trusted` (`validated=True`, reliability `high`, **zero HTTP**),
  independent of the `validate_alternatives` flag — `domain_fr.py:707-719`, `:737-755`.

So empty ⇒ a **runtime** cause: the content captured during the JS-redirect transition likely lacked
the `<head>` hreflang (page mid-navigation when `page.content()` ran; `getPageContentWithRetry` may
have grabbed a transitional doc). **Action:** log `html_content` length + `detectResult.alternative_urls`
on the homepage detect call to confirm. Moot once the locale fix is deployed (crawler stays on `/fr`),
but it's why the recovery net was doubly dead here.

---

## 3. Follow-up #2 — Decide the fate of the `validate_alternatives:false` Case-6 gate

### Recap
The crawler's homepage call sends `validate_alternatives:false` (`routes.ts:476`), which gates off
**Case 6** (`domain_fr.py:1213-1214` — `if self.validate_alternatives and reliable_alternatives:`).
Case 6 is the only path that **promotes** a discovered French alternative into the result (`ok`
false→true, `url=alt`) by browser-fetching it and NLP-confirming (`:1219-1301`, `fetch_html` per alt).
We shipped that gate deliberately (CLAUDE.md "Alternative-URL Validation Skip") to kill the browser
opens that were the OOM / `socket hang up` source.

### Latent regression
For a site where the crawler lands on a non-French page that *does* expose a French alternative in its
`html_content`: pre-flag the crawler's detect returned `ok=true url=/fr` via Case 6; post-flag it
returns `ok=false`. cryolor dodged this (empty alts + locale fix) but the class exists.

### The cheap option (nuance)
hreflang alternatives are `validated=True` with **zero HTTP** *regardless of the flag* (`_add_trusted`,
`domain_fr.py:707-719`). Case 6's browser fetch only *re-confirms* via NLP. So under
`validate_alternatives=false` you could **promote a trusted hreflang alt to the result with zero
HTTP** (trust the webmaster declaration we already mark `validated=True`), while still skipping the
browser confirm for medium/low candidates — restoring the safe promotion without re-introducing the
OOM source.

### Decision needed (pick ONE fix location — see coupling below)
- **(a)** Leave the gate as-is; fix recovery crawler-side via Follow-up #1 (honors `alternative_urls`).
- **(b)** Add the zero-HTTP trusted-hreflang promotion in api-detection under the flag.
- **(c)** Both (belt-and-braces).

---

## 4. Coupling + recommendation

The two follow-ups are **coupled**: if the crawler honors `alternative_urls` (Follow-up #1), then even
`ok=false`-with-hreflang lets it re-seed `/fr`, and Follow-up #2 becomes optional. So the real decision
is **one fix location, not two**:
- **Follow-up #1 (crawler honors resolved FR URL)** — general; covers every redirect mechanism. *Higher
  leverage.* Recommended if we want the general safety net.
- **Follow-up #2 (api-detection promotes hreflang)** — narrower; only helps the hreflang case.

**Recommendation:** the `locale:'fr-FR'` fix (shipped) closes the reported bug and the whole
`browser_language_detection` class. Treat #1 as the next step *if* we want redirect-mechanism-agnostic
robustness; #2 only if we choose to fix at the detection layer instead of the crawler.

---

## 5. File / evidence index (anchors)

Crawler (`apps-microservices/crawler-service/crawler/src/`):
- `routes.ts:221` landed-URL; `:419` isMainSite; `:473-477` detect call; `:482-575` ok/not-ok branches;
  `:511` sole `detectResult.url` use; `:535-546` alternative/not-french logs.
- `functions.ts:134-191` `processPage` = `page.content()` (full HTML); `:473` Camoufox launch (fixed).
- `camoufoxLaunchInput.ts` (new this session) — `CRAWLER_BROWSER_LOCALE='fr-FR'`.

api-detection (`apps-microservices/api-detection-langue-fr/app/core/`):
- `domain_fr.py:1077-1080` alternatives parsed (complete mode); `:1213-1214` Case-6 gate;
  `:1219-1301` Case-6 fetch+confirm; `:887-904` flag branch; `:707-719` `_add_trusted`;
  `:737-755` hreflang parse; `:527-548` `_compare_without_scheme`/`_is_self_url`;
  `:365-404` `_is_valid_language_alternative`.
- `services/scraper.py:328/331` api-detection's `locale:'fr-FR'` + `Accept-Language` (the working reference).

Related shipped work this session: commit `148f4bd7` (locale fix). Prior flag work:
CLAUDE.md "Alternative-URL Validation Skip (`validate_alternatives`)".
