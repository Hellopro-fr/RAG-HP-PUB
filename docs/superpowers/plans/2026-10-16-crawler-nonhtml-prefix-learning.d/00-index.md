# crawler-service — apprentissage des préfixes non-HTML (R23 (2)) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Empêcher le crawler de rejouer des URLs non-HTML sans extension (marsaleix `/image/…`) en apprenant, par dossier parent, les préfixes qui ne servent que du non-HTML, persistés d'un crawl au suivant avec révision par sonde, derrière `NONHTML_PREFIX_MODE` (`off` par défaut).

**Architecture:** Trois fichiers neufs : un module pur de décision (`nonHtmlPrefix.ts`, patron `facetCap.ts`), un module sidecar (sérialisation + I/O tmp/rename, patron `unjudgedUrls.ts`), une classe `NonHtmlPrefixGate` qui applique le mode et que portent `context.nonHtmlPrefix` (null en `off`). Câblage en 3 points de blocage (b1 enfilage `routes.ts`, b2 ré-amorçage `main.ts`, b3 prenav `functions.ts`), 2 points d'apprentissage (`routes.ts`), 1 point d'échec de sonde (`functions.ts`). Exemption absolue du dataset précédent.

**Tech Stack:** TypeScript (Node 23.5.0, `node:test` via `tsx`), Crawlee 3.16.0 / Playwright ; Python FastAPI (`app/router/admin.py`, pytest).

**Spec:** `docs/superpowers/specs/2026-10-16-crawler-nonhtml-prefix-learning-design.md` (commit `f4377f823`). Chemins de code ci-dessous relatifs à `apps-microservices/crawler-service/` ; `src/` = `crawler/src/`.

## Global Constraints

- **Mode `off` = zéro effet** : `context.nonHtmlPrefix` reste `null`, aucun appel des modules neufs, aucun fichier écrit, aucun compteur incrémenté, **aucune clé `filtered_nonhtml` dans le payload** (spread conditionnel, § Contrat C7). Les 509 tests existants passent **sans modification** (aucun `*.test.ts` existant modifié).
- **Identité testée = `request.url`** (l'identité de file), jamais `request.loadedUrl` ni le `url` local de `routes.ts:257` (`let url = request.loadedUrl;`). En b2, c'est `seedUrl` (la chaîne réellement enfilée, `main.ts:1613-1617`).
- **Exemption absolue** : une URL du dataset principal précédent (`source === 'dataset'`) et la page d'accueil (`site`) ne sont jamais bloquées, à aucun point. Comparaison au `/` final près (`normalizeUrlIdentity`).
- **Une variable vide ne donne jamais 0** : tout parse d'entier retombe sur le défaut pour `""`, non-entier, ≤ 0 (piège `resolveTimeoutMaxRetries("")`, `httpStatusPolicy.ts:49`).
- **Écriture sidecar = tmp + rename**, jamais d'exception remontée au crawl (échec ⇒ `console.warn`).
- **Aucun fichier existant de test n'est modifié.** Tests neufs = fichiers neufs.
- Commentaires de code : suivre le fichier édité (EN dans `routes.ts`/`functions.ts`/modules neufs ; `main.ts` mixte — EN pour les ajouts).
- Commits : Conventional Commits, corps EN puis `FR — <sujet>` + corps FR ; message par fichier (`git -C <WT> commit -F <scratchpad>/commit-T<nn>.txt`), jamais heredoc (mémoire `feedback_force_push_blocker_heredoc`).

**User decisions (already made):** (spec § 2, ne pas redemander)
- D1 : combinaison E + B (URLs isolées + apprentissage de préfixe).
- D2 : B persisté d'un crawl au suivant.
- D3 : clé = hôte + dossier parent du chemin.
- D4 : révision par sonde.
- D5 : E dans le même sidecar que B.

## Marqueurs de ce plan

- `<WT>` = racine absolue du worktree d'exécution (`git rev-parse --show-toplevel`, forme `D:/…`). `<CR>` = `<WT>/apps-microservices/crawler-service/crawler`.
- `<MAIN>` = racine du checkout principal (`D:/DevHellopro/Workspaces/RAG-HP-PUB`).
- `<scratchpad>` = scratchpad de la session qui exécute.

## Environnement et préconditions (mesurés le 2026-10-16, session de rédaction)

| Fait | Commande | Résultat |
|---|---|---|
| Base inchangée | `git -C <WT> log --oneline e57409aed..features/poc -- apps-microservices/crawler-service` | vide ; `git rev-parse features/poc` = `e57409aeda07…` |
| Shell | `type ls grep sed awk` | `ls` alias `ls -F --color=auto --show-control-chars` ⇒ écrire `command ls` dans une sortie comparée ; grep/sed/awk = `/usr/bin` |
| Garde d'isolation ARMÉE | essai `cd <calculé> && git …` | refusé (« changes directory … before running git ») ⇒ git toujours en `git -C <WT> …`, une commande git par appel ; `cd <CR> && node …` (sans git) accepté |
| Lockfile gitignoré | `git check-ignore -v --no-index crawler/package-lock.json` | `.gitignore:164` ⇒ absent d'un worktree neuf |
| Dépendances | copie `<MAIN>/apps-microservices/crawler-service/crawler/package-lock.json` → `<CR>/`, `cmp` = 0, puis `npm ci --ignore-scripts --no-audit --no-fund` | 377 paquets, ~3 min. **Déjà fait dans ce worktree** ; T1 Step 0 le refait seulement si `<CR>/node_modules` absent |
| Oracle | `cd <CR> && npm test 2>&1 \| tail -12` | `ℹ tests 509` `ℹ pass 509` `ℹ fail 0` (≈50 s) |
| Un seul fichier de test | `cd <CR> && node --import tsx --test src/<f>.test.ts` | `--import tsx` se résout depuis le cwd ⇒ toujours depuis `<CR>` |
| Script de test | `crawler/package.json` : `"test": "node --import tsx --test src/**/*.test.ts"` | un `*.test.ts` neuf sous `src/` ou `src/tools/` est ramassé |

## File Structure

| Fichier | Rôle | Tâche |
|---|---|---|
| Create `crawler/src/nonHtmlPrefix.ts` | décisions pures : modes, paramètres, clé, état, `recordNonHtml/recordHtml/recordProbeFailure`, `decide` | T1 |
| Create `crawler/src/nonHtmlPrefix.test.ts` | tests du module pur | T1 |
| Create `crawler/src/nonHtmlPrefixSidecar.ts` | sérialisation, parse tolérant, chargement current/previous, chemins, I/O tmp+rename | T2 |
| Create `crawler/src/nonHtmlPrefixSidecar.test.ts` | tests sidecar | T2 |
| Create `crawler/src/nonHtmlPrefixGate.ts` | classe `NonHtmlPrefixGate` : mode, exemption, logs, persistance | T3 |
| Create `crawler/src/nonHtmlPrefixGate.test.ts` | un test par point de blocage × mode | T3 |
| Modify `crawler/src/context.ts` | champ `nonHtmlPrefix` | T3 |
| Modify `crawler/src/main.ts` | init + chargement, exemption, b2, `readStat` + payload | T4 |
| Modify `crawler/src/routes.ts` | apprendre non-HTML, apprendre HTML, b1 | T5 |
| Modify `crawler/src/functions.ts` | b3 (hook prenav), échec de sonde | T6 |
| Create `crawler/src/nonHtmlPrefixWiring.test.ts` | parité texte-source du câblage et du compteur | T7 |
| Modify `app/router/admin.py` | `"pdf": "pdf-"` dans `_DATASET_PREFIXES` ; préfixe `NONHTML_` dans la whitelist d'env de `/admin/config` | T8 |
| Create `tests/test_admin_nonhtml_prefix.py` | tests Python de T8 | T8 |
| Create `crawler/src/tools/nonHtmlPrefixReplay.ts` | instrument de rejeu K=1…10 (lib + CLI gardée) | T9 |
| Create `crawler/src/tools/nonHtmlPrefixReplay.test.ts` | tests du rejeu | T9 |
| Modify `CLAUDE.md` (crawler-service) | section documentaire | T10 |

**Chaque fichier modifié n'est touché que par UNE tâche** (aucun fichier partagé entre tâches). Propriétés d'octets mesurées (`git -C <WT> ls-files --eol -- <chemins>`) :

| Fichier | index / copie | Méthode d'édition | Contrôle d'effet après édition |
|---|---|---|---|
| `crawler/src/functions.ts` | **i/crlf** w/crlf | outil Edit (insertion après ancre intacte) | `git -C <WT> ls-files --eol -- apps-microservices/crawler-service/crawler/src/functions.ts` doit rester `i/crlf` (un `i/mixed` = lignes LF insérées ⇒ corriger) ; `git -C <WT> diff --numstat -- <fichier>` : 0 ligne supprimée |
| `crawler/src/routes.ts`, `main.ts`, `context.ts`, `app/router/admin.py`, `CLAUDE.md` | i/lf w/crlf | outil Edit | `ls-files --eol` reste `i/lf` après `git add` ; `git diff --numstat` : supprimées = nombre annoncé par la tâche (0 pour une tâche d'insertions pures) |

Ignore status : aucun des chemins créés/modifiés n'est ignoré — à confirmer en T1 Step 0 par `git -C <WT> check-ignore -v --no-index <chemin>` sur les 16 chemins (attendu : aucune sortie, code 1). Après chaque `git add`, `git -C <WT> diff --cached --stat` doit lister exactement les fichiers de la tâche.

## Faits établis (base `e57409aed`, sortie numérotée citée)

Tous via `awk 'NR>=a && NR<=b {printf "%d: %s\n", NR, $0}' <fichier>` ou `grep -n`. **À l'exécution, localiser par contenu** (citation entre guillemets), pas par numéro.

| # | Fait | Ligne(s) |
|---|---|---|
| F1 | garde content-type : `if (contentType && !contentType.includes('text/html') && …)` ; log `Skipping non-HTML response:` ; `return;` | `routes.ts:368`, `:386`, `:387` |
| F2 | fin de la politique de statut : `throw new Error(\`HTTP ${status}\`);` puis `// --- Circuit Breaker Check (Dual-Mode) ---` puis `await context.statsManager.increment("processed");` | `routes.ts:443`, `:447`, `:451` |
| F3 | b1 : bloc facet cap `// Queue-purge #1: facet cap — drop discovered variants once the base is saturated.` … `return false;` `}` ; suivi de `// Queue-purge #2: filter-on-seen-base` | `routes.ts:1243-1247`, `:1249` |
| F4 | `transformRequestFunction` doit rester SYNCHRONE (commentaire `routes.ts:1254-1256`) ; `logBlocked('facet-cap', request.url)` | `routes.ts:1245`, `:1117` |
| F5 | b3 : hook prenav facet cap `// Queue-purge #1: facet cap. Content-agnostic backstop` … `throw new StaleVariantSkip(request.url, target);` (filter-on-seen dans le même hook) | `functions.ts:881-895` (fin du hook à localiser par contenu) |
| F6 | `failedRequestHandler` : branche `STALE_VARIANT_SKIP_MARKER` → `increment("purged_prenav")` → `return;` `}` puis `log.error(\`Request ${request.url} failed:` | `functions.ts:601-604`, `:606` |
| F7 | `StaleVariantSkip extends NonRetryableError`, `constructor(url: string, stripped: string)` | `staleVariantSkip.ts:18`, `:20` |
| F8 | `ensureUnjudgedSidecar(domain);` — après le bloc `dropData` (`:588-611`) ; cwd = storagePath (chemin relatif `storage/datasets/…`, `unjudgedUrls.ts:34-35`) | `main.ts:619` |
| F9 | `previousCrawlId` (`:120`), `crawlMode` (`:118`), `site` (`:95`) déclarés avant `:619` | `main.ts:95`, `:118`, `:120` |
| F10 | boucle de collecte `for await (const { url: consolidatedUrl, source } of allUrls) {` `if (matchesMainSite(consolidatedUrl, site)) continue;` `remainingUrls.push(…)` | `main.ts:961-964` |
| F11 | lancement du crawler `const crawler = await startCrawler(` APRÈS la consolidation ⇒ l'exemption est complète avant toute requête | `main.ts:1778` |
| F12 | seedPhase2 : `let skippedExtCount = 0;` ; `hasIgnoredExtensionForSeed(url)` ; fin du bloc `processUrl` ; commentaire `// Épinglage de l'identité de file, comme Phase 1 (:952)` ; `await requestQueue.addRequest({` `url: seedUrl,` `uniqueKey: seedUrl,` ; log `[seed-filter] skipped ${skippedExtCount}` | `main.ts:1560`, `:1573`, `:1605`, `:1606`, `:1615-1617`, `:1627` |
| F13 | `const filtered_ext = await readStat("filtered_ext");` ; payload `filtered_ext,` | `main.ts:1260`, `:1294` |
| F14 | `failed: Math.max(0, (finalStats?.requestsFailed \|\| 0) - purged_prenav)` ⇒ un blocage b3 (StaleVariantSkip ⇒ `purged_prenav`) ne gonfle pas `failed` | `main.ts:1281` |
| F15 | contexte partagé : `facetVariantCount: new Map<string, Set<string>>(),` | `context.ts:181` |
| F16 | `export function hasIgnoredExtensionForSeed(url: string): boolean` ; le fichier n'a pas d'import | `seedExtensionFilter.ts:36` |
| F17 | `export const rightTrimSlash = (str: string) => str.replace(/\/+$/, "");` (non importé : `functions.ts` est lourd) | `functions.ts:1657` |
| F18 | résolution du dataset précédent : `path.resolve('..', previousId)` / `storage/datasets/<domain>` puis `domain.replace(/\./g, '-')` ; lecteur saute `!file.startsWith('__')` et exige `.json` | `functions.ts:1266-1281`, `:1293` |
| F19 | patron tmp+rename : `const tmp = \`${file}.tmp\`; fs.writeFileSync(tmp, …); fs.renameSync(tmp, file);` | `unjudgedUrls.ts:53-57` |
| F20 | patron flag d'env : `export const QM_FACET_ENABLED =` / `QM_FACET_CAP_K = (() => {` | `facetCap.ts:8`, `:11` |
| F21 | `_DATASET_PREFIXES = {"main": "", "error": "error-", "nfr": "nfr-", "update": "update-"}` | `app/router/admin.py:225` |
| F22 | dataset pdf : `pdfDatasetName(context.config.crawleeStorageName, targetDomain)` (préfixe réel à lire dans sa définition — T8) | `routes.ts:377` |

## Contrat (identifiants à écrire À L'IDENTIQUE chez producteur et consommateur)

### C1 — `crawler/src/nonHtmlPrefix.ts` (T1 produit ; T2, T3, T9 consomment)

Pur : aucun `fs`, aucune lecture de `process.env` au chargement du module. Seul import : `hasIgnoredExtensionForSeed` depuis `./seedExtensionFilter.js` ; `node:path` (posix) autorisé.

```ts
export type NonHtmlPrefixMode = "off" | "shadow" | "on";
export function resolveNonHtmlPrefixMode(raw: string | undefined): NonHtmlPrefixMode;
// trim + toLowerCase ; "shadow" | "on" ⇒ tel quel ; tout le reste (undefined, "", inconnu) ⇒ "off"
export function resolvePositiveInt(raw: string | undefined, fallback: number): number;
// trim ; /^\d+$/ et > 0 ⇒ Number(raw) ; sinon (undefined, "", "abc", "0", "-1", "2.5") ⇒ fallback
export interface NonHtmlPrefixParams { minNonHtml: number; probes: number; isolatedMax: number; }
export const NONHTML_PREFIX_DEFAULTS: NonHtmlPrefixParams; // { minNonHtml: 5, probes: 3, isolatedMax: 10000 }
export function resolveNonHtmlPrefixParams(env: Record<string, string | undefined>): NonHtmlPrefixParams;
// NONHTML_PREFIX_MIN → minNonHtml ; NONHTML_PREFIX_PROBES → probes ; NONHTML_ISOLATED_MAX → isolatedMax ; via resolvePositiveInt
export function normalizeUrlIdentity(url: string): string; // url.replace(/\/+$/, "") — même règle que F17
export function prefixKey(url: string): string | null;
// new URL(url) (invalide ⇒ null) ; dir = path.posix.dirname(u.pathname) ; dir === "/" ⇒ null ; sinon `${u.host}${dir}`
// ex. https://www.marsaleix.fr/image/_1AAAB-x?y=1#z ⇒ "www.marsaleix.fr/image" ; https://h/telechargement?id=12 ⇒ null
export interface Probation { admitted: number; probeUrl: string | null; resolved: boolean; }
export interface PrefixEntry { nonHtml: number; sawHtml: boolean; confirmed: boolean; confirmedAt: string | null; probation: Probation | null; }
export interface NonHtmlPrefixState { params: NonHtmlPrefixParams; prefixes: Map<string, PrefixEntry>; isolated: Set<string>; loadedIsolated: Set<string>; }
export function createNonHtmlPrefixState(params: NonHtmlPrefixParams): NonHtmlPrefixState;
export function isKeyBlocking(entry: PrefixEntry, params: NonHtmlPrefixParams): boolean;
// !entry.sawHtml && (entry.confirmed || entry.nonHtml >= params.minNonHtml)
export type NonHtmlEvent = "ignored" | "counted" | "learned" | "confirmed" | "isolated";
export function recordNonHtml(state: NonHtmlPrefixState, url: string, nowIso: string): NonHtmlEvent;
export type HtmlEvent = "none" | "released";
export function recordHtml(state: NonHtmlPrefixState, url: string): HtmlEvent;
export function recordProbeFailure(state: NonHtmlPrefixState, url: string): boolean;
export type NonHtmlDecision = "allow" | "block" | "probe";
export function decide(state: NonHtmlPrefixState, url: string, isExempt: (normalizedUrl: string) => boolean): NonHtmlDecision;
```

Sémantique (normative ; `n` = `normalizeUrlIdentity(url)`, `key` = `prefixKey(url)`) :

- **`recordNonHtml`**, dans cet ordre :
  1. `hasIgnoredExtensionForSeed(url)` ⇒ `"ignored"` (rien ne change).
  2. `key === null` ⇒ si `n` absent de `isolated` et `isolated.size < isolatedMax` : l'ajouter, `"isolated"` ; sinon `"ignored"`.
  3. entrée absente ⇒ créer `{ nonHtml: 0, sawHtml: false, confirmed: false, confirmedAt: null, probation: null }`. Si `entry.sawHtml` ⇒ `nonHtml++`, `"counted"` (le veto tient pour tout le crawl).
  4. `wasBlocking = isKeyBlocking(entry)` avant incrément ; `nonHtml++`.
  5. probation non résolue (`probation && !probation.resolved`) ⇒ **toute** réponse non-HTML sous la clé la confirme : `probation.resolved = true`, `probation.probeUrl = null`, `confirmed = true`, `confirmedAt = nowIso` ⇒ `"confirmed"`.
  6. `wasBlocking` ⇒ `"counted"`.
  7. `isKeyBlocking(entry)` maintenant vrai (seuil K franchi) ⇒ `confirmedAt = nowIso` ⇒ `"learned"`.
  8. sinon (sous K) : ajouter `n` à `isolated` si absent et sous le plafond ⇒ `"isolated"`, sinon `"counted"`.
- **`recordHtml`** : `key === null` ⇒ `"none"`. Entrée absente ⇒ créer avec `sawHtml: true`, `"none"`. Entrée présente et `!sawHtml` et (`isKeyBlocking(entry)` ou probation non résolue) ⇒ `sawHtml = true`, probation (si présente) `resolved = true`, `probeUrl = null` ⇒ `"released"`. Sinon `sawHtml = true` ⇒ `"none"`.
- **`recordProbeFailure`** : vrai seulement si l'entrée de `key` a une probation non résolue dont `probeUrl === n` : `probeUrl = null` ; si `admitted >= probes` ⇒ `resolved = true`, `confirmed = true` (épuisée sans signal : bloque et reste persistée, spec § 3.3). Sinon `false`, rien ne change.
- **`decide`**, dans cet ordre :
  1. `isExempt(n)` ⇒ `"allow"`.
  2. `loadedIsolated.has(n)` ⇒ `"block"`.
  3. `key === null`, entrée absente, ou `entry.sawHtml` ⇒ `"allow"`.
  4. probation non résolue : `probeUrl === n` ⇒ `"probe"` (retry de la même sonde) ; `probeUrl !== null` ⇒ `"block"` ; `admitted < probes` ⇒ `admitted++`, `probeUrl = n`, `"probe"` ; sinon `resolved = true`, `confirmed = true`, `"block"`.
  5. `isKeyBlocking(entry)` ⇒ `"block"` ; sinon `"allow"`.

### C2 — `crawler/src/nonHtmlPrefixSidecar.ts` (T2 produit ; T3, T4 consomment)

```ts
export const NONHTML_PREFIX_SIDECAR = "__nonhtml_prefixes.json";
export const NONHTML_SIDECAR_VERSION = 1;
export interface SidecarData { prefixes: Map<string, { nonHtml: number; confirmedAt: string | null }>; urls: string[]; }
export function serializeNonHtmlPrefixState(state: NonHtmlPrefixState): string;
export function parseNonHtmlPrefixSidecar(raw: string | null): SidecarData;
export function loadSidecarInto(state: NonHtmlPrefixState, data: SidecarData, origin: "current" | "previous"): number;
export function currentSidecarPath(domain: string): string;
export function resolvePreviousSidecarPath(previousId: string, domain: string, cwd?: string): string | null;
export function readSidecarFile(file: string | null): string | null;
export function writeSidecarFile(file: string, text: string): void;
```

- **Format à l'octet** : `JSON.stringify({ version: 1, prefixes: { "<key>": { nonHtml, confirmedAt } }, urls: [ … ] })`, sans indentation, sans newline final. `prefixes` = entrées `!sawHtml && (isKeyBlocking(entry) || (probation !== null && !probation.resolved))`, ordre d'insertion de la Map. `urls` = `isolated` puis `loadedIsolated` (sans doublon), tronqué à `params.isolatedMax`.
- **Parse tolérant** : `null`, JSON invalide, non-objet, `version !== 1` ⇒ `{ prefixes: new Map(), urls: [] }`. Entrée de `prefixes` dont `nonHtml` n'est pas un entier ≥ 0 ⇒ ignorée ; `confirmedAt` non-string ⇒ `null` ; `urls` : seules les strings non vides.
- **`loadSidecarInto`** : clé déjà présente dans `state.prefixes` ⇒ sautée. `"current"` ⇒ `{ nonHtml, sawHtml: false, confirmed: true, confirmedAt, probation: null }`. `"previous"` ⇒ `{ nonHtml, sawHtml: false, confirmed: false, confirmedAt, probation: { admitted: 0, probeUrl: null, resolved: false } }`. `urls` ⇒ `loadedIsolated.add(normalizeUrlIdentity(u))` tant que `size < isolatedMax`. Rend le nombre de clés ajoutées. **Ordre d'appel imposé à T4 : `"current"` d'abord** (une clé confirmée par le crawl en cours n'est pas remise en probation par le précédent).
- **Chemins** : `currentSidecarPath(domain)` = `` `storage/datasets/${domain}/${NONHTML_PREFIX_SIDECAR}` `` (relatif, cwd = storagePath, F8). `resolvePreviousSidecarPath` = premier fichier existant parmi `path.resolve(cwd, '..', previousId, 'storage', 'datasets', domain, SIDECAR)` puis la même avec `domain.replace(/\./g, '-')` (F18) ; sinon `null`. `cwd` défaut `process.cwd()`.
- **I/O** : `readSidecarFile(null)` ⇒ `null` ; absent ou erreur ⇒ `null`. `writeSidecarFile` : `fs.mkdirSync(path.dirname(file), { recursive: true })`, `tmp = \`${file}.tmp\``, `writeFileSync(tmp, text)`, `renameSync(tmp, file)` ; toute exception ⇒ `console.warn(\`[nonhtml-prefix] sidecar write failed: ${(e as Error).message}\`)`, jamais relancée. Le nom tmp `__nonhtml_prefixes.json.tmp` commence par `__` et ne finit pas par `.json` (invisible à F18 et à `_count_files_in_dir`).

### C3 — `crawler/src/nonHtmlPrefixGate.ts` (T3 produit ; T4, T5, T6 consomment)

```ts
export type GatePoint = "enqueue" | "prenav" | "seed";
export interface NonHtmlPrefixGateDeps {
  mode: "shadow" | "on";
  state: NonHtmlPrefixState;
  log: (message: string) => void;
  persist: (serialized: string) => void;
  now?: () => string; // défaut () => new Date().toISOString()
}
export class NonHtmlPrefixGate {
  readonly mode: "shadow" | "on";
  readonly state: NonHtmlPrefixState;
  constructor(deps: NonHtmlPrefixGateDeps);
  addExempt(url: string): void;     // stocke normalizeUrlIdentity(url) dans un Set privé
  exemptCount(): number;
  check(url: string, point: GatePoint): boolean; // true = laisser passer
  onNonHtml(url: string): void;
  onHtml(url: string): void;
  onProbeFailure(url: string): void;
}
```

`check` appelle `decide(state, url, n => exempt.has(n))` : `"allow"` ⇒ `true`, sans log ; `"probe"` ⇒ log `` `[nonhtml-prefix] probe (${point}): ${url} [${key}]` ``, `true` ; `"block"` ⇒ mode `on` : log `` `[nonhtml-prefix] blocked (${point}): ${url} [${key}]` ``, `false` ; mode `shadow` : log `` `[nonhtml-prefix] would block (${point}): ${url} [${key}]` ``, `true`. (`key` = `prefixKey(url)`, `null` imprimé tel quel pour une isolée.) `check` est **synchrone** (F4). `check` n'incrémente aucun compteur : c'est l'appelant (C6).

`onNonHtml` : `recordNonHtml(state, url, now())` ; `"learned"` ⇒ log `` `Non-HTML prefix learned: ${key} (n=${entry.nonHtml})` `` (texte exigé par la spec § 3.2) + `persist(serializeNonHtmlPrefixState(state))` ; `"confirmed"` ⇒ log `` `Non-HTML prefix confirmed by probe: ${key} (n=${entry.nonHtml})` `` + persist ; `"isolated"` ⇒ persist sans log ; autres ⇒ rien. `onHtml` : `"released"` ⇒ log `` `Non-HTML prefix released: ${key} (n=${entry.nonHtml})` `` + persist (signal faux positif de la phase `shadow`). `onProbeFailure` : `true` ⇒ log `` `[nonhtml-prefix] probe failed: ${url} [${key}]` ``, sans persist.

### C4 — `context.ts` (T3)

Insérer juste après la ligne `facetVariantCount: new Map<string, Set<string>>(),` (F15) :
`    // R23 (2): non-HTML prefix learning gate. null when NONHTML_PREFIX_MODE=off (default) — zero effect.`
`    nonHtmlPrefix: null as NonHtmlPrefixGate | null,`
et `import type { NonHtmlPrefixGate } from "./nonHtmlPrefixGate.js";` en tête (forme des imports existants à suivre).

### C5 — Points de câblage (T4, T5, T6 produisent ; T7 vérifie le texte)

| Point | Fichier, ancre (contenu) | Code inséré (littéraux exigés) |
|---|---|---|
| Init | `main.ts`, juste après `ensureUnjudgedSidecar(domain);` (F8) | bloc C8 |
| Exemption dataset | `main.ts`, boucle F10, juste avant `remainingUrls.push(` | `if (source === 'dataset') context.nonHtmlPrefix?.addExempt(consolidatedUrl);` ; après la boucle : log `` `[nonhtml-prefix] exempt URLs: ${context.nonHtmlPrefix.exemptCount()}` `` si gate |
| b2 | `main.ts` seedPhase2, juste avant `// Épinglage de l'identité de file, comme Phase 1 (:952)` (F12) | `if (source === 'dataset') context.nonHtmlPrefix.addExempt(seedUrl);` puis `if (!context.nonHtmlPrefix.check(seedUrl, "seed")) { skippedNonHtmlCount++; …increment("filtered_nonhtml")…; continue; }`, sous `if (context.nonHtmlPrefix) {` ; `let skippedNonHtmlCount = 0;` après `let skippedExtCount = 0;` ; log `` `[seed-filter] skipped ${skippedNonHtmlCount} non-HTML-prefix baseline URL(s) (filtered_nonhtml)` `` après le log `filtered_ext` si > 0 |
| Apprendre non-HTML | `routes.ts`, juste avant `log.warning(\`Skipping non-HTML response:` (F1) | `context.nonHtmlPrefix?.onNonHtml(request.url);` |
| Apprendre HTML | `routes.ts`, juste avant `// --- Circuit Breaker Check (Dual-Mode) ---` (F2) | `if (response) context.nonHtmlPrefix?.onHtml(request.url);` — garde `if (response)` obligatoire : `:447` est atteint par une réponse `ok` (`:399-443` lève sur toute autre classe) **et** par `response` falsy (`:396` `if (response) {` fermé `:445`, paramètre optionnel `:215`) ; sans garde, l'absence de réponse poserait le veto `sawHtml` sans signal de contenu (trou signalé par le rédacteur T5, vérifié par le contrôleur) |
| b1 | `routes.ts`, juste après la fin du bloc facet cap (F3), avant `// Queue-purge #2: filter-on-seen-base` | `if (context.nonHtmlPrefix && !context.nonHtmlPrefix.check(request.url, "enqueue")) { logBlocked('nonhtml-prefix', request.url); if (context.statsManager) void context.statsManager.increment("filtered_nonhtml").catch(() => {}); return false; }` — T5 vérifie la signature de `logBlocked` (type du 1ᵉʳ argument) et l'adapte si c'est une union |
| b3 | `functions.ts`, **nouveau hook** inséré juste après la fermeture du hook facet cap (F5) dans `preNavigationHooks` | `async ({ request }) => { if (context.nonHtmlPrefix && !context.nonHtmlPrefix.check(request.url, "prenav")) { if (context.statsManager) await context.statsManager.increment("filtered_nonhtml"); throw new StaleVariantSkip(request.url, request.url); } },` |
| Échec de sonde | `functions.ts` `failedRequestHandler`, juste après la fermeture de la branche `STALE_VARIANT_SKIP_MARKER` (F6), avant `log.error(\`Request ${request.url} failed:` | `context.nonHtmlPrefix?.onProbeFailure(request.url);` |
| `readStat` | `main.ts`, juste après `const filtered_ext = await readStat("filtered_ext");` (F13) | `const filtered_nonhtml = await readStat("filtered_nonhtml");` |
| Payload | `main.ts`, juste après la ligne `        filtered_ext,` du payload (F13) | `        ...(context.nonHtmlPrefix ? { filtered_nonhtml } : {}),` |

**Décision du contrat là où la spec se tait (à signaler à l'user au rapport final)** : la spec ne nomme aucun point où « timeout ou erreur » d'une sonde est constaté. Choix : `failedRequestHandler` (terminal), donc après les tentatives plafonnées par R23 (1) (≤ 3 × 90 s), et une page HTML non-`ok` (404) compte comme échec de sonde, cohérent avec § 3.2 « une page 404 HTML ne libère rien ». Frontière acceptée : une sonde admise qui ne finit jamais (doublon dédupliqué par Crawlee, retour anticipé du handler) laisse la clé bloquée pour le reste du crawl — même effet que « aucun signal », persistée en probation.

**Décision du contrat (identité en b2)** : la spec § 3.2 place b2 « juste après `hasIgnoredExtensionForSeed` » mais impose l'identité `request.url`. En b2, la chaîne enfilée est `seedUrl` (après `stripActionAnchor` et `processUrl`), donc le contrôle se place juste avant l'`addRequest`, et une URL `source === 'dataset'` y ajoute aussi `seedUrl` à l'exemption (sinon b3 la testerait sous une forme absente du Set).

### C6 — Compteur `filtered_nonhtml`

Nom exact `filtered_nonhtml`. Incrémenté **seulement quand un blocage est effectif** (mode `on`, `check` ⇒ `false`) : `routes.ts` b1 (`void … .catch(() => {})`, synchrone), `functions.ts` b3 (`await`), `main.ts` b2 (`await`). En `shadow` : jamais (rien n'est filtré ; la mesure se lit dans les logs `would block`). Lu par `readStat("filtered_nonhtml")` (`main.ts`), posé par spread conditionnel (C5). Un blocage b3 compte aussi `purged_prenav` (F6) — recouvrement voulu (spec § 3.2), `failed` reste juste (F14).

### C7 — Mode `off`

`context.nonHtmlPrefix === null` ⇒ chaque point C5 est un no-op (`?.` ou garde `if (context.nonHtmlPrefix)`), le payload n'a pas la clé, aucun sidecar n'est lu ni écrit.

### C8 — Bloc d'init (`main.ts`, T4)

```ts
// R23 (2): non-HTML prefix learning. Loaded AFTER the dropData block (a clean restart dropped
// this crawl's dataset dir, sidecar included; an OOM relaunch keeps it). Previous crawl's
// sidecar (update mode) enters probation. Absent file = empty state; nothing created at startup.
const nonHtmlPrefixMode = resolveNonHtmlPrefixMode(process.env.NONHTML_PREFIX_MODE);
if (nonHtmlPrefixMode !== "off") {
    const nonHtmlState = createNonHtmlPrefixState(resolveNonHtmlPrefixParams(process.env));
    const nonHtmlSidecarFile = currentSidecarPath(domain);
    const fromCurrent = loadSidecarInto(nonHtmlState, parseNonHtmlPrefixSidecar(readSidecarFile(nonHtmlSidecarFile)), "current");
    const fromPrevious = (crawlMode === 'update' && previousCrawlId)
        ? loadSidecarInto(nonHtmlState, parseNonHtmlPrefixSidecar(readSidecarFile(resolvePreviousSidecarPath(previousCrawlId, domain))), "previous")
        : 0;
    context.nonHtmlPrefix = new NonHtmlPrefixGate({
        mode: nonHtmlPrefixMode,
        state: nonHtmlState,
        log: (m) => console.log(m),
        persist: (text) => writeSidecarFile(nonHtmlSidecarFile, text),
    });
    context.nonHtmlPrefix.addExempt(site);
    console.log(`[nonhtml-prefix] mode=${nonHtmlPrefixMode} K=${nonHtmlState.params.minNonHtml} probes=${nonHtmlState.params.probes} loaded current=${fromCurrent} previous=${fromPrevious} isolated=${nonHtmlState.loadedIsolated.size}`);
}
```

T4 vérifie que `domain` est une `string` à ce point (sinon garde `if (domain)` comme `ensureUnjudgedSidecar`).

## Table producteurs / consommateurs

| Artefact | Producteur | Consommateurs | Format |
|---|---|---|---|
| API C1 | T1 | T2, T3, T9 | signatures C1, exportées nommément |
| API C2 | T2 | T3 (`serializeNonHtmlPrefixState`), T4 (le reste) | signatures C2 |
| API C3 + champ C4 | T3 | T4, T5, T6 | signatures C3 ; `context.nonHtmlPrefix` |
| Littéraux C5/C6 dans le source | T4, T5, T6 | T7 (assertions texte) | chaînes exactes de la table C5 : `check(request.url, "enqueue")`, `check(request.url, "prenav")`, `check(seedUrl, "seed")`, `onNonHtml(request.url)`, `onHtml(request.url)`, `onProbeFailure(request.url)`, `increment("filtered_nonhtml")`, `readStat("filtered_nonhtml")`, `{ filtered_nonhtml }` |
| `__nonhtml_prefixes.json` | T3/T4 au runtime | crawl suivant (T4), T10 (doc) | C2 |
| Kind `pdf` de `GET /admin/dataset` | T8 | T9 (CLI lit un export de cet endpoint) | forme de réponse de l'endpoint existant, lue par T8 et recopiée dans sa section ; T9 lit la section T8 ou `admin.py` |
| Log `[nonhtml-prefix] would block (` / `Non-HTML prefix released:` | T3 | phase `shadow` (registre, T10 doc) | C3 |
| Message de commit | chaque tâche | — | `<scratchpad>/commit-T<nn>.txt`, `git -C <WT> commit -F <ce fichier>` |

## Pilote

Mécanisme de confinement : la variable d'environnement `NONHTML_PREFIX_MODE`, lue par le processus Node du crawl. **Elle est globale à la VM (tous les domaines), aucun mécanisme par domaine n'existe ni n'est créé.** T10 documente comment elle atteint le conteneur (à lire dans `docker-compose.yml`, service crawler, `env_file`/`environment`) et T8 l'expose dans `GET /admin/config` (whitelist `NONHTML_`) pour qu'on vérifie le mode sur la VM sans shell.

## Phases d'exécution

1. Ce plan (T1-T10) : local, gratuit, commits dans le worktree, aucun déploiement.
2. Hors plan, au registre R23 [contrôleur T10] : merge `features/poc` → push → rebuild crawler-service (mode `off`) ; VM en `shadow` sur quelques MAJ (compter `would block` et `released`) ; rejeu K (T9) sur des exports `pdf` + `main` ; puis `on` ; preuve d'effet spec § 6 (0 `Navigation timed out` sur `/image/` une fois la clé chargée ou apprise, `filtered_nonhtml` > 0).

## Couverture de la spec (paire exigence → tâche)

| Spec | Exigence | Tâche |
|---|---|---|
| § 3.1 | `prefixKey` (racine ⇒ null, requête/fragment ignorés) | T1 |
| § 3.1 | état par clé ; `recordNonHtml` (seule URL sans extension ignorée ; isolées plafonnées) ; `recordHtml` (veto) ; `decide` (allow/block/probe) | T1 |
| § 3.1 | `serialize` / `parse` tolérant (absent, corrompu, version inconnue) | T2 |
| § 3.1, § 4 | mode appliqué par l'appelant, `would block` en shadow | T3 |
| § 3.2 | apprendre non-HTML, apprendre HTML (seule classe `ok`) | T5 |
| § 3.2 | b1 | T5 ; b3 + recouvrement `purged_prenav` | T6 ; b2 | T4 |
| § 3.2 | charger current + previous (résolution domaine / sanitisé) | T2 (chemins), T4 (appel) |
| § 3.2 | persister à chaque clé apprise/confirmée/URL isolée | T3 |
| § 3.2 | compteur `filtered_nonhtml` (3 incréments, `readStat`, payload) | T4, T5, T6 ; parité T7 |
| § 3.3 | automate de sonde (non-HTML / HTML / timeout ×3) | T1 ; point d'échec T6 ; persistance T2 |
| § 3.4 | emplacement, tmp+rename, `dropData`, pas de création au démarrage | T2, T4 |
| § 3.4 | invisibilité aux lecteurs du dossier dataset | T2 (nom `__…`, tmp non `.json`), T10 (doc) — aucun lecteur modifié |
| § 4 | 3 modes, valeur inconnue ⇒ off ; K/PROBES/ISOLATED_MAX ; vide ≠ 0 | T1 |
| § 4 | déploiement en 3 temps | hors plan : registre (T10 [contrôleur]) |
| § 5 | exemption absolue dataset précédent, au `/` près, Set synchrone avant le crawler | T1 (normalize), T3 (`addExempt`), T4 (remplissage, F11) |
| § 5 | `previousTotal` non affecté | T4 (aucune URL dataset écartée — constat, pas de code) |
| § 6 | `nonHtmlPrefix.test.ts` neuf (+ `nonHtmlPrefixSidecar.test.ts` pour le parse tolérant) | T1, T2 |
| § 6 | un test par point de blocage | T3 (gate × point × mode) + T7 (placement texte) |
| § 6 | parité du compteur | T7 |
| § 6 | caractérisation 509/509 en off sans modification | T7 (et T10 final) |
| § 6 | prérequis rejeu : `"pdf": "pdf-"` | T8 ; instrument de rejeu | T9 ; exécution du rejeu : hors plan (registre) |
| § 6 | preuve d'effet après déploiement | hors plan : registre (T10 [contrôleur]) |
| § 7 | persistance BO de `filtered_nonhtml`, exemption élargie | hors plan (spec § 7) |
| contrat | homepage exemptée (`addExempt(site)`) | T4 |
| contrat | whitelist `NONHTML_` de `/admin/config` | T8 |

## Tâches

| N° | Nom | Fichiers | Dépend de |
|---|---|---|---|
| 1 | Module pur de décision | `crawler/src/nonHtmlPrefix.ts`, `.test.ts` | — |
| 2 | Sidecar : sérialisation, parse, chemins, I/O | `crawler/src/nonHtmlPrefixSidecar.ts`, `.test.ts` | T1 |
| 3 | Gate + champ de contexte | `crawler/src/nonHtmlPrefixGate.ts`, `.test.ts`, `crawler/src/context.ts` | T1, T2 |
| 4 | Câblage `main.ts` (init, exemption, b2, compteur) | `crawler/src/main.ts` | T3 |
| 5 | Câblage `routes.ts` (apprentissages, b1) | `crawler/src/routes.ts` | T3 |
| 6 | Câblage `functions.ts` (b3, échec de sonde) | `crawler/src/functions.ts` | T3 |
| 7 | Parité texte-source + suite complète | `crawler/src/nonHtmlPrefixWiring.test.ts` | T4, T5, T6 |
| 8 | admin.py : kind `pdf` + whitelist `NONHTML_` | `app/router/admin.py`, `tests/test_admin_nonhtml_prefix.py` | — |
| 9 | Instrument de rejeu K | `crawler/src/tools/nonHtmlPrefixReplay.ts`, `.test.ts` | T1, T8 (forme de l'export) |
| 10 | Documentation + vérification finale + registre | `CLAUDE.md` (crawler-service) | T1-T9 |

Chaque tâche finit par : suite ciblée verte, puis `cd <CR> && npm test 2>&1 | tail -12` (attendu : `ℹ fail 0`, `ℹ pass` = 509 + tests neufs cumulés), puis commit de ses seuls fichiers. T8 lance en plus pytest (commande mesurée dans sa section).
