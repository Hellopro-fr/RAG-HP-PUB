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
### Task 1: Module pur de décision
> NOMS NEUFS : NonHtmlPrefixMode, resolveNonHtmlPrefixMode, resolvePositiveInt, NonHtmlPrefixParams, NONHTML_PREFIX_DEFAULTS, resolveNonHtmlPrefixParams, normalizeUrlIdentity, prefixKey, Probation, PrefixEntry, NonHtmlPrefixState, createNonHtmlPrefixState, isKeyBlocking, NonHtmlEvent, recordNonHtml, HtmlEvent, recordHtml, recordProbeFailure, NonHtmlDecision, decide (produit) ⇒ T1

**Goal:** Écrire le module pur `nonHtmlPrefix.ts` (modes, paramètres, clé de préfixe, état, `recordNonHtml` / `recordHtml` / `recordProbeFailure` / `decide`) à l'identique du contrat C1 de l'index, et tester chaque branche numérotée.

**Files:**
- Create: `apps-microservices/crawler-service/crawler/src/nonHtmlPrefix.ts`
- Test: `apps-microservices/crawler-service/crawler/src/nonHtmlPrefix.test.ts`

**Acceptance Criteria:**
- [ ] `nonHtmlPrefix.ts` exporte exactement les 20 identifiants de la ligne NOMS NEUFS (types compris), avec les signatures du contrat C1 ; son seul import runtime est `hasIgnoredExtensionForSeed` (`./seedExtensionFilter.js`) plus `posix` de `node:path` ; aucun `process.env`, aucun `fs`.
- [ ] `resolveNonHtmlPrefixMode` : `shadow` / `on` (trim + minuscules) tels quels, tout le reste (`undefined`, `""`, inconnu) ⇒ `off`.
- [ ] `resolvePositiveInt` retombe sur le repli pour `undefined`, `""`, `"abc"`, `"0"`, `"-1"`, `"2.5"` (jamais 0 pour une variable vide).
- [ ] `recordNonHtml` branches 1 à 8, `recordHtml` (4 cas), `recordProbeFailure` (vrai/faux), `decide` branches 1 à 5 : chacune a au moins un test nommé d'après son numéro.
- [ ] `node --import tsx --test src/nonHtmlPrefix.test.ts` : `ℹ fail 0`, `ℹ pass` = nombre de `test(` du fichier (compté Step 4).
- [ ] Suite complète : `ℹ fail 0` et `ℹ pass` = 509 + ce nombre ; aucun fichier existant modifié (`git -C <WT> diff --cached --stat` = 2 fichiers).
- [ ] `npx tsc --noEmit` ne signale aucune erreur dans `nonHtmlPrefix*.ts` (les tests sont dans `include` de `tsconfig.json`).

**Verify:** `cd <CR> && node --import tsx --test src/nonHtmlPrefix.test.ts`

**Steps:**

- [ ] **Step 0: Préconditions d'environnement (une fois, première tâche du plan)**

`<CR>` = `<WT>/apps-microservices/crawler-service/crawler`. Chaque commande dans son propre appel.

1. Dépendances. Attendu `present`; sinon appliquer la recette (3 min environ) :

```bash
test -d <CR>/node_modules && echo present || echo absent
```

Si `absent` (le lockfile est gitignoré, `.gitignore:164`, donc absent d'un worktree neuf) :

```bash
cp <MAIN>/apps-microservices/crawler-service/crawler/package-lock.json <CR>/package-lock.json
cmp <MAIN>/apps-microservices/crawler-service/crawler/package-lock.json <CR>/package-lock.json && echo identical
cd <CR> && npm ci --ignore-scripts --no-audit --no-fund 2>&1 | tail -5
```

Attendu : `identical`, puis un résumé npm sans erreur (377 paquets mesurés le 2026-10-16).

2. Aucun des 16 chemins du plan n'est ignoré par git. Une seule commande git (liste d'arguments), puis le code retour imprimé par une commande qui n'est pas git :

```bash
git -C <WT> check-ignore -v --no-index apps-microservices/crawler-service/crawler/src/nonHtmlPrefix.ts apps-microservices/crawler-service/crawler/src/nonHtmlPrefix.test.ts apps-microservices/crawler-service/crawler/src/nonHtmlPrefixSidecar.ts apps-microservices/crawler-service/crawler/src/nonHtmlPrefixSidecar.test.ts apps-microservices/crawler-service/crawler/src/nonHtmlPrefixGate.ts apps-microservices/crawler-service/crawler/src/nonHtmlPrefixGate.test.ts apps-microservices/crawler-service/crawler/src/context.ts apps-microservices/crawler-service/crawler/src/main.ts apps-microservices/crawler-service/crawler/src/routes.ts apps-microservices/crawler-service/crawler/src/functions.ts apps-microservices/crawler-service/crawler/src/nonHtmlPrefixWiring.test.ts apps-microservices/crawler-service/app/router/admin.py apps-microservices/crawler-service/tests/test_admin_nonhtml_prefix.py apps-microservices/crawler-service/crawler/src/tools/nonHtmlPrefixReplay.ts apps-microservices/crawler-service/crawler/src/tools/nonHtmlPrefixReplay.test.ts apps-microservices/crawler-service/CLAUDE.md; echo "check-ignore rc=$?"
```

Attendu : aucune ligne de chemin, puis `check-ignore rc=1` (1 = aucun chemin ignoré). Un `rc=0` ou une ligne `.gitignore:N:…` ⇒ STOP, rapporter le chemin et la règle.

3. Oracle de départ (≈ 50 s) :

```bash
cd <CR> && npm test 2>&1 | tail -12
```

Attendu : `ℹ tests 509`, `ℹ pass 509`, `ℹ fail 0`. Autre valeur ⇒ STOP (la base a bougé : noter la valeur mesurée `<BASE>` et l'utiliser à la place de 509 dans les attendus de cette tâche).

- [ ] **Step 1: Écrire le test qui échoue**

Créer `apps-microservices/crawler-service/crawler/src/nonHtmlPrefix.test.ts` (forme de `facetCap.test.ts` : `node:test`, `assert/strict`, imports en `.js`). Paramètres de test fixés : `K = 3`, `probes = 2`, `isolatedMax = 2`. Aucune URL de test n'a de point dans son chemin (sinon `hasIgnoredExtensionForSeed` lirait une extension).

```ts
// apps-microservices/crawler-service/crawler/src/nonHtmlPrefix.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import {
    NONHTML_PREFIX_DEFAULTS,
    createNonHtmlPrefixState,
    decide,
    isKeyBlocking,
    normalizeUrlIdentity,
    prefixKey,
    recordHtml,
    recordNonHtml,
    recordProbeFailure,
    resolveNonHtmlPrefixMode,
    resolveNonHtmlPrefixParams,
    resolvePositiveInt,
    type NonHtmlPrefixParams,
    type NonHtmlPrefixState,
    type PrefixEntry,
    type Probation,
} from "./nonHtmlPrefix.js";

const P: NonHtmlPrefixParams = { minNonHtml: 3, probes: 2, isolatedMax: 2 };
const NOW = "2026-10-16T10:00:00.000Z";
const LATER = "2026-10-16T11:00:00.000Z";
const KEY = "h.fr/image";

/** A no-extension URL under the key `h.fr/image`. */
const img = (i: number): string => `https://h.fr/image/p${i}`;
/** A key-less URL (parent directory is the root). */
const bare = (i: number): string => `https://h.fr/telechargement?id=${i}`;

const fresh = (): NonHtmlPrefixState => createNonHtmlPrefixState({ ...P });
const entry = (over: Partial<PrefixEntry> = {}): PrefixEntry => ({
    nonHtml: 0,
    sawHtml: false,
    confirmed: false,
    confirmedAt: null,
    probation: null,
    ...over,
});
const probation = (over: Partial<Probation> = {}): Probation => ({
    admitted: 0,
    probeUrl: null,
    resolved: false,
    ...over,
});
const withEntry = (e: PrefixEntry): NonHtmlPrefixState => {
    const s = fresh();
    s.prefixes.set(KEY, e);
    return s;
};
const probing = (p: Partial<Probation>): NonHtmlPrefixState =>
    withEntry(entry({ nonHtml: 5, probation: probation(p) }));
const got = (s: NonHtmlPrefixState, key: string = KEY): PrefixEntry => {
    const e = s.prefixes.get(key);
    assert.ok(e, `no entry for ${key}`);
    return e;
};
const never = (): boolean => false;

// ---------------------------------------------------------------- modes and numbers

test("resolveNonHtmlPrefixMode: shadow and on pass through, trimmed and case-folded", () => {
    assert.equal(resolveNonHtmlPrefixMode("shadow"), "shadow");
    assert.equal(resolveNonHtmlPrefixMode("on"), "on");
    assert.equal(resolveNonHtmlPrefixMode("  ON "), "on");
    assert.equal(resolveNonHtmlPrefixMode("Shadow"), "shadow");
});

test("resolveNonHtmlPrefixMode: undefined, empty, off and unknown values are off", () => {
    for (const raw of [undefined, "", "   ", "off", "true", "1", "enabled", "shadow2"]) {
        assert.equal(resolveNonHtmlPrefixMode(raw), "off", `raw=${JSON.stringify(raw)}`);
    }
});

test("resolvePositiveInt: a positive integer string is parsed (trimmed)", () => {
    assert.equal(resolvePositiveInt("5", 9), 5);
    assert.equal(resolvePositiveInt(" 12 ", 9), 12);
    assert.equal(resolvePositiveInt("007", 9), 7);
});

test("resolvePositiveInt: undefined, empty, non-integer and non-positive fall back (empty is never 0)", () => {
    for (const raw of [undefined, "", "abc", "0", "-1", "2.5", "   ", "1e3", "00"]) {
        assert.equal(resolvePositiveInt(raw, 9), 9, `raw=${JSON.stringify(raw)}`);
    }
});

test("resolveNonHtmlPrefixParams: no variable gives the defaults, as a fresh object", () => {
    assert.deepEqual(NONHTML_PREFIX_DEFAULTS, { minNonHtml: 5, probes: 3, isolatedMax: 10000 });
    const r = resolveNonHtmlPrefixParams({});
    assert.deepEqual(r, NONHTML_PREFIX_DEFAULTS);
    assert.notEqual(r, NONHTML_PREFIX_DEFAULTS, "never the shared defaults object");
});

test("resolveNonHtmlPrefixParams: each variable feeds its own field", () => {
    const r = resolveNonHtmlPrefixParams({
        NONHTML_PREFIX_MIN: "8",
        NONHTML_PREFIX_PROBES: "2",
        NONHTML_ISOLATED_MAX: "50",
    });
    assert.deepEqual(r, { minNonHtml: 8, probes: 2, isolatedMax: 50 });
    assert.deepEqual(resolveNonHtmlPrefixParams({ NONHTML_PREFIX_MIN: "8" }), {
        minNonHtml: 8,
        probes: 3,
        isolatedMax: 10000,
    });
});

test("resolveNonHtmlPrefixParams: empty or invalid values keep the defaults, never 0", () => {
    for (const bad of ["", "0", "abc", "-4", "2.5"]) {
        const r = resolveNonHtmlPrefixParams({
            NONHTML_PREFIX_MIN: bad,
            NONHTML_PREFIX_PROBES: bad,
            NONHTML_ISOLATED_MAX: bad,
        });
        assert.deepEqual(r, NONHTML_PREFIX_DEFAULTS, `bad=${JSON.stringify(bad)}`);
    }
});

// ---------------------------------------------------------------- identity and key

test("normalizeUrlIdentity: strips trailing slashes only", () => {
    assert.equal(normalizeUrlIdentity("https://h.fr/a/"), "https://h.fr/a");
    assert.equal(normalizeUrlIdentity("https://h.fr/a///"), "https://h.fr/a");
    assert.equal(normalizeUrlIdentity("https://h.fr/a"), "https://h.fr/a");
    assert.equal(normalizeUrlIdentity("https://h.fr/"), "https://h.fr");
    assert.equal(normalizeUrlIdentity("https://h.fr/a?x=1"), "https://h.fr/a?x=1");
});

test("prefixKey: host + parent directory, query and fragment ignored (index examples)", () => {
    assert.equal(prefixKey("https://www.marsaleix.fr/image/_1AAAB-x?y=1#z"), "www.marsaleix.fr/image");
    assert.equal(prefixKey("https://h.fr/telechargement?id=12"), null);
});

test("prefixKey: root, directory-only, empty and invalid URLs are key-less", () => {
    assert.equal(prefixKey("https://h.fr/"), null);
    assert.equal(prefixKey("https://h.fr"), null);
    assert.equal(prefixKey("https://h.fr/image/"), null, "posix dirname of /image/ is /");
    assert.equal(prefixKey("not a url"), null);
    assert.equal(prefixKey(""), null);
});

test("prefixKey: port and depth kept, scheme and host case ignored", () => {
    assert.equal(prefixKey("https://h.fr:8443/a/b"), "h.fr:8443/a");
    assert.equal(prefixKey("https://h.fr/a/b/c"), "h.fr/a/b");
    assert.equal(prefixKey("http://h.fr/image/x"), prefixKey("https://h.fr/image/x"));
    assert.equal(prefixKey("https://H.FR/image/x"), "h.fr/image");
    assert.notEqual(prefixKey("https://www.h.fr/image/x"), prefixKey("https://h.fr/image/x"));
});

// ---------------------------------------------------------------- state

test("createNonHtmlPrefixState: empty collections, params kept", () => {
    const s = createNonHtmlPrefixState({ ...P });
    assert.deepEqual(s.params, P);
    assert.equal(s.prefixes.size, 0);
    assert.equal(s.isolated.size, 0);
    assert.equal(s.loadedIsolated.size, 0);
});

test("isKeyBlocking: confirmed or K reached, and never once HTML was seen", () => {
    assert.equal(isKeyBlocking(entry({ confirmed: true }), P), true);
    assert.equal(isKeyBlocking(entry({ nonHtml: 3 }), P), true);
    assert.equal(isKeyBlocking(entry({ nonHtml: 2 }), P), false);
    assert.equal(isKeyBlocking(entry({ nonHtml: 9, confirmed: true, sawHtml: true }), P), false);
});

// ---------------------------------------------------------------- recordNonHtml

test("recordNonHtml 1: an ignored-extension URL changes nothing", () => {
    const s = fresh();
    assert.equal(recordNonHtml(s, "https://h.fr/image/p1.jpg", NOW), "ignored");
    assert.equal(recordNonHtml(s, "https://h.fr/telechargement.pdf", NOW), "ignored");
    assert.equal(s.prefixes.size, 0);
    assert.equal(s.isolated.size, 0);
});

test("recordNonHtml 2: a key-less URL is isolated once, deduplicated on identity, capped at isolatedMax", () => {
    const s = fresh();
    assert.equal(recordNonHtml(s, bare(1), NOW), "isolated");
    assert.equal(recordNonHtml(s, bare(1), NOW), "ignored", "duplicate");
    assert.equal(recordNonHtml(s, "https://h.fr/doc", NOW), "isolated");
    assert.equal(recordNonHtml(s, "https://h.fr/doc/", NOW), "ignored", "trailing slash is the same identity");
    assert.equal(recordNonHtml(s, bare(3), NOW), "ignored", "cap of 2 reached");
    assert.deepEqual([...s.isolated], [bare(1), "https://h.fr/doc"]);
    assert.equal(s.prefixes.size, 0);
});

test("recordNonHtml 3: under a key that served HTML the count grows but nothing is learned", () => {
    const s = fresh();
    assert.equal(recordHtml(s, img(0)), "none");
    for (const i of [1, 2, 3, 4]) assert.equal(recordNonHtml(s, img(i), NOW), "counted");
    const e = got(s);
    assert.equal(e.nonHtml, 4);
    assert.equal(e.sawHtml, true);
    assert.equal(e.confirmedAt, null);
    assert.equal(isKeyBlocking(e, s.params), false);
    assert.equal(s.isolated.size, 0);
});

test("recordNonHtml 3/8/7: first hits create the entry and are isolated; the K-th hit learns", () => {
    const s = fresh();
    assert.equal(recordNonHtml(s, img(1), NOW), "isolated");
    assert.deepEqual(got(s), entry({ nonHtml: 1 }));
    assert.equal(recordNonHtml(s, img(2), NOW), "isolated");
    assert.equal(s.isolated.size, 2);
    assert.equal(recordNonHtml(s, img(3), NOW), "learned");
    const e = got(s);
    assert.equal(e.nonHtml, 3);
    assert.equal(e.confirmedAt, NOW);
    assert.equal(e.confirmed, false);
    assert.equal(isKeyBlocking(e, s.params), true);
    assert.equal(s.isolated.size, 2, "the learning hit is not isolated");
});

test("recordNonHtml 8: under K, a hit at the isolated cap or a repeated identity is only counted", () => {
    const s = fresh();
    recordNonHtml(s, bare(1), NOW);
    recordNonHtml(s, bare(2), NOW);
    assert.equal(s.isolated.size, 2);
    assert.equal(recordNonHtml(s, img(1), NOW), "counted", "cap reached");
    assert.equal(s.isolated.size, 2);
    assert.equal(got(s).nonHtml, 1);

    const t = fresh();
    assert.equal(recordNonHtml(t, img(1), NOW), "isolated");
    assert.equal(recordNonHtml(t, `${img(1)}/`, NOW), "counted", "same identity after trailing slash");
    assert.equal(got(t).nonHtml, 2);
    assert.equal(t.isolated.size, 1);
});

test("recordNonHtml 4/6: once blocking, further hits are counted and confirmedAt is kept", () => {
    const s = fresh();
    for (const i of [1, 2, 3]) recordNonHtml(s, img(i), NOW);
    assert.equal(recordNonHtml(s, img(4), LATER), "counted");
    const e = got(s);
    assert.equal(e.nonHtml, 4);
    assert.equal(e.confirmedAt, NOW);
});

test("recordNonHtml 5: any non-HTML under an unresolved probation confirms the key", () => {
    const s = withEntry(entry({ nonHtml: 1, probation: probation({ admitted: 1, probeUrl: img(9) }) }));
    assert.equal(recordNonHtml(s, img(5), NOW), "confirmed", "a URL other than the probe also confirms");
    const e = got(s);
    assert.equal(e.nonHtml, 2);
    assert.equal(e.confirmed, true);
    assert.equal(e.confirmedAt, NOW);
    assert.deepEqual(e.probation, { admitted: 1, probeUrl: null, resolved: true });
});

test("recordNonHtml 5 before 6: a previous-crawl key already at K is still confirmed by the probe", () => {
    const s = withEntry(entry({ nonHtml: 7, confirmedAt: "2026-10-01T00:00:00.000Z", probation: probation() }));
    assert.equal(recordNonHtml(s, img(1), NOW), "confirmed");
    assert.equal(got(s).confirmedAt, NOW);
    assert.equal(got(s).nonHtml, 8);
});

test("recordNonHtml 6: a resolved probation no longer re-confirms", () => {
    const s = withEntry(
        entry({
            nonHtml: 4,
            confirmed: true,
            confirmedAt: NOW,
            probation: probation({ admitted: 3, resolved: true }),
        }),
    );
    assert.equal(recordNonHtml(s, img(1), LATER), "counted");
    assert.equal(got(s).confirmedAt, NOW);
    assert.equal(got(s).nonHtml, 5);
});

test("recordNonHtml: keys are counted independently (host + parent directory)", () => {
    const s = fresh();
    const urls = [
        "https://h.fr/image/a",
        "https://h.fr/image/b",
        "https://h.fr/pdf/a",
        "https://h.fr/pdf/b",
        "https://other.fr/image/a",
        "https://other.fr/image/b",
    ];
    for (const u of urls) assert.notEqual(recordNonHtml(s, u, NOW), "learned");
    assert.deepEqual([...s.prefixes.keys()], ["h.fr/image", "h.fr/pdf", "other.fr/image"]);
    for (const e of s.prefixes.values()) assert.equal(e.nonHtml, 2);
});

// ---------------------------------------------------------------- recordHtml

test("recordHtml: a key-less URL is none and creates nothing", () => {
    const s = fresh();
    assert.equal(recordHtml(s, bare(1)), "none");
    assert.equal(s.prefixes.size, 0);
});

test("recordHtml: an absent key is created with the veto set", () => {
    const s = fresh();
    assert.equal(recordHtml(s, img(1)), "none");
    assert.deepEqual(got(s), entry({ sawHtml: true }));
    assert.equal(recordNonHtml(s, img(2), NOW), "counted", "the veto holds");
});

test("recordHtml: a learned (blocking) key is released", () => {
    const s = fresh();
    for (const i of [1, 2, 3]) recordNonHtml(s, img(i), NOW);
    assert.equal(recordHtml(s, img(7)), "released");
    const e = got(s);
    assert.equal(e.sawHtml, true);
    assert.equal(e.nonHtml, 3);
    assert.equal(isKeyBlocking(e, s.params), false);
    assert.equal(decide(s, img(8), never), "allow");
});

test("recordHtml: a confirmed key under K is released", () => {
    const s = withEntry(entry({ nonHtml: 1, confirmed: true }));
    assert.equal(recordHtml(s, img(1)), "released");
    assert.equal(got(s).sawHtml, true);
});

test("recordHtml: a key under an unresolved probation is released and the probation closed", () => {
    const s = withEntry(entry({ nonHtml: 1, probation: probation({ admitted: 1, probeUrl: img(1) }) }));
    assert.equal(recordHtml(s, img(1)), "released");
    assert.equal(got(s).sawHtml, true);
    assert.deepEqual(got(s).probation, { admitted: 1, probeUrl: null, resolved: true });
});

test("recordHtml: a key under K with no probation only gets the veto", () => {
    const s = withEntry(entry({ nonHtml: 1 }));
    assert.equal(recordHtml(s, img(1)), "none");
    assert.equal(got(s).sawHtml, true);
});

test("recordHtml: a second HTML hit on a vetoed key is none", () => {
    const s = fresh();
    recordHtml(s, img(1));
    assert.equal(recordHtml(s, img(2)), "none");
    assert.equal(got(s).sawHtml, true);
});

// ---------------------------------------------------------------- recordProbeFailure

test("recordProbeFailure: a key-less URL is false", () => {
    const s = probing({ admitted: 1, probeUrl: bare(1) });
    assert.equal(recordProbeFailure(s, bare(1)), false);
});

test("recordProbeFailure: an unknown key is false", () => {
    assert.equal(recordProbeFailure(fresh(), img(1)), false);
});

test("recordProbeFailure: an entry without probation is false and unchanged", () => {
    const s = withEntry(entry({ nonHtml: 5 }));
    assert.equal(recordProbeFailure(s, img(1)), false);
    assert.deepEqual(got(s), entry({ nonHtml: 5 }));
});

test("recordProbeFailure: a resolved probation is false and unchanged", () => {
    const s = probing({ admitted: 3, resolved: true });
    assert.equal(recordProbeFailure(s, img(1)), false);
    assert.deepEqual(got(s).probation, { admitted: 3, probeUrl: null, resolved: true });
    assert.equal(got(s).confirmed, false);
});

test("recordProbeFailure: a URL other than the in-flight probe is false and unchanged", () => {
    const s = probing({ admitted: 1, probeUrl: img(1) });
    assert.equal(recordProbeFailure(s, img(2)), false);
    assert.deepEqual(got(s).probation, { admitted: 1, probeUrl: img(1), resolved: false });
});

test("recordProbeFailure: the probe failing with admissions left frees the slot, key still in probation", () => {
    const s = probing({ admitted: 1, probeUrl: img(1) });
    assert.equal(recordProbeFailure(s, img(1)), true);
    assert.deepEqual(got(s).probation, { admitted: 1, probeUrl: null, resolved: false });
    assert.equal(got(s).confirmed, false);
});

test("recordProbeFailure: the last admitted probe failing resolves the probation as confirmed", () => {
    const s = probing({ admitted: 2, probeUrl: img(1) });
    assert.equal(recordProbeFailure(s, img(1)), true);
    assert.deepEqual(got(s).probation, { admitted: 2, probeUrl: null, resolved: true });
    assert.equal(got(s).confirmed, true);
    assert.equal(isKeyBlocking(got(s), s.params), true);
});

test("recordProbeFailure: the failed URL is matched on normalized identity", () => {
    const s = probing({ admitted: 1, probeUrl: img(1) });
    assert.equal(recordProbeFailure(s, `${img(1)}/`), true);
    assert.equal(got(s).probation?.probeUrl, null);
});

// ---------------------------------------------------------------- decide

test("decide 1: an exempt URL is allowed even if blocked elsewhere; the predicate sees the normalized identity", () => {
    const s = withEntry(entry({ nonHtml: 9, confirmed: true }));
    s.loadedIsolated.add(img(1));
    const seen: string[] = [];
    const r = decide(s, `${img(1)}/`, (n) => {
        seen.push(n);
        return true;
    });
    assert.equal(r, "allow");
    assert.deepEqual(seen, [img(1)]);
});

test("decide 2: a loadedIsolated URL is blocked before its key is looked at", () => {
    const s = withEntry(entry({ sawHtml: true, nonHtml: 1 }));
    s.loadedIsolated.add(img(1));
    s.loadedIsolated.add(bare(1));
    assert.equal(decide(s, img(1), never), "block");
    assert.equal(decide(s, `${img(1)}/`, never), "block");
    assert.equal(decide(s, bare(1), never), "block");
    assert.equal(decide(s, img(2), never), "allow", "same key, vetoed, not isolated");
});

test("decide 3: key-less, unknown key and HTML-vetoed key are allowed", () => {
    const s = withEntry(entry({ sawHtml: true, confirmed: true, nonHtml: 9 }));
    assert.equal(decide(s, bare(1), never), "allow");
    assert.equal(decide(s, "https://h.fr/other/x", never), "allow");
    assert.equal(decide(s, img(1), never), "allow");
});

test("decide 4a: the in-flight probe URL is probed again (retry of the same probe)", () => {
    const s = withEntry(entry({ nonHtml: 6, probation: probation({ admitted: 1, probeUrl: img(1) }) }));
    assert.equal(decide(s, `${img(1)}/`, never), "probe");
    assert.deepEqual(got(s).probation, { admitted: 1, probeUrl: img(1), resolved: false });
});

test("decide 4b: another URL while a probe is in flight is blocked, nothing changes", () => {
    const s = withEntry(entry({ nonHtml: 6, probation: probation({ admitted: 1, probeUrl: img(1) }) }));
    assert.equal(decide(s, img(2), never), "block");
    assert.deepEqual(got(s).probation, { admitted: 1, probeUrl: img(1), resolved: false });
});

test("decide 4c: with no probe in flight and admissions left, the URL becomes the probe", () => {
    const s = withEntry(entry({ nonHtml: 6, probation: probation({ admitted: 1 }) }));
    assert.equal(decide(s, img(2), never), "probe");
    assert.deepEqual(got(s).probation, { admitted: 2, probeUrl: img(2), resolved: false });
    assert.equal(decide(s, img(3), never), "block", "a probe is now in flight");
});

test("decide 4d: with admissions exhausted and no probe, the probation resolves as confirmed and blocks", () => {
    const s = withEntry(entry({ nonHtml: 6, probation: probation({ admitted: 2 }) }));
    assert.equal(decide(s, img(3), never), "block");
    assert.deepEqual(got(s).probation, { admitted: 2, probeUrl: null, resolved: true });
    assert.equal(got(s).confirmed, true);
    assert.equal(decide(s, img(4), never), "block");
});

test("decide 4: two probes timing out in turn leave the key blocking (spec 3.3, exhausted without signal)", () => {
    const s = withEntry(entry({ nonHtml: 6, probation: probation() }));
    assert.equal(decide(s, img(1), never), "probe");
    assert.equal(recordProbeFailure(s, img(1)), true);
    assert.equal(decide(s, img(2), never), "probe");
    assert.equal(recordProbeFailure(s, img(2)), true);
    assert.deepEqual(got(s).probation, { admitted: 2, probeUrl: null, resolved: true });
    assert.equal(got(s).confirmed, true);
    assert.equal(decide(s, img(3), never), "block");
});

test("decide 5: without probation, a key blocks from K and allows below K", () => {
    const s = withEntry(entry({ nonHtml: 2 }));
    assert.equal(decide(s, img(1), never), "allow");
    got(s).nonHtml = 3;
    assert.equal(decide(s, img(1), never), "block");
});

test("decide 5: a confirmed key under K blocks", () => {
    const s = withEntry(entry({ nonHtml: 1, confirmed: true }));
    assert.equal(decide(s, img(1), never), "block");
});

test("lifecycle: learn at K, block, then a later HTML page releases the key for the whole crawl", () => {
    const s = fresh();
    for (const i of [1, 2, 3]) recordNonHtml(s, img(i), NOW);
    assert.equal(decide(s, img(4), never), "block");
    assert.equal(decide(s, "https://h.fr/", never), "allow", "key-less URL");
    assert.equal(recordHtml(s, img(4)), "released");
    assert.equal(decide(s, img(5), never), "allow");
    assert.equal(recordNonHtml(s, img(6), LATER), "counted");
    assert.equal(decide(s, img(7), never), "allow", "the veto holds");
});
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

```bash
cd <CR> && node --import tsx --test src/nonHtmlPrefix.test.ts
```

Attendu : échec de chargement du module (`ERR_MODULE_NOT_FOUND`, `Cannot find module` pointant `nonHtmlPrefix.js`) ; `ℹ fail` ≥ 1, aucun test passé.

- [ ] **Step 3: Écrire l'implémentation**

Créer `apps-microservices/crawler-service/crawler/src/nonHtmlPrefix.ts` (patron `facetCap.ts` : fonctions pures, aucune lecture de `process.env` au chargement ; `resolve*` reçoivent leur entrée en paramètre).

```ts
// apps-microservices/crawler-service/crawler/src/nonHtmlPrefix.ts
/**
 * R23 (2): non-HTML prefix learning — pure decision module.
 *
 * Learns, per `host + parent directory`, the prefixes that only ever serve non-HTML
 * (marsaleix `/image/<token>` served as image/* with no extension), so the crawler stops
 * replaying them. No I/O, no env read at load time: the mode and the parameters are
 * resolved by the caller from the environment and passed in. Spec:
 * docs/superpowers/specs/2026-10-16-crawler-nonhtml-prefix-learning-design.md
 */
import { posix } from "node:path";
import { hasIgnoredExtensionForSeed } from "./seedExtensionFilter.js";

export type NonHtmlPrefixMode = "off" | "shadow" | "on";

/** Anything but "shadow" / "on" (trimmed, case-folded) is "off" — undefined, "" and unknown included. */
export function resolveNonHtmlPrefixMode(raw: string | undefined): NonHtmlPrefixMode {
    const v = (raw ?? "").trim().toLowerCase();
    return v === "shadow" || v === "on" ? v : "off";
}

/**
 * Positive integer from an env string. Empty, non-integer or <= 0 falls back: an empty
 * variable must never read as 0 (the `resolveTimeoutMaxRetries("")` trap, httpStatusPolicy.ts).
 */
export function resolvePositiveInt(raw: string | undefined, fallback: number): number {
    const v = (raw ?? "").trim();
    if (!/^\d+$/.test(v)) return fallback;
    const n = Number(v);
    return n > 0 ? n : fallback;
}

export interface NonHtmlPrefixParams {
    minNonHtml: number;
    probes: number;
    isolatedMax: number;
}

export const NONHTML_PREFIX_DEFAULTS: NonHtmlPrefixParams = {
    minNonHtml: 5,
    probes: 3,
    isolatedMax: 10000,
};

export function resolveNonHtmlPrefixParams(env: Record<string, string | undefined>): NonHtmlPrefixParams {
    return {
        minNonHtml: resolvePositiveInt(env.NONHTML_PREFIX_MIN, NONHTML_PREFIX_DEFAULTS.minNonHtml),
        probes: resolvePositiveInt(env.NONHTML_PREFIX_PROBES, NONHTML_PREFIX_DEFAULTS.probes),
        isolatedMax: resolvePositiveInt(env.NONHTML_ISOLATED_MAX, NONHTML_PREFIX_DEFAULTS.isolatedMax),
    };
}

/** Queue identity: trailing slashes dropped (same rule as `rightTrimSlash`, functions.ts). */
export function normalizeUrlIdentity(url: string): string {
    return url.replace(/\/+$/, "");
}

/**
 * `host + parent directory of the path`. Query and fragment are ignored. Invalid URL or a
 * parent directory that is the root (`/telechargement?id=12`) gives null: such a URL has
 * no prefix to learn and is handled as an isolated URL.
 */
export function prefixKey(url: string): string | null {
    let u: URL;
    try {
        u = new URL(url);
    } catch {
        return null;
    }
    const dir = posix.dirname(u.pathname);
    if (dir === "/" || dir === ".") return null;
    return `${u.host}${dir}`;
}

export interface Probation {
    admitted: number;
    probeUrl: string | null;
    resolved: boolean;
}

export interface PrefixEntry {
    nonHtml: number;
    sawHtml: boolean;
    confirmed: boolean;
    confirmedAt: string | null;
    probation: Probation | null;
}

export interface NonHtmlPrefixState {
    params: NonHtmlPrefixParams;
    prefixes: Map<string, PrefixEntry>;
    isolated: Set<string>;
    loadedIsolated: Set<string>;
}

export function createNonHtmlPrefixState(params: NonHtmlPrefixParams): NonHtmlPrefixState {
    return { params, prefixes: new Map(), isolated: new Set(), loadedIsolated: new Set() };
}

/** A key blocks once confirmed or K non-HTML hits are counted — and never after an HTML page was seen. */
export function isKeyBlocking(entry: PrefixEntry, params: NonHtmlPrefixParams): boolean {
    return !entry.sawHtml && (entry.confirmed || entry.nonHtml >= params.minNonHtml);
}

const newEntry = (): PrefixEntry => ({
    nonHtml: 0,
    sawHtml: false,
    confirmed: false,
    confirmedAt: null,
    probation: null,
});

const isPending = (p: Probation | null): p is Probation => p !== null && !p.resolved;

/** Adds an identity to the isolated set unless already present or at the cap. */
function addIsolated(state: NonHtmlPrefixState, identity: string): boolean {
    if (state.isolated.has(identity) || state.isolated.size >= state.params.isolatedMax) return false;
    state.isolated.add(identity);
    return true;
}

export type NonHtmlEvent = "ignored" | "counted" | "learned" | "confirmed" | "isolated";

/** A response of a non-HTML content-type was served for `url`. Order of the cases is normative. */
export function recordNonHtml(state: NonHtmlPrefixState, url: string, nowIso: string): NonHtmlEvent {
    // 1. A URL with a known binary extension is already filtered elsewhere: learn nothing.
    if (hasIgnoredExtensionForSeed(url)) return "ignored";
    const n = normalizeUrlIdentity(url);
    const key = prefixKey(url);
    // 2. No prefix to learn: remember the URL itself (capped).
    if (key === null) return addIsolated(state, n) ? "isolated" : "ignored";
    // 3. Entry creation; a key that served HTML keeps its veto for the whole crawl.
    let entry = state.prefixes.get(key);
    if (!entry) {
        entry = newEntry();
        state.prefixes.set(key, entry);
    }
    if (entry.sawHtml) {
        entry.nonHtml++;
        return "counted";
    }
    // 4.
    const wasBlocking = isKeyBlocking(entry, state.params);
    entry.nonHtml++;
    // 5. Under an unresolved probation, ANY non-HTML under the key confirms it.
    if (isPending(entry.probation)) {
        entry.probation.resolved = true;
        entry.probation.probeUrl = null;
        entry.confirmed = true;
        entry.confirmedAt = nowIso;
        return "confirmed";
    }
    // 6.
    if (wasBlocking) return "counted";
    // 7. K reached by this very hit.
    if (isKeyBlocking(entry, state.params)) {
        entry.confirmedAt = nowIso;
        return "learned";
    }
    // 8. Under K: the URL is also remembered on its own (capped).
    return addIsolated(state, n) ? "isolated" : "counted";
}

export type HtmlEvent = "none" | "released";

/** An `ok`-class HTML page was served for `url`. Sets the veto; "released" = a blocking or probing key was freed. */
export function recordHtml(state: NonHtmlPrefixState, url: string): HtmlEvent {
    const key = prefixKey(url);
    if (key === null) return "none";
    const entry = state.prefixes.get(key);
    if (!entry) {
        state.prefixes.set(key, { ...newEntry(), sawHtml: true });
        return "none";
    }
    if (!entry.sawHtml && (isKeyBlocking(entry, state.params) || isPending(entry.probation))) {
        entry.sawHtml = true;
        if (entry.probation) {
            entry.probation.resolved = true;
            entry.probation.probeUrl = null;
        }
        return "released";
    }
    entry.sawHtml = true;
    return "none";
}

/**
 * The probe URL failed (timeout / error, no HTTP verdict). True only if `url` is the in-flight
 * probe of an unresolved probation. Out of admissions ⇒ the key is confirmed without signal
 * (blocks, stays persisted — spec 3.3).
 */
export function recordProbeFailure(state: NonHtmlPrefixState, url: string): boolean {
    const key = prefixKey(url);
    if (key === null) return false;
    const entry = state.prefixes.get(key);
    const p = entry?.probation;
    if (!entry || !p || p.resolved || p.probeUrl !== normalizeUrlIdentity(url)) return false;
    p.probeUrl = null;
    if (p.admitted >= state.params.probes) {
        p.resolved = true;
        entry.confirmed = true;
    }
    return true;
}

export type NonHtmlDecision = "allow" | "block" | "probe";

/** Verdict for `url` before it is fetched. May admit a probe (mutates the probation). Order is normative. */
export function decide(
    state: NonHtmlPrefixState,
    url: string,
    isExempt: (normalizedUrl: string) => boolean,
): NonHtmlDecision {
    const n = normalizeUrlIdentity(url);
    // 1. Absolute exemption (previous dataset, homepage).
    if (isExempt(n)) return "allow";
    // 2. Isolated URL learned by a previous crawl.
    if (state.loadedIsolated.has(n)) return "block";
    // 3.
    const key = prefixKey(url);
    const entry = key === null ? undefined : state.prefixes.get(key);
    if (!entry || entry.sawHtml) return "allow";
    // 4. Probation: one probe at a time, `probes` admissions at most.
    const p = entry.probation;
    if (isPending(p)) {
        if (p.probeUrl === n) return "probe";
        if (p.probeUrl !== null) return "block";
        if (p.admitted < state.params.probes) {
            p.admitted++;
            p.probeUrl = n;
            return "probe";
        }
        p.resolved = true;
        entry.confirmed = true;
        return "block";
    }
    // 5.
    return isKeyBlocking(entry, state.params) ? "block" : "allow";
}
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe, et compter**

```bash
cd <CR> && node --import tsx --test src/nonHtmlPrefix.test.ts
```

Attendu : `ℹ fail 0`, `ℹ pass <N>`. Mesurer `<N>` = nombre de `test(` du fichier :

```bash
grep -c '^test(' <CR>/src/nonHtmlPrefix.test.ts
```

Attendu : `<N>` égal à `ℹ pass` (valeur rédigée de ce plan : 49). Consigner `<N>` : l'attendu de la suite complète est `509 + <N>`.

- [ ] **Step 5: Contrôles d'effet (types, imports, pureté)**

Les tests sont dans `include` de `tsconfig.json` : `tsx` ne type-check pas, `tsc` oui.

```bash
cd <CR> && npx tsc --noEmit 2>&1 | grep -c nonHtmlPrefix
```

Attendu : `0` (aucune erreur dans les fichiers neufs ; des erreurs préexistantes ailleurs ne comptent pas — si le compte est non nul, lire les lignes et corriger les fichiers de cette tâche).

```bash
grep -nE "process\.env|from \"node:fs\"|^import " <CR>/src/nonHtmlPrefix.ts
```

Attendu : exactement deux lignes, les deux `import` (`node:path`, `./seedExtensionFilter.js`) ; aucune ligne `process.env` ni `node:fs`.

- [ ] **Step 6: Suite complète**

```bash
cd <CR> && npm test 2>&1 | tail -12
```

Attendu : `ℹ fail 0` et `ℹ pass` = 509 + `<N>` (558 si `<N>` = 49).

- [ ] **Step 7: Commit**

Écrire le message avec l'outil Write dans `<scratchpad>/commit-T01.txt` :

```text
feat(crawler): add pure non-HTML prefix decision module (R23)

Add nonHtmlPrefix.ts: mode and parameter resolution (empty env never reads
as 0), host + parent-directory prefix key, per-key state, and the
recordNonHtml / recordHtml / recordProbeFailure / decide state machine with
its probation (one probe at a time). Pure, no I/O, no env read at load time;
nothing imports it yet, so the crawler behaviour is unchanged.

FR — ajout du module pur de décision des préfixes non-HTML (R23)

Ajoute nonHtmlPrefix.ts : résolution du mode et des paramètres (une variable
vide ne vaut jamais 0), clé de préfixe hôte + dossier parent, état par clé,
et l'automate recordNonHtml / recordHtml / recordProbeFailure / decide avec
sa probation (une sonde à la fois). Pur, sans I/O, sans lecture d'env au
chargement ; rien ne l'importe encore, le comportement du crawler est
inchangé.
```

Puis, chaque commande dans son propre appel :

```bash
git -C <WT> add apps-microservices/crawler-service/crawler/src/nonHtmlPrefix.ts apps-microservices/crawler-service/crawler/src/nonHtmlPrefix.test.ts
```

```bash
git -C <WT> diff --cached --stat
```

Attendu : exactement les deux fichiers ci-dessus, rien d'autre.

```bash
git -C <WT> ls-files --eol -- apps-microservices/crawler-service/crawler/src/nonHtmlPrefix.ts apps-microservices/crawler-service/crawler/src/nonHtmlPrefix.test.ts
```

Attendu : `i/lf` sur les deux lignes (jamais `i/mixed`). Puis :

```bash
git -C <WT> commit -F <scratchpad>/commit-T01.txt
```
### Task 2: Sidecar : sérialisation, parse, chemins, I/O
> NOMS NEUFS : NONHTML_PREFIX_SIDECAR (produit) ⇒ T2, NONHTML_SIDECAR_VERSION (produit) ⇒ T2, SidecarData (produit) ⇒ T2, serializeNonHtmlPrefixState (produit) ⇒ T2, parseNonHtmlPrefixSidecar (produit) ⇒ T2, loadSidecarInto (produit) ⇒ T2, currentSidecarPath (produit) ⇒ T2, resolvePreviousSidecarPath (produit) ⇒ T2, readSidecarFile (produit) ⇒ T2, writeSidecarFile (produit) ⇒ T2, NonHtmlPrefixState (consommé) ⇒ T1, PrefixEntry (consommé) ⇒ T1, createNonHtmlPrefixState (consommé) ⇒ T1, isKeyBlocking (consommé) ⇒ T1, normalizeUrlIdentity (consommé) ⇒ T1, NONHTML_PREFIX_DEFAULTS (consommé) ⇒ T1

**Goal:** Écrire le module sidecar (format JSON exact, parse tolérant, chargement current/previous, chemins, I/O tmp + rename sans exception) que T3 (sérialisation) et T4 (chargement, écriture) consomment, sans redéfinir aucun type de T1.

**Files:**
- Create: `apps-microservices/crawler-service/crawler/src/nonHtmlPrefixSidecar.ts`
- Test: `apps-microservices/crawler-service/crawler/src/nonHtmlPrefixSidecar.test.ts`

**Acceptance Criteria:**
- [ ] `serializeNonHtmlPrefixState` rend, à l'octet, `JSON.stringify({ version: 1, prefixes, urls })` sans indentation ni newline final ; `prefixes` ne contient que les entrées `!sawHtml && (isKeyBlocking || probation non résolue)`, dans l'ordre d'insertion de la Map ; `urls` = `isolated` puis `loadedIsolated`, sans doublon, tronqué à `params.isolatedMax`.
- [ ] `parseNonHtmlPrefixSidecar` rend `{ prefixes: new Map(), urls: [] }` pour `null`, JSON invalide, non-objet, `version !== 1` ; ignore une entrée dont `nonHtml` n'est pas un entier >= 0 ; `confirmedAt` non-string => `null` ; ne garde de `urls` que les strings non vides.
- [ ] `loadSidecarInto` saute une clé déjà présente, crée `confirmed: true` + `probation: null` en `"current"` et `confirmed: false` + probation `{ admitted: 0, probeUrl: null, resolved: false }` en `"previous"`, normalise les URLs (`normalizeUrlIdentity`), plafonne `loadedIsolated` à `params.isolatedMax`, rend le nombre de clés ajoutées.
- [ ] `currentSidecarPath("ex.tld")` = `storage/datasets/ex.tld/__nonhtml_prefixes.json` ; `resolvePreviousSidecarPath` essaie le domaine puis sa forme sanitisée (points => tirets) sous `<cwd>/../<previousId>/storage/datasets/`, rend `null` si aucun fichier n'existe.
- [ ] `writeSidecarFile` crée le dossier, écrit via `<file>.tmp` + rename, ne laisse aucun `.tmp`, et sur échec émet `console.warn("[nonhtml-prefix] sidecar write failed: …")` sans jamais lever ; `readSidecarFile(null)`, fichier absent ou illisible => `null`.
- [ ] 29 tests neufs dans `nonHtmlPrefixSidecar.test.ts`, aucun fichier de test existant modifié, aucun import hors `./nonHtmlPrefix.js` pour les types/fonctions de T1.

**Verify:** `cd <CR> && node --import tsx --test src/nonHtmlPrefixSidecar.test.ts`

**Steps:**

- [ ] **Step 1: Préconditions et ligne de base `<BASE>`**

T1 doit être commité (ses exports sont consommés tels que signés dans l'index § C1).

Run: `command ls <CR>/src/nonHtmlPrefix.ts <CR>/src/nonHtmlPrefix.test.ts`
Expected: les deux chemins listés (sinon STOP : T1 absent, ne rien écrire).

Run: `grep -nE "^export (function|const|type|interface) (createNonHtmlPrefixState|isKeyBlocking|normalizeUrlIdentity|NONHTML_PREFIX_DEFAULTS|NonHtmlPrefixState|PrefixEntry)\b" <CR>/src/nonHtmlPrefix.ts`
Expected: 6 lignes (une par nom). Un nom manquant => STOP, rapporter à l'user (contrat C1 rompu).

Run: `cd <CR> && npm test 2>&1 | tail -12`
Expected: `ℹ fail 0`. Consigner la valeur de `ℹ pass` comme `<BASE>` (= 509 + tests de T1). La suite finale de ce task attendra `ℹ pass` = `<BASE>` + 29.

- [ ] **Step 2: Écrire le test (rouge)**

Create `apps-microservices/crawler-service/crawler/src/nonHtmlPrefixSidecar.test.ts` :

```ts
import { test, mock } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
    createNonHtmlPrefixState,
    NONHTML_PREFIX_DEFAULTS,
    type NonHtmlPrefixState,
    type PrefixEntry,
} from "./nonHtmlPrefix.js";
import {
    NONHTML_PREFIX_SIDECAR,
    NONHTML_SIDECAR_VERSION,
    currentSidecarPath,
    loadSidecarInto,
    parseNonHtmlPrefixSidecar,
    readSidecarFile,
    resolvePreviousSidecarPath,
    serializeNonHtmlPrefixState,
    writeSidecarFile,
} from "./nonHtmlPrefixSidecar.js";

const TS = "2026-01-01T00:00:00.000Z";

const entry = (over: Partial<PrefixEntry> = {}): PrefixEntry => ({
    nonHtml: 0,
    sawHtml: false,
    confirmed: false,
    confirmedAt: null,
    probation: null,
    ...over,
});

const stateWith = (isolatedMax = 3): NonHtmlPrefixState =>
    createNonHtmlPrefixState({ ...NONHTML_PREFIX_DEFAULTS, minNonHtml: 5, probes: 3, isolatedMax });

const withTmp = (fn: (tmp: string) => void): void => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "nhps-"));
    try { fn(tmp); } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
};

const EMPTY_BYTES = '{"version":1,"prefixes":{},"urls":[]}';

// ---------------------------------------------------------------- serialize

test("serialize: exact bytes, entries filtered, Map insertion order kept", () => {
    const s = stateWith();
    // blocking by threshold (nonHtml >= K=5), not confirmed
    s.prefixes.set("h/threshold", entry({ nonHtml: 5, confirmedAt: TS }));
    // vetoed by HTML => never persisted, even if confirmed
    s.prefixes.set("h/veto", entry({ nonHtml: 9, sawHtml: true, confirmed: true, confirmedAt: TS }));
    // under K, no probation => not blocking, not persisted
    s.prefixes.set("h/under", entry({ nonHtml: 2 }));
    // confirmed => blocking even under K
    s.prefixes.set("h/confirmed", entry({ nonHtml: 1, confirmed: true, confirmedAt: TS }));
    // unresolved probation => persisted, confirmedAt null kept as null
    s.prefixes.set("h/probing", entry({ nonHtml: 7, probation: { admitted: 1, probeUrl: "https://h/probing/a", resolved: false } }));
    // resolved probation, not confirmed, under K => not persisted
    s.prefixes.set("h/resolved", entry({ nonHtml: 1, probation: { admitted: 3, probeUrl: null, resolved: true } }));
    // unresolved probation but HTML seen => not persisted
    s.prefixes.set("h/probehtml", entry({ nonHtml: 7, sawHtml: true, probation: { admitted: 1, probeUrl: null, resolved: false } }));
    s.isolated.add("https://h/x");
    s.isolated.add("https://h/y");
    assert.equal(
        serializeNonHtmlPrefixState(s),
        '{"version":1,"prefixes":{' +
            '"h/threshold":{"nonHtml":5,"confirmedAt":"2026-01-01T00:00:00.000Z"},' +
            '"h/confirmed":{"nonHtml":1,"confirmedAt":"2026-01-01T00:00:00.000Z"},' +
            '"h/probing":{"nonHtml":7,"confirmedAt":null}' +
            '},"urls":["https://h/x","https://h/y"]}',
    );
});

test("serialize: empty state => exact empty document, no newline, no indentation", () => {
    const out = serializeNonHtmlPrefixState(stateWith());
    assert.equal(out, EMPTY_BYTES);
    assert.equal(out.includes("\n"), false);
    assert.equal(NONHTML_SIDECAR_VERSION, 1);
});

test("serialize: urls = isolated then loadedIsolated, deduplicated, truncated to isolatedMax", () => {
    const s = stateWith(3);
    s.isolated.add("https://h/a");
    s.isolated.add("https://h/b");
    s.loadedIsolated.add("https://h/b"); // duplicate of an isolated entry
    s.loadedIsolated.add("https://h/c");
    s.loadedIsolated.add("https://h/d"); // 4th distinct => cut by isolatedMax=3
    assert.deepEqual(JSON.parse(serializeNonHtmlPrefixState(s)).urls, ["https://h/a", "https://h/b", "https://h/c"]);
});

test("serialize -> parse round trip keeps keys, counts, confirmedAt and urls", () => {
    const s = stateWith();
    s.prefixes.set("h/one", entry({ nonHtml: 6, confirmed: true, confirmedAt: TS }));
    s.prefixes.set("h/two", entry({ nonHtml: 2, probation: { admitted: 0, probeUrl: null, resolved: false } }));
    s.isolated.add("https://h/z");
    const data = parseNonHtmlPrefixSidecar(serializeNonHtmlPrefixState(s));
    assert.deepEqual([...data.prefixes.entries()], [
        ["h/one", { nonHtml: 6, confirmedAt: TS }],
        ["h/two", { nonHtml: 2, confirmedAt: null }],
    ]);
    assert.deepEqual(data.urls, ["https://h/z"]);
});

// -------------------------------------------------------------------- parse

test("parse: null => empty data", () => {
    const d = parseNonHtmlPrefixSidecar(null);
    assert.equal(d.prefixes.size, 0);
    assert.deepEqual(d.urls, []);
});

test("parse: invalid JSON => empty data", () => {
    for (const raw of ["", "{", "not json", '{"version":1,'])
        assert.deepEqual(parseNonHtmlPrefixSidecar(raw), { prefixes: new Map(), urls: [] }, raw);
});

test("parse: non-object JSON (array, number, string, null) => empty data", () => {
    for (const raw of ["[]", "[1,2]", "5", '"x"', "null", "true"])
        assert.deepEqual(parseNonHtmlPrefixSidecar(raw), { prefixes: new Map(), urls: [] }, raw);
});

test("parse: version other than 1 (or missing) => empty data even if the body is valid", () => {
    const body = '"prefixes":{"h/a":{"nonHtml":9,"confirmedAt":null}},"urls":["https://h/x"]';
    for (const raw of [`{"version":2,${body}}`, `{"version":"1",${body}}`, `{"version":0,${body}}`, `{${body}}`])
        assert.deepEqual(parseNonHtmlPrefixSidecar(raw), { prefixes: new Map(), urls: [] }, raw);
});

test("parse: prefixes that is not a plain object => empty prefixes, urls still read", () => {
    for (const p of ["[]", '"x"', "5", "null"]) {
        const d = parseNonHtmlPrefixSidecar(`{"version":1,"prefixes":${p},"urls":["https://h/x"]}`);
        assert.equal(d.prefixes.size, 0, p);
        assert.deepEqual(d.urls, ["https://h/x"], p);
    }
});

test("parse: entry with nonHtml not an integer >= 0 (or not an object) is ignored, valid ones kept", () => {
    const raw = JSON.stringify({
        version: 1,
        prefixes: {
            "h/neg": { nonHtml: -1, confirmedAt: null },
            "h/float": { nonHtml: 1.5, confirmedAt: null },
            "h/str": { nonHtml: "3", confirmedAt: null },
            "h/missing": { confirmedAt: null },
            "h/null": null,
            "h/array": [5],
            "h/zero": { nonHtml: 0, confirmedAt: null },
            "h/ok": { nonHtml: 4, confirmedAt: TS },
        },
        urls: [],
    });
    const d = parseNonHtmlPrefixSidecar(raw);
    assert.deepEqual([...d.prefixes.entries()], [
        ["h/zero", { nonHtml: 0, confirmedAt: null }],
        ["h/ok", { nonHtml: 4, confirmedAt: TS }],
    ]);
});

test("parse: confirmedAt that is not a string => null", () => {
    const raw = JSON.stringify({
        version: 1,
        prefixes: {
            "h/num": { nonHtml: 1, confirmedAt: 12345 },
            "h/obj": { nonHtml: 1, confirmedAt: {} },
            "h/abs": { nonHtml: 1 },
            "h/str": { nonHtml: 1, confirmedAt: TS },
        },
        urls: [],
    });
    const d = parseNonHtmlPrefixSidecar(raw);
    assert.equal(d.prefixes.get("h/num")?.confirmedAt, null);
    assert.equal(d.prefixes.get("h/obj")?.confirmedAt, null);
    assert.equal(d.prefixes.get("h/abs")?.confirmedAt, null);
    assert.equal(d.prefixes.get("h/str")?.confirmedAt, TS);
});

test("parse: urls keeps only non-empty strings; urls absent or not an array => []", () => {
    const raw = JSON.stringify({ version: 1, prefixes: {}, urls: ["https://h/a", "", 5, null, {}, "https://h/b"] });
    assert.deepEqual(parseNonHtmlPrefixSidecar(raw).urls, ["https://h/a", "https://h/b"]);
    assert.deepEqual(parseNonHtmlPrefixSidecar('{"version":1,"prefixes":{}}').urls, []);
    assert.deepEqual(parseNonHtmlPrefixSidecar('{"version":1,"prefixes":{},"urls":"https://h/a"}').urls, []);
});

// ------------------------------------------------------------ loadSidecarInto

const DATA = () => parseNonHtmlPrefixSidecar(JSON.stringify({
    version: 1,
    prefixes: { "h/a": { nonHtml: 6, confirmedAt: TS }, "h/b": { nonHtml: 2, confirmedAt: null } },
    urls: ["https://h/x/", "https://h/y"],
}));

test("loadSidecarInto current: confirmed entries, no probation, count of added keys", () => {
    const s = stateWith(10);
    assert.equal(loadSidecarInto(s, DATA(), "current"), 2);
    assert.deepEqual(s.prefixes.get("h/a"), { nonHtml: 6, sawHtml: false, confirmed: true, confirmedAt: TS, probation: null });
    assert.deepEqual(s.prefixes.get("h/b"), { nonHtml: 2, sawHtml: false, confirmed: true, confirmedAt: null, probation: null });
});

test("loadSidecarInto previous: unconfirmed entries in unresolved probation, admitted 0", () => {
    const s = stateWith(10);
    assert.equal(loadSidecarInto(s, DATA(), "previous"), 2);
    assert.deepEqual(s.prefixes.get("h/a"), {
        nonHtml: 6, sawHtml: false, confirmed: false, confirmedAt: TS,
        probation: { admitted: 0, probeUrl: null, resolved: false },
    });
});

test("loadSidecarInto: a key already in state.prefixes is skipped and not counted", () => {
    const s = stateWith(10);
    const existing = entry({ nonHtml: 99, sawHtml: true });
    s.prefixes.set("h/a", existing);
    assert.equal(loadSidecarInto(s, DATA(), "current"), 1);
    assert.equal(s.prefixes.get("h/a"), existing); // same object, untouched
    assert.equal(s.prefixes.get("h/b")?.confirmed, true);
});

test("loadSidecarInto: urls are normalised (trailing slash) and loadedIsolated is capped at isolatedMax", () => {
    const s = stateWith(10);
    loadSidecarInto(s, DATA(), "current");
    assert.deepEqual([...s.loadedIsolated], ["https://h/x", "https://h/y"]);
    const capped = stateWith(1);
    loadSidecarInto(capped, DATA(), "current");
    assert.deepEqual([...capped.loadedIsolated], ["https://h/x"]);
});

test("loadSidecarInto order: current first, then previous => a key in both stays confirmed, not re-probed", () => {
    const s = stateWith(10);
    const added1 = loadSidecarInto(s, DATA(), "current");
    const added2 = loadSidecarInto(s, DATA(), "previous");
    assert.equal(added1, 2);
    assert.equal(added2, 0);
    assert.equal(s.prefixes.get("h/a")?.confirmed, true);
    assert.equal(s.prefixes.get("h/a")?.probation, null);
});

// -------------------------------------------------------------------- chemins

test("currentSidecarPath: relative path under storage/datasets/<domain>", () => {
    assert.equal(NONHTML_PREFIX_SIDECAR, "__nonhtml_prefixes.json");
    assert.equal(currentSidecarPath("ex.tld"), "storage/datasets/ex.tld/__nonhtml_prefixes.json");
});

const plantPrevious = (tmp: string, dirName: string): string => {
    const dir = path.join(tmp, "prev", "storage", "datasets", dirName);
    fs.mkdirSync(dir, { recursive: true });
    const file = path.join(dir, NONHTML_PREFIX_SIDECAR);
    fs.writeFileSync(file, EMPTY_BYTES);
    return file;
};

test("resolvePreviousSidecarPath: finds the file under the original domain name", () => {
    withTmp((tmp) => {
        const cwd = path.join(tmp, "current");
        fs.mkdirSync(cwd, { recursive: true });
        const file = plantPrevious(tmp, "ex.tld");
        assert.equal(resolvePreviousSidecarPath("prev", "ex.tld", cwd), file);
    });
});

test("resolvePreviousSidecarPath: falls back to the sanitised domain (dots => hyphens)", () => {
    withTmp((tmp) => {
        const cwd = path.join(tmp, "current");
        fs.mkdirSync(cwd, { recursive: true });
        const file = plantPrevious(tmp, "ex-tld");
        assert.equal(resolvePreviousSidecarPath("prev", "ex.tld", cwd), file);
    });
});

test("resolvePreviousSidecarPath: the original name wins when both exist", () => {
    withTmp((tmp) => {
        const cwd = path.join(tmp, "current");
        fs.mkdirSync(cwd, { recursive: true });
        plantPrevious(tmp, "ex-tld");
        const original = plantPrevious(tmp, "ex.tld");
        assert.equal(resolvePreviousSidecarPath("prev", "ex.tld", cwd), original);
    });
});

test("resolvePreviousSidecarPath: absent previous crawl, absent dataset or absent file => null", () => {
    withTmp((tmp) => {
        const cwd = path.join(tmp, "current");
        fs.mkdirSync(cwd, { recursive: true });
        assert.equal(resolvePreviousSidecarPath("nope", "ex.tld", cwd), null);
        fs.mkdirSync(path.join(tmp, "prev", "storage", "datasets", "ex.tld"), { recursive: true }); // dir, no sidecar
        assert.equal(resolvePreviousSidecarPath("prev", "ex.tld", cwd), null);
    });
});

// ------------------------------------------------------------------------ I/O

test("writeSidecarFile: creates missing directories, writes the text, leaves no .tmp", () => {
    withTmp((tmp) => {
        const file = path.join(tmp, "a", "b", NONHTML_PREFIX_SIDECAR);
        writeSidecarFile(file, EMPTY_BYTES);
        assert.equal(fs.readFileSync(file, "utf-8"), EMPTY_BYTES);
        assert.deepEqual(fs.readdirSync(path.dirname(file)), [NONHTML_PREFIX_SIDECAR]);
    });
});

test("writeSidecarFile: a second write replaces the content (no append, no .tmp)", () => {
    withTmp((tmp) => {
        const file = path.join(tmp, NONHTML_PREFIX_SIDECAR);
        writeSidecarFile(file, "first-version-longer-than-second");
        writeSidecarFile(file, "second");
        assert.equal(fs.readFileSync(file, "utf-8"), "second");
        assert.deepEqual(fs.readdirSync(tmp), [NONHTML_PREFIX_SIDECAR]);
    });
});

test("writeSidecarFile: directory cannot be created => console.warn, no throw", () => {
    withTmp((tmp) => {
        const blocker = path.join(tmp, "blocker");
        fs.writeFileSync(blocker, "x"); // a FILE where a directory is needed
        const warn = mock.method(console, "warn", () => {});
        try {
            assert.doesNotThrow(() => writeSidecarFile(path.join(blocker, "sub", NONHTML_PREFIX_SIDECAR), EMPTY_BYTES));
            assert.equal(warn.mock.callCount(), 1);
            assert.match(String(warn.mock.calls[0].arguments[0]), /^\[nonhtml-prefix\] sidecar write failed: /);
        } finally {
            warn.mock.restore();
        }
    });
});

test("writeSidecarFile: rename fails (target is a directory) => console.warn, no throw, no .tmp left", () => {
    withTmp((tmp) => {
        const file = path.join(tmp, NONHTML_PREFIX_SIDECAR);
        fs.mkdirSync(file); // target path is a directory: renameSync(tmp, file) must fail
        const warn = mock.method(console, "warn", () => {});
        try {
            assert.doesNotThrow(() => writeSidecarFile(file, EMPTY_BYTES));
            assert.equal(warn.mock.callCount(), 1);
            assert.match(String(warn.mock.calls[0].arguments[0]), /^\[nonhtml-prefix\] sidecar write failed: /);
            assert.equal(fs.existsSync(`${file}.tmp`), false);
        } finally {
            warn.mock.restore();
        }
    });
});

test("readSidecarFile(null) => null", () => {
    assert.equal(readSidecarFile(null), null);
});

test("readSidecarFile: absent file or unreadable path (a directory) => null", () => {
    withTmp((tmp) => {
        assert.equal(readSidecarFile(path.join(tmp, "absent.json")), null);
        assert.equal(readSidecarFile(tmp), null); // reading a directory throws EISDIR => null
    });
});

test("readSidecarFile: returns the exact text written by writeSidecarFile", () => {
    withTmp((tmp) => {
        const file = path.join(tmp, "x", NONHTML_PREFIX_SIDECAR);
        writeSidecarFile(file, EMPTY_BYTES);
        assert.equal(readSidecarFile(file), EMPTY_BYTES);
    });
});
```

- [ ] **Step 3: Lancer le test, constater l'échec**

Run: `cd <CR> && node --import tsx --test src/nonHtmlPrefixSidecar.test.ts`
Expected: ÉCHEC, `Cannot find module './nonHtmlPrefixSidecar.js'` (`ERR_MODULE_NOT_FOUND`), `ℹ fail 1`. Tout autre échec (import de `./nonHtmlPrefix.js`) => STOP : T1 non conforme à l'index.

- [ ] **Step 4: Implémenter le module**

Create `apps-microservices/crawler-service/crawler/src/nonHtmlPrefixSidecar.ts` :

```ts
/**
 * `__nonhtml_prefixes.json` — the durable record of the non-HTML URL prefixes the crawler
 * learned (R23 (2)): one entry per `host/parent-dir` key, plus the isolated non-HTML URLs
 * (no usable parent dir, or below the learning threshold).
 *
 * Shape (exact bytes, no indentation, no trailing newline):
 *   {"version":1,"prefixes":{"<key>":{"nonHtml":N,"confirmedAt":"<iso>"|null}},"urls":["<url>",…]}
 *
 * Persisted keys: not vetoed by an HTML response AND (blocking OR still in unresolved probation).
 * The key always contains a "/" (host + dir), so object-key reordering of integer-like keys
 * cannot happen and the Map insertion order survives the JSON round trip.
 *
 * The `__` prefix is load-bearing, like `__unjudged_urls.json` (unjudgedUrls.ts): the dataset
 * readers skip `__`-prefixed names and `_count_files_in_dir` ignores them. The tmp name
 * (`<file>.tmp`) starts with `__` and does not end in `.json`, so a leftover stays invisible.
 *
 * Pure (de)serialisation + path helpers + two tiny I/O wrappers. Nothing here throws into the
 * crawl: a failed write degrades to a `console.warn`.
 */
import fs from "node:fs";
import path from "node:path";
import { isKeyBlocking, normalizeUrlIdentity, type NonHtmlPrefixState } from "./nonHtmlPrefix.js";

export const NONHTML_PREFIX_SIDECAR = "__nonhtml_prefixes.json";
export const NONHTML_SIDECAR_VERSION = 1;

export interface SidecarData {
    prefixes: Map<string, { nonHtml: number; confirmedAt: string | null }>;
    urls: string[];
}

const emptyData = (): SidecarData => ({ prefixes: new Map(), urls: [] });

const isPlainObject = (v: unknown): v is Record<string, unknown> =>
    typeof v === "object" && v !== null && !Array.isArray(v);

/** Exact-byte serialisation of the persistable part of the state. */
export function serializeNonHtmlPrefixState(state: NonHtmlPrefixState): string {
    const prefixes: Record<string, { nonHtml: number; confirmedAt: string | null }> = {};
    for (const [key, entry] of state.prefixes) {
        if (entry.sawHtml) continue;
        const probing = entry.probation !== null && !entry.probation.resolved;
        if (!isKeyBlocking(entry, state.params) && !probing) continue;
        prefixes[key] = { nonHtml: entry.nonHtml, confirmedAt: entry.confirmedAt };
    }
    const urls = [...new Set([...state.isolated, ...state.loadedIsolated])].slice(0, state.params.isolatedMax);
    return JSON.stringify({ version: NONHTML_SIDECAR_VERSION, prefixes, urls });
}

/** Tolerant reader: anything unexpected degrades to "less data", never to an exception. */
export function parseNonHtmlPrefixSidecar(raw: string | null): SidecarData {
    if (raw === null) return emptyData();
    let json: unknown;
    try { json = JSON.parse(raw); } catch { return emptyData(); }
    if (!isPlainObject(json) || json.version !== NONHTML_SIDECAR_VERSION) return emptyData();

    const data = emptyData();
    if (isPlainObject(json.prefixes)) {
        for (const [key, value] of Object.entries(json.prefixes)) {
            if (!isPlainObject(value)) continue;
            const nonHtml = value.nonHtml;
            if (typeof nonHtml !== "number" || !Number.isInteger(nonHtml) || nonHtml < 0) continue;
            const confirmedAt = typeof value.confirmedAt === "string" ? value.confirmedAt : null;
            data.prefixes.set(key, { nonHtml, confirmedAt });
        }
    }
    if (Array.isArray(json.urls)) {
        data.urls = json.urls.filter((u): u is string => typeof u === "string" && u !== "");
    }
    return data;
}

/**
 * Merge sidecar data into the state; returns the number of prefix keys added.
 * Call order imposed on the caller: "current" FIRST, then "previous" — a key the current crawl
 * already confirmed is skipped (not put back in probation by the previous crawl's copy).
 */
export function loadSidecarInto(
    state: NonHtmlPrefixState,
    data: SidecarData,
    origin: "current" | "previous",
): number {
    let added = 0;
    for (const [key, value] of data.prefixes) {
        if (state.prefixes.has(key)) continue;
        state.prefixes.set(key, origin === "current"
            ? { nonHtml: value.nonHtml, sawHtml: false, confirmed: true, confirmedAt: value.confirmedAt, probation: null }
            : {
                nonHtml: value.nonHtml, sawHtml: false, confirmed: false, confirmedAt: value.confirmedAt,
                probation: { admitted: 0, probeUrl: null, resolved: false },
            });
        added++;
    }
    for (const u of data.urls) {
        if (state.loadedIsolated.size >= state.params.isolatedMax) break;
        state.loadedIsolated.add(normalizeUrlIdentity(u));
    }
    return added;
}

/** Same relative convention as unjudgedUrls.ts (cwd = storagePath). */
export function currentSidecarPath(domain: string): string {
    return `storage/datasets/${domain}/${NONHTML_PREFIX_SIDECAR}`;
}

/**
 * Previous crawl's sidecar, resolved like `loadDatasetUrlsGenerator` resolves its dataset
 * (functions.ts, `path.resolve('..', previousId)` then original domain name, then dots => hyphens).
 * `null` when neither file exists.
 */
export function resolvePreviousSidecarPath(previousId: string, domain: string, cwd: string = process.cwd()): string | null {
    const base = path.resolve(cwd, "..", previousId, "storage", "datasets");
    for (const name of [domain, domain.replace(/\./g, "-")]) {
        const file = path.join(base, name, NONHTML_PREFIX_SIDECAR);
        if (fs.existsSync(file)) return file;
    }
    return null;
}

/** `null` for a null path, an absent file or any read error. */
export function readSidecarFile(file: string | null): string | null {
    if (file === null) return null;
    try { return fs.readFileSync(file, "utf-8"); } catch { return null; }
}

/**
 * tmp + rename (the crawl can be SIGKILLed mid-write; same reason as unjudgedUrls.ts).
 * Never throws: a failure is a warning, the crawl goes on (the in-memory state is unaffected).
 */
export function writeSidecarFile(file: string, text: string): void {
    const tmp = `${file}.tmp`;
    try {
        fs.mkdirSync(path.dirname(file), { recursive: true });
        fs.writeFileSync(tmp, text);
        fs.renameSync(tmp, file);
    } catch (e) {
        console.warn(`[nonhtml-prefix] sidecar write failed: ${(e as Error).message}`);
        try { fs.rmSync(tmp, { force: true }); } catch { /* best effort: do not leave a stale tmp */ }
    }
}
```

- [ ] **Step 5: Lancer le test, constater le succès**

Run: `cd <CR> && node --import tsx --test src/nonHtmlPrefixSidecar.test.ts`
Expected: `ℹ tests 29`, `ℹ pass 29`, `ℹ fail 0`. Un échec sur « rename fails (target is a directory) » : relever le message d'erreur réel de la plateforme et le rapporter (le test dépend de ce que `renameSync(fichier, dossier)` lève, EPERM sous Windows / EISDIR sous Linux) ; ne pas affaiblir l'assertion sans rapport.

- [ ] **Step 6: Suite complète**

Run: `cd <CR> && npm test 2>&1 | tail -12`
Expected: `ℹ fail 0` et `ℹ pass` = `<BASE>` + 29 (valeur de `<BASE>` relevée au Step 1).

- [ ] **Step 7: Commit**

Write `<scratchpad>/commit-T02.txt` (outil Write, pas de heredoc) :

```text
feat(crawler): add non-HTML prefix sidecar module (R23)

Add nonHtmlPrefixSidecar.ts: exact-byte serialisation of the learned
prefixes and isolated URLs, tolerant parser (absent, corrupt, unknown
version, bad entries), current/previous loading (previous enters
probation), path helpers (current + previous crawl, original and
sanitised domain) and tmp+rename I/O that never throws into the crawl.
Pure addition, nothing is wired yet.

FR — ajouter le module sidecar des préfixes non-HTML (R23)

Ajoute nonHtmlPrefixSidecar.ts : sérialisation à l'octet des préfixes
appris et des URLs isolées, lecteur tolérant (absent, corrompu, version
inconnue, entrées invalides), chargement current/previous (le précédent
entre en probation), chemins (crawl courant et précédent, domaine
d'origine et sanitisé) et I/O tmp+rename qui ne lève jamais dans le
crawl. Ajout pur, rien n'est encore câblé.
```

Run: `git -C <WT> add apps-microservices/crawler-service/crawler/src/nonHtmlPrefixSidecar.ts apps-microservices/crawler-service/crawler/src/nonHtmlPrefixSidecar.test.ts`
Run: `git -C <WT> diff --cached --stat`
Expected: exactement ces 2 fichiers (deux lignes + total), rien d'autre.

Run: `git -C <WT> ls-files --eol -- apps-microservices/crawler-service/crawler/src/nonHtmlPrefixSidecar.ts apps-microservices/crawler-service/crawler/src/nonHtmlPrefixSidecar.test.ts`
Expected: `i/lf` pour les deux (fichiers neufs ; un `i/crlf` ou `i/mixed` => réécrire le fichier en LF avant de commiter).

Run: `git -C <WT> commit -F <scratchpad>/commit-T02.txt`
Expected: commit créé, 2 fichiers, aucune ligne supprimée.
### Task 3: Gate + champ de contexte
> NOMS NEUFS : NonHtmlPrefixGate (produit) ⇒ T3, GatePoint (produit) ⇒ T3, NonHtmlPrefixGateDeps (produit) ⇒ T3, context.nonHtmlPrefix (produit) ⇒ T3, decide / recordNonHtml / recordHtml / recordProbeFailure / prefixKey / normalizeUrlIdentity / NonHtmlPrefixState (consommé) ⇒ T1, serializeNonHtmlPrefixState (consommé) ⇒ T2

**Blocked by:** 1, 2

**Goal:** Créer la classe `NonHtmlPrefixGate` (mode, exemption, logs, persistance, check synchrone sans compteur) avec un test par point de blocage × mode, et déclarer le champ `context.nonHtmlPrefix` (null par défaut) dans `context.ts`.

**Files:**
- Create: `apps-microservices/crawler-service/crawler/src/nonHtmlPrefixGate.ts`
- Create: `apps-microservices/crawler-service/crawler/src/nonHtmlPrefixGate.test.ts`
- Modify: `apps-microservices/crawler-service/crawler/src/context.ts`

**Acceptance Criteria:**
- [ ] `check` renvoie `true` + log `[nonhtml-prefix] would block (<point>): <url> [<key>]` en mode `shadow`, `false` + log `[nonhtml-prefix] blocked (<point>): <url> [<key>]` en mode `on`, pour chacun des 3 points `enqueue`, `prenav`, `seed`.
- [ ] `check` d'une sonde renvoie `true` + log `[nonhtml-prefix] probe (<point>): <url> [<key>]` ; un `allow` renvoie `true` sans aucun log.
- [ ] Une URL passée à `addExempt` (avec ou sans `/` final) n'est jamais bloquée, quelle que soit la forme (avec/sans `/`) testée.
- [ ] `persist` est appelé sur `learned`, `confirmed`, `isolated` ; pas sur `counted` ; `onHtml` `released` ⇒ log + persist ; `onProbeFailure` ⇒ log sans persist.
- [ ] `check` est synchrone (renvoie un `boolean`, pas une `Promise`) et n'incrémente aucun compteur (le fichier n'importe ni `context` ni `StatsManager`).
- [ ] `context.ts` porte `nonHtmlPrefix: null as NonHtmlPrefixGate | null,` juste après `facetVariantCount`, et `import type { NonHtmlPrefixGate }` ; `git diff --numstat` de `context.ts` = 3 ajoutées, 0 supprimée ; `ls-files --eol` reste `i/lf`.
- [ ] Aucun test existant modifié ; `ℹ fail 0` ; `ℹ pass` = `<PASS_AVANT>` + 19 (19 `test(` ajoutés par cette tâche).

**Verify:** `cd <CR> && node --import tsx --test src/nonHtmlPrefixGate.test.ts`

**Steps:**

- [ ] **Step 1: Mesurer la base (suite complète avant T3)**

Run : `cd <CR> && npm test 2>&1 | tail -12`
Attendu : `ℹ fail 0`. Consigner la valeur de `ℹ pass` comme `<PASS_AVANT>` (= 509 + tests de T1 + tests de T2). Vérifier aussi que les modules consommés existent : `cd <CR> && ls src/nonHtmlPrefix.ts src/nonHtmlPrefixSidecar.ts` (sinon STOP : T1/T2 non faits).

- [ ] **Step 2: Écrire le test qui échoue**

Create `<CR>/src/nonHtmlPrefixGate.test.ts` :

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { NonHtmlPrefixGate } from "./nonHtmlPrefixGate.js";
import type { GatePoint } from "./nonHtmlPrefixGate.js";
import { createNonHtmlPrefixState, NONHTML_PREFIX_DEFAULTS } from "./nonHtmlPrefix.js";

const NOW = "2026-10-16T00:00:00.000Z";
const KEY = "h.fr/image";
const U1 = "https://h.fr/image/a1";
const U2 = "https://h.fr/image/a2";
const U3 = "https://h.fr/image/a3";
const ISOLATED = "https://h.fr/telechargement?id=12";

function makeGate(mode: "shadow" | "on", minNonHtml = 2) {
    const logs: string[] = [];
    const persisted: string[] = [];
    const state = createNonHtmlPrefixState({ ...NONHTML_PREFIX_DEFAULTS, minNonHtml });
    const gate = new NonHtmlPrefixGate({
        mode,
        state,
        log: (m) => logs.push(m),
        persist: (t) => persisted.push(t),
        now: () => NOW,
    });
    return { gate, state, logs, persisted };
}

// Learns KEY (K=2: two non-HTML answers) then clears the recorded logs/persists.
function learned(mode: "shadow" | "on") {
    const g = makeGate(mode);
    g.gate.onNonHtml(U1);
    g.gate.onNonHtml(U2);
    g.logs.length = 0;
    g.persisted.length = 0;
    return g;
}

// Loaded-from-previous-crawl entry: over K but still in probation (no probe admitted yet).
function withProbation(mode: "shadow" | "on") {
    const g = makeGate(mode);
    g.state.prefixes.set(KEY, {
        nonHtml: 5,
        sawHtml: false,
        confirmed: false,
        confirmedAt: null,
        probation: { admitted: 0, probeUrl: null, resolved: false },
    });
    return g;
}

function expectBlockDecision(mode: "shadow" | "on", point: GatePoint) {
    const g = learned(mode);
    const passed = g.gate.check(U3, point);
    return { passed, logs: g.logs, persisted: g.persisted };
}

test("enqueue + shadow: passes and logs would block", () => {
    const r = expectBlockDecision("shadow", "enqueue");
    assert.equal(r.passed, true);
    assert.deepEqual(r.logs, [`[nonhtml-prefix] would block (enqueue): ${U3} [${KEY}]`]);
    assert.equal(r.persisted.length, 0);
});

test("enqueue + on: refuses and logs blocked", () => {
    const r = expectBlockDecision("on", "enqueue");
    assert.equal(r.passed, false);
    assert.deepEqual(r.logs, [`[nonhtml-prefix] blocked (enqueue): ${U3} [${KEY}]`]);
});

test("prenav + shadow: passes and logs would block", () => {
    const r = expectBlockDecision("shadow", "prenav");
    assert.equal(r.passed, true);
    assert.deepEqual(r.logs, [`[nonhtml-prefix] would block (prenav): ${U3} [${KEY}]`]);
});

test("prenav + on: refuses and logs blocked", () => {
    const r = expectBlockDecision("on", "prenav");
    assert.equal(r.passed, false);
    assert.deepEqual(r.logs, [`[nonhtml-prefix] blocked (prenav): ${U3} [${KEY}]`]);
});

test("seed + shadow: passes and logs would block", () => {
    const r = expectBlockDecision("shadow", "seed");
    assert.equal(r.passed, true);
    assert.deepEqual(r.logs, [`[nonhtml-prefix] would block (seed): ${U3} [${KEY}]`]);
});

test("seed + on: refuses and logs blocked", () => {
    const r = expectBlockDecision("on", "seed");
    assert.equal(r.passed, false);
    assert.deepEqual(r.logs, [`[nonhtml-prefix] blocked (seed): ${U3} [${KEY}]`]);
});

test("probe: passes in both modes and logs probe", () => {
    for (const mode of ["shadow", "on"] as const) {
        const g = withProbation(mode);
        assert.equal(g.gate.check(U1, "enqueue"), true);
        assert.deepEqual(g.logs, [`[nonhtml-prefix] probe (enqueue): ${U1} [${KEY}]`]);
    }
});

test("allow: unknown prefix passes without any log", () => {
    const g = learned("on");
    assert.equal(g.gate.check("https://h.fr/produits/p1", "enqueue"), true);
    assert.equal(g.gate.check("https://h.fr/", "prenav"), true);
    assert.deepEqual(g.logs, []);
});

test("exemption without trailing slash protects both forms", () => {
    const g = learned("on");
    g.gate.addExempt(U3);
    assert.equal(g.gate.check(U3, "prenav"), true);
    assert.equal(g.gate.check(`${U3}/`, "prenav"), true);
    assert.deepEqual(g.logs, []);
    // control: a non-exempt sibling is still blocked
    assert.equal(g.gate.check("https://h.fr/image/a4", "prenav"), false);
    assert.equal(g.logs.length, 1);
});

test("exemption with trailing slash protects both forms", () => {
    const g = learned("on");
    g.gate.addExempt(`${U3}/`);
    assert.equal(g.gate.check(U3, "seed"), true);
    assert.equal(g.gate.check(`${U3}/`, "seed"), true);
    assert.deepEqual(g.logs, []);
});

test("exemptCount counts distinct normalized URLs", () => {
    const g = makeGate("on");
    assert.equal(g.gate.exemptCount(), 0);
    g.gate.addExempt(U3);
    g.gate.addExempt(`${U3}/`);
    g.gate.addExempt(U1);
    assert.equal(g.gate.exemptCount(), 2);
});

test("onNonHtml learned: logs the learned prefix and persists", () => {
    const g = makeGate("shadow");
    g.gate.onNonHtml(U1); // below K: isolated, persists without log
    assert.deepEqual(g.logs, []);
    g.gate.onNonHtml(U2); // K reached: learned
    assert.deepEqual(g.logs, [`Non-HTML prefix learned: ${KEY} (n=2)`]);
    assert.equal(g.persisted.length, 2);
});

test("onNonHtml counted: neither logs nor persists", () => {
    const g = learned("on");
    g.gate.onNonHtml(U3); // already blocking: counted
    assert.deepEqual(g.logs, []);
    assert.equal(g.persisted.length, 0);
});

test("onNonHtml confirmed (probation): logs and persists", () => {
    const g = withProbation("on");
    g.gate.onNonHtml(U1);
    assert.deepEqual(g.logs, [`Non-HTML prefix confirmed by probe: ${KEY} (n=6)`]);
    assert.equal(g.persisted.length, 1);
});

test("onNonHtml isolated (no folder key): persists without log", () => {
    const g = makeGate("on");
    g.gate.onNonHtml(ISOLATED);
    assert.deepEqual(g.logs, []);
    assert.equal(g.persisted.length, 1);
    assert.ok(g.persisted[0].includes(ISOLATED));
});

test("onHtml released: logs the release and persists", () => {
    const g = learned("shadow");
    g.gate.onHtml(U3);
    assert.deepEqual(g.logs, [`Non-HTML prefix released: ${KEY} (n=2)`]);
    assert.equal(g.persisted.length, 1);
    // the veto holds: the prefix no longer blocks
    assert.equal(g.gate.check(U1, "enqueue"), true);
});

test("onProbeFailure: logs without persisting; unrelated URL is silent", () => {
    const g = withProbation("on");
    assert.equal(g.gate.check(U1, "enqueue"), true); // admits U1 as the probe
    g.logs.length = 0;
    g.gate.onProbeFailure(U1);
    assert.deepEqual(g.logs, [`[nonhtml-prefix] probe failed: ${U1} [${KEY}]`]);
    assert.equal(g.persisted.length, 0);
    g.gate.onProbeFailure(U2); // not the admitted probe
    assert.equal(g.logs.length, 1);
});

test("injected now() stamps confirmedAt in the persisted sidecar", () => {
    const g = makeGate("on");
    g.gate.onNonHtml(U1);
    g.gate.onNonHtml(U2);
    const last = g.persisted[g.persisted.length - 1];
    assert.ok(last.includes(`"confirmedAt":"${NOW}"`));
});

test("default now() yields an ISO timestamp", () => {
    const logs: string[] = [];
    const persisted: string[] = [];
    const state = createNonHtmlPrefixState({ ...NONHTML_PREFIX_DEFAULTS, minNonHtml: 1 });
    const gate = new NonHtmlPrefixGate({
        mode: "on",
        state,
        log: (m) => logs.push(m),
        persist: (t) => persisted.push(t),
    });
    gate.onNonHtml(U1);
    assert.match(persisted[persisted.length - 1], /"confirmedAt":"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
});
```

- [ ] **Step 3: Lancer le test — il doit échouer**

Run : `cd <CR> && node --import tsx --test src/nonHtmlPrefixGate.test.ts`
Attendu : échec, module `./nonHtmlPrefixGate.js` introuvable (`ERR_MODULE_NOT_FOUND`), `ℹ fail` ≥ 1.

- [ ] **Step 4: Implémenter la gate**

Create `<CR>/src/nonHtmlPrefixGate.ts` :

```ts
import {
    decide,
    normalizeUrlIdentity,
    prefixKey,
    recordHtml,
    recordNonHtml,
    recordProbeFailure,
} from "./nonHtmlPrefix.js";
import type { NonHtmlPrefixState } from "./nonHtmlPrefix.js";
import { serializeNonHtmlPrefixState } from "./nonHtmlPrefixSidecar.js";

export type GatePoint = "enqueue" | "prenav" | "seed";

export interface NonHtmlPrefixGateDeps {
    mode: "shadow" | "on";
    state: NonHtmlPrefixState;
    log: (message: string) => void;
    persist: (serialized: string) => void;
    now?: () => string;
}

/**
 * Applies the NONHTML_PREFIX_MODE policy on top of the pure decisions of nonHtmlPrefix.ts.
 * `check` is synchronous (it runs inside Crawlee's transformRequestFunction) and never
 * touches a counter: the caller increments `filtered_nonhtml` only when it actually drops.
 */
export class NonHtmlPrefixGate {
    readonly mode: "shadow" | "on";
    readonly state: NonHtmlPrefixState;
    private readonly log: (message: string) => void;
    private readonly persist: (serialized: string) => void;
    private readonly now: () => string;
    private readonly exempt = new Set<string>();

    constructor(deps: NonHtmlPrefixGateDeps) {
        this.mode = deps.mode;
        this.state = deps.state;
        this.log = deps.log;
        this.persist = deps.persist;
        this.now = deps.now ?? (() => new Date().toISOString());
    }

    addExempt(url: string): void {
        this.exempt.add(normalizeUrlIdentity(url));
    }

    exemptCount(): number {
        return this.exempt.size;
    }

    /** true = let the URL through. */
    check(url: string, point: GatePoint): boolean {
        const decision = decide(this.state, url, (n) => this.exempt.has(n));
        if (decision === "allow") return true;
        const key = prefixKey(url);
        if (decision === "probe") {
            this.log(`[nonhtml-prefix] probe (${point}): ${url} [${key}]`);
            return true;
        }
        if (this.mode === "on") {
            this.log(`[nonhtml-prefix] blocked (${point}): ${url} [${key}]`);
            return false;
        }
        this.log(`[nonhtml-prefix] would block (${point}): ${url} [${key}]`);
        return true;
    }

    onNonHtml(url: string): void {
        const event = recordNonHtml(this.state, url, this.now());
        const key = prefixKey(url);
        const n = key === null ? 0 : (this.state.prefixes.get(key)?.nonHtml ?? 0);
        if (event === "learned") {
            this.log(`Non-HTML prefix learned: ${key} (n=${n})`);
            this.persist(serializeNonHtmlPrefixState(this.state));
        } else if (event === "confirmed") {
            this.log(`Non-HTML prefix confirmed by probe: ${key} (n=${n})`);
            this.persist(serializeNonHtmlPrefixState(this.state));
        } else if (event === "isolated") {
            this.persist(serializeNonHtmlPrefixState(this.state));
        }
    }

    onHtml(url: string): void {
        const event = recordHtml(this.state, url);
        if (event !== "released") return;
        const key = prefixKey(url);
        const n = key === null ? 0 : (this.state.prefixes.get(key)?.nonHtml ?? 0);
        this.log(`Non-HTML prefix released: ${key} (n=${n})`);
        this.persist(serializeNonHtmlPrefixState(this.state));
    }

    onProbeFailure(url: string): void {
        if (!recordProbeFailure(this.state, url)) return;
        this.log(`[nonhtml-prefix] probe failed: ${url} [${prefixKey(url)}]`);
    }
}
```

- [ ] **Step 5: Lancer le test — il doit passer**

Run : `cd <CR> && node --import tsx --test src/nonHtmlPrefixGate.test.ts`
Attendu : `ℹ tests 19`, `ℹ pass 19`, `ℹ fail 0`.
Si un test échoue sur un compte `n=` ou un nombre de `persist`, relire la sémantique C1 (`recordNonHtml` étapes 4-8 : sous K une URL à clé est `isolated` et persiste ; K atteint ⇒ `learned`) avant de toucher au code : ne pas ajuster l'attendu au résultat.

- [ ] **Step 6: Déclarer le champ dans `context.ts`**

Fichier `<CR>/src/context.ts` : octets mesurés `i/lf w/crlf` ; édition par l'outil Edit, deux insertions, ancres sur ligne entière.
Unicité des ancres (compte de sous-chaîne sur le fichier, mesuré à la rédaction) :
- `import type { CollapseOrigin, CollapseGate } from "./qmConsumptionSkip.js";` ⇒ **1**
- `    facetVariantCount: new Map<string, Set<string>>(),` ⇒ **1**

Re-mesurer avant d'éditer (attendu `1` puis `1`) :
`PYTHONIOENCODING=utf-8 python -I -c "print(open(r'<CR>/src/context.ts',encoding='utf-8',newline='').read().count('import type { CollapseOrigin, CollapseGate } from \"./qmConsumptionSkip.js\";'))"`
`PYTHONIOENCODING=utf-8 python -I -c "print(open(r'<CR>/src/context.ts',encoding='utf-8',newline='').read().count('    facetVariantCount: new Map<string, Set<string>>(),'))"`

Edit 1 — `old_string` :
```
import type { CollapseOrigin, CollapseGate } from "./qmConsumptionSkip.js";
```
`new_string` :
```
import type { CollapseOrigin, CollapseGate } from "./qmConsumptionSkip.js";
import type { NonHtmlPrefixGate } from "./nonHtmlPrefixGate.js";
```

Edit 2 — `old_string` :
```
    facetVariantCount: new Map<string, Set<string>>(),
```
`new_string` :
```
    facetVariantCount: new Map<string, Set<string>>(),
    // R23 (2): non-HTML prefix learning gate. null when NONHTML_PREFIX_MODE=off (default) — zero effect.
    nonHtmlPrefix: null as NonHtmlPrefixGate | null,
```

`import type` : effacé à la compilation, pas de cycle (la gate n'importe pas `context`).

- [ ] **Step 7: Contrôle d'effet sur `context.ts`**

Run (une commande git par appel) :
`git -C <WT> add apps-microservices/crawler-service/crawler/src/context.ts`
`git -C <WT> ls-files --eol -- apps-microservices/crawler-service/crawler/src/context.ts` ⇒ doit rester `i/lf` (un `i/mixed` = lignes LF/CRLF mêlées par l'Edit ⇒ corriger).
`git -C <WT> diff --cached --numstat -- apps-microservices/crawler-service/crawler/src/context.ts` ⇒ `3	0	…context.ts` (3 ajoutées, 0 supprimée).
`git -C <WT> reset -q -- apps-microservices/crawler-service/crawler/src/context.ts` n'est pas nécessaire : le fichier reste indexé pour le commit du Step 9.

- [ ] **Step 8: Suite complète**

Run : `cd <CR> && npm test 2>&1 | tail -12`
Attendu : `ℹ fail 0` et `ℹ pass` = `<PASS_AVANT>` + 19 (19 `test(` ajoutés par T3 : 6 point×mode, probe, allow, 2 exemptions, exemptCount, learned, counted, confirmed, isolated, released, probe failure, `now` injecté, `now` par défaut). Le typage de `context.ts` est exercé par tout test qui l'importe ; une erreur de chemin d'import y échouerait.

- [ ] **Step 9: Commit**

Écrire avec l'outil Write `<scratchpad>/commit-T03.txt` :
```
feat(crawler): add NonHtmlPrefixGate and context.nonHtmlPrefix field (R23)

Class applying NONHTML_PREFIX_MODE (shadow/on) on the pure prefix decisions:
synchronous check() per blocking point (enqueue, prenav, seed), absolute
exemption set, exact log literals, persistence of the sidecar on
learned/confirmed/isolated/released. context.nonHtmlPrefix stays null in
mode off, so nothing is wired yet.

FR — ajouter NonHtmlPrefixGate et le champ context.nonHtmlPrefix (R23)

Classe qui applique NONHTML_PREFIX_MODE (shadow/on) sur les décisions pures
de préfixe : check() synchrone par point de blocage (enqueue, prenav, seed),
ensemble d'exemption absolue, littéraux de log exacts, persistance du sidecar
sur learned/confirmed/isolated/released. context.nonHtmlPrefix reste null en
mode off : rien n'est encore câblé.
```
Puis :
`git -C <WT> add apps-microservices/crawler-service/crawler/src/nonHtmlPrefixGate.ts apps-microservices/crawler-service/crawler/src/nonHtmlPrefixGate.test.ts apps-microservices/crawler-service/crawler/src/context.ts`
`git -C <WT> diff --cached --stat` ⇒ exactement ces 3 fichiers.
`git -C <WT> commit -F <scratchpad>/commit-T03.txt`
### Task 4: Câblage `main.ts` (init, exemption, b2, compteur)
> NOMS NEUFS : skippedNonHtmlCount (produit) ⇒ T04, filtered_nonhtml (produit : variable `readStat` + clé de payload) ⇒ T04, nonHtmlPrefixMode (produit) ⇒ T04 ; resolveNonHtmlPrefixMode, resolveNonHtmlPrefixParams, createNonHtmlPrefixState (consommés) ⇒ T01 ; currentSidecarPath, loadSidecarInto, parseNonHtmlPrefixSidecar, readSidecarFile, resolvePreviousSidecarPath, writeSidecarFile (consommés) ⇒ T02 ; NonHtmlPrefixGate, `context.nonHtmlPrefix` (consommés) ⇒ T03

**Blocked by:** 3

**Goal:** Câbler `main.ts` pour que, hors mode `off`, le gate soit construit et chargé (sidecar courant puis précédent), que les URLs du dataset précédent soient exemptées, que le ré-amorçage Phase 2 (b2) bloque les URLs de préfixes appris, et que le compteur `filtered_nonhtml` soit lu et publié dans le payload (clé absente en `off`).

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts`

**Acceptance Criteria:**
- [ ] `main.ts` importe `./nonHtmlPrefix.js`, `./nonHtmlPrefixSidecar.js`, `./nonHtmlPrefixGate.js` (noms exacts de C1/C2/C3, forme des imports voisins).
- [ ] Le bloc C8 suit `ensureUnjudgedSidecar(domain);` ; `"current"` est chargé avant `"previous"`.
- [ ] `if (source === 'dataset') context.nonHtmlPrefix?.addExempt(consolidatedUrl);` précède `remainingUrls.push(` dans la boucle F10 ; le log `[nonhtml-prefix] exempt URLs:` suit la boucle.
- [ ] b2 : `addExempt(seedUrl)` (dataset) puis `check(seedUrl, "seed")`, `continue` + `increment("filtered_nonhtml")` sous `if (context.nonHtmlPrefix)`, placé AVANT l'`addRequest` de seedPhase2 ; log `[seed-filter] skipped … non-HTML-prefix baseline URL(s) (filtered_nonhtml)` si > 0.
- [ ] `readStat("filtered_nonhtml")` et `...(context.nonHtmlPrefix ? { filtered_nonhtml } : {}),` présents ; aucune clé `filtered_nonhtml` non conditionnelle dans le payload.
- [ ] `git -C <WT> ls-files --eol -- apps-microservices/crawler-service/crawler/src/main.ts` reste `i/lf` après `git add` ; `git -C <WT> diff --cached --numstat -- <main.ts>` : 0 ligne supprimée (insertions pures).
- [ ] `npx tsc --noEmit` : aucune erreur NOUVELLE par rapport à la mesure de base `<TSC_BASE>` ; suite complète `ℹ fail 0` et `ℹ pass <PASS_T03>` (T4 ajoute 0 test).

**Verify:** `cd <CR> && npm test 2>&1 | tail -12`

**Steps:**

- [ ] **Step 1: Mesures de départ (aucune écriture)**

`package.json` : `"build": "tsc"`, pas de script de typecheck dédié ; `tsconfig.json` (`include ./src/**/*`, extends `@apify/tsconfig`) permet `npx tsc --noEmit` depuis `<CR>`. Mesurer la base AVANT d'éditer (T1-T3 sont commités, leurs modules existent) :

```bash
cd <CR> && ls src/nonHtmlPrefix.ts src/nonHtmlPrefixSidecar.ts src/nonHtmlPrefixGate.ts
```
Attendu : les trois fichiers listés (sinon STOP : T3 n'est pas fait).

```bash
cd <CR> && npx tsc --noEmit 2>&1 | tail -5
```
Consigner le nombre de lignes `error TS` en `<TSC_BASE>` (idéalement 0 ; sinon l'implémenteur compare ensuite le NOMBRE et la liste des fichiers en erreur).

```bash
cd <CR> && npm test 2>&1 | tail -12
```
Attendu : `ℹ fail 0` ; consigner `ℹ pass` en `<PASS_T03>` (509 + tests neufs de T1-T3). T4 ne doit pas le changer.

```bash
git -C <WT> ls-files --eol -- apps-microservices/crawler-service/crawler/src/main.ts
```
Attendu : `i/lf    w/crlf`.

- [ ] **Step 2: Faits relevés dans `main.ts` (base `e57409aed`), à re-localiser par contenu**

| Question | Réponse | Preuve |
|---|---|---|
| Type de `domain` au point d'init | `export const domain = getArg(...)` = `string \| undefined`, mais rétréci en `string` après `if (!id \|\| !domain \|\| !site …) { … process.exit(1); }` (`main.ts:180-183`, `process.exit` est `never`) ; `site` idem | `main.ts:94-95`, `:180-183` ; `ensureUnjudgedSidecar(domain)` accepte `string \| undefined` (`unjudgedUrls.ts:66`) donc n'est PAS une preuve de rétrécissement |
| Garde `if (domain)` nécessaire ? | Non attendu. **Si** `tsc` signale TS2345 sur `currentSidecarPath(domain)` ou `addExempt(site)`, envelopper le bloc C8 dans `if (domain && site) { … }` | tranché par `tsc` (Step 6) |
| `source` en portée en seedPhase2 ? | OUI : `for (const { url, source } of remainingUrls) {` | `main.ts:1561` |
| `continue` légal en b2 ? | OUI : boucle `for … of` ; le `continue` voisin de `filtered_ext` est dans la même boucle | `main.ts:1561`, `:1578` (`continue;` du bloc `hasIgnoredExtensionForSeed`) |
| Forme de `increment` | `if (context.statsManager) { await context.statsManager.increment("filtered_ext"); }` | `main.ts:1575-1577` ; autre forme `main.ts:969-971` (`increment("filtered_duplicate", n)`) |
| Boucle F10 atteinte quand ? | Branche `if (crawlMode === 'update') {` seulement ; l'init C8, elle, est au niveau racine (tous modes) | `main.ts:897`, `:961` |
| `crawlMode` / `previousCrawlId` / `site` déclarés avant l'init | OUI | `main.ts:95`, `:118`, `:120` (init à `:619`) |
| Aucun nom neuf ne collisionne | `nonHtmlPrefix`, `filtered_nonhtml`, `skippedNonHtmlCount` : 0 occurrence dans `main.ts` (compte de sous-chaîne) | Step 3 |

- [ ] **Step 3: Prouver l'unicité de chaque ancre Edit (compte de sous-chaîne = 1)**

Écrire d'abord ce script avec l'outil Write dans `<scratchpad>/anchors-T04.py` (jamais en `python -c`, il contient des backticks et des accents) :

```python
# <scratchpad>/anchors-T04.py
import sys
t = open(sys.argv[1], encoding="utf-8", newline="").read()
anchors = [
    'import { hasIgnoredExtensionForSeed } from "./seedExtensionFilter.js";',
    "ensureUnjudgedSidecar(domain);",
    "remainingUrls.push({ url: consolidatedUrl, source });",
    "const totalConsolidated = remainingUrls.length + 1; // +1 for homepage",
    "let skippedExtCount = 0;",
    "// Épinglage de l'identité de file, comme Phase 1 (:952) et l'amorce standard",
    "console.log(`[seed-filter] skipped ${skippedExtCount} ignored-extension baseline URL(s) (filtered_ext)`);",
    'const filtered_ext = await readStat("filtered_ext");',
    "        filtered_ext,",
]
for a in anchors:
    print(t.count(a), repr(a))
for n in ["nonHtmlPrefix", "filtered_nonhtml", "skippedNonHtmlCount"]:
    print(t.count(n), "(nouveau nom, attendu 0 avant édition)", n)
```

```bash
PYTHONIOENCODING=utf-8 python -I <scratchpad>/anchors-T04.py <CR>/src/main.ts
```
Attendu (mesuré en rédaction sur la base `e57409aed`) : `1` pour chacune des 9 ancres, `0` pour les 3 noms neufs. Un compte ≠ 1 ⇒ STOP, rapporter. Toutes les ancres sont des SOUS-CHAÎNES d'une seule ligne (le fichier est `w/crlf` : une ancre multi-lignes ne matcherait pas) ; l'indentation initiale de la ligne reste devant l'ancre et n'est pas à retaper.

- [ ] **Step 4: Éditions (outil Edit, `replace_all` faux, 8 éditions)**

Fichier : `<CR>/src/main.ts`. Chaque `new_string` COMMENCE par l'ancre intacte (insertion pure : 0 ligne supprimée).

**4a — imports** (ancre 1, compte 1). `old_string` :
```ts
import { hasIgnoredExtensionForSeed } from "./seedExtensionFilter.js";
```
`new_string` :
```ts
import { hasIgnoredExtensionForSeed } from "./seedExtensionFilter.js";
import { resolveNonHtmlPrefixMode, resolveNonHtmlPrefixParams, createNonHtmlPrefixState } from "./nonHtmlPrefix.js";
import { currentSidecarPath, loadSidecarInto, parseNonHtmlPrefixSidecar, readSidecarFile, resolvePreviousSidecarPath, writeSidecarFile } from "./nonHtmlPrefixSidecar.js";
import { NonHtmlPrefixGate } from "./nonHtmlPrefixGate.js";
```

**4b — init C8** (ancre 2, compte 1 ; le bloc suit `ensureUnjudgedSidecar(domain);`, après le bloc `dropData`). `old_string` :
```ts
ensureUnjudgedSidecar(domain);
```
`new_string` :
```ts
ensureUnjudgedSidecar(domain);

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
(`"current"` d'abord : ordre imposé par C2. Si `tsc` impose le rétrécissement, voir Step 2 : envelopper dans `if (domain && site) {`.)

**4c — exemption dataset, boucle F10** (ancre 3, compte 1 ; ligne à 4 espaces d'indentation dans la boucle). `old_string` :
```ts
remainingUrls.push({ url: consolidatedUrl, source });
```
`new_string` (la 1ʳᵉ ligne reprend l'indentation déjà présente, les suivantes la portent en toutes lettres) :
```ts
if (source === 'dataset') context.nonHtmlPrefix?.addExempt(consolidatedUrl);
        remainingUrls.push({ url: consolidatedUrl, source });
```

**4d — log d'exemption après la boucle** (ancre 4, compte 1). `old_string` :
```ts
const totalConsolidated = remainingUrls.length + 1; // +1 for homepage
```
`new_string` :
```ts
if (context.nonHtmlPrefix) {
        console.log(`[nonhtml-prefix] exempt URLs: ${context.nonHtmlPrefix.exemptCount()}`);
    }

    const totalConsolidated = remainingUrls.length + 1; // +1 for homepage
```
(Le log s'insère juste après la fermeture `}` de la boucle F10 ; la ligne vide qui précédait `const totalConsolidated` reste avant `if (context.nonHtmlPrefix)`.)

**4e — compteur local b2** (ancre 5, compte 1). `old_string` :
```ts
let skippedExtCount = 0;
```
`new_string` :
```ts
let skippedExtCount = 0;
            let skippedNonHtmlCount = 0;
```

**4f — b2, juste avant l'`addRequest`** (ancre 6, compte 1 ; le bloc va AVANT le commentaire d'épinglage, donc après le re-nettoyage `processUrl`, `seedUrl` est final). `old_string` :
```ts
// Épinglage de l'identité de file, comme Phase 1 (:952) et l'amorce standard
```
`new_string` :
```ts
// R23 (2) b2: test the identity actually enqueued (seedUrl, after stripActionAnchor and
                // the queue-purge re-clean). A dataset URL is exempted under that same form, or b3
                // would test it under a string absent from the exemption Set.
                if (context.nonHtmlPrefix) {
                    if (source === 'dataset') context.nonHtmlPrefix.addExempt(seedUrl);
                    if (!context.nonHtmlPrefix.check(seedUrl, "seed")) {
                        skippedNonHtmlCount++;
                        if (context.statsManager) {
                            await context.statsManager.increment("filtered_nonhtml");
                        }
                        continue;
                    }
                }

                // Épinglage de l'identité de file, comme Phase 1 (:952) et l'amorce standard
```

**4g — log de fin de seedPhase2** (ancre 7, compte 1). La ligne ancre est suivie de `            }` (fermeture du `if (skippedExtCount > 0)`) : on rouvre un `if` après cette fermeture en réutilisant ce `}` comme fermeture du NOUVEAU bloc. `old_string` :
```ts
console.log(`[seed-filter] skipped ${skippedExtCount} ignored-extension baseline URL(s) (filtered_ext)`);
```
`new_string` :
```ts
console.log(`[seed-filter] skipped ${skippedExtCount} ignored-extension baseline URL(s) (filtered_ext)`);
            }
            if (skippedNonHtmlCount > 0) {
                console.log(`[seed-filter] skipped ${skippedNonHtmlCount} non-HTML-prefix baseline URL(s) (filtered_nonhtml)`);
```
(le `}` d'origine qui suivait ferme maintenant le second `if`.)

**4h — `readStat` et payload** (ancres 8 et 9, comptes 1 et 1). Deux Edit séparés.
`old_string` :
```ts
const filtered_ext = await readStat("filtered_ext");
```
`new_string` :
```ts
const filtered_ext = await readStat("filtered_ext");
    const filtered_nonhtml = await readStat("filtered_nonhtml");
```
`old_string` (8 espaces + nom + virgule ; seule occurrence, compte 1) :
```ts
        filtered_ext,
```
`new_string` :
```ts
        filtered_ext,
        ...(context.nonHtmlPrefix ? { filtered_nonhtml } : {}),
```
(spread conditionnel C7 : en `off`, la clé n'existe pas dans le JSON du webhook.)

- [ ] **Step 5: Contrôles d'effet des octets (après les éditions)**

```bash
git -C <WT> add apps-microservices/crawler-service/crawler/src/main.ts
```
```bash
git -C <WT> ls-files --eol -- apps-microservices/crawler-service/crawler/src/main.ts
```
Attendu : `i/lf    w/crlf` (un `i/mixed` ⇒ corriger les lignes LF insérées).
```bash
git -C <WT> diff --cached --numstat -- apps-microservices/crawler-service/crawler/src/main.ts
```
Attendu : `<N>	0	…main.ts` avec **0 ligne supprimée** (N ≈ 61 ; seul le zéro est exigé). Une suppression ≠ 0 ⇒ une éditions a consommé une ligne : la rétablir.

Relire le diff des 8 insertions : `git -C <WT> diff --cached -U2 -- apps-microservices/crawler-service/crawler/src/main.ts` (≈ 150 lignes) ; vérifier visuellement que 4g n'a pas rompu l'accolade (deux `if` consécutifs, fermés).

- [ ] **Step 6: Typecheck et suite complète**

```bash
cd <CR> && npx tsc --noEmit 2>&1 | tail -5
```
Attendu : nombre d'`error TS` = `<TSC_BASE>` (aucune erreur dans `main.ts` attribuable à ce lot). Une erreur TS2345 sur `domain`/`site` ⇒ appliquer la garde de Step 2 et refaire Step 5.

```bash
cd <CR> && node --import tsx --test src/statNameParity.test.ts
```
Attendu : `ℹ fail 0` (fichier existant, inchangé ; il lit `main.ts` en texte).

```bash
cd <CR> && npm test 2>&1 | tail -12
```
Attendu : `ℹ fail 0` et `ℹ pass <PASS_T03>` (T4 ajoute 0 `test(` : parité texte-source en T7). Un `pass` différent ⇒ STOP.

Mode `off` : aucun test ne définit `NONHTML_PREFIX_MODE` ⇒ `context.nonHtmlPrefix` reste `null`, chaque point inséré est un no-op (`?.` / `if (context.nonHtmlPrefix)`), payload sans la clé.

- [ ] **Step 7: Commit**

Écrire `<scratchpad>/commit-T04.txt` avec l'outil Write :
```text
feat(crawler): wire non-HTML prefix gate into main.ts (R23)

Init the NonHtmlPrefixGate behind NONHTML_PREFIX_MODE (off by default,
zero effect): load current then previous sidecar, exempt the homepage and
every previous-dataset URL, block learned prefixes at the phase-2 re-seed
(b2) on the enqueued identity (seedUrl), and publish filtered_nonhtml in
the webhook payload only when the gate exists. Insertions only.

FR — câbler la barrière des préfixes non-HTML dans main.ts (R23)

Initialise NonHtmlPrefixGate derrière NONHTML_PREFIX_MODE (off par
défaut, effet nul) : charge le sidecar courant puis le précédent, exempte
la page d'accueil et toutes les URLs du dataset précédent, bloque les
préfixes appris au ré-amorçage de la phase 2 (b2) sur l'identité enfilée
(seedUrl), et publie filtered_nonhtml dans le payload seulement si la
barrière existe. Insertions pures.
```
```bash
git -C <WT> diff --cached --stat
```
Attendu : exactement `apps-microservices/crawler-service/crawler/src/main.ts`.
```bash
git -C <WT> commit -F <scratchpad>/commit-T04.txt
```
### Task 5: Câblage `routes.ts` (apprentissages, b1)
> NOMS NEUFS : `'nonhtml-prefix'` (raison `logBlocked`) (produit) ⇒ T05 ; `NonHtmlPrefixGate` / `context.nonHtmlPrefix` (consommé, C3/C4) ⇐ T03

**Blocked by:** 3

**Goal:** Câbler dans `routes.ts` les deux points d'apprentissage (non-HTML, HTML) et le point de blocage b1 (enfilage), tous no-op quand `context.nonHtmlPrefix` est `null`.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/routes.ts`

**Acceptance Criteria:**
- [ ] `context.nonHtmlPrefix?.onNonHtml(request.url);` figure une fois, immédiatement avant `log.warning(\`Skipping non-HTML response:`, donc après le `pushData` du dataset pdf et avant le `return;`.
- [ ] `if (response) context.nonHtmlPrefix?.onHtml(request.url);` figure une fois, immédiatement avant `// --- Circuit Breaker Check (Dual-Mode) ---`.
- [ ] Le bloc b1 (`check(request.url, "enqueue")`, `logBlocked('nonhtml-prefix', request.url)`, `increment("filtered_nonhtml")`, `return false;`) figure une fois, entre le bloc facet cap et `// Queue-purge #2: filter-on-seen-base`, et reste synchrone (aucun `await`).
- [ ] `git diff --numstat` sur `routes.ts` : 0 ligne supprimée ; `ls-files --eol` reste `i/lf` ; aucun `*.test.ts` modifié.
- [ ] `npx tsc --noEmit` sort en code 0 ; la suite complète donne `ℹ fail 0` et `ℹ pass` inchangé par T5 (T5 ajoute 0 test).

**Verify:** `cd <CR> && npx tsc --noEmit`

**Steps:**

Faits lus à la rédaction (base `e57409aed`, `routes.ts`, à re-localiser par CONTENU à l'exécution) :
- `:309` `const logBlocked = (reason: string, url: string) => {` : le 1ᵉʳ argument est un `string`, pas une union ⇒ **aucun ajout de type** pour `'nonhtml-prefix'`.
- `:1117` `transformRequestFunction: (request) => {` : `request` est la requête candidate (`request.url` lu aux `:1119`, `:1239`, `:1244`, et réécrit par l'action-anchor strip `:1128-1130`) ⇒ `request.url` est l'identité enfilée. La fonction doit rester synchrone ; aucun `increment` n'y existait : le patron `void … .catch(() => {})` est neuf ici (il garde la fonction synchrone).
- `:396` `if (response) {` fermé `:445`, `:399-443` lève sur toute classe non-`ok`, `response` est un paramètre optionnel (`:215`) ⇒ `:447` est atteint par une réponse `ok` ET par `response` falsy ⇒ garde `if (response)` obligatoire pour le point HTML. Les `return` des `:328-357` précèdent `:360` ; le `return` de `:387` précède `:391`.
- Ancres (compte de sous-chaîne, `python -I`, sur le fichier de la base) : `` log.warning(`Skipping non-HTML response: `` = 1 ; `        // --- Circuit Breaker Check (Dual-Mode) ---` (8 espaces) = 1 ; `                        // Queue-purge #2: filter-on-seen-base` (24 espaces) = 1.
- `routes.ts` est `i/lf w/crlf` : édition à l'outil Edit, une ancre d'UNE ligne par édition.

- [ ] **Step 1: Pré-contrôles (ancres, base, gate présent)**

Run (un appel par commande git) :
`git -C <WT> log --oneline -3`
`git -C <WT> ls-files --eol -- apps-microservices/crawler-service/crawler/src/routes.ts`
Attendu : `i/lf    w/crlf`. Puis, pour chacune des trois ancres :
`PYTHONIOENCODING=utf-8 python -I -c "import sys;print(open(sys.argv[1],encoding='utf-8',newline='').read().count(sys.argv[2]))" <CR>/src/routes.ts "<ancre>"`
avec les ancres `log.warning(` + `` `Skipping non-HTML response: ``, `        // --- Circuit Breaker Check (Dual-Mode) ---` et `                        // Queue-purge #2: filter-on-seen-base`. Attendu : `1` trois fois (autre valeur ⇒ STOP, rapporter).
Vérifier aussi que T3 est en place : `grep -n "nonHtmlPrefix" <CR>/src/context.ts` doit rendre au moins une ligne (le champ C4) ; sinon STOP (T3 non fait).

- [ ] **Step 2: Apprendre non-HTML**

Outil Edit sur `<CR>/src/routes.ts` :
`old_string` (une ligne, sans l'indentation de tête) :
```
log.warning(`Skipping non-HTML response: ${url} (Content-Type: ${contentType})`);
```
`new_string` (la 2ᵉ ligne porte 16 espaces) :
```
context.nonHtmlPrefix?.onNonHtml(request.url);
                log.warning(`Skipping non-HTML response: ${url} (Content-Type: ${contentType})`);
```

- [ ] **Step 3: Apprendre HTML (garde `if (response)`)**

Outil Edit sur `<CR>/src/routes.ts` :
`old_string` (ligne entière, 8 espaces de tête) :
```
        // --- Circuit Breaker Check (Dual-Mode) ---
```
`new_string` :
```
        // R23 (2): learn HTML. Reached by an `ok`-class response AND by a missing response
        // (response is optional): the guard keeps "no response" from vetoing a prefix.
        if (response) context.nonHtmlPrefix?.onHtml(request.url);

        // --- Circuit Breaker Check (Dual-Mode) ---
```

- [ ] **Step 4: b1 (enfilage)**

Outil Edit sur `<CR>/src/routes.ts` :
`old_string` (ligne entière, 24 espaces de tête) :
```
                        // Queue-purge #2: filter-on-seen-base — drop a discovered variant whose
```
`new_string` (indentation 24 espaces conservée ; ligne vide avant et après le bloc) :
```
                        // R23 (2): non-HTML prefix gate (b1). Synchronous on purpose: the counter
                        // is fire-and-forget (void … .catch) so transformRequestFunction stays sync.
                        if (context.nonHtmlPrefix && !context.nonHtmlPrefix.check(request.url, "enqueue")) {
                            logBlocked('nonhtml-prefix', request.url);
                            if (context.statsManager) void context.statsManager.increment("filtered_nonhtml").catch(() => {});
                            return false;
                        }

                        // Queue-purge #2: filter-on-seen-base — drop a discovered variant whose
```
Si l'ancre `old_string` ci-dessus (ligne entière) ne correspond pas à cause de la suite de la ligne, n'utiliser que `// Queue-purge #2: filter-on-seen-base` (compte 1) et reporter l'insertion avant elle avec la même indentation.

- [ ] **Step 5: Contrôles d'effet (octets et diff)**

Run :
`git -C <WT> diff --numstat -- apps-microservices/crawler-service/crawler/src/routes.ts`
Attendu : `<N>	0	…` (0 supprimée ; N = lignes insérées, 14 environ).
`git -C <WT> diff -U0 -- apps-microservices/crawler-service/crawler/src/routes.ts`
Attendu : uniquement des lignes `+` (aucune ligne `-`), les trois insertions aux emplacements ci-dessus.
Après `git -C <WT> add apps-microservices/crawler-service/crawler/src/routes.ts` : `git -C <WT> ls-files --eol -- apps-microservices/crawler-service/crawler/src/routes.ts` doit rendre `i/lf`. Un `i/mixed` ⇒ corriger les fins de ligne des lignes insérées avant de poursuivre.

- [ ] **Step 6: Typecheck**

Run : `cd <CR> && npx tsc --noEmit`
Attendu : aucune sortie, code 0.

- [ ] **Step 7: Suite complète**

Run : `cd <CR> && npm test 2>&1 | tail -12`
Attendu : `ℹ fail 0` et `ℹ pass` = 509 + tests neufs de T1 à T4 (T5 en ajoute 0). Mode `off` par défaut ⇒ aucun test existant ne change.

- [ ] **Step 8: Commit**

Écrire `<scratchpad>/commit-T05.txt` avec l'outil Write :
```
feat(crawler): wire non-HTML prefix learning and enqueue gate in routes (R23)

Learn non-HTML responses before the content-type skip, learn HTML on
ok-class responses only (guarded by `if (response)`), and block queued
candidates at enqueue (b1) with the filtered_nonhtml counter. No-op when
context.nonHtmlPrefix is null (NONHTML_PREFIX_MODE=off, default).

FR — câbler l'apprentissage des préfixes non-HTML et le blocage à l'enfilage dans routes (R23)

Apprend les réponses non-HTML avant le saut content-type, apprend le HTML
sur les seules réponses de classe ok (garde `if (response)`), et bloque les
candidats à l'enfilage (b1) avec le compteur filtered_nonhtml. Sans effet
quand context.nonHtmlPrefix vaut null (mode off, par défaut).
```
Puis :
`git -C <WT> add apps-microservices/crawler-service/crawler/src/routes.ts`
`git -C <WT> diff --cached --stat` (attendu : exactement `routes.ts`)
`git -C <WT> commit -F <scratchpad>/commit-T05.txt`
### Task 6: Câblage `functions.ts` (b3, échec de sonde)
> NOMS NEUFS : aucun

**Blocked by:** 3

**Goal:** Ajouter à `functions.ts` le point de blocage b3 (nouveau hook de pré-navigation qui lève `StaleVariantSkip` quand la gate refuse l'URL) et le point « échec de sonde » (`failedRequestHandler` appelle `onProbeFailure`), sans aucun effet en mode `off`.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/functions.ts`

**Acceptance Criteria:**
- [ ] `functions.ts` contient exactement une fois chacun : `context.nonHtmlPrefix.check(request.url, "prenav")`, `increment("filtered_nonhtml")`, `context.nonHtmlPrefix?.onProbeFailure(request.url);` (comptes de sous-chaîne, Step 4).
- [ ] Le nouveau hook est le dernier élément de `preNavigationHooks`, inséré APRÈS la fermeture `},` du hook facet cap / filter-on-seen (celui dont la dernière instruction est `throw new StaleVariantSkip(request.url, target);`, `functions.ts:894-896` à la base `e57409aed`) et AVANT `],` de `preNavigationHooks`.
- [ ] `context` est le singleton de module importé en tête (`functions.ts:25`, `import { context } from "./context.js";`) : aucun import neuf n'est nécessaire (`StaleVariantSkip` est déjà importé, `functions.ts:50`).
- [ ] Un blocage b3 n'appelle PAS `onProbeFailure` : le `throw new StaleVariantSkip` est terminal (`NonRetryableError`, `staleVariantSkip.ts:18` ; `_canRequestBeRetried` renvoie `false`, `node_modules/@crawlee/basic/internals/basic-crawler.js:1329-1331`), `failedRequestHandler` le reconnaît par `STALE_VARIANT_SKIP_MARKER` et fait `return;` (`functions.ts:601-604`) AVANT la ligne insérée pour la sonde (qui précède `log.error(` `functions.ts:606`).
- [ ] Mode `off` : `context.nonHtmlPrefix` vaut `null` ⇒ le hook sort sans rien faire et l'appel `?.` est un no-op.
- [ ] Octets : `git -C <WT> ls-files --eol -- apps-microservices/crawler-service/crawler/src/functions.ts` affiche `i/crlf  w/crlf` après édition ET après `git add` ; nombre de `\n` non précédés de `\r` = 0 ; `git diff --numstat` : 0 ligne supprimée.
- [ ] Suite complète : `ℹ fail 0` et `ℹ pass` = `<PASS_AVANT>` (inchangé : T6 ajoute 0 `test(`) ; `tsc --noEmit` n'ajoute aucune erreur par rapport à `<TSC_AVANT>`.

**Verify:** `cd <CR> && npm test 2>&1 | tail -12`

**Steps:**

- [ ] **Step 1: Mesurer l'état de départ (aucune édition)**

  Prérequis : T3 commité (`context.ts` porte `nonHtmlPrefix`, `nonHtmlPrefixGate.ts` existe).

  ```bash
  git -C <WT> log --oneline -8
  grep -n "nonHtmlPrefix" <CR>/src/context.ts
  grep -n "check(url: string, point\|onProbeFailure" <CR>/src/nonHtmlPrefixGate.ts
  cd <CR> && npm test 2>&1 | tail -12
  cd <CR> && npx tsc --noEmit 2>&1 | grep -c "error TS"
  git -C <WT> ls-files --eol -- apps-microservices/crawler-service/crawler/src/functions.ts
  ```

  Attendu : `context.ts` contient `nonHtmlPrefix: null as NonHtmlPrefixGate | null,` ; la gate expose `check` et `onProbeFailure` ; `ℹ fail 0` — consigne `<PASS_AVANT>` = la valeur de `ℹ pass` ; `grep -c` de tsc : consigne `<TSC_AVANT>` (peut valoir 0 ou un nombre préexistant ; seule la non-augmentation compte) ; `i/crlf  w/crlf`. Sortie différente (T3 absent, `i/mixed`) ⇒ STOP, rapporter.

- [ ] **Step 2: Localiser par contenu et prouver l'unicité des ancres**

  À la base `e57409aed` les ancres sont aux lignes ci-dessous ; à l'exécution, localiser par contenu.

  ```bash
  grep -n "recordQmCollapsed(request.url, target, 'filter_on_seen', 'prenav');" <CR>/src/functions.ts
  grep -n "^        postNavigationHooks: \[" <CR>/src/functions.ts
  grep -n "STALE_VARIANT_SKIP_MARKER))" <CR>/src/functions.ts
  grep -n "log.error(\`Request \${request.url} failed:" <CR>/src/functions.ts
  ```

  Attendu (base) : `893:`, `899:`, `601:`, `606:`. Relire `awk 'NR>=880 && NR<=900 {printf "%d: %s\n", NR, $0}' <CR>/src/functions.ts` : la fin du hook facet cap est la ligne `            },` (base `:896`), suivie de `        ],` (base `:897`), d'une ligne vide, puis `        postNavigationHooks: [`.

  Comptes de sous-chaîne (mesurés à la rédaction sur la base, tous attendus = 1) :

  ```bash
  PYTHONIOENCODING=utf-8 python -I -c "s=open(r'<CR>/src/functions.ts',encoding='utf-8',newline='').read(); print(s.count('        postNavigationHooks: ['), s.count('            log.error(\`Request \${request.url} failed:'), s.count('                    throw new StaleVariantSkip(request.url, target);\r\n                }\r\n            },\r\n        ],\r\n\r\n        postNavigationHooks: ['))"
  ```

  Attendu : `1 1 1`.

  Propriété du point d'insertion b3 (lue, base) : `preNavigationHooks` est la liste des `functions.ts:800-897` ; un hook qui lève `StaleVariantSkip` y est le patron existant (`:878`, `:887`, `:894`) ; `context` est le singleton importé `functions.ts:25` (aucune portée locale à vérifier : les hooks voisins l'utilisent tel quel, `:874`, `:885`).

- [ ] **Step 3: Insérer b3 (outil Edit, ancre intacte)**

  Outil Edit sur `<CR>/src/functions.ts`. L'ancre est la fin du hook facet cap jusqu'à `postNavigationHooks: [` (unique, compte 1). Les lignes insérées doivent être en CRLF (le fichier est `i/crlf`).

  `old_string` :

  ```ts
                      throw new StaleVariantSkip(request.url, target);
                  }
              },
          ],

          postNavigationHooks: [
  ```

  `new_string` :

  ```ts
                      throw new StaleVariantSkip(request.url, target);
                  }
              },
              // R23 (2) b3: non-HTML prefix gate. Drops a request whose parent folder was
              // learned (or loaded from the previous crawl) as non-HTML-only, BEFORE
              // page.goto. Only mode "on" returns false from check(); "shadow" only logs.
              // A thrown StaleVariantSkip is terminal (NonRetryableError) and handled by the
              // STALE_VARIANT_SKIP_MARKER branch of failedRequestHandler (counts purged_prenav,
              // returns before onProbeFailure). Zero effect when context.nonHtmlPrefix is null.
              async ({ request }) => {
                  if (context.nonHtmlPrefix && !context.nonHtmlPrefix.check(request.url, "prenav")) {
                      if (context.statsManager) await context.statsManager.increment("filtered_nonhtml");
                      throw new StaleVariantSkip(request.url, request.url);
                  }
              },
          ],

          postNavigationHooks: [
  ```

  Si l'outil Edit refuse l'ancre multi-lignes (fins de ligne CRLF non appariées) : ne PAS passer en `w` texte ; utiliser le repli binaire, script écrit avec Write dans `<scratchpad>/t06_insert_b3.py` (jamais `python -c`), qui lit en `rb`, vérifie `count == 1` de l'ancre en CRLF, insère le bloc avec `\r\n`, réécrit en `wb`, puis relancer les contrôles du Step 5.

- [ ] **Step 4: Insérer l'échec de sonde (outil Edit, ancre d'une ligne)**

  Outil Edit sur `<CR>/src/functions.ts`. `old_string` (une ligne, compte 1, Step 2) :

  ```ts
              log.error(`Request ${request.url} failed: ${String(request.errorMessages)}`);
  ```

  `new_string` :

  ```ts
              // R23 (2): a probe admitted by the non-HTML prefix gate ended terminally (timeout or
              // error, after the capped retries). Reached only for non-StaleVariantSkip failures:
              // the marker branch above has already returned. No-op when the gate is null.
              context.nonHtmlPrefix?.onProbeFailure(request.url);

              log.error(`Request ${request.url} failed: ${String(request.errorMessages)}`);
  ```

  Comptes de sous-chaîne après les deux insertions (chacun attendu = 1) :

  ```bash
  PYTHONIOENCODING=utf-8 python -I -c "s=open(r'<CR>/src/functions.ts',encoding='utf-8',newline='').read(); print(s.count('context.nonHtmlPrefix.check(request.url, \"prenav\")'), s.count('increment(\"filtered_nonhtml\")'), s.count('context.nonHtmlPrefix?.onProbeFailure(request.url);'))"
  ```

  Attendu : `1 1 1`.

- [ ] **Step 5: Contrôle de fins de ligne et de diff (AVANT `git add`, puis après)**

  ```bash
  PYTHONIOENCODING=utf-8 python -I -c "b=open(r'<CR>/src/functions.ts','rb').read(); print(b.count(b'\n')-b.count(b'\r\n'))"
  git -C <WT> ls-files --eol -- apps-microservices/crawler-service/crawler/src/functions.ts
  git -C <WT> diff --numstat -- apps-microservices/crawler-service/crawler/src/functions.ts
  ```

  Attendu : `0` (aucun `\n` sans `\r`) ; `i/crlf  w/crlf` ; numstat `16	0	…` (16 lignes ajoutées en tout : 11 pour b3, 5 pour la sonde — le compte exact dépend des lignes de commentaire ; l'invariant est **la colonne des suppressions = 0**). Un `i/mixed`, un compte ≠ 0 ou une suppression ⇒ corriger (lignes LF insérées) avant d'avancer.

- [ ] **Step 6: Vérifier le typage et la suite complète**

  ```bash
  cd <CR> && npx tsc --noEmit 2>&1 | grep -c "error TS"
  cd <CR> && npm test 2>&1 | tail -12
  ```

  Attendu : compte tsc ≤ `<TSC_AVANT>` et aucune erreur citant `functions.ts` ou `nonHtmlPrefix` ; `ℹ fail 0` et `ℹ pass` = `<PASS_AVANT>` (T6 ajoute 0 test ; le câblage est testé par T7).

- [ ] **Step 7: Commit**

  Écrire `<scratchpad>/commit-T06.txt` avec l'outil Write :

  ```text
  feat(crawler): wire non-HTML prefix gate into prenav hook and probe failure (R23)

  Add a last preNavigationHook that asks context.nonHtmlPrefix.check(url, "prenav")
  and throws StaleVariantSkip when blocked (counts filtered_nonhtml; purged_prenav
  via the existing marker branch). failedRequestHandler calls onProbeFailure for
  non-skip failures. No-op while NONHTML_PREFIX_MODE is off (context field null).

  FR — brancher la gate des préfixes non-HTML sur le hook de pré-navigation et l'échec de sonde (R23)

  Ajoute un dernier preNavigationHook qui interroge context.nonHtmlPrefix.check(url, "prenav")
  et lève StaleVariantSkip si l'URL est bloquée (compte filtered_nonhtml ; purged_prenav via
  la branche marqueur existante). failedRequestHandler appelle onProbeFailure pour les échecs
  autres que le skip. Sans effet tant que NONHTML_PREFIX_MODE vaut off (champ de contexte null).
  ```

  ```bash
  git -C <WT> add apps-microservices/crawler-service/crawler/src/functions.ts
  git -C <WT> diff --cached --stat
  git -C <WT> ls-files --eol -- apps-microservices/crawler-service/crawler/src/functions.ts
  git -C <WT> commit -F <scratchpad>/commit-T06.txt
  ```

  Attendu : `--stat` liste exactement `functions.ts` ; `i/crlf  w/crlf` ; commit créé.
### Task 7: Parité texte-source + suite complète
> NOMS NEUFS : littéraux C5/C6 (consommé) ⇒ T4, T5, T6

**Blocked by:** 4, 5, 6

**Goal:** Figer par un test texte-source le câblage de `main.ts`, `routes.ts` et `functions.ts` (littéraux, nombre d'occurrences, ordre aux points d'ancrage, parité du compteur `filtered_nonhtml`), puis prouver la caractérisation du mode `off` : suite complète verte sans `NONHTML_PREFIX_MODE`, et aucun des 509 tests d'origine modifié.

**Files:**
- Create: `apps-microservices/crawler-service/crawler/src/nonHtmlPrefixWiring.test.ts`
- Test: `apps-microservices/crawler-service/crawler/src/nonHtmlPrefixWiring.test.ts`

**Acceptance Criteria:**
- [ ] `nonHtmlPrefixWiring.test.ts` contient exactement 9 `test(` et tous passent sur le câblage de T4, T5, T6.
- [ ] Un test neuf échoue quand un littéral C5 est altéré dans `routes.ts` (mutation du Step 3, revenue à l'état commité ensuite).
- [ ] `increment("filtered_nonhtml")` figure exactement 1 fois dans chacun de `main.ts` (b2), `routes.ts` (b1), `functions.ts` (b3) ; `readStat("filtered_nonhtml")` 1 fois (`main.ts`) ; le spread `...(context.nonHtmlPrefix ? { filtered_nonhtml } : {})` 1 fois.
- [ ] Aucun `increment("filtered_nonhtml")` hors d'un bloc qui suit (≤ 500 caractères avant) un `!context.nonHtmlPrefix.check(` ; autant de `check(` négatifs que d'incréments (1 par fichier).
- [ ] Ordres : `routes.ts` — `onNonHtml(` avant `Skipping non-HTML response:`, `onHtml(` avant `// --- Circuit Breaker Check (Dual-Mode) ---`, b1 entre `// Queue-purge #1: facet cap` et `// Queue-purge #2: filter-on-seen-base` ; `functions.ts` — `onProbeFailure(` après `STALE_VARIANT_SKIP_MARKER` (usage dans `failedRequestHandler`) et avant `Request ${request.url} failed:` ; `main.ts` — init après `ensureUnjudgedSidecar(domain);`, `check(seedUrl, "seed")` avant `uniqueKey: seedUrl`.
- [ ] `npm test` avec `NONHTML_PREFIX_MODE` non défini : `ℹ fail 0` et `ℹ pass` = `<PASS_AVANT>` + 9 (`<PASS_AVANT>` mesuré au Step 1, ≥ 509).
- [ ] `git -C <WT> diff --name-only --diff-filter=MDR e57409aed -- '*.test.ts'` : sortie vide (aucun test existant modifié, supprimé ni renommé ; seuls des fichiers neufs, `A`).

**Verify:** `cd <CR> && node --import tsx --test src/nonHtmlPrefixWiring.test.ts`

**Steps:**

- [ ] **Step 1: Mesurer l'état de départ (T4, T5, T6 commités, T7 pas encore écrit)**

Chaque commande séparément ; git toujours en `git -C <WT>` :

```bash
git -C <WT> status --short
```
Attendu : vide (arbre propre ; sinon STOP — une tâche précédente n'a pas commité).

```bash
git -C <WT> log --oneline e57409aed..HEAD
```
Attendu : les commits de T1 à T6 (au minimum un par tâche).

```bash
cd <CR> && env -u NONHTML_PREFIX_MODE npm test 2>&1 | tail -12
```
Attendu : `ℹ fail 0`. Consigner la valeur de `ℹ pass` : c'est `<PASS_AVANT>` (≥ 509 ; = 509 + tests neufs de T1-T6). Un `ℹ fail` > 0 ici = une tâche précédente est cassée : STOP, rapporter.

Mesurer chaque ancre du câblage (chaque commande rend un nombre ; attendu entre crochets) :

```bash
PYTHONIOENCODING=utf-8 python -I -c "print(open(r'<CR>/src/routes.ts',encoding='utf-8',newline='').read().count('increment(\"filtered_nonhtml\")'))"
PYTHONIOENCODING=utf-8 python -I -c "print(open(r'<CR>/src/functions.ts',encoding='utf-8',newline='').read().count('increment(\"filtered_nonhtml\")'))"
PYTHONIOENCODING=utf-8 python -I -c "print(open(r'<CR>/src/main.ts',encoding='utf-8',newline='').read().count('increment(\"filtered_nonhtml\")'))"
```
Attendu : `1`, `1`, `1`. Autre valeur ⇒ la tâche T5, T6 ou T4 a dévié du contrat C5/C6 : STOP, rapporter (ne pas adapter le test).

- [ ] **Step 2: Écrire le test (il doit passer d'emblée : le câblage existe déjà)**

Forme : celle de `crawler/src/statNameParity.test.ts` (`fs.readFileSync(path.join(import.meta.dirname, f), "utf-8")`). Les comptages se font sur le source dont les lignes de commentaire sont blanchies à longueur égale (les offsets restent comparables avec le source brut, où se lisent les marqueurs de commentaire).

Créer `apps-microservices/crawler-service/crawler/src/nonHtmlPrefixWiring.test.ts` :

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

/**
 * R23 (2) — wiring parity of the non-HTML prefix gate.
 *
 * routes.ts (a Crawlee handler needing a live browser), functions.ts and main.ts are not
 * unit-testable here, and nothing type-checks that a counter written in one file is read by
 * name in another or that a hook sits on the right side of an anchor. Source-text assertions
 * on purpose (same stance as statNameParity.test.ts): exact literals, exact occurrence
 * counts, and ORDER at each anchor point. The gate's own logic is covered by
 * nonHtmlPrefixGate.test.ts.
 *
 * Counts run on the source with `//` comment lines blanked to equal length, so a comment that
 * quotes a literal cannot satisfy or break a count; offsets stay comparable with the raw
 * source, where the comment markers are read.
 */
const raw = (f: string) =>
    fs.readFileSync(path.join(import.meta.dirname, f), "utf-8");
const blankComments = (s: string) =>
    s.replace(/^[ \t]*\/\/.*$/gm, (m) => " ".repeat(m.length));
const count = (s: string, needle: string) => s.split(needle).length - 1;
const at = (s: string, needle: string): number => {
    const i = s.indexOf(needle);
    assert.notEqual(i, -1, `anchor not found: ${needle}`);
    return i;
};
const COUNTER_INC = 'increment("filtered_nonhtml")';
const NEG_CHECK = /!\s*context\.nonHtmlPrefix\.check\(/g;

function assertCounts(code: string, file: string, literals: Array<[string, number]>) {
    for (const [literal, expected] of literals) {
        assert.equal(
            count(code, literal),
            expected,
            `${file}: expected exactly ${expected} of ${literal}`,
        );
    }
}

test("routes.ts: C5 literals present the exact number of times (b1 + learning points)", () => {
    const code = blankComments(raw("routes.ts"));
    assertCounts(code, "routes.ts", [
        ['check(request.url, "enqueue")', 1],
        ["onNonHtml(request.url)", 1],
        ["onHtml(request.url)", 1],
        [COUNTER_INC, 1],
        ["context.nonHtmlPrefix?.onNonHtml(request.url);", 1],
        ["context.nonHtmlPrefix?.onHtml(request.url);", 1],
    ]);
    assert.match(
        code,
        /context\.nonHtmlPrefix\s*&&\s*!context\.nonHtmlPrefix\.check\(request\.url, "enqueue"\)/,
        "routes.ts: b1 must be guarded by context.nonHtmlPrefix (mode off = no-op)",
    );
});

test("functions.ts: C5 literals present the exact number of times (b3 + probe failure)", () => {
    const code = blankComments(raw("functions.ts"));
    assertCounts(code, "functions.ts", [
        ['check(request.url, "prenav")', 1],
        ["onProbeFailure(request.url)", 1],
        [COUNTER_INC, 1],
        ["context.nonHtmlPrefix?.onProbeFailure(request.url);", 1],
    ]);
    assert.match(
        code,
        /context\.nonHtmlPrefix\s*&&\s*!context\.nonHtmlPrefix\.check\(request\.url, "prenav"\)/,
        "functions.ts: b3 must be guarded by context.nonHtmlPrefix (mode off = no-op)",
    );
});

test("main.ts: C5 literals present the exact number of times (init, exemption, b2, counter)", () => {
    const code = blankComments(raw("main.ts"));
    assertCounts(code, "main.ts", [
        ['check(seedUrl, "seed")', 1],
        [COUNTER_INC, 1],
        ['readStat("filtered_nonhtml")', 1],
        ["context.nonHtmlPrefix?.addExempt(consolidatedUrl);", 1],
        ["context.nonHtmlPrefix.addExempt(seedUrl);", 1],
        ["context.nonHtmlPrefix.addExempt(site);", 1],
        ["new NonHtmlPrefixGate(", 1],
        ["resolveNonHtmlPrefixMode(process.env.NONHTML_PREFIX_MODE)", 1],
    ]);
    const i = at(code, 'check(seedUrl, "seed")');
    assert.match(
        code.slice(Math.max(0, i - 600), i),
        /if \(context\.nonHtmlPrefix\) \{/,
        "main.ts: b2 must sit under `if (context.nonHtmlPrefix) {` (mode off = no-op)",
    );
});

test("filtered_nonhtml: exactly one increment per file (b1, b2, b3) and one readStat", () => {
    const files = ["routes.ts", "functions.ts", "main.ts"];
    let total = 0;
    for (const f of files) {
        const n = count(blankComments(raw(f)), COUNTER_INC);
        assert.equal(n, 1, `${f}: expected exactly 1 ${COUNTER_INC}, got ${n}`);
        total += n;
    }
    assert.equal(total, 3, "three blocking points, three increments");
    assert.equal(
        count(blankComments(raw("main.ts")), 'readStat("filtered_nonhtml")'),
        1,
        "main.ts must read back the name the three points write",
    );
});

test("filtered_nonhtml: payload carries it only through the conditional spread (mode off = no key)", () => {
    const code = blankComments(raw("main.ts"));
    const spread = "...(context.nonHtmlPrefix ? { filtered_nonhtml } : {})";
    assert.equal(count(code, spread), 1, `main.ts: expected exactly 1 ${spread}`);
    assert.doesNotMatch(
        code,
        /^\s*filtered_nonhtml,\s*$/m,
        "main.ts: filtered_nonhtml must not appear as a bare payload key (mode off would carry it)",
    );
    assert.ok(
        at(code, 'readStat("filtered_nonhtml")') < at(code, spread),
        "main.ts: readStat must precede the payload that uses it",
    );
});

test("routes.ts: order at the anchors (learn before skip log, html before breaker, b1 between the two queue-purge blocks)", () => {
    const src = raw("routes.ts");
    const code = blankComments(src);
    assert.ok(
        at(code, "onNonHtml(request.url)") < at(src, "Skipping non-HTML response:"),
        "onNonHtml must precede the `Skipping non-HTML response:` log",
    );
    assert.ok(
        at(code, "onHtml(request.url)") < at(src, "// --- Circuit Breaker Check (Dual-Mode) ---"),
        "onHtml must precede the circuit breaker block",
    );
    const b1 = at(code, 'check(request.url, "enqueue")');
    assert.ok(
        at(src, "// Queue-purge #1: facet cap") < b1 &&
            b1 < at(src, "// Queue-purge #2: filter-on-seen-base"),
        "b1 must sit between the facet cap block and the filter-on-seen-base block",
    );
});

test("functions.ts: order at the anchors (probe failure after the stale-variant branch, before the error log)", () => {
    const src = raw("functions.ts");
    const code = blankComments(src);
    const handler = at(src, "String(request.errorMessages).includes(STALE_VARIANT_SKIP_MARKER)");
    const probe = at(code, "onProbeFailure(request.url)");
    const errLog = at(src, "Request ${request.url} failed:");
    assert.ok(
        handler < probe && probe < errLog,
        "onProbeFailure must come after the STALE_VARIANT_SKIP_MARKER branch and before log.error(`Request … failed:`)",
    );
});

test("main.ts: order at the anchors (init after the sidecar guard, b2 check before the enqueue)", () => {
    const src = raw("main.ts");
    const code = blankComments(src);
    const sidecar = at(src, "ensureUnjudgedSidecar(domain);");
    assert.ok(
        sidecar < at(code, "resolveNonHtmlPrefixMode(process.env.NONHTML_PREFIX_MODE)") &&
            sidecar < at(code, "new NonHtmlPrefixGate("),
        "the gate must be initialised after ensureUnjudgedSidecar(domain);",
    );
    assert.ok(
        at(code, 'check(seedUrl, "seed")') < at(src, "uniqueKey: seedUrl"),
        "b2 must test the seed before it is enqueued with uniqueKey: seedUrl",
    );
});

test("filtered_nonhtml parity: every increment follows a negative check( within 500 chars, and counts match", () => {
    for (const f of ["routes.ts", "functions.ts", "main.ts"]) {
        const code = blankComments(raw(f));
        const negChecks = code.match(NEG_CHECK) ?? [];
        const incs = count(code, COUNTER_INC);
        assert.equal(
            negChecks.length,
            incs,
            `${f}: ${negChecks.length} negative check( vs ${incs} increments — a blocking point without its counter (or the reverse)`,
        );
        let from = 0;
        for (let k = 0; k < incs; k++) {
            const i = code.indexOf(COUNTER_INC, from);
            from = i + COUNTER_INC.length;
            const before = code.slice(Math.max(0, i - 500), i);
            assert.match(
                before,
                /!\s*context\.nonHtmlPrefix\.check\(/,
                `${f}: increment("filtered_nonhtml") outside a block that follows a negative check(`,
            );
        }
    }
});
```

Compte de `test(` du fichier : 9 (routes literals, functions literals, main literals, une-par-fichier, payload, order routes, order functions, order main, parity). Vérifier : `grep -c '^test(' <CR>/src/nonHtmlPrefixWiring.test.ts` doit rendre `9`.

- [ ] **Step 3: Lancer le test, puis prouver qu'il peut échouer (mutation)**

```bash
cd <CR> && node --import tsx --test src/nonHtmlPrefixWiring.test.ts
```
Attendu : `ℹ tests 9`, `ℹ pass 9`, `ℹ fail 0`. Un échec ici est un FAIT sur T4/T5/T6 (littéral ou ordre qui ne suit pas le contrat C5) : lire le message d'assertion, rapporter le fichier et le littéral ; ne pas assouplir le test pour le faire passer.

Mutation de preuve (le test doit échouer, puis le fichier revient à l'état commité). Avec l'outil Edit, dans `<CR>/src/routes.ts`, remplacer l'unique occurrence de `context.nonHtmlPrefix?.onHtml(request.url);` par `context.nonHtmlPrefix?.onHtml(request.urlX);` (unicité : déjà établie par le test du Step 3, compte = 1). Puis :

```bash
cd <CR> && node --import tsx --test src/nonHtmlPrefixWiring.test.ts
```
Attendu : `ℹ fail` ≥ 2 (le test « routes.ts: C5 literals… » et « routes.ts: order at the anchors »). Revenir à l'état commité :

```bash
git -C <WT> checkout -- apps-microservices/crawler-service/crawler/src/routes.ts
```
```bash
git -C <WT> status --short
```
Attendu : seule la ligne `?? apps-microservices/crawler-service/crawler/src/nonHtmlPrefixWiring.test.ts` (routes.ts n'apparaît plus). Relancer le test : `ℹ pass 9`, `ℹ fail 0`.

- [ ] **Step 4: Caractérisation du mode `off` — suite complète sans la variable**

```bash
cd <CR> && env -u NONHTML_PREFIX_MODE npm test 2>&1 | tail -12
```
Attendu : `ℹ fail 0` et `ℹ pass` = `<PASS_AVANT>` + 9. Les tests de T3 (gate × point × mode) couvrent `shadow` / `on` ; ce run prouve que, la variable absente, rien ne change pour les tests d'origine.

Aucun des 509 tests d'origine n'est modifié (la commande doit rendre une sortie VIDE ; `--diff-filter=MDR` = modifié, supprimé, renommé) :

```bash
git -C <WT> diff --name-only --diff-filter=MDR e57409aed -- '*.test.ts'
```
Attendu : aucune ligne. Et pour montrer que ce qui a changé est neuf (lecture seule, informatif) :

```bash
git -C <WT> diff --name-status --diff-filter=A e57409aed -- '*.test.ts'
```
Attendu : uniquement des lignes `A` — `nonHtmlPrefix.test.ts`, `nonHtmlPrefixSidecar.test.ts`, `nonHtmlPrefixGate.test.ts` (T1-T3), `tools/nonHtmlPrefixReplay.test.ts` si T9 est déjà fait, et le fichier de T7 une fois ajouté à l'index (le fichier T7 non indexé n'apparaît pas encore : normal).

Contrôle d'effet sur les trois fichiers câblés (T7 n'en modifie aucun) :

```bash
git -C <WT> diff --stat -- apps-microservices/crawler-service/crawler/src/main.ts apps-microservices/crawler-service/crawler/src/routes.ts apps-microservices/crawler-service/crawler/src/functions.ts
```
Attendu : vide (arbre propre sur ces fichiers, après le `checkout` du Step 3).

- [ ] **Step 5: Commit**

Écrire avec l'outil Write `<scratchpad>/commit-T07.txt` :

```text
test(crawler): pin non-HTML prefix wiring by source text (R23)

Source-text test over main.ts, routes.ts and functions.ts: exact C5/C6
literals and occurrence counts, ordering at each anchor point, one
increment("filtered_nonhtml") per blocking point (b1/b2/b3) each following
a negative check( , one readStat, conditional payload spread. Existing
tests untouched; full suite green with NONHTML_PREFIX_MODE unset.

FR — test(crawler) : figer le cablage des prefixes non-HTML par le texte source (R23)

Test texte-source sur main.ts, routes.ts et functions.ts : litteraux C5/C6
exacts et nombre d'occurrences, ordre a chaque point d'ancrage, un seul
increment("filtered_nonhtml") par point de blocage (b1/b2/b3), chacun
apres un check( negatif, un readStat, spread conditionnel du payload.
Tests existants inchanges ; suite complete verte sans NONHTML_PREFIX_MODE.
```

```bash
git -C <WT> add apps-microservices/crawler-service/crawler/src/nonHtmlPrefixWiring.test.ts
```
```bash
git -C <WT> diff --cached --stat
```
Attendu : exactement 1 fichier (`nonHtmlPrefixWiring.test.ts`).
```bash
git -C <WT> ls-files --eol -- apps-microservices/crawler-service/crawler/src/nonHtmlPrefixWiring.test.ts
```
Attendu : `i/lf` (fichier neuf).
```bash
git -C <WT> commit -F <scratchpad>/commit-T07.txt
```
### Task 8: admin.py : kind `pdf` + whitelist `NONHTML_`
> NOMS NEUFS : clé `"pdf"` de `_DATASET_PREFIXES` (produit) ⇒ T8, préfixe `NONHTML_` de `_ENV_WHITELIST_PREFIXES` (produit) ⇒ T8

**Blocked by:** none

**Goal:** Rendre le dataset `pdf-<nom>` (URLs non-HTML déjà rencontrées) lisible par `GET /admin/dataset/{crawl_id}?kind=pdf` et rendre les variables `NONHTML_*` visibles dans `GET /admin/config`.

**Files:**
- Modify: `apps-microservices/crawler-service/app/router/admin.py`
- Create: `apps-microservices/crawler-service/tests/test_admin_nonhtml_prefix.py`
- Test: `apps-microservices/crawler-service/tests/test_admin_nonhtml_prefix.py`

**Acceptance Criteria:**
- [ ] `_DATASET_PREFIXES["pdf"] == "pdf-"` (copie littérale de `pdfDatasetName`, `crawler/src/httpStatusPolicy.ts:289-290`).
- [ ] `GET /admin/dataset/9?kind=pdf` lit `storage/datasets/pdf-<domaine>` ET `pdf-<domaine avec . → ->` ; `kind=main` ne voit jamais ce dossier ; un `kind` inconnu rend 422.
- [ ] `GET /admin/config` expose `NONHTML_PREFIX_MODE` et `NONHTML_PREFIX_MIN` dans `env`, et jamais une variable hors whitelist.
- [ ] `git diff --numstat` de `admin.py` : **2 lignes supprimées** (la ligne `_DATASET_PREFIXES` et la ligne `kind: str = Query(...)`), 6 ajoutées ; `ls-files --eol` reste `i/lf`.
- [ ] Les tests existants `test_admin_config.py` (dont `test_compose_env_parity`) et `test_admin_dataset_sample.py` restent verts, sans modification.

**Verify:** `cd <WT>/apps-microservices/crawler-service && python -m pytest tests/test_admin_nonhtml_prefix.py tests/test_admin_config.py tests/test_admin_dataset_sample.py -q`

**Steps:**

Faits lus pour cette tâche (base `e57409aed`, `awk 'NR>=a && NR<=b {printf "%d: %s\n", NR, $0}'` ; à l'exécution, localiser par CONTENU) :

| Fait | Source |
|---|---|
| Préfixe réel : `export function pdfDatasetName(crawleeStorageName: string \| undefined, domain: string): string { return crawleeStorageName ? \`pdf-${crawleeStorageName}\` : \`pdf-${domain}\`; }` ; `crawleeStorageName` = `domain.replace(/\./g, '-')` | `crawler/src/httpStatusPolicy.ts:289-290` ; `crawler/src/main.ts:149` |
| Les deux candidats de `_dataset_dir` (`domain`, puis `domain.replace(".", "-")`, préfixés) couvrent donc `pdf-example.com` et `pdf-example-com` | `app/router/admin.py:239-240` |
| Le dataset `pdf-…` reçoit `{url, source, status, content_type, timestamp}` ⇒ l'endpoint rend `url` | `crawler/src/routes.ts:379-385` |
| **Trou du contrat** : `kind` est validé par une REGEX de `Query`, pas par le dict : `kind: str = Query("main", pattern="^(main\|error\|nfr\|update)$"),` (`admin.py:248`). Ajouter la seule clé au dict (F21) laisserait `?kind=pdf` en 422 ⇒ la regex change aussi (2ᵉ ligne supprimée) | `app/router/admin.py:248` |
| Route réelle : `@router.get("/dataset/{crawl_id}")` sous `APIRouter(prefix="/admin")` ⇒ `GET /admin/dataset/{crawl_id}` (l'index écrit `/admin/dataset`) | `admin.py:246`, `:24` |
| Whitelist d'env : tuple `_ENV_WHITELIST_PREFIXES` (`admin.py:191-200`), filtre `k.startswith(_ENV_WHITELIST_PREFIXES)` (`:220-221`) ; dernière entrée `"ARCHIVED_",` | `admin.py:199` |

**Forme de réponse de `GET /admin/dataset/{crawl_id}` pour `kind != "update"` (à CONSOMMER par T9, `admin.py:335-336` et `:317-333`) :**

```text
200 {
  "kind": str,                 # écho du paramètre ("pdf")
  "total_records": int,        # nombre de fichiers .json du dossier (hors html_index.json et hors noms commençant par "__"), AVANT pagination
  "offset": int, "returned": int,
  "records": [                 # plus récent d'abord (mtime desc, nom desc à égalité), tranche [offset : offset+limit]
    { "file": str,             # nom du fichier .json
      "size_bytes": int,
      "mtime": str,            # ISO UTC
      "url": str | null,       # item["url"] ; null si fichier illisible
      "content_length": int,   # len(item["content"] or "") ; 0 pour un item pdf (pas de champ content)
      "content_preview": str,  # seulement si content_chars > 0
      "parse_error": str }     # seulement si fichier > 20 000 000 octets ou illisible (alors pas de content_length)
  ]
}
404 { "detail": "Dataset not on local disk (crawl may be stashed/archived — …" }   # dossier absent
422                              # kind hors regex, limit hors 1..100, offset < 0
```

Paramètres : `kind` (défaut `main`), `offset` ≥ 0 (défaut 0), `limit` 1..100 (défaut 20), `content_chars` 0..5000. **Le plafond est 100 enregistrements par appel** ⇒ T9 pagine par `offset`. `content_type` du dataset pdf n'est PAS rendu par l'endpoint (seuls `url`, `file`, `size_bytes`, `mtime`, `content_length`).

- [ ] **Step 0: Mesurer le cwd neutre et la commande pytest (lecture seule)**

`app/core/config.py:133-136` déclare `"env_file": ".env"` (relatif au cwd). Mesures de la rédaction : aucun `.env` sous le worktree ni sous `crawler-service/` ; un `.env` existe au checkout principal (`<MAIN>/.env`, NE PAS le lire). `crawler-service/conftest.py` (racine du service) ajoute `libs/` et la racine du dépôt à `sys.path` ; `tests/` n'a pas d'`__init__.py` ; il n'y a pas de `pytest.ini` pour ce service ; la CI (`.github/workflows/ci_services_crawler.yml`) ne lance PAS pytest ⇒ la commande ci-dessous est dérivée de `conftest.py` + des tests voisins, puis mesurée ici. Le cwd `<WT>/apps-microservices/crawler-service` est neutre (pas de `.env`) et met `app/` sur `sys.path` (`python -m pytest` ajoute le cwd).

Run: `command ls -a <WT>/apps-microservices/crawler-service | grep -c "^\.env"` — attendu : `0` (sinon, lancer pytest depuis un cwd neutre sans `.env` et le noter).

Run (base verte, avant toute édition) : `cd <WT>/apps-microservices/crawler-service && python -m pytest tests/test_admin_config.py tests/test_admin_dataset_sample.py -q 2>&1 | tail -5`
Attendu : `N passed` avec N > 0 et aucun `failed`/`error`. Consigner `<PYTEST_BASE>` = N. Si pytest ou fastapi manque (`ModuleNotFoundError`), STOP et rapporter : l'implémenteur n'installe rien sans le dire.

- [ ] **Step 1: Écrire le test qui échoue**

Create `apps-microservices/crawler-service/tests/test_admin_nonhtml_prefix.py` (valeurs factices neutres, aucune variable réelle lue) :

```python
# tests/test_admin_nonhtml_prefix.py
"""R23 (2): kind=pdf on GET /admin/dataset/{crawl_id} and the NONHTML_ env
prefix on GET /admin/config."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app_and_storage(monkeypatch, tmp_path):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    from app.router.admin import router as AdminRouter
    from app.router.crawler import get_job_or_recover
    app = FastAPI()
    app.include_router(AdminRouter)
    job = {"crawl_id": "9", "status": "finished", "domain": "example.com",
           "storage_path": str(tmp_path)}

    async def fake_dep(crawl_id: str):
        return job

    app.dependency_overrides[get_job_or_recover] = fake_dep
    return app, tmp_path


def _mk_dataset(storage, dirname, items):
    d = storage / "storage" / "datasets" / dirname
    d.mkdir(parents=True)
    for name, payload in items:
        (d / name).write_text(json.dumps(payload), encoding="utf-8")
    return d


def test_pdf_prefix_matches_crawler_dataset_name():
    # crawler/src/httpStatusPolicy.ts pdfDatasetName: `pdf-${crawleeStorageName}`
    from app.router.admin import _DATASET_PREFIXES
    assert _DATASET_PREFIXES["pdf"] == "pdf-"


def test_kind_pdf_reads_sanitized_pdf_dataset(app_and_storage):
    app, storage = app_and_storage
    _mk_dataset(storage, "pdf-example-com", [
        ("a.json", {"url": "https://example.com/image/x1", "source": "",
                    "status": 200, "content_type": "image/jpeg"}),
        ("b.json", {"url": "https://example.com/image/x2", "source": "",
                    "status": 200, "content_type": "image/jpeg"}),
    ])
    resp = TestClient(app).get("/admin/dataset/9", params={"kind": "pdf"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "pdf"
    assert body["total_records"] == 2
    assert {r["url"] for r in body["records"]} == {
        "https://example.com/image/x1", "https://example.com/image/x2"}
    assert set(body) == {"kind", "total_records", "offset", "returned", "records"}


def test_kind_pdf_reads_unsanitized_dir_too(app_and_storage):
    app, storage = app_and_storage
    _mk_dataset(storage, "pdf-example.com", [("a.json", {"url": "https://example.com/d/1"})])
    body = TestClient(app).get("/admin/dataset/9", params={"kind": "pdf"}).json()
    assert body["total_records"] == 1


def test_kind_main_never_reads_pdf_dir(app_and_storage):
    app, storage = app_and_storage
    _mk_dataset(storage, "pdf-example-com", [("a.json", {"url": "https://example.com/d/1"})])
    resp = TestClient(app).get("/admin/dataset/9")  # kind=main
    assert resp.status_code == 404  # only pdf-example-com exists: main finds nothing


def test_kind_pdf_absent_is_404(app_and_storage):
    app, _ = app_and_storage
    resp = TestClient(app).get("/admin/dataset/9", params={"kind": "pdf"})
    assert resp.status_code == 404


def test_unknown_kind_still_rejected(app_and_storage):
    app, _ = app_and_storage
    assert TestClient(app).get("/admin/dataset/9", params={"kind": "bogus"}).status_code == 422


@pytest.fixture
def config_client(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    from app.router.admin import router as AdminRouter
    app = FastAPI()
    app.include_router(AdminRouter)
    return TestClient(app)


def test_nonhtml_env_exposed_in_config(config_client, monkeypatch):
    monkeypatch.setenv("NONHTML_PREFIX_MODE", "shadow")
    monkeypatch.setenv("NONHTML_PREFIX_MIN", "5")
    monkeypatch.setenv("NONHTML_PREFIX_PROBES", "3")
    monkeypatch.setenv("NONHTML_ISOLATED_MAX", "7")
    env = config_client.get("/admin/config").json()["env"]
    assert env["NONHTML_PREFIX_MODE"] == "shadow"
    assert env["NONHTML_PREFIX_MIN"] == "5"
    assert env["NONHTML_PREFIX_PROBES"] == "3"
    assert env["NONHTML_ISOLATED_MAX"] == "7"


def test_non_whitelisted_lookalike_not_exposed(config_client, monkeypatch):
    monkeypatch.setenv("XNONHTML_PREFIX_MODE", "shadow")
    env = config_client.get("/admin/config").json()["env"]
    assert "XNONHTML_PREFIX_MODE" not in env
```

- [ ] **Step 2: Lancer le test — il doit échouer**

Run: `cd <WT>/apps-microservices/crawler-service && python -m pytest tests/test_admin_nonhtml_prefix.py -q 2>&1 | tail -15`
Attendu : échecs — `KeyError: 'pdf'` (test 1), `assert 422 == 200` (tests `kind=pdf`), `KeyError: 'NONHTML_PREFIX_MODE'` ; PASSENT déjà : `test_kind_main_never_reads_pdf_dir`, `test_unknown_kind_still_rejected`, `test_non_whitelisted_lookalike_not_exposed`, et `test_kind_pdf_absent_is_404` ne passe PAS (422 ≠ 404). Un échec d'import (`ModuleNotFoundError: app`) = mauvais cwd ⇒ corriger le cwd, pas le test.

- [ ] **Step 3: Implémenter — 3 éditions, outil Edit, sur `apps-microservices/crawler-service/app/router/admin.py`**

Unicité des ancres prouvée par comptage de sous-chaîne (lecture, base `e57409aed`) : `_DATASET_PREFIXES = {"main"` = 1 ; `(main|error|nfr|update)` = 1 ; `    "ARCHIVED_",` = 1. Le fichier est `i/lf w/crlf` : édition par l'outil Edit, ancres d'UNE ligne.

Edit 1 — `admin.py`, ligne `_DATASET_PREFIXES` (remplace 1 ligne) :

```python
_DATASET_PREFIXES = {"main": "", "error": "error-", "nfr": "nfr-", "update": "update-",
                     "pdf": "pdf-"}  # pdf-: crawler pdfDatasetName (non-HTML responses skipped by routes.ts)
```

Edit 2 — `admin.py`, dans la signature de `dataset_sample` : remplacer la sous-chaîne `pattern="^(main|error|nfr|update)$"` par `pattern="^(main|error|nfr|update|pdf)$"` (remplace 1 ligne).

Edit 3 — `admin.py`, fin du tuple `_ENV_WHITELIST_PREFIXES` : remplacer la ligne `    "ARCHIVED_",` par (insertion pure, la ligne d'origine est conservée à l'identique) :

```python
    "ARCHIVED_",
    # NONHTML_PREFIX_MODE/MIN/PROBES + NONHTML_ISOLATED_MAX (R23 (2)): lets an
    # operator read the learning mode on the VM without a shell. No secret here.
    "NONHTML_",
```

Contrôle de la parité compose : `test_compose_env_parity` exige que toute variable du bloc `environment` de `crawler-service` du `docker-compose.yml` soit couverte ; ajouter `NONHTML_` ne peut que couvrir davantage (T10 documente comment la variable atteint le conteneur).

- [ ] **Step 4: Lancer le test — il doit passer**

Run: `cd <WT>/apps-microservices/crawler-service && python -m pytest tests/test_admin_nonhtml_prefix.py tests/test_admin_config.py tests/test_admin_dataset_sample.py -q 2>&1 | tail -5`
Attendu : `<PYTEST_BASE> + 8 passed`, 0 failed (8 = nombre de `def test_` du fichier neuf : `test_pdf_prefix_matches_crawler_dataset_name`, `test_kind_pdf_reads_sanitized_pdf_dataset`, `test_kind_pdf_reads_unsanitized_dir_too`, `test_kind_main_never_reads_pdf_dir`, `test_kind_pdf_absent_is_404`, `test_unknown_kind_still_rejected`, `test_nonhtml_env_exposed_in_config`, `test_non_whitelisted_lookalike_not_exposed`).

- [ ] **Step 5: Suite Python du service**

Run: `cd <WT>/apps-microservices/crawler-service && python -m pytest tests -q -x --ignore=tests/integration 2>&1 | tail -8`
Attendu : `0 failed`. Un échec préexistant sans lien avec `admin.py` (le constater en relançant le seul fichier fautif et en lisant sa trace : l’import ou le test ne touche-t-il pas `admin.py` ?) est rapporté, pas corrigé ; ne rien « réparer » hors périmètre.

- [ ] **Step 6: Contrôle d'effet sur `admin.py`**

Run: `git -C <WT> diff --numstat -- apps-microservices/crawler-service/app/router/admin.py`
Attendu : `6	2	apps-microservices/crawler-service/app/router/admin.py` (6 ajoutées : 2 pour `_DATASET_PREFIXES` + 1 pour la regex + 3 de la whitelist ; 2 supprimées : `_DATASET_PREFIXES` et `kind: str = Query(…)`). Un autre compte ⇒ une fin de ligne a été réécrite : annuler l'édition fautive et la refaire.
Run: `git -C <WT> ls-files --eol -- apps-microservices/crawler-service/app/router/admin.py`
Attendu : `i/lf` (la copie de travail reste `w/crlf`).

- [ ] **Step 7: Commit**

Write `<scratchpad>/commit-T08.txt` (outil Write) :

```text
feat(crawler-service): expose pdf dataset kind and NONHTML_ env in admin API (R23)

Add "pdf" to _DATASET_PREFIXES and to the kind regex of GET /admin/dataset
so the non-HTML URL dataset (pdf-<name>) can be sampled without downloading
the results tar; whitelist the NONHTML_ env prefix in GET /admin/config so
the learning mode is readable on the VM. Tests cover both endpoints.

FR — exposer le kind pdf et l'env NONHTML_ dans l'API admin (R23)

Ajoute "pdf" à _DATASET_PREFIXES et à la regex de kind de GET /admin/dataset
pour échantillonner le dataset des URLs non-HTML (pdf-<nom>) sans télécharger
le tar de résultats ; whiteliste le préfixe d'env NONHTML_ dans GET
/admin/config pour lire le mode d'apprentissage sur la VM. Tests des deux
endpoints.
```

Run: `git -C <WT> add apps-microservices/crawler-service/app/router/admin.py apps-microservices/crawler-service/tests/test_admin_nonhtml_prefix.py`
Run: `git -C <WT> diff --cached --stat` — attendu : exactement ces 2 fichiers.
Run: `git -C <WT> commit -F <scratchpad>/commit-T08.txt`
### Task 9: Instrument de rejeu K
> NOMS NEUFS : ExportRecord (produit) ⇒ T9, ReplayRow (produit) ⇒ T9, KResult (produit) ⇒ T9, extractRecords (produit) ⇒ T9, buildReplayRows (produit) ⇒ T9, replayForK (produit) ⇒ T9, replayAll (produit) ⇒ T9, formatReport (produit) ⇒ T9, main (produit) ⇒ T9, createNonHtmlPrefixState (consommé) ⇒ T1, NONHTML_PREFIX_DEFAULTS (consommé) ⇒ T1, recordNonHtml (consommé) ⇒ T1, recordHtml (consommé) ⇒ T1, decide (consommé) ⇒ T1

**Blocked by:** 1, 8

**Goal:** Fournir une lib pure + un CLI gardé qui rejoue, pour K = 1…10, les appels `recordNonHtml` / `recordHtml` / `decide` de C1 sur des exports JSON des datasets `pdf` et `main` d'un crawl, et rapporte par K les clés apprises, libérées, les pages HTML qui auraient été bloquées et les URLs non-HTML évitées.

**Files:**
- Create: `apps-microservices/crawler-service/crawler/src/tools/nonHtmlPrefixReplay.ts`
- Test: `apps-microservices/crawler-service/crawler/src/tools/nonHtmlPrefixReplay.test.ts`

**Acceptance Criteria:**
- [ ] `replayAll(rows)` rend 10 `KResult` (K = 1…10), chacun rejoué avec `createNonHtmlPrefixState({ ...NONHTML_PREFIX_DEFAULTS, minNonHtml: K })` ; seuls `recordNonHtml`, `recordHtml` et `decide` de C1 sont appelés (aucune re-implémentation du seuil).
- [ ] Sur la fixture du test : K=3 ⇒ `keysLearned 1, keysReleased 1, avoidedNonHtml 3, htmlBlocked 1, isolated 3` ; K=1 ⇒ `avoidedNonHtml 5` ; K=7 ⇒ `keysLearned 0, keysReleased 0, avoidedNonHtml 0, isolated 7`.
- [ ] Une URL à extension ignorée (`hasIgnoredExtensionForSeed`) n'est jamais comptée dans `avoidedNonHtml` (le filtre d'extension l'écarte déjà).
- [ ] L'ordre de rejeu est déterministe : `mtime` croissant, puis non-HTML avant HTML, puis nom de fichier, puis rang d'entrée.
- [ ] `main([])` ⇒ 2 + usage sur stderr ; fichier illisible ou JSON invalide ⇒ 1 ; entrées valides ⇒ 0 + tableau sur stdout.
- [ ] Importer le module ne lance pas `main` (garde « lancé directement »).
- [ ] 10 `test(` ajoutés ; aucun fichier de test existant modifié.

**Verify:** `cd <CR> && node --import tsx --test src/tools/nonHtmlPrefixReplay.test.ts`

**Steps:**

- [ ] **Step 0: mesures préalables (lecture seule)**

Faits relus pour cette section (base `e57409aed`, à re-localiser par contenu) :
- Endpoint réel : `GET /admin/dataset/{crawl_id}?kind=<main|error|nfr|update|pdf>&offset=&limit=` (`app/router/admin.py:246`, prefix `/admin` `:24`) ; après T8, `kind=pdf` est servi. `limit` ≤ 100, **plus récent d'abord** (`admin.py:314`) ⇒ un export complet se pagine (`offset` += 100 jusqu'à `returned == 0`).
- Réponse : `{ "kind", "total_records", "offset", "returned", "records": [ { "file", "size_bytes", "mtime", "url", "content_length"? , "parse_error"? } ] }` (`admin.py:317-318`, `:335-336`). `mtime` = date du FICHIER (`datetime.utcfromtimestamp(...).isoformat()`), `url` = `item.get("url")`. Le `timestamp` des lignes `pdf` n'est PAS servi.
- Champ URL écrit : dataset `pdf` `{ url, source, status, content_type, timestamp }` (`routes.ts:379-385`) ou `{ url, source, status, timestamp }` (`functions.ts:625-630`) ; dataset principal `{ url, content, title }` (`functions.ts:1866-1870`) ou `{ url, content }` (`routes.ts:1373`). Dans les deux cas le champ est `url`, et l'export admin le re-sert sous `records[].url`.

Re-vérifier T8 : `grep -n '"pdf": "pdf-"' apps-microservices/crawler-service/app/router/admin.py` doit rendre 1 ligne ; sinon STOP (T8 non livré).

Mesurer le total de départ de la suite : `cd <CR> && npm test 2>&1 | tail -12` ⇒ consigner `<BASE>` = la valeur de `ℹ pass` (attendu `ℹ fail 0`).

- [ ] **Step 1: test qui échoue**

Create `apps-microservices/crawler-service/crawler/src/tools/nonHtmlPrefixReplay.test.ts` :

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import {
    buildReplayRows,
    extractRecords,
    formatReport,
    main,
    replayAll,
    replayForK,
} from "./nonHtmlPrefixReplay.js";

const rec = (url: string, mtime: string, file = "000000001.json") => ({ file, size_bytes: 1, mtime, url });
const T = (s: string) => `2026-01-01T00:00:${s}`;

// Replay order = mtime ascending: a1..a6 (01-06), x.pdf (06.500), page (07), d1 (08), p1 (10).
const pdfExport = {
    kind: "pdf",
    total_records: 8,
    offset: 0,
    returned: 8,
    records: [
        rec("https://h.test/image/a1", T("01")),
        rec("https://h.test/image/a2", T("02")),
        rec("https://h.test/image/a3", T("03")),
        rec("https://h.test/image/a4", T("04")),
        rec("https://h.test/image/a5", T("05")),
        rec("https://h.test/image/a6", T("06")),
        rec("https://h.test/image/x.pdf", T("06.500")),
        rec("https://h.test/dl?id=1", T("08")),
    ].reverse(), // the endpoint serves newest first
};
const mainExport = {
    kind: "main",
    records: [rec("https://h.test/produits/p1", T("10")), rec("https://h.test/image/page", T("07"))],
};

test("extractRecords accepts a page object, a bare array and an array of pages; drops rows without url", () => {
    const r = rec("https://h.test/a", T("01"));
    assert.equal(extractRecords({ records: [r, { file: "f" }, { url: "" }] }).length, 1);
    assert.equal(extractRecords([r, r]).length, 2);
    assert.equal(extractRecords([{ records: [r] }, { records: [r, r] }]).length, 3);
    assert.deepEqual(extractRecords("nope"), []);
    assert.deepEqual(extractRecords(null), []);
});

test("buildReplayRows orders by mtime, then non-HTML before HTML, then file", () => {
    const rows = buildReplayRows(
        [rec("https://h.test/n2", T("02"), "000000002.json"), rec("https://h.test/n1", T("01"))],
        [rec("https://h.test/h1", T("02"), "000000000.json"), rec("https://h.test/h0", T("00"))],
    );
    assert.deepEqual(
        rows.map((r) => `${r.kind}:${r.url.slice(-2)}`),
        ["html:h0", "nonhtml:n1", "nonhtml:n2", "html:h1"],
    );
});

test("replayForK K=3: learns the key once, releases it on the HTML page, counts the avoided URLs", () => {
    const rows = buildReplayRows(extractRecords(pdfExport), extractRecords(mainExport));
    const r = replayForK(rows, 3);
    assert.equal(r.k, 3);
    assert.equal(r.keysLearned, 1);
    assert.equal(r.keysReleased, 1);
    assert.equal(r.avoidedNonHtml, 3); // a4, a5, a6 — x.pdf excluded (ignored extension)
    assert.equal(r.htmlBlocked, 1); // /image/page seen under a blocking key
    assert.equal(r.isolated, 3); // a1, a2 (under K) + d1 (no parent folder)
    assert.equal(r.nonHtmlRows, 8);
    assert.equal(r.htmlRows, 2);
});

test("replayForK K=1 avoids more, K=7 never learns", () => {
    const rows = buildReplayRows(extractRecords(pdfExport), extractRecords(mainExport));
    const k1 = replayForK(rows, 1);
    assert.equal(k1.keysLearned, 1);
    assert.equal(k1.avoidedNonHtml, 5);
    assert.equal(k1.isolated, 1);
    const k7 = replayForK(rows, 7);
    assert.equal(k7.keysLearned, 0);
    assert.equal(k7.keysReleased, 0);
    assert.equal(k7.avoidedNonHtml, 0);
    assert.equal(k7.htmlBlocked, 0);
    assert.equal(k7.isolated, 7);
});

test("an ignored-extension non-HTML URL is never counted as avoided", () => {
    const rows = buildReplayRows(
        [
            rec("https://h.test/image/a1", T("01")),
            rec("https://h.test/image/a2", T("02")),
            rec("https://h.test/image/b.png", T("03")),
        ],
        [],
    );
    const r = replayForK(rows, 2);
    assert.equal(r.keysLearned, 1);
    assert.equal(r.avoidedNonHtml, 0);
});

test("replayAll covers K=1..10 and the learned count never grows with K", () => {
    const rows = buildReplayRows(extractRecords(pdfExport), extractRecords(mainExport));
    const all = replayAll(rows);
    assert.deepEqual(all.map((r) => r.k), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    for (let i = 1; i < all.length; i++) {
        assert.ok(all[i].keysLearned <= all[i - 1].keysLearned);
        assert.ok(all[i].avoidedNonHtml <= all[i - 1].avoidedNonHtml);
    }
    assert.equal(all[5].avoidedNonHtml, 0); // K=6: a6 itself crosses the threshold
});

test("formatReport prints a header and one line per K", () => {
    const rows = buildReplayRows(extractRecords(pdfExport), extractRecords(mainExport));
    const text = formatReport(replayAll(rows));
    const lines = text.trimEnd().split("\n");
    assert.match(lines[0], /^K\s+learned\s+released\s+avoided\s+html_blocked\s+isolated$/);
    assert.equal(lines.length, 11);
    assert.match(text, /^\s*3\s+1\s+1\s+3\s+1\s+3\s*$/m);
});

function capture(fn: () => number): { code: number; out: string; err: string } {
    const log = console.log;
    const error = console.error;
    let out = "";
    let err = "";
    console.log = (...a: unknown[]) => { out += a.join(" ") + "\n"; };
    console.error = (...a: unknown[]) => { err += a.join(" ") + "\n"; };
    try {
        return { code: fn(), out, err };
    } finally {
        console.log = log;
        console.error = error;
    }
}

test("main: missing arguments => usage on stderr and code 2", () => {
    const r = capture(() => main([]));
    assert.equal(r.code, 2);
    assert.match(r.err, /Usage:/);
    assert.equal(capture(() => main(["only-one.json"])).code, 2);
});

test("main: unreadable or invalid file => code 1", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "nhr-"));
    try {
        const bad = path.join(dir, "bad.json");
        fs.writeFileSync(bad, "{not json");
        assert.equal(capture(() => main([path.join(dir, "absent.json"), bad])).code, 1);
        assert.equal(capture(() => main([bad, bad])).code, 1);
    } finally {
        fs.rmSync(dir, { recursive: true, force: true });
    }
});

test("main: valid exports => code 0 and the K table on stdout", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "nhr-"));
    try {
        const pdf = path.join(dir, "pdf.json");
        const mainFile = path.join(dir, "main.json");
        fs.writeFileSync(pdf, JSON.stringify(pdfExport));
        fs.writeFileSync(mainFile, JSON.stringify(mainExport));
        const r = capture(() => main([pdf, mainFile]));
        assert.equal(r.code, 0);
        assert.match(r.out, /^\s*3\s+1\s+1\s+3\s+1\s+3\s*$/m);
        assert.equal(r.err, "");
    } finally {
        fs.rmSync(dir, { recursive: true, force: true });
    }
});
```

- [ ] **Step 2: constater l'échec**

Run : `cd <CR> && node --import tsx --test src/tools/nonHtmlPrefixReplay.test.ts`
Attendu : échec (`ERR_MODULE_NOT_FOUND` sur `./nonHtmlPrefixReplay.js`), `ℹ fail` ≥ 1.

- [ ] **Step 3: implémentation**

Create `apps-microservices/crawler-service/crawler/src/tools/nonHtmlPrefixReplay.ts` :

```ts
#!/usr/bin/env node
/**
 * R23 (2) — replay instrument to derive K (NONHTML_PREFIX_MIN).
 *
 * Input: two JSON exports of `GET /admin/dataset/{crawl_id}` (kind=pdf = non-HTML
 * responses, kind=main = HTML pages), or bare arrays of their records.
 * For each K = 1..10 it replays recordNonHtml / recordHtml / decide of
 * nonHtmlPrefix.ts (consumed as signed) on a state built with minNonHtml = K.
 *
 * Replay order (a CONTRACT GAP, chosen here): the endpoint serves the FILE mtime,
 * not the row `timestamp`, and main rows carry no timestamp at all. Rows are merged
 * by `mtime` ascending; ties: non-HTML first (pessimistic for false positives),
 * then file name, then input rank. An mtime reset by a stash/restore flattens the
 * order — then the table is only an approximation.
 *
 * Free instrument: internal data only, no network.
 */
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import {
    NONHTML_PREFIX_DEFAULTS,
    createNonHtmlPrefixState,
    decide,
    recordHtml,
    recordNonHtml,
} from "../nonHtmlPrefix.js";
import { hasIgnoredExtensionForSeed } from "../seedExtensionFilter.js";

export interface ExportRecord {
    url: string;
    mtime: string;
    file: string;
}

export interface ReplayRow {
    url: string;
    kind: "nonhtml" | "html";
    mtime: string;
    file: string;
    seq: number;
}

export interface KResult {
    k: number;
    /** keys that crossed K (recordNonHtml => "learned") */
    keysLearned: number;
    /** learned keys that later saw HTML (recordHtml => "released") = false positives */
    keysReleased: number;
    /** non-HTML URLs decide() would have blocked after learning (ignored extensions excluded) */
    avoidedNonHtml: number;
    /** HTML pages requested while their key was blocking (the harm if released late) */
    htmlBlocked: number;
    /** "isolated" events of recordNonHtml (sidecar size driver) */
    isolated: number;
    nonHtmlRows: number;
    htmlRows: number;
}

const toRecord = (x: unknown): ExportRecord | null => {
    if (typeof x !== "object" || x === null) return null;
    const o = x as Record<string, unknown>;
    if (typeof o.url !== "string" || o.url === "") return null;
    return {
        url: o.url,
        mtime: typeof o.mtime === "string" ? o.mtime : "",
        file: typeof o.file === "string" ? o.file : "",
    };
};

/** Accepts a page object `{records}`, a bare array of records, or an array of pages. */
export function extractRecords(input: unknown): ExportRecord[] {
    const out: ExportRecord[] = [];
    const visit = (x: unknown): void => {
        if (Array.isArray(x)) {
            x.forEach(visit);
            return;
        }
        if (typeof x === "object" && x !== null && Array.isArray((x as { records?: unknown }).records)) {
            ((x as { records: unknown[] }).records).forEach(visit);
            return;
        }
        const r = toRecord(x);
        if (r) out.push(r);
    };
    visit(input);
    return out;
}

export function buildReplayRows(nonHtml: ExportRecord[], html: ExportRecord[]): ReplayRow[] {
    const rows: ReplayRow[] = [
        ...nonHtml.map((r, i): ReplayRow => ({ ...r, kind: "nonhtml", seq: i })),
        ...html.map((r, i): ReplayRow => ({ ...r, kind: "html", seq: nonHtml.length + i })),
    ];
    const rank = (r: ReplayRow) => (r.kind === "nonhtml" ? 0 : 1);
    const cmp = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);
    return rows.sort(
        (a, b) => cmp(a.mtime, b.mtime) || rank(a) - rank(b) || cmp(a.file, b.file) || a.seq - b.seq,
    );
}

export function replayForK(rows: ReplayRow[], k: number): KResult {
    const state = createNonHtmlPrefixState({ ...NONHTML_PREFIX_DEFAULTS, minNonHtml: k });
    const never = () => false; // no exemption: the replay has no previous dataset
    const res: KResult = {
        k, keysLearned: 0, keysReleased: 0, avoidedNonHtml: 0, htmlBlocked: 0,
        isolated: 0, nonHtmlRows: 0, htmlRows: 0,
    };
    for (const row of rows) {
        if (row.kind === "nonhtml") {
            res.nonHtmlRows++;
            if (decide(state, row.url, never) === "block") {
                // a blocked URL is never fetched, hence never recorded
                if (!hasIgnoredExtensionForSeed(row.url)) res.avoidedNonHtml++;
                continue;
            }
            const ev = recordNonHtml(state, row.url, "1970-01-01T00:00:00.000Z");
            if (ev === "learned") res.keysLearned++;
            else if (ev === "isolated") res.isolated++;
        } else {
            res.htmlRows++;
            if (decide(state, row.url, never) === "block") res.htmlBlocked++;
            if (recordHtml(state, row.url) === "released") res.keysReleased++;
        }
    }
    return res;
}

export function replayAll(rows: ReplayRow[], kMin = 1, kMax = 10): KResult[] {
    const out: KResult[] = [];
    for (let k = kMin; k <= kMax; k++) out.push(replayForK(rows, k));
    return out;
}

export function formatReport(results: KResult[]): string {
    const cols = (c: string[]) => c.map((v, i) => v.padStart(i === 0 ? 2 : 13)).join("  ").trimStart();
    const lines = [cols(["K", "learned", "released", "avoided", "html_blocked", "isolated"])];
    for (const r of results) {
        lines.push(cols([r.k, r.keysLearned, r.keysReleased, r.avoidedNonHtml, r.htmlBlocked, r.isolated].map(String)));
    }
    return lines.join("\n") + "\n";
}

const USAGE =
    "Usage: nonHtmlPrefixReplay.ts <pdf-export.json> <main-export.json>\n" +
    "  Exports of GET /admin/dataset/{crawl_id}?kind=pdf and ?kind=main (paginate: limit<=100, concatenate the pages).";

export function main(argv: string[]): number {
    if (argv.length !== 2) {
        console.error(USAGE);
        return 2;
    }
    let pdf: unknown;
    let mainData: unknown;
    try {
        pdf = JSON.parse(fs.readFileSync(path.resolve(argv[0]), "utf-8"));
        mainData = JSON.parse(fs.readFileSync(path.resolve(argv[1]), "utf-8"));
    } catch (e) {
        console.error(`Cannot read export: ${(e as Error).message}`);
        return 1;
    }
    const rows = buildReplayRows(extractRecords(pdf), extractRecords(mainData));
    console.log(`# rows: ${rows.length} (order: mtime asc, non-HTML first on ties)`);
    console.log(formatReport(replayAll(rows)).trimEnd());
    return 0;
}

const samePath = (a: string, b: string) =>
    process.platform === "win32" ? path.resolve(a).toLowerCase() === path.resolve(b).toLowerCase()
        : path.resolve(a) === path.resolve(b);

// Run only when launched directly (never on import, e.g. from the test file).
if (process.argv[1] !== undefined && samePath(process.argv[1], fileURLToPath(import.meta.url))) {
    process.exit(main(process.argv.slice(2)));
}
```

- [ ] **Step 4: constater le succès ciblé**

Run : `cd <CR> && node --import tsx --test src/tools/nonHtmlPrefixReplay.test.ts`
Attendu : `ℹ pass 10`, `ℹ fail 0`. Si un compteur de la fixture diverge (K=3 `isolated`, `htmlBlocked`), relire la sémantique C1 de l'index (étape 8 de `recordNonHtml` : une non-HTML sous K compte « isolated ») avant de toucher au test : l'écart signale une divergence de T1, à rapporter, pas à absorber.

- [ ] **Step 5: contrôle de la garde CLI (usage ⇒ 2)**

Run : `cd <CR> && node --import tsx src/tools/nonHtmlPrefixReplay.ts`
Attendu : ligne `Usage: nonHtmlPrefixReplay.ts …` sur stderr. Puis, SANS pipe : `cd <CR> && node --import tsx src/tools/nonHtmlPrefixReplay.ts; echo "code=$?"` ⇒ `code=2`.

- [ ] **Step 6: suite complète**

Run : `cd <CR> && npm test 2>&1 | tail -12`
Attendu : `ℹ fail 0` et `ℹ pass` = `<BASE>` + 10 (`<BASE>` mesuré au Step 0 ; 10 = nombre de `test(` du fichier ci-dessus, compté sur le bloc).

- [ ] **Step 7: commit**

Write `<scratchpad>/commit-T09.txt` (outil Write) :

```text
feat(crawler): add non-HTML prefix replay instrument to derive K (R23)

Pure lib + guarded CLI replaying recordNonHtml/recordHtml/decide for K=1..10
over exports of the pdf and main datasets (GET /admin/dataset). Reports per K
the learned/released keys, HTML pages that would have been blocked and the
non-HTML URLs that would have been avoided. Replay order is mtime-based
(the endpoint serves no row timestamp); ties put non-HTML first.

FR — ajout de l'instrument de rejeu des préfixes non-HTML pour dériver K (R23)

Lib pure + CLI gardé rejouant recordNonHtml/recordHtml/decide pour K=1..10 sur
des exports des datasets pdf et main. Rapporte par K les clés apprises et
libérées, les pages HTML qui auraient été bloquées et les URLs non-HTML
évitées. L'ordre de rejeu suit le mtime (l'endpoint ne sert pas le timestamp
des lignes) ; à égalité, le non-HTML passe en premier.
```

Puis :
- `git -C <WT> add apps-microservices/crawler-service/crawler/src/tools/nonHtmlPrefixReplay.ts apps-microservices/crawler-service/crawler/src/tools/nonHtmlPrefixReplay.test.ts`
- `git -C <WT> diff --cached --stat` doit lister exactement ces 2 fichiers.
- `git -C <WT> commit -F <scratchpad>/commit-T09.txt`
- Contrôle d'effet : `git -C <WT> ls-files --eol -- apps-microservices/crawler-service/crawler/src/tools/nonHtmlPrefixReplay.ts apps-microservices/crawler-service/crawler/src/tools/nonHtmlPrefixReplay.test.ts` (fichiers neufs : consigner `i/lf` ou `i/crlf` tel quel, aucune comparaison).

- [ ] **Step 8: exécution réelle du rejeu [contrôleur]**

Hors dépôt et hors portée de l'implémenteur (exports de crawls stockés = appels à l'API admin de la VM avec clé). Le contrôleur exporte `kind=pdf` et `kind=main` d'un crawl marsaleix (pagination `limit=100`), concatène les pages en deux fichiers, lance `cd <CR> && node --import tsx src/tools/nonHtmlPrefixReplay.ts <pdf.json> <main.json>` et consigne le tableau au registre R23 pour arbitrer K.
### Task 10: Documentation + vérification finale + registre
> NOMS NEUFS : aucun (consomme `NONHTML_PREFIX_MODE`, `NONHTML_PREFIX_MIN`, `NONHTML_PREFIX_PROBES`, `NONHTML_ISOLATED_MAX` ⇐ T1 ; `__nonhtml_prefixes.json` ⇐ T2 ; `filtered_nonhtml` ⇐ T4/T5/T6 ; logs ⇐ T3 ; whitelist `NONHTML_` ⇐ T8)

**Blocked by:** 1, 2, 3, 4, 5, 6, 7, 8, 9

**Goal:** Documenter dans `apps-microservices/crawler-service/CLAUDE.md` l'apprentissage des préfixes non-HTML (modes, réglages, sidecar, compteur, logs, chemin de la variable jusqu'au conteneur, `/admin/config`), puis rejouer la vérification finale de tout le plan et consigner au registre les phases hors plan.

**Files:**
- Modify: `apps-microservices/crawler-service/CLAUDE.md`

**Acceptance Criteria:**
- [ ] Une section `## Non-HTML Prefix Learning` existe UNE fois, insérée juste avant `## Phase-2 limitDiez (zero-touch)` (après la section `## Failure Classification & Auto-Recovery on Restart`, dont elle ne sépare pas le « See also » de `## HTTP Status & Navigation Retry Policy`).
- [ ] `git -C <WT> diff --numstat -- apps-microservices/crawler-service/CLAUDE.md` après `git add` : 0 ligne supprimée (insertion pure ; aucun fait existant du fichier n'est contredit par le code, voir Step 1).
- [ ] `git -C <WT> ls-files --eol -- apps-microservices/crawler-service/CLAUDE.md` indique `i/lf` après `git add` ; la copie de travail reste `w/crlf` (pas `w/mixed`).
- [ ] La section cite : les 3 modes et le défaut `off`, `NONHTML_PREFIX_MIN` = 5, `NONHTML_PREFIX_PROBES` = 3, `NONHTML_ISOLATED_MAX` = 10000, le sidecar `__nonhtml_prefixes.json` et son invisibilité (`_count_files_in_dir` `crawler_manager.py`, lecteur `functions.ts`), la probation, l'exemption, `filtered_nonhtml`, les logs `would block` et `released`, le chemin `docker-compose.yml` `env_file`, `GET /admin/config`.
- [ ] Suite TS complète : `ℹ fail 0` et `ℹ pass <PASS_T09>` (le `ℹ pass` mesuré à la fin de T9 ; T10 ajoute 0 `test(`).
- [ ] pytest de T8 vert (commande de la Verify de T8).
- [ ] `git -C <WT> diff --stat e57409aed --diff-filter=M -- '*.test.ts'` : sortie vide (aucun test existant modifié).
- [ ] Une seule entrée de registre touchée (R23), par l'étape `[contrôleur]`.

**Verify:** `cd <CR> && npm test 2>&1 | tail -12`

**Steps:**

- [ ] **Step 1: Mesurer l'état de départ (lecture seule)**

  Les faits ci-dessous ont été relus à la rédaction (2026-10-16, base `e57409aed`) ; les re-mesurer, ne pas les croire.

  ```bash
  git -C <WT> ls-files --eol -- apps-microservices/crawler-service/CLAUDE.md
  ```
  Attendu : `i/lf    w/crlf`. (Mesuré à la rédaction : 1162 séquences CRLF pour 1162 lignes.)

  ```bash
  PYTHONIOENCODING=utf-8 python -I -c "print(open(r'<WT>/apps-microservices/crawler-service/CLAUDE.md',encoding='utf-8',newline='').read().count('## Phase-2 limitDiez (zero-touch)'))"
  ```
  Attendu : `1` (mesuré à la rédaction ; ligne 999, précédée de la ligne 997 `Spec: docs/superpowers/specs/2026-06-16-crawler-failure-recovery-design.md.`). Même commande avec `NONHTML` : attendu `0` (le fichier ne contient encore rien de R23 (2)).

  Faits à relire dans le code avant d'écrire la section (chacun est cité dans le texte inséré) :

  ```bash
  grep -n "name.startswith('__')" <WT>/apps-microservices/crawler-service/app/core/crawler_manager.py
  grep -n "file.endsWith('.json') && !file.startsWith('__')" <WT>/apps-microservices/crawler-service/crawler/src/functions.ts
  grep -n "env_file" <WT>/docker-compose.yml
  grep -n "NONHTML" <WT>/docker-compose.yml
  grep -n "create_subprocess_exec" <WT>/apps-microservices/crawler-service/app/core/crawler_manager.py
  grep -n "_ENV_WHITELIST_PREFIXES = (" <WT>/apps-microservices/crawler-service/app/router/admin.py
  ```
  Attendus (rédaction) : `crawler_manager.py:155` ; `functions.ts:1293` ; `docker-compose.yml:1416` (`env_file:` du service `crawler-service`, bloc commençant à `:1392`, suivi de `- .env`) ; `NONHTML` dans `docker-compose.yml` : aucune sortie ; `crawler_manager.py:794` (appel SANS `env=` ⇒ le sous-processus Node hérite de l'environnement du conteneur Python) ; `admin.py:191`. Si T8 est fait, `grep -n '"NONHTML_"' <WT>/apps-microservices/crawler-service/app/router/admin.py` doit rendre une ligne dans ce tuple. **Un fait qui ne se retrouve pas ⇒ STOP, ne pas écrire la phrase correspondante, rapporter.**

  Contradiction avec un fait existant du fichier : aucune trouvée à la rédaction (la ligne 1074, `GET /admin/config` « whitelisted Node env (DIEZ_/QM_/TIMING_…) », reste exacte : `NONHTML_` s'y ajoute sans la contredire ; elle n'est PAS réécrite, la section ci-dessous le dit). Suppressions autorisées : 0.

- [ ] **Step 2: Insérer la section (outil Edit, ancre = ligne entière unique)**

  Outil **Edit** sur `<WT>/apps-microservices/crawler-service/CLAUDE.md`.

  `old_string` (une ligne entière ; compte de sous-chaîne = 1, mesuré Step 1) :

  ```text
  ## Phase-2 limitDiez (zero-touch)
  ```

  `new_string` = le bloc ci-dessous (quatre apostrophes inverses = la section elle-même, à copier SANS la clôture) suivi d'une ligne vide puis de la ligne `## Phase-2 limitDiez (zero-touch)` :

  ````markdown
  ## Non-HTML Prefix Learning (R23 (2), `NONHTML_PREFIX_MODE`)

  Stops the crawler from replaying extension-less non-HTML URLs (measured case: `marsaleix.fr`
  `/image/…`, every attempt a 90 s `Navigation timed out`). R23 (1) capped the retries
  (`TIMEOUT_MAX_RETRIES`, see "HTTP Status & Navigation Retry Policy"); this feature stops the
  URLs being queued and navigated at all. The unit is the **parent folder** of the URL path
  (`prefixKey`: `https://www.marsaleix.fr/image/_1AAAB-x?y=1#z` ⇒ `www.marsaleix.fr/image`; a root-level
  URL has no key and is only tracked as an *isolated* URL).

  **Mode — `NONHTML_PREFIX_MODE` (Node, read once at startup by `main.ts`):**

  | Value | Behaviour |
  |---|---|
  | `off` (**default**; also `""` and any unknown value) | zero effect: `context.nonHtmlPrefix` stays `null`, no sidecar read or written, no counter, **no `filtered_nonhtml` key in the payload** |
  | `shadow` | learns, persists and logs, **never blocks** and never increments `filtered_nonhtml`; the measure is in the logs (below) |
  | `on` | blocks at the three points (enqueue, seed re-queue, pre-navigation) and counts `filtered_nonhtml` |

  **Tunables (Node env, inherited like the others; an empty, non-integer or ≤ 0 value falls back to the
  default — never to 0):**

  | Variable | Default | Effect |
  |---|---|---|
  | `NONHTML_PREFIX_MIN` | `5` | non-HTML responses under one key (with no HTML seen) before it blocks (K) |
  | `NONHTML_PREFIX_PROBES` | `3` | URLs of a loaded key let through per crawl to re-check it |
  | `NONHTML_ISOLATED_MAX` | `10000` | cap on remembered key-less / under-K URLs in the sidecar |

  **What counts, and the veto.** Only a response that failed the `text/html` content-type guard
  (`routes.ts`, log `Skipping non-HTML response:`) counts, and only if the URL has no ignored
  extension. **One HTML page of class `ok` under a key vetoes it for the rest of the crawl** (a 404 HTML
  page releases nothing). A key blocks once `nonHtml ≥ K` with no HTML seen, or once confirmed.

  **Sidecar `__nonhtml_prefixes.json`.** Location: `storage/datasets/<domain>/__nonhtml_prefixes.json`
  (relative to the job's storage path, i.e. the main dataset directory). Format: one JSON line,
  `{"version":1,"prefixes":{"<key>":{"nonHtml":n,"confirmedAt":…}},"urls":[…]}`. Written through
  `__nonhtml_prefixes.json.tmp` + rename on every learned / confirmed / isolated event, never raising
  into the crawl (a failure is a `console.warn`). A missing, corrupt or other-version file reads as
  empty. It is **invisible to the dataset readers by design**: `_count_files_in_dir`
  (`app/core/crawler_manager.py:146`) skips every name starting with `__` (`:155`), and the
  previous-dataset reader in `functions.ts` (`:1293`) requires `.json` AND no `__` prefix — the `.tmp`
  name fails both. Same lifecycle as `__unjudged_urls.json`: it is dropped with the dataset on a clean
  restart (`dropData`) and kept across an OOM relaunch; nothing is created at startup.

  **Probation at the next crawl (update mode only).** The previous crawl's sidecar (looked up under
  `<previousId>/storage/datasets/<domain>`, then the dots→hyphens name) loads each key **unconfirmed**:
  the first `NONHTML_PREFIX_PROBES` URLs of the key pass, one at a time. Any non-HTML response confirms
  the key; one HTML page releases it (log `Non-HTML prefix released:`); a probe that fails
  (`failedRequestHandler`, i.e. after the capped retries) does not release it, and when all probes are
  spent with no signal the key is confirmed and stays persisted. The current crawl's own sidecar (OOM
  relaunch) loads already confirmed, and is loaded first.

  **Exemption.** A URL of the previous main dataset (`source === 'dataset'` in the `main.ts` consolidation
  loop) and the homepage are never blocked, at any point; the comparison ignores a trailing `/`. The
  set is complete before the crawler starts (`startCrawler` runs after the consolidation).

  **Counter `filtered_nonhtml`.** Incremented only when a block is effective (mode `on`): enqueue
  (`routes.ts`), pre-navigation (`functions.ts`, which also counts `purged_prenav` through
  `StaleVariantSkip` — the overlap is intended, `failed` stays correct) and seed re-queue (`main.ts`).
  It is read by `readStat("filtered_nonhtml")` and shipped in `_callback_payload.json` **only when the
  gate exists** (`shadow` and `on`; absent in `off`). It counts handler passes, like `filtered_nonfr`
  (an OOM relaunch resumes the same `stats:{id}` hash). BO does not persist it (spec § 7).

  **Logs to count in `shadow`** (`GET /admin/logs/{crawl_id}?grep=…`):

  | Log | Meaning |
  |---|---|
  | `[nonhtml-prefix] would block (enqueue\|prenav\|seed):` | what `on` would have filtered — the gain |
  | `Non-HTML prefix released:` | a key that was blocking (or on probation) then served HTML — **a false positive**; any occurrence is read before switching to `on` |
  | `Non-HTML prefix learned:` / `… confirmed by probe:` | key learned this crawl / confirmed by a probe |
  | `[nonhtml-prefix] probe (…):` / `probe failed:` / `blocked (…):` | probe let through / probe failure / effective block (`on`) |
  | `[nonhtml-prefix] mode=… K=… probes=… loaded current=… previous=… isolated=…` | startup line: the mode and the loaded state |

  **How the variable reaches the container.** `docker-compose.yml` has **no `NONHTML_*` line**: the
  `crawler-service` block (`:1392`) takes the shared `.env` through `env_file: - .env` (`:1416-1417`), so
  the mode is set on the VM by adding `NONHTML_PREFIX_MODE=shadow` to that `.env` and recreating the
  container (a plain restart does not re-read `.env`). The Python orchestrator spawns the Node crawler
  with `create_subprocess_exec` and no `env=` (`crawler_manager.py:794`), so Node inherits it. **It is
  global to the VM — every domain; no per-domain switch exists.** If a `NONHTML_*` line is ever added to
  the compose `environment:` block, `tests/test_admin_config.py::test_compose_env_parity` requires it to
  match `_ENV_WHITELIST_PREFIXES` (`NONHTML_` does).

  **Checking the mode without a shell:** `GET /admin/config` lists the Node env whose name starts with a
  whitelisted prefix; `NONHTML_` is in `_ENV_WHITELIST_PREFIXES` (`app/router/admin.py`), so the raw
  `NONHTML_PREFIX_MODE` (absent ⇒ `off`) appears under `env`. The older line of the endpoint table above
  (`DIEZ_/QM_/TIMING_…`) is an example list, not the full whitelist.

  **Rollout (outside the code plan, tracked in the registry, entry R23):** merge `features/poc`, push,
  rebuild with the mode `off` → `shadow` on a few update crawls (count `would block` and `released`) →
  replay K with `crawler/src/tools/nonHtmlPrefixReplay.ts` on `pdf` + `main` exports (`_DATASET_PREFIXES`
  has a `pdf` kind) → `on` → effect proof: 0 `Navigation timed out` on `/image/` once the key is loaded or
  learned, and `filtered_nonhtml` > 0.

  Spec: `docs/superpowers/specs/2026-10-16-crawler-nonhtml-prefix-learning-design.md`.
  Plan: `docs/superpowers/plans/2026-10-16-crawler-nonhtml-prefix-learning.md`.
  ````

  Avant de lancer l'Edit : relire chaque affirmation de la section contre la sortie des relevés du Step 1 (ex. `:1416-1417`, `:794`, `:155`, `:1293`) ; si un numéro a bougé, corriger le numéro dans le `new_string` (jamais la phrase).

- [ ] **Step 3: Contrôles d'effet de l'édition**

  ```bash
  git -C <WT> ls-files --eol -- apps-microservices/crawler-service/CLAUDE.md
  ```
  Attendu : `i/lf    w/crlf`. Un `w/mixed` = l'Edit a écrit des lignes LF : convertir les lignes insérées en CRLF (script Python en `'rb'`/`'wb'` qui remplace `\n` isolé par `\r\n` sur la zone insérée), puis relire ce contrôle.

  ```bash
  PYTHONIOENCODING=utf-8 python -I -c "t=open(r'<WT>/apps-microservices/crawler-service/CLAUDE.md',encoding='utf-8',newline='').read(); print(t.count('## Non-HTML Prefix Learning'), t.count('## Phase-2 limitDiez (zero-touch)'), t.count('NONHTML_PREFIX_MODE')>=5)"
  ```
  Attendu : `1 1 True`.

  ```bash
  git -C <WT> add apps-microservices/crawler-service/CLAUDE.md
  ```
  ```bash
  git -C <WT> diff --cached --numstat
  ```
  Attendu : une seule ligne, `<N>  0  apps-microservices/crawler-service/CLAUDE.md` (N = lignes de la section, **0 supprimée**). Une suppression > 0 ⇒ l'Edit a touché autre chose : `git -C <WT> reset -- apps-microservices/crawler-service/CLAUDE.md`, restaurer, recommencer. Puis :

  ```bash
  git -C <WT> ls-files --eol -- apps-microservices/crawler-service/CLAUDE.md
  ```
  Attendu : `i/lf    w/crlf` (index resté LF).

- [ ] **Step 4: Vérification finale du plan (lecture/exécution, aucune édition)**

  **4a. Suite TS complète** (le `ℹ pass` de départ est celui noté à la fin de T9 ; le relire dans la sortie de la Verify de T9 et l'appeler `<PASS_T09>` ; T10 ajoute 0 `test(`) :

  ```bash
  cd <CR> && npm test 2>&1 | tail -12
  ```
  Attendu : `ℹ fail 0` ET `ℹ pass <PASS_T09>` (= 509 + total des `test(` neufs de T1-T9). Mesure : écrire la valeur lue. Un `ℹ pass` différent de `<PASS_T09>` ou un `fail` > 0 ⇒ STOP, ne pas commiter, rapporter.

  **4b. pytest de T8** : lancer **la commande de la Verify de T8** (section T08), sans la retaper ici ni l'adapter. Attendu : le succès décrit dans cette section, compte de tests **non nul**.

  **4c. Commits du plan** :

  ```bash
  git -C <WT> log --oneline e57409aed..HEAD
  ```
  Attendu : les commits de documentation du plan (`75364b2e6`, `f4377f823`, `3a2d707bf`, puis le commit d'assemblage du plan s'il y en a un) ET un commit par tâche T1 à T9 (messages écrits via `<scratchpad>/commit-T01.txt` … `commit-T09.txt`) ; **pas encore** celui de T10. Compter les commits de tâches : 9. Un manquant ⇒ rapporter la tâche.

  **4d. Aucun test existant modifié** :

  ```bash
  git -C <WT> diff --stat e57409aed --diff-filter=M -- '*.test.ts'
  ```
  Attendu : **sortie vide** (les `*.test.ts` du plan sont tous des fichiers neufs, filtre `M` = modifiés).

- [ ] **Step 5: Commit de la documentation**

  Écrire avec l'outil **Write** le fichier `<scratchpad>/commit-T10.txt` :

  ```text
  docs(crawler): document non-HTML prefix learning (R23)

  Add the "Non-HTML Prefix Learning" section to the crawler-service
  CLAUDE.md: NONHTML_PREFIX_MODE (off/shadow/on, default off), the three
  tunables and their defaults, the __nonhtml_prefixes.json sidecar and why
  dataset readers do not see it, probation, exemption, the filtered_nonhtml
  counter, the shadow logs to count, how the variable reaches the container
  (env_file) and GET /admin/config. Pure insertion, no line removed.

  FR — docs(crawler) : documenter l'apprentissage des préfixes non-HTML (R23)

  Ajoute la section « Non-HTML Prefix Learning » au CLAUDE.md du
  crawler-service : NONHTML_PREFIX_MODE (off/shadow/on, défaut off), les
  trois réglages et leurs défauts, le sidecar __nonhtml_prefixes.json et
  son invisibilité aux lecteurs du dataset, la probation, l'exemption, le
  compteur filtered_nonhtml, les logs à compter en shadow, le chemin de la
  variable jusqu'au conteneur (env_file) et GET /admin/config. Insertion
  pure, aucune ligne supprimée.
  ```

  ```bash
  git -C <WT> diff --cached --stat
  ```
  Attendu : exactement `apps-microservices/crawler-service/CLAUDE.md`.

  ```bash
  git -C <WT> commit -F <scratchpad>/commit-T10.txt
  ```
  ```bash
  git -C <WT> status --short
  ```
  Attendu : sortie vide.

- [ ] **Step 6: [contrôleur] Consigner les phases hors plan au registre R23**

  Hors portée de l'implémenteur (écriture sous `C:/Users/USER/.claude`, registre mémoire). Le contrôleur écrit, dans l'entrée `### R23 · crawler-service` de `C:/Users/USER/.claude/projects/D--DevHellopro-Workspaces-RAG-HP-PUB/memory/ACTIONS.md`, une ligne insérée **juste avant** la ligne `- **En attente** : user — déployer (1) dans la journée du 2026-10-16` (ancre dont le compte était **1** à la rédaction, 2026-10-16 ; re-compter) :

  ```text
    Phases d'exécution hors plan (index § Phases d'exécution 2), chacune une décision de l'user : (a) merger `worktree-r23-nonhtml-prefix` dans `features/poc` puis pousser et rebuild `./tools/build_crawler.sh --up` mode `off` (ajouter rien à `.env`) ; (b) `NONHTML_PREFIX_MODE=shadow` dans le `.env` de la VM + recréer le conteneur, vérifier par `GET /admin/config`, compter `would block` et `released` sur quelques MAJ ; (c) rejeu K (`crawler/src/tools/nonHtmlPrefixReplay.ts`, T9) sur exports `pdf` + `main` ; (d) `on` ; (e) preuve d'effet spec § 6 (0 `Navigation timed out` sur `/image/`, `filtered_nonhtml` > 0). Variable GLOBALE à la VM. Détail : section `## Non-HTML Prefix Learning` de `apps-microservices/crawler-service/CLAUDE.md`. Re-dériver (a) : `git -C D:/DevHellopro/Workspaces/RAG-HP-PUB merge-base --is-ancestor <sha T10> origin/features/poc`.
  ```

  et remplace le bloc `- **Reprise** :` de R23 par le prompt de reprise de la phase suivante (règle `actions-a-faire.md` : un prompt périmé se retire). **Repli si le mode auto refuse l'écriture (`[Self-Modification]`)** : écrire un script `<scratchpad>/r23_registre_patch.py` (outil Write) qui (1) lit `ACTIONS.md` en `'rb'`, (2) `assert data.count(ANCRE) == 1` avec `ANCRE` = les octets UTF-8 de `- **En attente** : user — déployer (1) dans la journée du 2026-10-16`, (3) insère la ligne ci-dessus avant l'ancre, (4) n'écrit (`'wb'`, fichier temporaire puis remplacement) que sans `--check` ; lancer `python <scratchpad>/r23_registre_patch.py --check` (lecture seule, compte et affiche le delta attendu) ; puis donner à l'user la commande d'écriture à lancer lui-même : `! python <scratchpad>/r23_registre_patch.py`. Après écriture (hook ou script) : relire le fichier, `grep -c '^### R23 ' ACTIONS.md` = 1, et re-dériver la place de l'entrée (`grep -n '^## \|^### R23 '`).

- [ ] **Step 7: [contrôleur] Graphe graphify : mesurer, puis décider**

  Le skill `graphify` est hors portée de l'implémenteur. Mesure en lecture seule, depuis le worktree :

  ```bash
  cd <WT> && python scripts/graphify_plan_update.py
  ```
  Code retour 0 ⇒ rien n'est dû, fin. Sinon le script liste les zones dues et pourquoi (un `.md` modifié = extraction LLM requise ; un fichier absent du graphe = hors portée du hook post-commit). Décision du contrôleur : si `apps-microservices/crawler-service` est listé, lancer `/graphify apps-microservices/crawler-service --update` **avec ce chemin explicite** (jamais `--update` nu, jamais `graphify update .`, jamais supprimer `graphify-out/manifest.json`) ; si le service n'est pas dans le périmètre du graphe (le CLAUDE.md du dépôt cite 4 services sur 99 : `crawler-service` en est), noter la décision au rapport final. Aucune écriture du graphe par l'implémenteur.
