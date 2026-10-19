# Disjoncteur `not_eligible` séparé — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Séparer, dans le disjoncteur de MAJ du crawler, les URLs du dataset devenues non éligibles (CASE 3) des erreurs HTTP (CASE 1), chacune avec son seuil (0,15 HTTP inchangé ; 0,5 `not_eligible` neuf).

**Architecture:** Un compteur Redis `not_eligible` neuf écrit à côté de `errors` en CASE 3 de `UpdateChecker.checkUrl()`. La fonction pure `shouldTripErrorRateBreaker()` prend deux décisions sur le même dénominateur (`processed + errorsUnprocessed`) : HTTP = `max(0, errors − notEligible)`, puis `notEligible`. Le seuil `maxNotEligibleRate` traverse tous les étages comme `maxErrorRate` (contexte, CLI Node, schéma et mappage Python) ; le rapport `_update_report.json` gagne deux clés additives.

**Tech Stack:** TypeScript (Node 22, `node:test` via `tsx`, `tsc`), Python 3.12 (FastAPI, Pydantic 2, pytest).

**Spec:** `docs/superpowers/specs/2026-10-19-not-eligible-breaker-design.md` (commit `6784d3cc3`). Toute ancre `fichier:ligne` de ce plan est lue à `3cd3b7af` (= `features/poc`, base du worktree).

## Global Constraints

- Préfixe de la raison HTTP **`Error rate too high (`** conservé octet pour octet ; suffixe HTTP **`${httpErrors} HTTP errors / ${attempts} attempts`** (spec §3). Raison neuve : préfixe **`Not-eligible rate too high (`**.
- Défaut **0,5** partout (`context.ts`, CLI `main.ts`). Comparaison **stricte** `>` pour les deux décisions (égalité au seuil ⇒ pas d'arrêt).
- `maxErrorRate` non `> 0` ⇒ les DEUX décisions coupées (décision 2 avant 3 et 4). `maxNotEligibleRate` absent ou `0` ⇒ décision 4 coupée seule.
- `notEligible` absent ⇒ résultat **identique** à l'ancien : les 9 tests existants de `errorRateBreaker.test.ts` passent **sans modification**.
- `errors` reste le compteur combiné : aucun lecteur de `errors` hors du disjoncteur n'est modifié (spec §4 — `routes.ts` mode micro et legacy `maxErrors`, `updateHealthVerdict.ts` code).
- Aucune modification de `StatsManager.ts`, `nonHtmlPrefixWiring.test.ts`, des régions R23, ni d'aucun fichier BO / Marketplace.
- Commits : Conventional Commits, sujet EN, corps EN puis `FR — <sujet français>` + corps FR ; message écrit dans un fichier, `git commit -F <fichier>`.

**User decisions (already made):**
- Design (c) approuvé le 2026-10-19, seuil `not_eligible` 0,5 — `D:/DevHellopro/Marketplace/.claude/a8/design_c_approuve_2026-10-19.md`.
- Mappage Python `max_not_eligible_rate` (spec §3.2) GARDÉ dans ce lot.
- Suffixe « HTTP errors » de la raison HTTP (spec §3) GARDÉ.
- Spec inchangée ; option (b) (séparer le verdict de santé) écartée.

---

## Environnement d'exécution (mesuré au 2026-10-19, session de rédaction)

- Session **lancée dans le worktree** `D:/DevHellopro/Workspaces/RAG-HP-PUB/.claude/worktrees/a8-not-eligible-breaker`, branche `worktree-a8-not-eligible-breaker`, garde d'isolation ARMÉE : elle refuse une variable shell en position d'option (`sed -n 1p $S/x` refusé, mesuré) ⇒ **chemins littéraux**, relatifs à la racine du worktree ou absolus ; une commande git par appel.
- Shell Bash de l'outil : `type ls grep sed awk` ⇒ `/usr/bin/ls`, `/usr/bin/grep` (hashed), `/usr/bin/sed`, `/usr/bin/awk` (source : `D:/DevHellopro/Marketplace/.claude/a8/plan_facts_raw_2026-10-19.txt`, section `== shell`).
- ⛔ **Ne jamais `cd` dans `apps-microservices/crawler-service`** ni `Read` un fichier sous ce dossier depuis le fil principal : son `CLAUDE.md` (~25k tokens) est alors injecté. cwd = racine du worktree ; lire par `grep -n` / `sed -n` en chemin relatif. (Un implémenteur qui édite par l'outil Edit doit lire le fichier par Read : coût accepté dans SON contexte.)
- `CRAWLER` ci-dessous = `apps-microservices/crawler-service/crawler` (abréviation de lecture du plan ; **toujours écrire le chemin en entier dans une commande**).

### Commandes prescrites (sondées le 2026-10-19 depuis la racine du worktree)

| Usage | Commande | Sonde |
|---|---|---|
| Un fichier de test TS | `node --import file:///D:/DevHellopro/Workspaces/RAG-HP-PUB/.claude/worktrees/a8-not-eligible-breaker/apps-microservices/crawler-service/crawler/node_modules/tsx/dist/loader.mjs --test D:/DevHellopro/Workspaces/RAG-HP-PUB/.claude/worktrees/a8-not-eligible-breaker/apps-microservices/crawler-service/crawler/src/<fichier>.test.ts` | `errorRateBreaker.test.ts` : `tests 9 / pass 9 / fail 0`, rc 0, ~1 s |
| Suite TS entière | `npm --prefix D:/DevHellopro/Workspaces/RAG-HP-PUB/.claude/worktrees/a8-not-eligible-breaker/apps-microservices/crawler-service/crawler test` (en `run_in_background`, ~255 s) | ligne de base : `tests 653 / pass 653 / fail 0`, rc 0 ; la sortie imprime `> crawler-engine@1.0.0 test` (preuve du lieu) |
| Build TS | `npm --prefix D:/DevHellopro/Workspaces/RAG-HP-PUB/.claude/worktrees/a8-not-eligible-breaker/apps-microservices/crawler-service/crawler run build` | ligne de base à `3cd3b7af` : `> crawler-engine@1.0.0 build` / `> tsc`, aucune erreur, rc 0 ; `git status --short` reste vide (sortie `dist/` non suivie) |
| Tests Python | `PYTHONPATH=apps-microservices/crawler-service python -m pytest apps-microservices/crawler-service/tests/<fichier>.py -q -p no:cacheprovider` | `tests/test_crawler.py` : `3 passed`, rc 0 (conftest `apps-microservices/crawler-service/conftest.py` chargé) |
| Contrôle d'EOL (effet d'une édition) | `python -c "import sys; b=open(sys.argv[1],'rb').read(); print('LF', b.count(b'\n'), 'CRLF', b.count(b'\r\n'))" <chemin>` | attendu : les deux nombres **égaux** (fichier tout CRLF) |

⛔ Forme refusée / à ne pas employer : `npm --prefix … exec -- node --import tsx …` (sondé : bloqué > 120 s sans sortie, tué).
⚠ La commande « un fichier » sur un test qui lit le texte source (`import.meta.dirname`) fonctionne : le chemin est relatif au fichier de test, pas au cwd.

## File Structure — propriétés d'octets

`git ls-files --eol -- <chemins>` (2026-10-19, à `3cd3b7af`) : **tous `i/lf w/crlf`**, sauf `CRAWLER/src/functions.ts` **`i/crlf w/crlf`**. `core.autocrlf=true`. Aucun cible ignoré (`git check-ignore -v --no-index` rc 1 sur le plan, `errorRateBreaker.ts`, un test Python neuf, `CLAUDE.md`).

**Règle unique pour tout fichier édité** : outil Edit (préserve le CRLF de la copie de travail) ; **après chaque édition**, contrôle d'EOL ci-dessus ⇒ `LF == CRLF` ; puis `git diff --numstat -- <chemin>` ⇒ ajouts/suppressions conformes à l'attendu de la tâche. Un fichier neuf (test Python) s'écrit en LF ou CRLF sans contrainte, mais le contrôle d'EOL rend alors l'un ou l'autre de façon homogène : `CRLF == 0` ou `LF == CRLF`.

| Fichier | Tâches | Rôle |
|---|---|---|
| `CRAWLER/src/class/UpdateChecker.ts` | T1 | écrivain `not_eligible` (CASE 3) |
| `CRAWLER/src/tests/UpdateChecker.deleteVerdict.test.ts` | T1 | attendu `:116` mis à jour |
| `CRAWLER/src/tests/UpdateChecker.datasetIdentity.test.ts` | T1 | cas `folded` non éligible |
| `CRAWLER/src/errorsUnprocessedParity.test.ts` | **T1, T3** | parité texte UpdateChecker (T1), routes (T3) — fichier partagé |
| `CRAWLER/src/errorRateBreaker.ts` | T2 | fonction pure |
| `CRAWLER/src/errorRateBreaker.test.ts` | T2 | 9 cas intacts + neufs + grille |
| `CRAWLER/src/updateHealthVerdict.ts` | T2 | commentaire `:184` seul |
| `CRAWLER/src/context.ts`, `CRAWLER/src/main.ts`, `CRAWLER/src/routes.ts` | T3 | câblage |
| `CRAWLER/src/functions.ts` | T4 | rapport (`i/crlf`) |
| `CRAWLER/src/statNameParity.test.ts` | T4 (lecture/garde ; extension facultative) | épingle du rapport |
| `apps-microservices/crawler-service/app/schemas/crawler.py`, `…/app/router/crawler.py`, test Python neuf sous `apps-microservices/crawler-service/tests/` | T5 | Python |
| `apps-microservices/crawler-service/CLAUDE.md` | T6 | doc § Circuit Breaker |

**Fichier partagé `errorsUnprocessedParity.test.ts`** (91 lignes, `i/lf w/crlf`, LF 91 = CRLF 91 mesuré) : chaque tâche **ajoute un `test(...)` neuf en fin de fichier** (insertion pure : `git diff --numstat` ⇒ suppressions **0**), n'édite aucun test existant ; contrôle d'EOL après l'édition. T3 localise la fin de fichier par contenu, jamais par le numéro qu'a mesuré T1.

## Faits établis (commande citée ; `grep -n` lancé depuis la racine du worktree à `3cd3b7af`)

- CASE 3 : `grep -n 'increment("\|CASE 3\|No longer eligible' apps-microservices/crawler-service/crawler/src/class/UpdateChecker.ts` ⇒ `348:        //  CASE 3: Success (2xx, no redirect)`, `362:                // No longer eligible → mark as deleted`, `363:                await this.statsManager.increment("errors");`, `375:                    await this.statsManager.increment("accounted");`. Écrivains de `errors` dans ce fichier : `239` (CASE 1) et `363` (CASE 3) — 2 au total. `errors_unprocessed` : `246` seul.
- Fonction pure : `grep -n "export \|Error rate too high\|return {" apps-microservices/crawler-service/crawler/src/errorRateBreaker.ts` ⇒ `35:export interface ErrorRateBreakerStats {`, `44:export interface ErrorRateBreakerConfig {`, `49:export function shouldTripErrorRateBreaker(`, `73:            reason: \`Error rate too high (…` ; fichier 83 lignes, test 126 lignes, 9 `test(` (`== breaker tests` du fichier de faits : lignes 16, 28, 46, 56, 67, 77, 99, 107, 116).
- Lecteurs du résultat du disjoncteur en code de prod : `grep -n "errorBreaker\.\|shouldTripErrorRateBreaker" apps-microservices/crawler-service/crawler/src/*.ts apps-microservices/crawler-service/crawler/src/class/*.ts | grep -v "\.test\.ts"` ⇒ `routes.ts:485` (appel), `routes.ts:494` (`errorBreaker.trip` / `errorBreaker.reason`) — **total 1 site d'appel, 0 lecteur de `.rate`** ⇒ le changement de sens de `rate` (devient le taux HTTP) n'a aucun lecteur de prod ; seuls les tests le lisent (« champ métrique » : aucun lecteur à mettre à jour hors T2).
- Appel routes : `routes.ts:465` `const errorsUnprocessed = await context.statsManager.getValue("errors_unprocessed");`, `routes.ts:485-486` `shouldTripErrorRateBreaker(` / `{ errors, processed, errorsUnprocessed },` ; `const cb = context.config.circuitBreaker;` à `routes.ts:458` (`grep -n "const cb = context.config.circuitBreaker" apps-microservices/crawler-service/crawler/src/routes.ts`).
- Contexte / CLI : `context.ts:57` `circuitBreaker: {`, `context.ts:65` `maxErrorRate: 0.15,     // 15%` ; `main.ts:90` `const parseNumericArg = (key: string, npmKey: string, defaultValue: number): number => {`, `main.ts:132` `const maxErrorRate = parseNumericArg('maxErrorRate', 'npm_config_maxerrorrate', 0.15);`, `main.ts:162` `circuitBreaker: {`, `main.ts:168` `maxErrorRate: maxErrorRate,`, `main.ts:1022` ligne `Limits: MinSample=…ErrorRate=…` (source : fichier de faits, sections `== context`, `== main`).
- Rapport : `functions.ts:1441` `const errorsUnprocessed = …getValue("errors_unprocessed");`, `:1459` `const report = {`, `:1465` `metrics: {`, `:1471` `errors_unprocessed: errorsUnprocessed,`, `:1472` `previous_total: cb.previousTotal`, `:1480` `thresholds: {`, `:1483` `max_error_rate: cb.maxErrorRate,` (fichier de faits, `== functions`).
- Python : `app/schemas/crawler.py:43` `class UpdateThresholds(BaseModel):`, `:51` `max_error_rate: Optional[float] = Field(None, description=…)` ; `app/router/crawler.py:243` `async def start_new_crawl(payload: CrawlRequest):`, `:292-293` mappage `max_error_rate` ⇒ `params["maxErrorRate"]`. Passage à Node générique : `app/core/crawler_manager.py` `for key, value in params.items(): if value is not None: command.append(f"--{key}={value}")` (lu par `sed -n 772,784p`) ⇒ `params["maxNotEligibleRate"]` devient `--maxNotEligibleRate=<v>` sans code neuf. **Aucun test Python existant** ne touche `start_new_crawl` / `update_thresholds` / `maxErrorRate` (`grep -ln "start_new_crawl\|maxErrorRate\|update_thresholds" apps-microservices/crawler-service/tests/*.py` ⇒ vide).
- Tests UpdateChecker : `deleteVerdict.test.ts:116` `assert.deepEqual(stats._calls, ['errors', 'accounted']);`, `:71` et `:87` (CASE 1) ; `datasetIdentity.test.ts:139` `test('a folded match on an eligible 200 stays confirmed but no longer credits accounted', …` (patron pour le cas folded non éligible).
- Parité : `errorsUnprocessedParity.test.ts:22` helper `src(f)` (lit `path.join(import.meta.dirname, f)`), tests `:24`, `:63`, `:83` (`` `errors` keeps exactly its two live writers in UpdateChecker ``).
- Épingle rapport : `statNameParity.test.ts:87`, `:102`, `:119` (`generateUpdateReport…`), `:147` (préfixe disjoncteur ≠ verdict).
- Commentaire : `updateHealthVerdict.ts:184` `// ⚠ Deliberately NOT the words "Error rate too high (" — errorRateBreaker.ts:73 emits that`.
- Doc : `crawler-service/CLAUDE.md:84` `## Circuit Breaker (Update Mode Rate Guards)`, `:98` ligne de table `maxErrorRate`, `:124` phrase fausse (« `updateHealthVerdict.ts` also emits the same `Error rate too high (` prefix… »).

## Contrat — noms produits / consommés (à écrire À L'IDENTIQUE)

| Nom | Produit par | Consommé par |
|---|---|---|
| clé Redis / stat **`not_eligible`** (`increment("not_eligible")`, `getValue("not_eligible")`) | T1 | T3 (`routes.ts`), T4 (`functions.ts`), T6 (doc) |
| `ErrorRateBreakerStats.notEligible?: number` | T2 | T3 |
| `ErrorRateBreakerConfig.maxNotEligibleRate?: number` | T2 | T3 (via `cb`) |
| champ de retour **`notEligibleRate`** (et `rate` = taux HTTP) | T2 | tests T2 seulement |
| raison **`Not-eligible rate too high (`** | T2 | T6 (doc) |
| `context.config.circuitBreaker.maxNotEligibleRate` (défaut `0.50`) | T3 | T4 (`cb.maxNotEligibleRate`) |
| argument CLI **`maxNotEligibleRate`**, clé npm **`npm_config_maxnoteligiblerate`** | T3 | T5 (`params["maxNotEligibleRate"]`) |
| champ Pydantic **`max_not_eligible_rate`** | T5 | — (BO futur) |
| clés de rapport **`metrics.not_eligible`**, **`thresholds.max_not_eligible_rate`** | T4 | T6 (doc), BO (aucun lecteur aujourd'hui, spec §5) |

## Population à couvrir — exigences de la spec ⇒ tâche

| Exigence (spec) | Tâche |
|---|---|
| §2.1 `increment("not_eligible")` juste après `increment("errors")` en CASE 3, deux orthographes, avant l'écriture JSONL `deleted` ; ordre `errors` puis `not_eligible` | T1 |
| §2.1 `StatsManager` non modifié | toutes (contrôle : `git diff --stat` final ne le liste pas — T7) |
| §2.2 numérateur HTTP `Math.max(0, errors − notEligible)` ; clé absente ⇒ ancien disjoncteur | T2 |
| §3 décisions 1-4, comparaisons strictes, interfaces, `notEligibleRate`, propriété de relaxation écrite en en-tête de module | T2 |
| §3 raison HTTP (préfixe + suffixe `HTTP errors`) ; raison `Not-eligible rate too high (` | T2 |
| §3 échappatoire `maxErrorRate = 0` ⇒ deux décisions coupées | T2 (test) |
| §3.1 `routes.ts` : lecture `notEligible`, passage dans l'appel ; rien d'autre | T3 |
| §3.2 `context.ts`, CLI `main.ts`, champ `circuitBreaker`, ligne `Limits:` `NotEligibleRate=…%` | T3 |
| §3.2 schéma + mappage Python | T5 |
| §4 lecteurs de `errors` inchangés ; `updateHealthVerdict.ts:184` re-pointé sur le symbole (commentaire seul) | T2 (commentaire), T7 (contrôle « aucune autre ligne ») |
| §5 rapport : `notEligible` lu à côté de `errorsUnprocessed`, `metrics.not_eligible` après `errors_unprocessed` et avant `previous_total` sans `}` intérieur ; `thresholds.max_not_eligible_rate` après `max_error_rate` | T4 |
| §5 aucun paquet BO ; seuil BO `referentiel_seuils_cb` / `shell.php` | hors plan : décision de spec (§5, §9) |
| §7 `errorRateBreaker.test.ts` (8 cas listés + grille) | T2 |
| §7 parité UpdateChecker (1 `increment("not_eligible")` après `CASE 3: Success` ; `errors` reste à 2) | T1 |
| §7 parité routes (liaison + passage) | T3 |
| §7 `deleteVerdict.test.ts:116` ⇒ `['errors', 'not_eligible', 'accounted']` ; `:71`, `:87` inchangés | T1 |
| §7 cas `folded` 200 non éligible ⇒ `['errors', 'not_eligible']` | T1 |
| §7 Python : présent ⇒ clé, absent ⇒ clé absente | T5 |
| §7 `npm run build` | T3 (après câblage), T7 |
| §8 `statNameParity.test.ts` tient | T4 (run), T7 |
| §8 `CLAUDE.md` § Circuit Breaker + phrase `:124` | T6 |
| §8 branches vivantes : `git merge-base --is-ancestor <tête> features/poc` pour toute branche neuve | T7 |
| Déploiement du crawler-service | hors plan : geste séparé après merge (registre A8) |
| Commentaires citant des NUMÉROS de ligne de `errorRateBreaker.ts` hors `:184` : `updateHealthVerdict.ts:123` (« :53-54 »), `updateHealthVerdict.test.ts:277`, `:322` (signalés par le rédacteur de T2, non re-lus par le contrôleur) | hors plan à la rédaction : à trancher en revue de T2 (re-pointer sur le symbole, commentaire seul) ou laisser ; consigné dans le handoff |

**Pilote** : aucun mécanisme de confinement — le défaut 0,5 s'applique à tous les runs MAJ dès le déploiement (constat ; la spec n'en nomme pas). Seule coupure : `maxNotEligibleRate = 0` via CLI, ou `max_error_rate = 0` (`?bypasscberrors=1`).

## Préconditions des commandes prescrites

- Tests TS : `node_modules` du worktree installé (`npm ci --ignore-scripts`, 2026-10-19) ; ligne de base 653/653 ci-dessus.
- `npm run build` : `context.config.circuitBreaker` est typé par inférence depuis `context.ts` ⇒ T3 ajoute le champ à `context.ts` **avant** de l'affecter dans `main.ts` ; T4 lit `cb.maxNotEligibleRate` ⇒ **T4 dépend de T3**.
- Tests Python : `PYTHONPATH=apps-microservices/crawler-service` obligatoire depuis la racine du worktree (sinon `import app` échoue).
- Garde d'isolation : chaque commande ci-dessus a été lancée telle quelle sous la garde (acceptée et exécutée) sauf `git commit -F` (forme simple, une commande).

## Tâches

| N° | Nom | Fichiers | Dépend de |
|---|---|---|---|
| 1 | Compteur `not_eligible` en CASE 3 | `UpdateChecker.ts`, `tests/UpdateChecker.deleteVerdict.test.ts`, `tests/UpdateChecker.datasetIdentity.test.ts`, `errorsUnprocessedParity.test.ts` | — |
| 2 | Fonction pure à deux décisions | `errorRateBreaker.ts`, `errorRateBreaker.test.ts`, `updateHealthVerdict.ts` (commentaire) | — |
| 3 | Câblage `maxNotEligibleRate` + appel routes | `context.ts`, `main.ts`, `routes.ts`, `errorsUnprocessedParity.test.ts` | 1, 2 |
| 4 | Rapport `_update_report.json` | `functions.ts` (+ `statNameParity.test.ts` facultatif) | 3 |
| 5 | Schéma et mappage Python | `app/schemas/crawler.py`, `app/router/crawler.py`, test Python neuf | — |
| 6 | Doc `CLAUDE.md` § Circuit Breaker | `apps-microservices/crawler-service/CLAUDE.md` | 2, 3, 4, 5 |
| 7 | Vérification finale (sans commit) | — (lecture, suites, build, branches) | 1-6 |

T3 dépend de T1 par le fichier partagé `errorsUnprocessedParity.test.ts` (ordre des insertions) et de T2 par la signature.
### Task 1: Compteur `not_eligible` en CASE 3
> NOMS NEUFS : clé Redis / stat `not_eligible` (`increment("not_eligible")`) (produit) ⇒ T03, T04, T06

**Goal:** `UpdateChecker.checkUrl()` incrémente un compteur `not_eligible` neuf, juste après `errors`, quand une URL du dataset répond 2xx sans redirection mais n'est plus éligible (CASE 3), pour les deux orthographes (exacte et repliée), avant l'écriture JSONL `deleted`. `errors` reste inchangé (2 écrivains).

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/class/UpdateChecker.ts:362-363` (ancre : le commentaire `// No longer eligible → mark as deleted` suivi de `increment("errors")` — `:363` seul n'est pas unique, `:239` est identique ; l'ancre est donc sur deux lignes)
- Modify: `apps-microservices/crawler-service/crawler/src/tests/UpdateChecker.deleteVerdict.test.ts:116` (attendu) et `:109` (titre du test)
- Modify: `apps-microservices/crawler-service/crawler/src/tests/UpdateChecker.datasetIdentity.test.ts:150` (insertion d'un test neuf avant `// TEST 8`)
- Modify: `apps-microservices/crawler-service/crawler/src/errorsUnprocessedParity.test.ts:83-91` (test neuf ajouté en fin de fichier, insertion pure)

Chemins `Modify` lus à `3cd3b7af` (`grep -n` : `UpdateChecker.ts:362` commentaire, `:363` `increment("errors")`, `:370` `writeJsonl(UpdateChecker.DELETED_FILE, result)` ; `deleteVerdict.test.ts:116` ; `datasetIdentity.test.ts:150` `// TEST 8`).

**Acceptance Criteria:**
- [ ] En CASE 3, dataset, 2xx, inéligible, orthographe exacte : `stats._calls` vaut `['errors', 'not_eligible', 'accounted']` (`deleteVerdict.test.ts`).
- [ ] Même scénario, orthographe repliée (`stored + '/'`) : `['errors', 'not_eligible']`, l'événement `deleted` est écrit une fois, `accounted` absent (`datasetIdentity.test.ts`).
- [ ] `increment("not_eligible")` apparaît **1** fois dans `UpdateChecker.ts`, après `CASE 3: Success`, après le premier `increment("errors")` de CASE 3 et avant `UpdateChecker.DELETED_FILE` de CASE 3 (test de parité).
- [ ] `increment("errors")` reste à **2** occurrences dans `UpdateChecker.ts` (test de parité existant `:83`, non modifié).
- [ ] Les attendus CASE 1 de `deleteVerdict.test.ts` (`:71`, `:87`) et les 8 tests existants de `datasetIdentity.test.ts` passent sans modification.
- [ ] Les trois fichiers de test passent : `deleteVerdict` 6/6, `datasetIdentity` 9/9, `errorsUnprocessedParity` 4/4.
- [ ] Chaque fichier édité garde `LF == CRLF` ; `git show --stat HEAD` liste exactement les 4 fichiers de la tâche.

**Verify:** `node --import file:///D:/DevHellopro/Workspaces/RAG-HP-PUB/.claude/worktrees/a8-not-eligible-breaker/apps-microservices/crawler-service/crawler/node_modules/tsx/dist/loader.mjs --test D:/DevHellopro/Workspaces/RAG-HP-PUB/.claude/worktrees/a8-not-eligible-breaker/apps-microservices/crawler-service/crawler/src/tests/UpdateChecker.deleteVerdict.test.ts` ⇒ `tests 6 / pass 6 / fail 0`, rc 0 ; puis, en plus :
- même commande avec `src/tests/UpdateChecker.datasetIdentity.test.ts` ⇒ `tests 9 / pass 9 / fail 0`.
- même commande avec `src/errorsUnprocessedParity.test.ts` ⇒ `tests 4 / pass 4 / fail 0`.

**Blocked by:** aucune (T1 est une racine : table « Tâches » de l'index, colonne « Dépend de » = —).

**Steps:**

- [ ] **Step 1: Écrire les tests qui échouent (3 fichiers).**

  1a. `deleteVerdict.test.ts` — Read le fichier, puis Edit (ancres uniques, vérifiées par `grep -c -F` = 1 chacune) :

  ancien :
  ```
  test('dataset 200, no longer eligible (not_eligible): deleted event written, errors + accounted counted', async () => {
  ```
  nouveau :
  ```
  test('dataset 200, no longer eligible (not_eligible): deleted event written, errors + not_eligible + accounted counted', async () => {
  ```

  ancien :
  ```
      assert.deepEqual(stats._calls, ['errors', 'accounted']);
  ```
  nouveau :
  ```
      assert.deepEqual(stats._calls, ['errors', 'not_eligible', 'accounted']);
  ```

  1b. `datasetIdentity.test.ts` — Read, puis Edit : insertion pure avant le commentaire du TEST 8. Ancre unique (`grep -c -F` = 1) :

  ancien :
  ```
  // TEST 8 — CASE 2, variante repliée redirigeant hors dataset : l'événement REDIRECTED
  ```
  nouveau :
  ```
  // TEST 9 — CASE 3, variante repliée NON éligible : l'événement `deleted` s'écrit pour les deux
  // orthographes (jugement sur le contenu), `errors` puis `not_eligible` s'incrémentent, mais
  // `accounted` reste réservé à l'orthographe exacte.
  test('a folded match on a non-eligible 200 is deleted and counts errors + not_eligible, no accounted', async () => {
      const stored = 'https://www.example.fr/a';
      const consolidator = makeConsolidator([stored]);
      const stats = makeStats();
      const writer = makeWriter();
      const r = await makeChecker(consolidator, stats, writer)
          .checkUrl(stored + '/', stored + '/', 'discovered', 200, false);

      assert.equal(r.action, 'deleted');
      assert.equal(r.reason, 'not_eligible');
      assert.deepEqual(stats._calls, ['errors', 'not_eligible']);
      assert.equal(writer._calls.length, 1);
      assert.equal(writer._calls[0][0], UpdateChecker.DELETED_FILE);
  });

  // TEST 8 — CASE 2, variante repliée redirigeant hors dataset : l'événement REDIRECTED
  ```
  (le bloc inséré compte 18 lignes : 3 de commentaire, 14 de test, 1 ligne vide.)

  1c. `errorsUnprocessedParity.test.ts` — Read, puis Edit : ajout en fin de fichier, ancre multi-ligne (les trois dernières lignes du fichier ; l'outil Edit préserve le CRLF, sondé) :

  ancien :
  ```
          "`errors` feeds the BO health guard and both deletion caps — this lot must not change its count",
      );
  });
  ```
  nouveau :
  ```
          "`errors` feeds the BO health guard and both deletion caps — this lot must not change its count",
      );
  });

  test("not_eligible is written ONCE, in CASE 3, right after `errors` and before the deleted JSONL write", () => {
      const checker = src("class/UpdateChecker.ts");

      const increments = checker.match(/increment\("not_eligible"\)/g) ?? [];
      assert.equal(
          increments.length,
          1,
          "expected exactly one `not_eligible` writer — CASE 3 (2xx, dataset URL, no longer eligible)",
      );

      const case3 = checker.indexOf("CASE 3: Success");
      assert.ok(case3 !== -1, "the CASE 3 marker comment must still exist");
      const errorsWrite = checker.indexOf('increment("errors")', case3);
      const notEligible = checker.indexOf('increment("not_eligible")');
      const deletedWrite = checker.indexOf("UpdateChecker.DELETED_FILE", case3);
      assert.ok(errorsWrite > case3, "CASE 3 must still write `errors`");
      assert.ok(notEligible > errorsWrite, "`not_eligible` must follow `errors` in CASE 3");
      assert.ok(notEligible < deletedWrite, "`not_eligible` must precede the deleted JSONL write");
  });
  ```
  (le bloc ajouté compte 20 lignes, aucune supprimée.)

  Puis, pour chacun des trois fichiers, contrôle d'EOL : `python -c "import sys; b=open(sys.argv[1],'rb').read(); print('LF', b.count(b'\n'), 'CRLF', b.count(b'\r\n'))" <chemin>` ⇒ nombres **égaux** (chemins : les trois ci-dessus, complets depuis la racine du worktree) ; puis `git diff --numstat -- <chemin>` ⇒ `deleteVerdict` **2 2**, `datasetIdentity` **18 0**, `errorsUnprocessedParity` **20 0**.

- [ ] **Step 2: Lancer les trois tests, attendre l'ÉCHEC.**

  Les trois commandes de **Verify**, une par appel. Attendu avant l'implémentation : `deleteVerdict` `tests 6 / pass 5 / fail 1` (le test `:109`, attendu `['errors', 'not_eligible', 'accounted']` reçu `['errors', 'accounted']`) ; `datasetIdentity` `tests 9 / pass 8 / fail 1` (TEST 9) ; `errorsUnprocessedParity` `tests 4 / pass 3 / fail 1` (`increments.length` 0 au lieu de 1). rc ≠ 0 pour chacun. Un autre décompte ⇒ s'arrêter et diagnostiquer avant d'implémenter.

- [ ] **Step 3: Implémenter l'écrivain en CASE 3.**

  Read `apps-microservices/crawler-service/crawler/src/class/UpdateChecker.ts`, puis Edit. Ancre multi-ligne unique (le commentaire n'a qu'une occurrence ; `increment("errors")` seul en a deux) :

  ancien :
  ```
                  // No longer eligible → mark as deleted
                  await this.statsManager.increment("errors");
  ```
  nouveau :
  ```
                  // No longer eligible → mark as deleted
                  await this.statsManager.increment("errors");
                  // `errors` reste le compteur combiné ; `not_eligible` isole ce sous-ensemble
                  // (2xx inéligible) pour que le disjoncteur le juge à son propre seuil.
                  await this.statsManager.increment("not_eligible");
  ```
  (indentation : 16 espaces, comme la ligne `errors` voisine ; ordre `errors` puis `not_eligible`, avant `const result` et l'écriture JSONL ; aucune condition `match === 'exact'` : les deux orthographes comptent, comme `errors`.)

  Contrôle d'EOL sur `apps-microservices/crawler-service/crawler/src/class/UpdateChecker.ts` ⇒ `LF == CRLF` ; `git diff --numstat -- apps-microservices/crawler-service/crawler/src/class/UpdateChecker.ts` ⇒ **3 0**. Aucune modification de `StatsManager.ts` (le compteur est un champ de hash Redis, créé à l'incrément).

- [ ] **Step 4: Relancer les trois tests, attendre le SUCCÈS.**

  Les trois commandes de **Verify** ⇒ `6/6`, `9/9`, `4/4`, `fail 0`, rc 0 chacun. Le test de parité existant `errors keeps exactly its two live writers` (`:83`) est dans le lot de 4 : il prouve que `errors` reste à 2.

- [ ] **Step 5: Contrôle d'effet (isolation de la tâche).**

  `git diff --numstat` (sans chemin) ⇒ exactement 4 lignes, `UpdateChecker.ts` **3 0**, `deleteVerdict.test.ts` **2 2**, `datasetIdentity.test.ts` **18 0**, `errorsUnprocessedParity.test.ts` **20 0** ; aucun autre fichier suivi (le dossier `docs/superpowers/plans/2026-10-19-not-eligible-breaker.d/` non suivi n'apparaît pas dans `git diff`, et n'est pas ajouté ici).

- [ ] **Step 6: Commit.**

  6a. Outil Write : écrire `<scratchpad>/msg_t01.txt` (`<scratchpad>` = marqueur résolu à l'exécution, répertoire scratchpad de la session) :
  ```
  feat(crawler): count not_eligible separately in UpdateChecker CASE 3

  A dataset URL that answers 2xx but is no longer eligible now increments a
  new `not_eligible` counter right after `errors`, for both the exact and the
  folded spelling. `errors` stays the combined counter (still two writers).
  Tests pin the counter order, the folded case and the source-text parity.

  FR — compter `not_eligible` séparément en CASE 3 de UpdateChecker

  Une URL du dataset qui répond 2xx mais n'est plus éligible incrémente
  désormais un compteur `not_eligible` neuf juste après `errors`, pour les
  deux orthographes (exacte et repliée). `errors` reste le compteur combiné
  (toujours deux écrivains). Les tests épinglent l'ordre des compteurs, le
  cas replié et la parité du texte source.
  ```

  6b. `git add apps-microservices/crawler-service/crawler/src/class/UpdateChecker.ts apps-microservices/crawler-service/crawler/src/tests/UpdateChecker.deleteVerdict.test.ts apps-microservices/crawler-service/crawler/src/tests/UpdateChecker.datasetIdentity.test.ts apps-microservices/crawler-service/crawler/src/errorsUnprocessedParity.test.ts`

  6c. `git commit -F <scratchpad>/msg_t01.txt`

  6d. `git show --stat HEAD` ⇒ liste exactement les 4 fichiers ci-dessus, aucun autre.
### Task 2: Fonction pure à deux décisions
> NOMS NEUFS : `ErrorRateBreakerStats.notEligible?: number` (produit) ⇒ T3 ; `ErrorRateBreakerConfig.maxNotEligibleRate?: number` (produit) ⇒ T3 ; champ de retour `notEligibleRate` (produit, `rate` = taux HTTP) ⇒ tests de T2 seulement ; raison `Not-eligible rate too high (` (produit) ⇒ T6

**Goal:** `shouldTripErrorRateBreaker()` prend deux décisions sur `attempts = processed + errorsUnprocessed` : HTTP (`max(0, errors − notEligible) / attempts` contre `maxErrorRate`, préfixe `Error rate too high (` conservé) puis `not_eligible` (`notEligible / attempts` contre `maxNotEligibleRate`, préfixe neuf `Not-eligible rate too high (`) ; `notEligible` absent ⇒ résultat de l'ancien disjoncteur.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/errorRateBreaker.ts:32` (ancre E1 : ` * Pure function (no Crawlee/Redis) so it is unit-testable in isolation.`), `:41` (E2 : `    errorsUnprocessed: number;`), `:46` (E3 : `    maxErrorRate: number;`), `:49-83` (E4 : fonction) — numéros lus par `grep -n` à `3cd3b7af`
- Modify: `apps-microservices/crawler-service/crawler/src/errorRateBreaker.test.ts:116-126` (dernier test existant ; insertion pure APRÈS la ligne 126)
- Modify: `apps-microservices/crawler-service/crawler/src/updateHealthVerdict.ts:184` (commentaire seul)

**Blocked by:** aucune (T2 ne dépend d'aucune tâche, index § Tâches).

**Acceptance Criteria:**
- [ ] `errorRateBreaker.test.ts` : `tests 20 / pass 20 / fail 0` ; les 9 tests existants sont intacts (`git diff --numstat` du fichier de test : suppressions `0`).
- [ ] `grep -c -F "Error rate too high (" apps-microservices/crawler-service/crawler/src/errorRateBreaker.ts` rend `1` et `grep -c -F "Not-eligible rate too high (" …/errorRateBreaker.ts` rend `1` (une émission chacune ; le commentaire d'en-tête ne cite aucun des deux préfixes).
- [ ] `statNameParity.test.ts` reste vert (le préfixe HTTP est toujours dans `errorRateBreaker.ts`) : `fail 0`.
- [ ] `updateHealthVerdict.ts` : `git diff --numstat` ⇒ `1	1` ; plus aucune occurrence de `errorRateBreaker.ts:73` dans ce fichier (`grep -c -F "errorRateBreaker.ts:73" …/updateHealthVerdict.ts` ⇒ `0`).
- [ ] Les trois fichiers : contrôle d'EOL `LF == CRLF`.
- [ ] `git show --stat HEAD` liste exactement les trois fichiers ci-dessus.

**Verify:** `node --import file:///D:/DevHellopro/Workspaces/RAG-HP-PUB/.claude/worktrees/a8-not-eligible-breaker/apps-microservices/crawler-service/crawler/node_modules/tsx/dist/loader.mjs --test D:/DevHellopro/Workspaces/RAG-HP-PUB/.claude/worktrees/a8-not-eligible-breaker/apps-microservices/crawler-service/crawler/src/errorRateBreaker.test.ts` ⇒ `tests 20 / pass 20 / fail 0`, rc 0.

**Steps:**

Dérivation des attendus (taux = valeur / attempts, `attempts = processed + errorsUnprocessed`, `pct = (taux × 100).toFixed(1)`) — chaque ligne est celle du test du même nom ci-dessous :

| Test | errors / processed / errorsUnprocessed / notEligible | attempts | httpErrors = max(0, errors − ne) | rate (HTTP) | notEligibleRate | Seuils | Attendu |
|---|---|---|---|---|---|---|---|
| A HTTP seul | 30 / 100 / 30 / 0 | 130 | 30 | 30/130 = 23,08 % → `23.1` | 0 | 0,15 ; 0,5 | trip ; raison `Error rate too high (23.1% > 15.0%, 30 HTTP errors / 130 attempts)` |
| B not_eligible seul | 60 / 100 / 0 / 60 | 100 | 0 | 0 | 60/100 = 0,6 → `60.0` | 0,15 ; 0,5 | trip ; raison `Not-eligible rate too high (60.0% > 50.0%, 60 not-eligible / 100 attempts)` |
| C combiné, chacun sous son seuil | 30 / 100 / 10 / 20 | 110 | 10 | 10/110 = 9,09 % → `9.1` < 15 | 20/110 = 18,18 % < 50 | 0,15 ; 0,5 | pas d'arrêt ; ancien taux 30/110 = 27,3 % > 15 % (l'ancien code aurait coupé) |
| D décision 4 coupée | 60 / 100 / 0 / 60 | 100 | 0 | 0 | 0,6 | `maxNotEligibleRate` = 0, puis absent | pas d'arrêt (les deux appels) |
| E décision 2 coupée | (E1) 500 / 100 / 500 / 0 ; (E2) 60 / 100 / 0 / 60 | 600 ; 100 | 500 ; 0 | 500/600 ; 0 | 0 ; 0,6 | `maxErrorRate` = 0, `maxNotEligibleRate` 0,5 | pas d'arrêt, raison `/disabled/`, les deux signaux coupés |
| F égalité stricte | (F1) 50 / 100 / 0 / 50 ; (F2) 51 / 100 / 0 / 51 | 100 | 0 | 0 | 50/100 = 0,5 ; 51/100 = 0,51 | 0,5 | F1 pas d'arrêt (0,5 non `>` 0,5) ; F2 trip, `51.0% > 50.0%, 51 not-eligible / 100 attempts` |
| G plancher | 3 / 100 / 0 / 5 | 100 | max(0, 3 − 5) = 0 | 0 (jamais négatif) | 5/100 = 0,05 | 0,15 ; 0,5 | pas d'arrêt, `rate` = 0 |
| H porte d'échantillon | 49 / 49 / 0 / 49 | 49 | 0 | 0 | 49/49 = 1 (> 0,5) | `minSample` 50 | pas d'arrêt, raison `/sample gate/` (processed 49 < 50) |
| I deux décisions vraies | 100 / 100 / 30 / 70 | 130 | 30 | 30/130 = 23,1 % > 15 | 70/130 = 53,8 % > 50 | 0,15 ; 0,5 | trip, raison **HTTP** (décision 3 avant 4) |
| J seuil 0 < s < maxErrorRate | 12 / 100 / 0 / 12 | 100 | 0 | 0 | 12/100 = 0,12 | `maxNotEligibleRate` 0,1 | trip `12.0% > 10.0%, 12 not-eligible / 100 attempts` alors que l'ancien taux 12/100 = 0,12 ≤ 0,15 ne coupait pas (la propriété de relaxation tombe hors de la grille) |

Grille (test K) : `processed ∈ {0, 8, 16, 24, 32, 40}` (6 valeurs), `eOff ∈ {0, 8, …, 40}` (6), `eOn` multiples de 4 de 0 à `processed`, `ne` multiples de 4 de 0 à `eOn`, `maxNotEligibleRate ∈ {0, 0.15, 0.5, 1}` (4). Paires `(eOn, ne)` pour `eOn = 4k` : `k + 1` ; pour `processed = 4K'` : `(K'+1)(K'+2)/2` avec `K' = 0, 2, 4, 6, 8, 10` ⇒ `1 + 6 + 15 + 28 + 45 + 66 = 161` ; total `161 × 6 × 4 = 3 864` appels (assertion de compte dans le test). Preuve du `trip_nouveau ⇒ trip_ancien` : `httpRate + notEligibleRate = ancien taux` quand `ne ≤ errors` (vrai : `ne ≤ eOn ≤ errors`) ; décision 3 : `httpRate > 0,15` ⇒ ancien taux ≥ `httpRate` > 0,15 ; décision 4 : `notEligibleRate > s` avec `s ≥ 0,15` (les quatre valeurs de la grille valent 0 — décision coupée — ou ≥ 0,15) ⇒ ancien taux ≥ `notEligibleRate` > 0,15. Non-vacuité : `processed = 40, eOff = 40, eOn = 0` ⇒ 40/80 = 0,5 > 0,15 ⇒ nouveau trip (`newTrips > 0`) ; `processed = 16, eOff = 0, eOn = 16, ne = 16, s = 1` ⇒ ancien 16/16 = 1 trip, nouveau : HTTP 0, `16/16 = 1` non `> 1` ⇒ pas d'arrêt (`relaxed > 0`).

- [ ] **Step 1: Écrire les 11 tests neufs (échec attendu)**

Lire d'abord `apps-microservices/crawler-service/crawler/src/errorRateBreaker.test.ts` (outil Read). Contrôle d'ancre : `grep -c -F "production logs are grepped on this prefix, got: " apps-microservices/crawler-service/crawler/src/errorRateBreaker.test.ts` ⇒ `1`. Outil Edit (insertion pure après le dernier test ; `old_string` = les trois dernières lignes du fichier, reprises à l'identique dans `new_string`) :

old_string :
```text
        `production logs are grepped on this prefix, got: ${r.reason}`,
    );
});
```

new_string :
```ts
        `production logs are grepped on this prefix, got: ${r.reason}`,
    );
});

// ---------------------------------------------------------------------------
// not_eligible split (spec 2026-10-19-not-eligible-breaker-design.md §3).
// `rate` is the HTTP rate, `notEligibleRate` the on-book half. Every expectation
// below is derived as value / attempts, attempts = processed + errorsUnprocessed.
// ---------------------------------------------------------------------------

const CFG_NE = { minSample: 50, maxErrorRate: 0.15, maxNotEligibleRate: 0.5 };

test('HTTP errors alone trip: 30/130 = 23.1% > 15%, prefix kept, suffix counts HTTP errors', () => {
    const r = shouldTripErrorRateBreaker(
        { errors: 30, processed: 100, errorsUnprocessed: 30, notEligible: 0 },
        CFG_NE,
    );
    assert.equal(r.attempts, 130);
    assert.equal(r.rate, 30 / 130);
    assert.equal(r.notEligibleRate, 0);
    assert.equal(r.trip, true);
    assert.equal(r.reason, 'Error rate too high (23.1% > 15.0%, 30 HTTP errors / 130 attempts)');
});

test('not_eligible alone trips under its own prefix: 60/100 = 60.0% > 50%', () => {
    const r = shouldTripErrorRateBreaker(
        { errors: 60, processed: 100, errorsUnprocessed: 0, notEligible: 60 },
        CFG_NE,
    );
    assert.equal(r.rate, 0);
    assert.equal(r.notEligibleRate, 60 / 100);
    assert.equal(r.trip, true);
    assert.equal(
        r.reason,
        'Not-eligible rate too high (60.0% > 50.0%, 60 not-eligible / 100 attempts)',
    );
});

test('combined 30/110 = 27.3% > 15% but HTTP 10/110 = 9.1% and not_eligible 20/110 = 18.2%: no stop', () => {
    const r = shouldTripErrorRateBreaker(
        { errors: 30, processed: 100, errorsUnprocessed: 10, notEligible: 20 },
        CFG_NE,
    );
    assert.equal(r.attempts, 110);
    assert.equal(r.rate, 10 / 110);
    assert.equal(r.notEligibleRate, 20 / 110);
    assert.equal(r.trip, false);
    assert.match(r.reason, /within threshold/);
    // The former breaker (one rate, one threshold) WOULD have stopped this run.
    assert.ok(30 / 110 > 0.15);
});

test('maxNotEligibleRate = 0 or absent disables the not_eligible decision alone', () => {
    const stats = { errors: 60, processed: 100, errorsUnprocessed: 0, notEligible: 60 };
    const zero = shouldTripErrorRateBreaker(stats, { ...CFG_NE, maxNotEligibleRate: 0 });
    assert.equal(zero.trip, false);
    assert.equal(zero.notEligibleRate, 60 / 100);
    const absent = shouldTripErrorRateBreaker(stats, CFG);
    assert.equal(absent.trip, false);
    assert.equal(absent.notEligibleRate, 60 / 100);
});

test('maxErrorRate = 0 disables BOTH decisions (operator escape hatch)', () => {
    const http = shouldTripErrorRateBreaker(
        { errors: 500, processed: 100, errorsUnprocessed: 500, notEligible: 0 },
        { ...CFG_NE, maxErrorRate: 0 },
    );
    assert.equal(http.trip, false);
    assert.match(http.reason, /disabled/);
    const onBook = shouldTripErrorRateBreaker(
        { errors: 60, processed: 100, errorsUnprocessed: 0, notEligible: 60 },
        { ...CFG_NE, maxErrorRate: 0 },
    );
    assert.equal(onBook.trip, false);
    assert.equal(onBook.notEligibleRate, 60 / 100);
    assert.match(onBook.reason, /disabled/);
});

test('strict comparison on the not_eligible threshold: 50/100 = 0.5 does not trip, 51/100 does', () => {
    const at = shouldTripErrorRateBreaker(
        { errors: 50, processed: 100, errorsUnprocessed: 0, notEligible: 50 },
        CFG_NE,
    );
    assert.equal(at.notEligibleRate, 0.5);
    assert.equal(at.trip, false);
    const over = shouldTripErrorRateBreaker(
        { errors: 51, processed: 100, errorsUnprocessed: 0, notEligible: 51 },
        CFG_NE,
    );
    assert.equal(over.trip, true);
    assert.equal(
        over.reason,
        'Not-eligible rate too high (51.0% > 50.0%, 51 not-eligible / 100 attempts)',
    );
});

test('the HTTP numerator is floored at 0 when notEligible exceeds errors (lost increment)', () => {
    const r = shouldTripErrorRateBreaker(
        { errors: 3, processed: 100, errorsUnprocessed: 0, notEligible: 5 },
        CFG_NE,
    );
    assert.equal(r.rate, 0);
    assert.equal(r.notEligibleRate, 5 / 100);
    assert.equal(r.trip, false);
});

test('the sample gate also shuts the not_eligible decision: processed 49 < 50', () => {
    const r = shouldTripErrorRateBreaker(
        { errors: 49, processed: 49, errorsUnprocessed: 0, notEligible: 49 },
        CFG_NE,
    );
    assert.equal(r.notEligibleRate, 1);
    assert.equal(r.trip, false);
    assert.match(r.reason, /sample gate/);
});

test('both decisions true: the HTTP reason wins (decision 3 before 4)', () => {
    // attempts = 100 + 30 = 130 ; HTTP 30/130 = 23.1% > 15% ; not_eligible 70/130 = 53.8% > 50%.
    const r = shouldTripErrorRateBreaker(
        { errors: 100, processed: 100, errorsUnprocessed: 30, notEligible: 70 },
        CFG_NE,
    );
    assert.equal(r.trip, true);
    assert.equal(r.rate, 30 / 130);
    assert.equal(r.notEligibleRate, 70 / 130);
    assert.ok(r.reason.startsWith('Error rate too high ('), r.reason);
});

test('a not_eligible threshold strictly between 0 and maxErrorRate breaks the relaxation property', () => {
    // 12/100 = 0.12 <= 0.15: the former breaker did not stop; at 0.1 the new one does.
    const r = shouldTripErrorRateBreaker(
        { errors: 12, processed: 100, errorsUnprocessed: 0, notEligible: 12 },
        { ...CFG_NE, maxNotEligibleRate: 0.1 },
    );
    assert.ok(12 / 100 <= 0.15);
    assert.equal(r.trip, true);
    assert.equal(
        r.reason,
        'Not-eligible rate too high (12.0% > 10.0%, 12 not-eligible / 100 attempts)',
    );
});

test('relaxation grid: trip(new) implies trip(old) for maxNotEligibleRate in {0, 0.15, 0.5, 1}', () => {
    // 6 processed x 6 eOff x 161 (eOn, ne) pairs x 4 thresholds = 3864 calls.
    let cases = 0;
    let newTrips = 0;
    let relaxed = 0;
    for (const maxNotEligibleRate of [0, 0.15, 0.5, 1]) {
        for (let processed = 0; processed <= 40; processed += 8) {
            for (let eOff = 0; eOff <= 40; eOff += 8) {
                for (let eOn = 0; eOn <= processed; eOn += 4) {
                    for (let ne = 0; ne <= eOn; ne += 4) {
                        const errors = eOff + eOn;
                        const attempts = processed + eOff;
                        const oldRate = attempts > 0 ? errors / attempts : 0;
                        const oldTrip = oldRate > 0.15;
                        const r = shouldTripErrorRateBreaker(
                            { errors, processed, errorsUnprocessed: eOff, notEligible: ne },
                            { minSample: 0, maxErrorRate: 0.15, maxNotEligibleRate },
                        );
                        cases += 1;
                        if (r.trip) {
                            newTrips += 1;
                            assert.ok(
                                oldTrip,
                                `new trips but old does not: processed=${processed} eOff=${eOff} eOn=${eOn} ne=${ne} max=${maxNotEligibleRate}`,
                            );
                        } else if (oldTrip) {
                            relaxed += 1;
                        }
                    }
                }
            }
        }
    }
    assert.equal(cases, 3864);
    assert.ok(newTrips > 0, 'the grid must contain trips, or the implication is vacuous');
    assert.ok(relaxed > 0, 'the grid must contain a relaxed run, or the split changes nothing');
});
```

- [ ] **Step 2: Contrôles d'effet du test, puis run FAIL**

Contrôle d'EOL : `python -c "import sys; b=open(sys.argv[1],'rb').read(); print('LF', b.count(b'\n'), 'CRLF', b.count(b'\r\n'))" apps-microservices/crawler-service/crawler/src/errorRateBreaker.test.ts` ⇒ les deux nombres égaux.
Puis `git diff --numstat -- apps-microservices/crawler-service/crawler/src/errorRateBreaker.test.ts` ⇒ suppressions `0` (ajouts > 0 ; tout autre nombre de suppressions : défaire et reprendre l'insertion).
Puis `grep -c "^test(" apps-microservices/crawler-service/crawler/src/errorRateBreaker.test.ts` ⇒ `20` (9 existants + 11 neufs : A, B, C, D, E, F, G, H, I, J, grille).
Run de la commande « Un fichier de test TS » de l'index sur `errorRateBreaker.test.ts` ⇒ **FAIL attendu : `tests 20 / pass 9 / fail 11`** (les 9 existants passent sur l'ancien code ; les 11 neufs échouent : `notEligibleRate` est `undefined`, le suffixe est `errors` et non `HTTP errors`, et la grille n'a aucun run relaxé). Un autre compte ⇒ lire la sortie avant d'écrire le code.

- [ ] **Step 3: Implémenter `errorRateBreaker.ts` (quatre éditions E1-E4, outil Edit)**

⛔ Pas d'outil Write sur ce fichier : il est `i/lf w/crlf`, une réécriture complète le passerait en LF (le contrôle d'EOL échouerait). Lire le fichier (Read), appliquer E1 à E4 dans cet ordre ; l'état final est exactement le bloc « Fichier complet » ci-dessous.

E1 — `old_string` (unique : `grep -c -F` ⇒ 1) :
```text
 * Pure function (no Crawlee/Redis) so it is unit-testable in isolation.
```
`new_string` :
```text
 * TWO DECISIONS SINCE THE `not_eligible` COUNTER (spec
 * docs/superpowers/specs/2026-10-19-not-eligible-breaker-design.md). The two natures of
 * `errors` above deserve two thresholds, on the SAME denominator (`attempts`):
 *   - HTTP rate         = max(0, errors - notEligible) / attempts  > maxErrorRate (0.15)
 *   - not-eligible rate = notEligible / attempts                   > maxNotEligibleRate (0.5)
 * `rate` is the HTTP rate; `notEligibleRate` is returned beside it. `notEligible` absent
 * counts 0, so a caller that does not pass it gets the former breaker's result exactly.
 * The max(0, ...) floor exists because StatsManager.increment() swallows Redis errors: a lost
 * `errors` increment followed by a successful `not_eligible` one would go negative.
 *
 * STRICT RELAXATION PROPERTY — httpRate + notEligibleRate = the former rate (while
 * errors >= notEligible), so for maxNotEligibleRate = 0 (decision off) or
 * maxNotEligibleRate >= maxErrorRate, `trip(new) => trip(old)`: this split only ever REMOVES
 * stops. A threshold strictly between 0 and maxErrorRate breaks it (a 10% non-French run
 * would stop that the former breaker let through). Whoever sets the threshold from a
 * referential (BO) must keep it at 0 or >= maxErrorRate.
 *
 * Both comparisons are strict (`>`). maxErrorRate <= 0 switches BOTH decisions off;
 * maxNotEligibleRate <= 0 or absent switches the second one off alone.
 *
 * Pure function (no Crawlee/Redis) so it is unit-testable in isolation.
```

E2 — `old_string` (unique) : `    errorsUnprocessed: number;` — `new_string` :
```text
    errorsUnprocessed: number;
    /** Cumulative `not_eligible` — the ON-BOOK half of `errors` (CASE 3). Absent = 0. */
    notEligible?: number;
```

E3 — `old_string` (unique) : `    maxErrorRate: number;` — `new_string` :
```text
    maxErrorRate: number;
    /** 0 or absent disables the not-eligible decision. */
    maxNotEligibleRate?: number;
```

E4 — `old_string` : la fonction entière, de `export function shouldTripErrorRateBreaker(` à la dernière `}` du fichier, telle que lue (35 lignes, `:49-83`) ; `new_string` : le texte de `const pct` jusqu'à la fin du fichier du bloc ci-dessous.

Fichier complet attendu (état final de `apps-microservices/crawler-service/crawler/src/errorRateBreaker.ts`) :

```ts
/**
 * Error-rate breaker decision (update mode, standard rates).
 *
 * Extracted from the inline block in routes.ts so it can be unit-tested at all:
 * this breaker was the only one of the three still computing its rate inline,
 * and it is the one that shipped a "rate" production observed at 722%.
 *
 * THE DEFECT THIS FIXES — the denominator excluded part of its own numerator.
 * `increment("processed")` happens at exactly one site, AFTER the HTTP status
 * policy. A dataset URL answering >= 400 or status 0 throws before that
 * increment, yet still increments `errors`. It counted in the numerator and
 * never in the denominator, so `errors / processed` was not a proportion —
 * 12 of the 69 runs stopped in the 2026-08-10 batch reported above 100%.
 *
 * ⚠ `errors` MIXES TWO NATURES, unlike the numerators of the two neighbouring
 * breakers (`shouldTripProxyWall`, `shouldTripExternalRedirectBreaker`), which
 * are disjoint from `processed` by construction:
 *   - CASE 1, HTTP error on a dataset URL   → never reaches `processed`  (OFF-BOOK)
 *   - CASE 3, 2xx same URL, no longer eligible → counted after it        (ON-BOOK)
 * `processed + errors` would therefore double-count the on-book half and dilute
 * the rate for the runs whose rate is already correct. The denominator is
 * `processed + errorsUnprocessed`, isolating the off-book half only.
 *
 * INVARIANT — the rate cannot exceed 1. Every on-book error is a URL already
 * inside `processed`, so `errors <= processed + errorsUnprocessed = attempts`.
 * A rate above 1 now means a counter bug, not a broken site.
 *
 * ⚠ THE SAMPLE GATE STAYS ON `processed`, NOT on `attempts`. Widening it would
 * let the breaker evaluate runs it never evaluated before (processed = 10 with
 * errorsUnprocessed = 45 opens a gate of 50 that 10 kept shut), i.e. it would
 * ADD stops. This change exists to remove stops decided on an invalid number.
 *
 * TWO DECISIONS SINCE THE `not_eligible` COUNTER (spec
 * docs/superpowers/specs/2026-10-19-not-eligible-breaker-design.md). The two natures of
 * `errors` above deserve two thresholds, on the SAME denominator (`attempts`):
 *   - HTTP rate         = max(0, errors - notEligible) / attempts  > maxErrorRate (0.15)
 *   - not-eligible rate = notEligible / attempts                   > maxNotEligibleRate (0.5)
 * `rate` is the HTTP rate; `notEligibleRate` is returned beside it. `notEligible` absent
 * counts 0, so a caller that does not pass it gets the former breaker's result exactly.
 * The max(0, ...) floor exists because StatsManager.increment() swallows Redis errors: a lost
 * `errors` increment followed by a successful `not_eligible` one would go negative.
 *
 * STRICT RELAXATION PROPERTY — httpRate + notEligibleRate = the former rate (while
 * errors >= notEligible), so for maxNotEligibleRate = 0 (decision off) or
 * maxNotEligibleRate >= maxErrorRate, `trip(new) => trip(old)`: this split only ever REMOVES
 * stops. A threshold strictly between 0 and maxErrorRate breaks it (a 10% non-French run
 * would stop that the former breaker let through). Whoever sets the threshold from a
 * referential (BO) must keep it at 0 or >= maxErrorRate.
 *
 * Both comparisons are strict (`>`). maxErrorRate <= 0 switches BOTH decisions off;
 * maxNotEligibleRate <= 0 or absent switches the second one off alone.
 *
 * Pure function (no Crawlee/Redis) so it is unit-testable in isolation.
 */
export interface ErrorRateBreakerStats {
    /** Cumulative `errors` counter — BOTH natures. */
    errors: number;
    /** Cumulative `processed` — URLs that passed the HTTP status policy. */
    processed: number;
    /** Cumulative `errors_unprocessed` — the OFF-BOOK half of `errors` only. */
    errorsUnprocessed: number;
    /** Cumulative `not_eligible` — the ON-BOOK half of `errors` (CASE 3). Absent = 0. */
    notEligible?: number;
}

export interface ErrorRateBreakerConfig {
    minSample: number;
    maxErrorRate: number;
    /** 0 or absent disables the not-eligible decision. */
    maxNotEligibleRate?: number;
}

const pct = (r: number): string => (r * 100).toFixed(1);

export function shouldTripErrorRateBreaker(
    stats: ErrorRateBreakerStats,
    cfg: ErrorRateBreakerConfig,
): { trip: boolean; rate: number; notEligibleRate: number; attempts: number; reason: string } {
    const attempts = stats.processed + stats.errorsUnprocessed;
    const notEligible = stats.notEligible ?? 0;
    const httpErrors = Math.max(0, stats.errors - notEligible);
    const rate = attempts > 0 ? httpErrors / attempts : 0;
    const notEligibleRate = attempts > 0 ? notEligible / attempts : 0;
    const verdict = (trip: boolean, reason: string) => ({ trip, rate, notEligibleRate, attempts, reason });

    if (stats.processed < cfg.minSample) {
        return verdict(false, `below sample gate (processed ${stats.processed}/${cfg.minSample})`);
    }
    if (!(cfg.maxErrorRate > 0)) {
        return verdict(false, "error-rate signal disabled (maxErrorRate = 0)");
    }
    if (rate > cfg.maxErrorRate) {
        // Prefix is load-bearing: production logs are grepped on it.
        return verdict(
            true,
            `Error rate too high (${pct(rate)}% > ${pct(cfg.maxErrorRate)}%, `
                + `${httpErrors} HTTP errors / ${attempts} attempts)`,
        );
    }
    const maxNotEligibleRate = cfg.maxNotEligibleRate ?? 0;
    if (maxNotEligibleRate > 0 && notEligibleRate > maxNotEligibleRate) {
        return verdict(
            true,
            `Not-eligible rate too high (${pct(notEligibleRate)}% > ${pct(maxNotEligibleRate)}%, `
                + `${notEligible} not-eligible / ${attempts} attempts)`,
        );
    }
    return verdict(false, `error rate ${pct(rate)}% within threshold`);
}
```

Lecture du bloc (contrôles de comptage) : `Error rate too high (` apparaît **1** fois (dans le template de la décision 3, hors commentaire) ; `Not-eligible rate too high (` **1** fois ; le commentaire d'en-tête ne contient aucun des deux. `return verdict(` apparaît **5** fois (porte, signal coupé, HTTP, not_eligible, within threshold). Le texte du cas non déclenché (`error rate ${pct(rate)}% within threshold`) est octet pour octet celui d'avant (`.toFixed(1)` via `pct`).

- [ ] **Step 4: Contrôles d'effet de l'implémentation**

Contrôle d'EOL : `python -c "import sys; b=open(sys.argv[1],'rb').read(); print('LF', b.count(b'\n'), 'CRLF', b.count(b'\r\n'))" apps-microservices/crawler-service/crawler/src/errorRateBreaker.ts` ⇒ `LF == CRLF`.
`git diff --numstat -- apps-microservices/crawler-service/crawler/src/errorRateBreaker.ts` ⇒ ajouts et suppressions non nuls ; **suppressions < 40** (le fichier d'origine fait 83 lignes ; au-delà, une édition a réécrit hors des quatre ancres : défaire et reprendre).
`grep -c -F "Error rate too high (" apps-microservices/crawler-service/crawler/src/errorRateBreaker.ts` ⇒ `1` ; `grep -c -F "Not-eligible rate too high (" apps-microservices/crawler-service/crawler/src/errorRateBreaker.ts` ⇒ `1`.

- [ ] **Step 5: Run PASS**

Commande « Un fichier de test TS » de l'index sur `errorRateBreaker.test.ts` ⇒ `tests 20 / pass 20 / fail 0`, rc 0. Les 9 existants passent sans modification (non-régression de la spec §3).

- [ ] **Step 6: Re-pointer le commentaire de `updateHealthVerdict.ts:184` sur le symbole**

Lire le fichier autour de `:184` (Read, `offset` 180, `limit` 10). Contrôle d'ancre : `grep -c -F "errorRateBreaker.ts:73 emits that" apps-microservices/crawler-service/crawler/src/updateHealthVerdict.ts` ⇒ `1`. Outil Edit, `old_string` :
```text
errorRateBreaker.ts:73 emits that
```
`new_string` :
```text
shouldTripErrorRateBreaker() (errorRateBreaker.ts) emits that
```
Contrôle d'EOL sur `apps-microservices/crawler-service/crawler/src/updateHealthVerdict.ts` ⇒ `LF == CRLF` ; `git diff --numstat -- apps-microservices/crawler-service/crawler/src/updateHealthVerdict.ts` ⇒ `1	1` ; `grep -c -F "errorRateBreaker.ts:73" apps-microservices/crawler-service/crawler/src/updateHealthVerdict.ts` ⇒ `0`.

- [ ] **Step 7: Contrôles d'effet croisés (tests voisins qui lisent le texte source)**

Commande « Un fichier de test TS » de l'index sur `statNameParity.test.ts` ⇒ `fail 0`, rc 0 (épingle `breaker.includes("Error rate too high (")` et l'absence du préfixe dans les `statusMessage` du verdict).
Idem sur `updateHealthVerdict.test.ts` ⇒ `fail 0`, rc 0 (le fichier modifié ne l'est que dans un commentaire).
Le build (`npm run build`) n'est pas lancé ici : aucun appelant ne change (`routes.ts` appelle encore avec trois champs, compatible avec `notEligible?`) ; il est prescrit à T3 après câblage.

- [ ] **Step 8: Commit (message bilingue, outil Write puis deux commandes séparées)**

Écrire par l'outil Write le fichier `<scratchpad>/msg_t02.txt` (`<scratchpad>` = répertoire de scratchpad de la session, résolu à l'exécution) :

```text
feat(crawler): two-decision error-rate breaker with a not_eligible rate (A8)

shouldTripErrorRateBreaker() now splits the combined `errors` numerator on
the same denominator (processed + errorsUnprocessed): HTTP errors,
max(0, errors - notEligible), against maxErrorRate (unchanged, prefix
"Error rate too high (" kept, suffix now "HTTP errors"), then notEligible
against the optional maxNotEligibleRate under the new prefix
"Not-eligible rate too high (". notEligible absent behaves as before (the 9
existing tests are untouched). maxErrorRate <= 0 still disables both
decisions. Adds the 10 cases of the spec plus a 3864-call relaxation grid
(trip(new) implies trip(old)). updateHealthVerdict.ts: comment only, the
errorRateBreaker.ts:73 line reference is replaced by the symbol name.

FR — disjoncteur du taux d'erreurs à deux décisions avec un taux not_eligible (A8)

shouldTripErrorRateBreaker() sépare maintenant le numérateur combiné
`errors` sur le même dénominateur (processed + errorsUnprocessed) : les
erreurs HTTP, max(0, errors - notEligible), contre maxErrorRate (inchangé,
préfixe « Error rate too high ( » conservé, suffixe « HTTP errors »), puis
notEligible contre maxNotEligibleRate (facultatif) sous le préfixe neuf
« Not-eligible rate too high ( ». Un notEligible absent se comporte comme
avant (les 9 tests existants sont intacts). maxErrorRate <= 0 coupe
toujours les deux décisions. Ajoute les cas de la spec et une grille de
relaxation de 3864 appels (trip(nouveau) implique trip(ancien)).
updateHealthVerdict.ts : commentaire seul, la référence de ligne
errorRateBreaker.ts:73 est remplacée par le nom du symbole.
```

Puis, en commandes séparées (une par appel) :
`git add apps-microservices/crawler-service/crawler/src/errorRateBreaker.ts apps-microservices/crawler-service/crawler/src/errorRateBreaker.test.ts apps-microservices/crawler-service/crawler/src/updateHealthVerdict.ts`
`git commit -F <scratchpad>/msg_t02.txt`
`git show --stat HEAD` ⇒ liste **exactement** ces trois fichiers (aucun autre ; en particulier ni le dossier `docs/superpowers/plans/…` ni `StatsManager.ts`).
### Task 3: Câblage `maxNotEligibleRate` et appel du disjoncteur dans routes
> NOMS NEUFS : `context.config.circuitBreaker.maxNotEligibleRate` (produit) ⇒ T4 ; argument CLI `maxNotEligibleRate` / clé npm `npm_config_maxnoteligiblerate` (produit) ⇒ T5 ; `not_eligible` (consommé de T1), `ErrorRateBreakerStats.notEligible` et `ErrorRateBreakerConfig.maxNotEligibleRate` (consommés de T2)

**Goal:** Le seuil `maxNotEligibleRate` (défaut 0,50) traverse `context.ts` et la CLI de `main.ts` jusqu'à `context.config.circuitBreaker`, et `routes.ts` lit le compteur Redis `not_eligible` puis le passe à `shouldTripErrorRateBreaker`.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/context.ts:65` (champ `maxNotEligibleRate: 0.50,` juste après `maxErrorRate: 0.15,     // 15%`)
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts:132` (constante CLI), `:168` (champ `circuitBreaker`), `:1022` (ligne `Limits:`)
- Modify: `apps-microservices/crawler-service/crawler/src/routes.ts:465` (lecture `not_eligible`), `:486` (passage dans l'appel) — numéros de la base `3cd3b7af`, à re-localiser par contenu
- Modify: `apps-microservices/crawler-service/crawler/src/errorsUnprocessedParity.test.ts` (deux tests ajoutés EN FIN de fichier, après celui de T1 ; fin localisée par contenu)
- Aucune modification : `apps-microservices/crawler-service/crawler/src/nonHtmlPrefixWiring.test.ts`, `StatsManager.ts`, les régions R23 de `main.ts` / `routes.ts` / `functions.ts`

**Acceptance Criteria:**
- [ ] `context.ts` porte `maxNotEligibleRate: 0.50,` une fois, dans `circuitBreaker`, après `maxErrorRate`.
- [ ] `main.ts` lit `maxNotEligibleRate` par `parseNumericArg('maxNotEligibleRate', 'npm_config_maxnoteligiblerate', 0.50)`, le met dans `context.config.circuitBreaker`, et la ligne `Limits:` imprime `NotEligibleRate=…%`.
- [ ] `routes.ts` lie `const notEligible = await context.statsManager.getValue("not_eligible");` et passe `notEligible` dans l'objet de la SEULE invocation `shouldTripErrorRateBreaker(` (1 site d'appel, inchangé).
- [ ] Le test existant `errors_unprocessed: UpdateChecker writes the name the breaker will read` reste vert sans modification (son regex `[^}]*\berrorsUnprocessed\b\s*[,}]` matche toujours l'objet élargi).
- [ ] Deux tests neufs en fin de `errorsUnprocessedParity.test.ts` : FAIL avant l'implémentation, PASS après ; `git diff --numstat` du fichier ⇒ suppressions **0**.
- [ ] `nonHtmlPrefixWiring.test.ts` passe, fichier non modifié (`git diff --stat` ne le liste pas).
- [ ] `npm run build` : rc après édition = rc de la ligne de base consignée à l'étape 1 (attendu 0).
- [ ] Contrôle d'EOL des 4 fichiers édités : `LF == CRLF`.

**Verify:** `node --import file:///D:/DevHellopro/Workspaces/RAG-HP-PUB/.claude/worktrees/a8-not-eligible-breaker/apps-microservices/crawler-service/crawler/node_modules/tsx/dist/loader.mjs --test D:/DevHellopro/Workspaces/RAG-HP-PUB/.claude/worktrees/a8-not-eligible-breaker/apps-microservices/crawler-service/crawler/src/errorsUnprocessedParity.test.ts` → `fail 0`, rc 0, compte de tests = (nombre avant ces deux ajouts, tests de T1 compris) + 2 ; le nombre se lit au run de l'étape 1. Puis :
- `node --import … --test …/src/nonHtmlPrefixWiring.test.ts` (même forme) → `fail 0`, rc 0.
- `npm --prefix D:/DevHellopro/Workspaces/RAG-HP-PUB/.claude/worktrees/a8-not-eligible-breaker/apps-microservices/crawler-service/crawler run build` → rc identique à la ligne de base de l'étape 1 (attendu 0).

**Steps:**

- [ ] **Step 1: Ligne de base — build et parité AVANT toute édition**

Lancer (une commande par appel), consigner rc et sortie utile dans le ledger/HANDOFF (la case « Build TS » de l'index est « à re-dériver » : cette mesure la renseigne) :

```
npm --prefix D:/DevHellopro/Workspaces/RAG-HP-PUB/.claude/worktrees/a8-not-eligible-breaker/apps-microservices/crawler-service/crawler run build
```
Noter : rc (attendu 0 ; si ≠ 0, ARRÊT et signalement au contrôleur — T1/T2 laissent un arbre qui ne compile pas, ou la base l'était déjà ; ne pas poursuivre sans le dire), et la dernière ligne imprimée.

```
node --import file:///D:/DevHellopro/Workspaces/RAG-HP-PUB/.claude/worktrees/a8-not-eligible-breaker/apps-microservices/crawler-service/crawler/node_modules/tsx/dist/loader.mjs --test D:/DevHellopro/Workspaces/RAG-HP-PUB/.claude/worktrees/a8-not-eligible-breaker/apps-microservices/crawler-service/crawler/src/errorsUnprocessedParity.test.ts
```
Noter `tests N / pass N / fail 0` (N = base de comparaison de l'étape 4).

Vérifier aussi que T1 et T2 sont dans l'arbre (symboles présents, sinon ARRÊT) :

```
grep -n "increment(\"not_eligible\")" apps-microservices/crawler-service/crawler/src/class/UpdateChecker.ts
```
→ 1 ligne.
```
grep -n "maxNotEligibleRate\|notEligible" apps-microservices/crawler-service/crawler/src/errorRateBreaker.ts
```
→ au moins 2 lignes (interfaces).

- [ ] **Step 2: Écrire les deux tests de parité (ils doivent échouer)**

Lire la fin de `apps-microservices/crawler-service/crawler/src/errorsUnprocessedParity.test.ts` (outil Read, offset proche de la fin ; la fin est le test de T1 après celui `` `errors` keeps exactly its two live writers ``). Outil Edit : `old_string` = les trois dernières lignes du fichier telles que lues (dernière assertion de T1 + `    );` + `});`), `new_string` = ces mêmes trois lignes, une ligne vide, puis le bloc ci-dessous. Si l'`old_string` n'est pas unique, Edit refuse : remonter d'une ligne et recommencer. Aucun test existant n'est modifié.

```ts
test("not_eligible: routes.ts reads the counter and forwards it into the breaker call", () => {
    const routes = src("routes.ts");

    assert.match(
        routes,
        /const\s+notEligible\s*=\s*await[^;]*getValue\("not_eligible"\)/,
        'the notEligible binding passed to the breaker must itself resolve to context.statsManager.getValue("not_eligible") — a renamed read paired with a hardcoded notEligible would revert decision 2 to the old combined numerator',
    );
    assert.match(
        routes,
        /shouldTripErrorRateBreaker\(\s*\{[^}]*\bnotEligible\b\s*[,}]/s,
        "routes.ts must pass notEligible as a property INTO the shouldTripErrorRateBreaker(...) call — reading the counter and not forwarding it leaves the not_eligible decision dead",
    );
});

test("maxNotEligibleRate: context default, CLI argument and circuitBreaker field agree", () => {
    assert.match(
        src("context.ts"),
        /maxNotEligibleRate:\s*0\.50\b/,
        "context.ts must default circuitBreaker.maxNotEligibleRate to 0.50",
    );

    const main = src("main.ts");
    assert.match(
        main,
        /const\s+maxNotEligibleRate\s*=\s*parseNumericArg\('maxNotEligibleRate',\s*'npm_config_maxnoteligiblerate',\s*0\.50\)/,
        "main.ts must parse --maxNotEligibleRate (npm key npm_config_maxnoteligiblerate, default 0.50) — the Python mapper sends exactly this name",
    );
    assert.match(
        main,
        /maxNotEligibleRate:\s*maxNotEligibleRate\s*,/,
        "main.ts must copy the parsed value into context.config.circuitBreaker — a parsed-but-unassigned argument is silently ignored",
    );
});
```

Le bloc ajoute 35 lignes (compté sur le bloc ci-dessus : 1 vide + 14 pour le 1er test + 1 vide + 19 pour le 2ᵉ). Contrôle d'EOL :

```
python -c "import sys; b=open(sys.argv[1],'rb').read(); print('LF', b.count(b'\n'), 'CRLF', b.count(b'\r\n'))" apps-microservices/crawler-service/crawler/src/errorsUnprocessedParity.test.ts
```
→ deux nombres égaux. Puis :
```
git diff --numstat -- apps-microservices/crawler-service/crawler/src/errorsUnprocessedParity.test.ts
```
→ suppressions **0** (ajouts = 35).

- [ ] **Step 3: Lancer le test — FAIL attendu**

Commande « Un fichier de test TS » avec `errorsUnprocessedParity.test.ts` (forme de l'étape 1).
Attendu : `fail 2` (les deux tests neufs : `notEligible` absent de routes ; `maxNotEligibleRate` absent de context/main), tests de l'étape 1 restent verts, rc ≠ 0. Un `fail` ≠ 2 ou un échec d'un test existant ⇒ ARRÊT et diagnostic avant d'éditer.

- [ ] **Step 4: `context.ts` — défaut du contexte**

Outil Edit sur `apps-microservices/crawler-service/crawler/src/context.ts` (ancre vérifiée unique : `grep -c -F` ⇒ 1) :

old_string :
```
            maxErrorRate: 0.15,     // 15%
```
new_string :
```
            maxErrorRate: 0.15,     // 15%
            maxNotEligibleRate: 0.50, // 50% — CASE 3 non-eligible, own decision (errorRateBreaker.ts)
```

Contrôle d'EOL de `context.ts` (même commande Python) → `LF == CRLF`. `git diff --numstat -- apps-microservices/crawler-service/crawler/src/context.ts` → `1	0`.

- [ ] **Step 5: `main.ts` — constante CLI, champ, ligne `Limits:`** (trois Edit, après `context.ts` : le type du champ s'infère de `context.ts`)

Edit 1 — old_string (unique, `grep -c -F` ⇒ 1) :
```
const maxErrorRate = parseNumericArg('maxErrorRate', 'npm_config_maxerrorrate', 0.15);
```
new_string :
```
const maxErrorRate = parseNumericArg('maxErrorRate', 'npm_config_maxerrorrate', 0.15);
const maxNotEligibleRate = parseNumericArg('maxNotEligibleRate', 'npm_config_maxnoteligiblerate', 0.50);
```

Edit 2 — old_string (unique, ⇒ 1) :
```
        maxErrorRate: maxErrorRate,
```
new_string :
```
        maxErrorRate: maxErrorRate,
        maxNotEligibleRate: maxNotEligibleRate,
```

Edit 3 — old_string (unique, ⇒ 1 ; fragment de la ligne `Limits:` du mode STANDARD) :
```
ErrorRate=${(context.config.circuitBreaker.maxErrorRate * 100).toFixed(1)}%, RedirectRate
```
new_string :
```
ErrorRate=${(context.config.circuitBreaker.maxErrorRate * 100).toFixed(1)}%, NotEligibleRate=${(context.config.circuitBreaker.maxNotEligibleRate * 100).toFixed(1)}%, RedirectRate
```

Contrôle d'EOL de `main.ts` → `LF == CRLF`. `git diff --numstat -- apps-microservices/crawler-service/crawler/src/main.ts` → `3	1` (2 lignes ajoutées + 1 ligne `Limits:` modifiée = 1 ajout/1 suppression).
Effet sur les régions épinglées (lecture, rien à modifier) : aucun des huit littéraux comptés par `nonHtmlPrefixWiring.test.ts` (`check(seedUrl, "seed")`, `increment("filtered_nonhtml")`, …) ni son ancre `ensureUnjudgedSidecar(domain);` n'est touché ; vérifié à l'étape 7 par le run du fichier.

- [ ] **Step 6: `routes.ts` — lecture du compteur et passage**

Edit 1 — old_string (unique, ⇒ 1) :
```
                const errorsUnprocessed = await context.statsManager.getValue("errors_unprocessed");
```
new_string :
```
                const errorsUnprocessed = await context.statsManager.getValue("errors_unprocessed");
                const notEligible = await context.statsManager.getValue("not_eligible");
```

Edit 2 — old_string (unique, ⇒ 1) :
```
                            { errors, processed, errorsUnprocessed },
```
new_string :
```
                            { errors, processed, errorsUnprocessed, notEligible },
```

Rien d'autre dans `routes.ts` (spec §3.1) : ni le mode micro, ni le repli `maxErrors`, ni les commentaires voisins. Contrôle d'EOL de `routes.ts` → `LF == CRLF`. `git diff --numstat -- apps-microservices/crawler-service/crawler/src/routes.ts` → `2	1`.
Contrôle du site d'appel unique : `grep -n "shouldTripErrorRateBreaker(" apps-microservices/crawler-service/crawler/src/routes.ts` → 1 ligne.

- [ ] **Step 7: Run PASS — parité, câblage R23, build**

Test de parité (forme de l'étape 1) → `tests N+2 / pass N+2 / fail 0`, rc 0 (N lu à l'étape 1).
`nonHtmlPrefixWiring.test.ts` (même forme, chemin `…/src/nonHtmlPrefixWiring.test.ts`) → `fail 0`, rc 0.
`errorRateBreaker.test.ts` (même forme) → `fail 0`, rc 0 (9 cas de l'index + ceux de T2 ; aucune édition ici, sentinelle de non-régression).
Build (commande de l'étape 1, relancée) → rc = rc de l'étape 1 (attendu 0) ; consigner la dernière ligne imprimée. Un rc 0 → 1 est une régression de type (ex. `notEligible` absent de `ErrorRateBreakerStats` : T2 incomplète) : corriger la cause, pas le test.

- [ ] **Step 8: Contrôles d'effet avant commit**

```
git status --short
```
→ exactement les 4 fichiers de la tâche (`context.ts`, `main.ts`, `routes.ts`, `errorsUnprocessedParity.test.ts`) en `M`, et rien d'autre de nouveau (le dossier de plan non suivi `docs/superpowers/plans/2026-10-19-not-eligible-breaker.d/` peut figurer en `??`, il n'est pas stagé).
```
git diff --stat
```
→ ne liste ni `nonHtmlPrefixWiring.test.ts` ni `StatsManager.ts`.

- [ ] **Step 9: Commit**

Écrire le message bilingue avec l'outil Write dans `<scratchpad>/msg_t03.txt` (`<scratchpad>` = le répertoire de scratchpad de la session, résolu à l'exécution) :

```
feat(crawler): wire maxNotEligibleRate and not_eligible into the update breaker

Add circuitBreaker.maxNotEligibleRate (default 0.50) in context.ts and the
--maxNotEligibleRate CLI argument in main.ts (npm key
npm_config_maxnoteligiblerate), print it on the startup Limits line, and make
routes.ts read the not_eligible counter and pass it to
shouldTripErrorRateBreaker. Two source-text parity tests pin the read, the
forwarding and the context/CLI default.

FR — câbler maxNotEligibleRate et not_eligible dans le disjoncteur de MAJ

Ajoute circuitBreaker.maxNotEligibleRate (défaut 0,50) dans context.ts et
l'argument CLI --maxNotEligibleRate dans main.ts (clé npm
npm_config_maxnoteligiblerate), l'imprime sur la ligne Limits au démarrage, et
fait lire le compteur not_eligible par routes.ts puis le passe à
shouldTripErrorRateBreaker. Deux tests de parité sur le texte source épinglent
la lecture, le passage et le défaut contexte/CLI.
```

Puis, en commandes séparées :
```
git add apps-microservices/crawler-service/crawler/src/context.ts apps-microservices/crawler-service/crawler/src/main.ts apps-microservices/crawler-service/crawler/src/routes.ts apps-microservices/crawler-service/crawler/src/errorsUnprocessedParity.test.ts
```
```
git commit -F <scratchpad>/msg_t03.txt
```
```
git show --stat HEAD
```
→ liste exactement les 4 fichiers ci-dessus, aucun autre.

**Blocked by:** Task 1, Task 2
### Task 4: Rapport `_update_report.json` : `metrics.not_eligible` et `thresholds.max_not_eligible_rate`
> NOMS NEUFS : not_eligible (consommé) ⇒ T1, cb.maxNotEligibleRate (consommé) ⇒ T3, metrics.not_eligible (produit) ⇒ T6, thresholds.max_not_eligible_rate (produit) ⇒ T6

**Goal:** `generateUpdateReport` lit le compteur `not_eligible` à côté de `errors_unprocessed` et écrit deux clés additives dans `_update_report.json` : `metrics.not_eligible` et `thresholds.max_not_eligible_rate`. Un test source-texte de `statNameParity.test.ts` épingle les deux noms (même défaillance silencieuse que `errors_unprocessed` : le Python transmet, le PHP lit par clé de chaîne).

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/functions.ts:1441` (lecture, `const errorsUnprocessed = await context.statsManager.getValue("errors_unprocessed");`), `:1471` (`errors_unprocessed: errorsUnprocessed,` dans `metrics`), `:1483` (`max_error_rate: cb.maxErrorRate,` dans `thresholds`). Fichier `i/crlf w/crlf` : LF 2315 = CRLF 2315 mesuré avant édition.
- Modify (insertion pure en fin de fichier) : `apps-microservices/crawler-service/crawler/src/statNameParity.test.ts` (171 lignes, 6 `test(`, LF 171 = CRLF 171, fin `\r\n`, mesuré avant édition ; dernière ligne de code ancrée par `:168` `it still divides by`).

**Décision (test neuf) :** utile. `statNameParity.test.ts:119` épingle `errors_unprocessed` pour la même raison (clé lue par chaîne côté PHP, renommage tsc-propre et suite-verte mais inerte). Les deux clés neuves ont le même profil et aucun test existant ne les couvre (`grep -n "not_eligible\|notEligible"` ⇒ aucune occurrence dans ces deux fichiers à `3cd3b7af`). Le test échoue d'abord (clés absentes de `functions.ts`).

**Acceptance Criteria:**
- [ ] `functions.ts` contient exactement une lecture `const notEligible = await context.statsManager.getValue("not_eligible");` placée juste après la lecture `errors_unprocessed`.
- [ ] Le littéral `report.metrics` contient `not_eligible: notEligible,` après `errors_unprocessed: errorsUnprocessed,` et avant `previous_total: cb.previousTotal` ; aucun `}` n'est ajouté dans `metrics` (les tranches de `statNameParity.test.ts` s'arrêtent au premier `}`).
- [ ] Le littéral `report.thresholds` contient `max_not_eligible_rate: cb.maxNotEligibleRate,` juste après `max_error_rate: cb.maxErrorRate,`.
- [ ] `git diff --numstat -- apps-microservices/crawler-service/crawler/src/functions.ts` ⇒ `3	0` ; contrôle d'EOL ⇒ LF = CRLF (2318 = 2318).
- [ ] `statNameParity.test.ts` : 7 `test(` (6 + 1), le test neuf contient 3 `assert.match` (lecture, `metrics`, `thresholds`) ; `git diff --numstat` ⇒ suppressions `0` ; contrôle d'EOL ⇒ LF = CRLF.
- [ ] Le test neuf est ROUGE avant l'édition de `functions.ts` et VERT après ; les 6 tests existants du fichier restent verts sans modification.
- [ ] `git show --stat HEAD` liste exactement 2 fichiers : `functions.ts` et `statNameParity.test.ts`.

**Verify:** `node --import file:///D:/DevHellopro/Workspaces/RAG-HP-PUB/.claude/worktrees/a8-not-eligible-breaker/apps-microservices/crawler-service/crawler/node_modules/tsx/dist/loader.mjs --test D:/DevHellopro/Workspaces/RAG-HP-PUB/.claude/worktrees/a8-not-eligible-breaker/apps-microservices/crawler-service/crawler/src/statNameParity.test.ts` ⇒ `tests 7 / pass 7 / fail 0`, rc 0 (forme « Un fichier de test TS » de l'index).
- Puis commande « Build TS » de l'index ⇒ rc 0, aucune erreur `tsc` (`cb.maxNotEligibleRate` résolu par le champ de `context.ts` ajouté en T3).

**Steps:**

- [ ] **Step 1: Mesures de départ (aucune écriture)**

Lancer, une commande par appel, chacune ⇒ la sortie attendue :
1. `git ls-files --eol -- apps-microservices/crawler-service/crawler/src/functions.ts apps-microservices/crawler-service/crawler/src/statNameParity.test.ts` ⇒ `i/crlf w/crlf` pour `functions.ts` ; `i/lf w/crlf` pour le test.
2. Contrôle d'EOL de l'index sur `functions.ts` ⇒ LF = CRLF (2315 si T1-T3 n'y ont pas touché ; sinon égaux de toute façon).
3. Contrôle d'EOL de l'index sur `statNameParity.test.ts` ⇒ `LF 171 CRLF 171`.
4. `grep -n "const errorsUnprocessed = \|errors_unprocessed: errorsUnprocessed,\|max_error_rate: cb.maxErrorRate," apps-microservices/crawler-service/crawler/src/functions.ts` ⇒ 3 lignes (`1441`, `1471`, `1483` à `3cd3b7af`) ; les numéros peuvent avoir bougé : travailler par contenu.
5. `grep -c -F "it still divides by" apps-microservices/crawler-service/crawler/src/statNameParity.test.ts` ⇒ `1` (ancre unique de l'insertion).
6. `grep -n "maxNotEligibleRate" apps-microservices/crawler-service/crawler/src/context.ts` ⇒ au moins 1 ligne (champ de T3). Absent ⇒ T3 non faite : s'arrêter.

- [ ] **Step 2: Écrire le test neuf, rouge (insertion pure en fin de `statNameParity.test.ts`)**

Outil Edit. `old_string` (fin du dernier test, 4 dernières lignes, indentation de 12/8/4 espaces) :

```ts
            `updateHealthVerdict.ts must not emit the breaker's wording (case-insensitive) — it still divides by \`processed\` alone: ${message}`,
        );
    }
});
```

`new_string` = ces mêmes 4 lignes, puis une ligne vide, puis :

```ts
/**
 * `not_eligible` splits the breaker's numerator (errorRateBreaker.ts: HTTP errors = errors minus
 * not_eligible) and, like `errors_unprocessed` above, only survives archiving if the report
 * carries it. crawler_manager.py forwards `metrics` wholesale to the BO webhook and the PHP reads
 * BY STRING KEY: a rename is tsc-clean, suite-green and silently inert downstream. The threshold
 * is pinned for the same reason — it is the number that decided a `not_eligible` stop.
 *
 * Source-text assertions, same anchors as the `errors_unprocessed` test: the reported value must
 * come from the counter itself, in `metrics`, with its threshold in `thresholds`.
 */
test("generateUpdateReport: not_eligible reaches report.metrics and its threshold reaches report.thresholds", () => {
    const functions = src("functions.ts");
    const report = reportLiteral(functions);
    const metricsStart = report.indexOf("metrics: {");
    const metrics = report.slice(metricsStart, report.indexOf("}", metricsStart));

    assert.match(
        metrics,
        /\bnot_eligible:\s*notEligible\b/,
        "report.metrics.not_eligible — without it the HTTP / not_eligible split of `errors` is unreproducible once the dataset is archived",
    );
    assert.match(
        functions,
        /const\s+notEligible\s*=\s*await[^;]*getValue\("not_eligible"\)/,
        "the reported value must come from the counter itself, not from a literal or a stale local",
    );
    assert.match(
        report,
        /\bmax_not_eligible_rate:\s*cb\.maxNotEligibleRate,/,
        "report.thresholds.max_not_eligible_rate — the threshold that decided a not_eligible stop",
    );
});
```

Contrôles d'effet : (a) contrôle d'EOL de l'index sur `statNameParity.test.ts` ⇒ LF = CRLF (si `LF ≠ CRLF` : `git checkout -- apps-microservices/crawler-service/crawler/src/statNameParity.test.ts` puis refaire l'édition) ; (b) `git diff --numstat -- apps-microservices/crawler-service/crawler/src/statNameParity.test.ts` ⇒ suppressions `0`, ajouts = nombre de lignes du bloc ajouté.

- [ ] **Step 3: Vérifier que le test est rouge**

Commande « Un fichier de test TS » de l'index sur `statNameParity.test.ts` ⇒ `tests 7`, `fail 1` (le test neuf, premier `assert.match` sur `metrics`), `pass 6`, rc ≠ 0. Un `fail 0` ici = le test ne mesure rien : corriger avant de continuer.

- [ ] **Step 4: Lecture du compteur dans `functions.ts`**

Outil Edit sur `apps-microservices/crawler-service/crawler/src/functions.ts`. `old_string` (ligne unique, vérifié `grep -c -F` ⇒ 1) :

```ts
        const errorsUnprocessed = await context.statsManager.getValue("errors_unprocessed");
```

`new_string` :

```ts
        const errorsUnprocessed = await context.statsManager.getValue("errors_unprocessed");
        // `errors` mixes HTTP errors with URLs that were 2xx but no longer eligible; the breaker
        // splits them with this counter (errorRateBreaker.ts). Reported for the same reason as
        // errorsUnprocessed: the numbers that decided a stop must outlive the dataset.
        const notEligible = await context.statsManager.getValue("not_eligible");
```

Contrôle : contrôle d'EOL ⇒ LF = CRLF ; `git diff --numstat -- apps-microservices/crawler-service/crawler/src/functions.ts` ⇒ `4	0`.

- [ ] **Step 5: Clé `metrics.not_eligible`**

Outil Edit. `old_string` (ligne unique, `grep -c -F` ⇒ 1) : `                errors_unprocessed: errorsUnprocessed,` ; `new_string` :

```ts
                errors_unprocessed: errorsUnprocessed,
                not_eligible: notEligible,
```

Ordre obtenu dans `metrics` : `…accounted, errors_unprocessed, not_eligible, previous_total` (aucun `}` ajouté). Contrôle : EOL ⇒ LF = CRLF ; numstat ⇒ `5	0`.

- [ ] **Step 6: Clé `thresholds.max_not_eligible_rate`**

Outil Edit. `old_string` (ligne unique, `grep -c -F` ⇒ 1) : `                max_error_rate: cb.maxErrorRate,` ; `new_string` :

```ts
                max_error_rate: cb.maxErrorRate,
                max_not_eligible_rate: cb.maxNotEligibleRate,
```

Contrôle : EOL ⇒ LF = CRLF ; numstat ⇒ `6	0` (6 ajouts, 0 suppression).

- [ ] **Step 7: Vérifier vert**

1. Commande « Un fichier de test TS » sur `statNameParity.test.ts` ⇒ `tests 7 / pass 7 / fail 0`, rc 0.
2. `grep -c -F "not_eligible" apps-microservices/crawler-service/crawler/src/functions.ts` ⇒ compter les occurrences lues (à ce stade : le littéral `"not_eligible"` de la lecture, la clé `metrics`, et le commentaire de `functions.ts:786` `deleted (not_eligible)` préexistant ; le dire dans le rapport sans en déduire d'unicité).
3. Commande « Build TS » de l'index ⇒ rc 0, sans erreur `tsc`.

- [ ] **Step 8: Commit**

1. Outil Write : `<scratchpad>/msg_t04.txt` (`<scratchpad>` = répertoire scratchpad de la session, résolu à l'exécution) :

```text
feat(crawler): report not_eligible and its threshold in _update_report.json (A8)

generateUpdateReport reads the not_eligible counter next to errors_unprocessed and
writes metrics.not_eligible and thresholds.max_not_eligible_rate (additive keys).
statNameParity.test.ts pins both names: the Python forwards and the PHP reads by
string key, so a rename would be tsc-clean and silently inert.

FR — feat(crawler) : rapporter not_eligible et son seuil dans _update_report.json (A8)

generateUpdateReport lit le compteur not_eligible a cote de errors_unprocessed et
ecrit metrics.not_eligible et thresholds.max_not_eligible_rate (cles additives).
statNameParity.test.ts epingle les deux noms : le Python transmet et le PHP lit par
cle de chaine, un renommage serait propre pour tsc et inerte en silence.
```

2. `git add apps-microservices/crawler-service/crawler/src/functions.ts apps-microservices/crawler-service/crawler/src/statNameParity.test.ts` (commande seule).
3. `git commit -F <scratchpad>/msg_t04.txt` (commande seule).
4. `git show --stat HEAD` ⇒ exactement les 2 fichiers ci-dessus (`functions.ts` : 6 insertions ; `statNameParity.test.ts` : insertions seules).

**Blocked by:** Task 3
### Task 5: Schéma et mappage Python `max_not_eligible_rate`
> NOMS NEUFS : `max_not_eligible_rate` (champ Pydantic) produit ⇒ aucun consommateur dans ce lot ; argument CLI `maxNotEligibleRate` (consommé, via `params["maxNotEligibleRate"]` et `crawler_manager.py`) ⇒ T3

**Goal:** `POST /start` accepte `update_thresholds.max_not_eligible_rate` et le transmet au sous-processus Node en `--maxNotEligibleRate=<v>` ; absent ⇒ aucune clé, donc le défaut Node (0,5) s'applique.

**Files:**
- Modify: `apps-microservices/crawler-service/app/schemas/crawler.py:51` (après `max_error_rate`, dans `UpdateThresholds`)
- Modify: `apps-microservices/crawler-service/app/router/crawler.py:293` (après le mappage `maxErrorRate`, dans `start_new_crawl`)
- Create: `apps-microservices/crawler-service/tests/test_update_thresholds_not_eligible.py`

**Acceptance Criteria:**
- [ ] `UpdateThresholds` porte `max_not_eligible_rate: Optional[float] = Field(None, …)`, juste après `max_error_rate`.
- [ ] `start_new_crawl` pose `params["maxNotEligibleRate"]` si et seulement si la valeur n'est pas `None` (`0.0` est transmis : `0` coupe la décision 4 côté Node).
- [ ] Test neuf, 3 cas : présent (0.4) ⇒ `params["maxNotEligibleRate"] == 0.4` ; `0.0` ⇒ clé présente, égale à `0.0` ; absent ⇒ clé absente.
- [ ] Avant l'implémentation : 2 FAIL (`KeyError: 'maxNotEligibleRate'`) + 1 pass (absent) ; après : `3 passed`.
- [ ] `tests/test_crawler.py` : `3 passed` inchangé. Seuls ces 3 fichiers sont dans le commit. EOL des deux fichiers édités : `LF == CRLF`.

**Verify:** `PYTHONPATH=apps-microservices/crawler-service python -m pytest apps-microservices/crawler-service/tests/test_update_thresholds_not_eligible.py -q -p no:cacheprovider` → `3 passed`, rc 0 ; la même commande sur `tests/test_crawler.py` → `3 passed`, rc 0.

**Steps:**

- [ ] **Step 1: Écrire le test (outil Write, fichier neuf)**

Ce que fait `start_new_crawl` (`app/router/crawler.py:243`, lu à `3cd3b7af`) : il bâtit `params` (lit `settings.APIFY_PROXY`, `:258`), puis `await crawler_manager.start_crawl(domain=…, start_url=…, crawl_id=…, callback_url=…, failure_callback_url=…, params=params)` (`:309-315`), puis rend `CrawlResponse`. Les deux seuls effets de bord à neutraliser sont donc `crawler_manager.start_crawl` et `settings` : monkeypatch des deux noms du module (`crawler_router.crawler_manager`, `crawler_router.settings`, importés `:15` et `:17`). Ni serveur ni Redis. Patron : `tests/test_crawler.py` (`import app.router.crawler as crawler_router`, `monkeypatch.setattr`, `AsyncMock`, `@pytest.mark.asyncio`).

Créer `apps-microservices/crawler-service/tests/test_update_thresholds_not_eligible.py` avec ce contenu exact :

```python
"""Tests for the `max_not_eligible_rate` threshold mapping in
app/router/crawler.py::start_new_crawl (not_eligible circuit breaker, A8).

`start_new_crawl` builds `params` and hands it to `crawler_manager.start_crawl`,
which turns each non-None entry into a `--key=value` CLI flag for the Node
crawler. The tests call the endpoint function directly (no server) and capture
the `params` it passes on.
Named test_update_thresholds_* so the TDD gate associates it with crawler.py.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.router.crawler as crawler_router
from app.schemas.crawler import CrawlRequest


def _payload(update_thresholds):
    return CrawlRequest(
        id="domaine_1",
        domain="example.com",
        start_url="https://example.com",
        callback_url="https://api.example.com/done",
        crawl_mode="update",
        previous_crawl_id="domaine_0",
        update_thresholds=update_thresholds,
    )


async def _captured_params(monkeypatch, update_thresholds):
    manager = SimpleNamespace(start_crawl=AsyncMock(return_value="domaine_1"))
    monkeypatch.setattr(crawler_router, "crawler_manager", manager)
    monkeypatch.setattr(crawler_router, "settings", SimpleNamespace(APIFY_PROXY=None))

    await crawler_router.start_new_crawl(_payload(update_thresholds))

    return manager.start_crawl.await_args.kwargs["params"]


@pytest.mark.asyncio
async def test_max_not_eligible_rate_is_mapped_when_present(monkeypatch):
    params = await _captured_params(
        monkeypatch, {"max_error_rate": 0.15, "max_not_eligible_rate": 0.4}
    )

    assert params["maxNotEligibleRate"] == 0.4
    assert params["maxErrorRate"] == 0.15  # neighbour mapping untouched


@pytest.mark.asyncio
async def test_max_not_eligible_rate_zero_is_forwarded(monkeypatch):
    """0 is a value, not 'absent': Node reads it as 'decision 4 disabled'."""
    params = await _captured_params(monkeypatch, {"max_not_eligible_rate": 0.0})

    assert params["maxNotEligibleRate"] == 0.0


@pytest.mark.asyncio
async def test_max_not_eligible_rate_key_absent_when_not_given(monkeypatch):
    params = await _captured_params(monkeypatch, {"max_error_rate": 0.15})

    assert "maxNotEligibleRate" not in params
    assert params["maxErrorRate"] == 0.15
```

- [ ] **Step 2: Contrôle d'EOL du fichier neuf, puis le voir ÉCHOUER**

Contrôle d'EOL :

```
python -c "import sys; b=open(sys.argv[1],'rb').read(); print('LF', b.count(b'\n'), 'CRLF', b.count(b'\r\n'))" apps-microservices/crawler-service/tests/test_update_thresholds_not_eligible.py
```

Attendu : `CRLF == 0` ou `LF == CRLF` (fichier neuf, l'un ou l'autre de façon homogène).

Puis :

```
PYTHONPATH=apps-microservices/crawler-service python -m pytest apps-microservices/crawler-service/tests/test_update_thresholds_not_eligible.py -q -p no:cacheprovider
```

Attendu (FAIL précis, dérivé du code lu) : `2 failed, 1 passed`, rc 1. Raison : sans le champ, `UpdateThresholds` (modèle Pydantic 2 sans `extra="forbid"`, `app/schemas/crawler.py:43`) **ignore en silence** `max_not_eligible_rate` ; le routeur ne pose donc jamais la clé ⇒ `KeyError: 'maxNotEligibleRate'` sur `params["maxNotEligibleRate"]` dans `test_max_not_eligible_rate_is_mapped_when_present` et `test_max_not_eligible_rate_zero_is_forwarded`. Le cas « absent » passe déjà (garde contre une régression : il doit rester vert après). Un autre échec (`ImportError`, `ValidationError`, `AttributeError` sur `crawler_manager`) = le test est mal bâti : corriger le test, pas le code.

- [ ] **Step 3: Ajouter le champ au schéma (outil Edit)**

Relire d'abord la ligne : `grep -n "max_error_rate: Optional" apps-microservices/crawler-service/app/schemas/crawler.py` → `51:` (1 ligne). Ancre à copier telle quelle (une seule ligne, 4 espaces d'indentation), unique : `grep -c -F "    max_error_rate: Optional[float] = Field(None, description=\"Standard Mode: Abort if error rate exceeds this ratio (e.g. 0.15 for 15%).\")" apps-microservices/crawler-service/app/schemas/crawler.py` → `1`.

Edit sur `apps-microservices/crawler-service/app/schemas/crawler.py` :

old_string :
```
    max_error_rate: Optional[float] = Field(None, description="Standard Mode: Abort if error rate exceeds this ratio (e.g. 0.15 for 15%).")
```
new_string :
```
    max_error_rate: Optional[float] = Field(None, description="Standard Mode: Abort if error rate exceeds this ratio (e.g. 0.15 for 15%).")
    max_not_eligible_rate: Optional[float] = Field(None, description="Standard Mode: Abort if the share of dataset URLs no longer eligible (2xx but not French) exceeds this ratio (e.g. 0.50 for 50%). 0 disables this branch; omitted = crawler default (0.50).")
```

- [ ] **Step 4: Contrôle d'EOL + numstat du schéma**

```
python -c "import sys; b=open(sys.argv[1],'rb').read(); print('LF', b.count(b'\n'), 'CRLF', b.count(b'\r\n'))" apps-microservices/crawler-service/app/schemas/crawler.py
```
Attendu : les deux nombres égaux.

```
git diff --numstat -- apps-microservices/crawler-service/app/schemas/crawler.py
```
Attendu : `1	0	apps-microservices/crawler-service/app/schemas/crawler.py` (1 ajout, 0 suppression).

- [ ] **Step 5: Ajouter le mappage au routeur (outil Edit)**

Le bloc `:281-:304` est indenté de 13 espaces pour `if`, 17 pour le corps : copier tel quel. Ancre = la ligne du corps `:293` (17 espaces), unique : `grep -c -F "                 params[\"maxErrorRate\"] = payload.update_thresholds.max_error_rate" apps-microservices/crawler-service/app/router/crawler.py` → `1`.

Edit sur `apps-microservices/crawler-service/app/router/crawler.py` :

old_string :
```
                 params["maxErrorRate"] = payload.update_thresholds.max_error_rate
```
new_string :
```
                 params["maxErrorRate"] = payload.update_thresholds.max_error_rate
             if payload.update_thresholds.max_not_eligible_rate is not None:
                 params["maxNotEligibleRate"] = payload.update_thresholds.max_not_eligible_rate
```

(`is not None`, pas `if value:` : un `0.0` doit passer. `crawler_manager.py` n'est pas modifié : sa boucle `for key, value in params.items(): if value is not None: command.append(f"--{key}={value}")` produit `--maxNotEligibleRate=0.0`.)

- [ ] **Step 6: Contrôle d'EOL + numstat du routeur**

```
python -c "import sys; b=open(sys.argv[1],'rb').read(); print('LF', b.count(b'\n'), 'CRLF', b.count(b'\r\n'))" apps-microservices/crawler-service/app/router/crawler.py
```
Attendu : les deux nombres égaux.

```
git diff --numstat -- apps-microservices/crawler-service/app/router/crawler.py
```
Attendu : `2	0	apps-microservices/crawler-service/app/router/crawler.py`.

- [ ] **Step 7: Voir le test PASSER, puis la non-régression**

```
PYTHONPATH=apps-microservices/crawler-service python -m pytest apps-microservices/crawler-service/tests/test_update_thresholds_not_eligible.py -q -p no:cacheprovider
```
Attendu : `3 passed`, rc 0.

```
PYTHONPATH=apps-microservices/crawler-service python -m pytest apps-microservices/crawler-service/tests/test_crawler.py -q -p no:cacheprovider
```
Attendu : `3 passed`, rc 0.

- [ ] **Step 8: Contrôle d'effet : périmètre de la tâche**

```
git status --short
```
Attendu : exactement `M` sur `apps-microservices/crawler-service/app/router/crawler.py` et `apps-microservices/crawler-service/app/schemas/crawler.py`, `??` sur `apps-microservices/crawler-service/tests/test_update_thresholds_not_eligible.py`, plus les entrées `docs/superpowers/plans/…` et tout fichier des tâches parallèles (les ignorer, ne stager que les 3 de la tâche).

- [ ] **Step 9: Commit (message bilingue écrit par l'outil Write)**

Écrire par l'outil Write `<scratchpad>/msg_t05.txt` (`<scratchpad>` = chemin du scratchpad de session, résolu à l'exécution) :

```
feat(crawler): map update_thresholds.max_not_eligible_rate to maxNotEligibleRate

Add the optional max_not_eligible_rate field to UpdateThresholds and forward it
from start_new_crawl as params["maxNotEligibleRate"] (only when not None, so 0
is forwarded and absent leaves the Node default). crawler_manager already turns
each non-None param into a --key=value flag, so no other code changes. New test
calls start_new_crawl directly and captures params: present, zero, absent.

FR — mappage de update_thresholds.max_not_eligible_rate vers maxNotEligibleRate

Ajoute le champ optionnel max_not_eligible_rate à UpdateThresholds et le
transmet depuis start_new_crawl en params["maxNotEligibleRate"] (seulement si
non None : 0 est transmis, absent laisse le défaut Node). crawler_manager
convertit déjà chaque param non None en drapeau --clé=valeur, aucun autre code
ne change. Le test neuf appelle start_new_crawl directement et capture params :
présent, zéro, absent.
```

Puis, en commandes séparées :

```
git add apps-microservices/crawler-service/app/schemas/crawler.py apps-microservices/crawler-service/app/router/crawler.py apps-microservices/crawler-service/tests/test_update_thresholds_not_eligible.py
```

```
git commit -F <scratchpad>/msg_t05.txt
```

```
git show --stat HEAD
```
Attendu : exactement 3 fichiers listés — les deux `app/…/crawler.py` et le test neuf — rien d'autre.
### Task 6: Doc `CLAUDE.md` § Circuit Breaker
> NOMS NEUFS : aucun (la doc reprend `not_eligible`, `maxNotEligibleRate`, `Not-eligible rate too high (`, `metrics.not_eligible`, `thresholds.max_not_eligible_rate`, `max_not_eligible_rate` du contrat de l'index, tels que produits par T1-T5)

**Goal:** Documenter dans `apps-microservices/crawler-service/CLAUDE.md` (§ Circuit Breaker) le second signal `not_eligible` : ligne `maxNotEligibleRate` dans la table des seuils, paragraphe sur les deux numérateurs, et correction de la phrase fausse « `updateHealthVerdict.ts` also emits the same `Error rate too high (` prefix » (`:124` à `3cd3b7af`).

**Files:**
- Modify: `apps-microservices/crawler-service/CLAUDE.md`

**Acceptance Criteria:**
- [ ] La table des seuils porte une ligne `maxNotEligibleRate` (défaut `0.5`, branche séparée, `0` la coupe seule), le titre dit « Four thresholds », et la ligne `maxErrorRate` ne dit plus « the **only** live branch ».
- [ ] Un paragraphe « Two numerators, one denominator » énonce : numérateur HTTP = `max(0, errors − not_eligible)`, numérateur `not_eligible`, même dénominateur `processed + errors_unprocessed`, les deux préfixes de raison (`Error rate too high (` conservé, `Not-eligible rate too high (` neuf), la propriété de relaxation (`maxNotEligibleRate = 0` ou `>= maxErrorRate` ⇒ pas plus d'arrêts que l'ancien), le bypass `max_error_rate = 0` qui coupe les DEUX signaux, et les deux clés de rapport.
- [ ] La phrase fausse de `:124` n'existe plus : le texte dit que `updateHealthVerdict.ts` n'émet PAS le préfixe, avec les preuves `updateHealthVerdict.ts:184` et `statNameParity.test.ts:147` ; `grep -c -F "also emits the same"` rend 0.
- [ ] Le fichier reste tout CRLF (`LF == CRLF`) et `git diff --numstat` ne montre que des ajouts et des remplacements de lignes de ce paragraphe, de la table et du titre (aucune autre section touchée).

**Verify:** `grep -n -F -e "maxNotEligibleRate" -e "Not-eligible rate too high (" -e "Four thresholds" -e "does **not** emit" apps-microservices/crawler-service/CLAUDE.md`

**Steps:**

Rappel de lieu : cwd = racine du worktree ; **ne jamais `Read` ce fichier** depuis le fil principal (son contenu, ~25k tokens, est injecté) — un implémenteur qui édite par l'outil Edit le lit par `Read` dans SON contexte. Fichier tout CRLF (`LF 1284 CRLF 1284` mesuré le 2026-10-19 à `3cd3b7af`) ; ancres ci-dessous lues à `3cd3b7af` : `:98` (ligne `maxErrorRate`), `:96`-`:100` (table), `:122` (« still computes »), `:124`-`:127` (phrase fausse).

- [ ] **Step 1: Contrôler les ancres (une commande par ancre, chacune doit rendre 1)**

  Lancer, un appel par ligne :
  - `grep -c -F "**Three thresholds, from" apps-microservices/crawler-service/CLAUDE.md`
  - `grep -c -F "the **only** live branch" apps-microservices/crawler-service/CLAUDE.md`
  - `grep -c -F "still computes" apps-microservices/crawler-service/CLAUDE.md`
  - `grep -c -F "also emits the same" apps-microservices/crawler-service/CLAUDE.md`

  (Ancres SANS backticks : un backtick dans une commande Bash entre guillemets est exécuté.) Attendu : `1` quatre fois. Un autre nombre ⇒ re-localiser par `grep -n -F` avant d'éditer ; jamais par décalage de numéro. Si T2-T5 ont déplacé du texte, cela ne change pas ces ancres (T2-T5 n'éditent pas ce fichier).

- [ ] **Step 2: Titre et ligne `maxErrorRate` de la table (deux Edit à ligne unique, CRLF préservé)**

  Edit 1, `old_string` → `new_string` :
  ```text
  **Three thresholds, from `job.params`:**
  ```
  ```text
  **Four thresholds, from `job.params`:**
  ```
  Edit 2 :
  ```text
  | `maxErrorRate` | `0.15` | the **only** live branch |
  ```
  ```text
  | `maxErrorRate` | `0.15` | live branch — HTTP errors (`errors − not_eligible`) |
  | `maxNotEligibleRate` | not sent by the BO — default `0.5` (`context.ts`, CLI `main.ts`; Python field `max_not_eligible_rate`) | live branch, **separate** from `maxErrorRate` — URLs of the dataset that are 2xx but no longer eligible; a `0` (or absent) disables this branch alone |
  ```
  Le paragraphe « Confirmed on production via `GET /admin/job/{crawl_id}` (2026-08-24) » reste tel quel : il date une mesure sur trois seuils, antérieure à `maxNotEligibleRate`.

- [ ] **Step 3: Insérer le paragraphe des deux numérateurs avant la ligne « still computes »**

  Edit, `old_string` (ligne unique, `:122` à `3cd3b7af`) :
  ```text
  ⚠ **`updateHealthVerdict.ts` still computes `errors / processed`** for the report the BO reads.
  ```
  `new_string` (le paragraphe, une ligne vide, puis l'ancre reprise à l'identique) :
  ```text
  **Two numerators, one denominator.** `errors` stays the combined counter (no reader of `errors` changed).
  CASE 3 of `UpdateChecker.checkUrl()` — a 2xx URL that is no longer eligible — also increments
  `not_eligible`, right after `errors`. `errorRateBreaker.ts` then takes two decisions over the same
  denominator `processed + errors_unprocessed`, behind the same sample gate, both with a strict `>`:

  - **HTTP:** `max(0, errors − not_eligible) / denominator > maxErrorRate` → reason prefix
    `Error rate too high (`, kept byte for byte; the suffix now reads `N HTTP errors / M attempts`.
  - **Not eligible:** `not_eligible / denominator > maxNotEligibleRate` (only if `maxNotEligibleRate > 0`)
    → reason prefix `Not-eligible rate too high (`. Grep production logs on each prefix to tell the
    two signals apart.

  ⚠ **Relaxation property.** `httpRate + notEligibleRate` equals the old rate, so for
  `maxNotEligibleRate = 0` or `maxNotEligibleRate >= maxErrorRate` the new breaker trips only where
  the old one tripped. A value strictly between `0` and `maxErrorRate` breaks it (a 10 % non-FR run
  would be stopped that was not before): the default `0.5` respects it, and any value the BO sends
  later must too. Written in the header comment of `errorRateBreaker.ts`.

  ⚠ **`max_error_rate = 0` (`?bypasscberrors=1`) disables BOTH signals** — the `maxErrorRate > 0` guard
  comes before both decisions. `maxNotEligibleRate = 0` (CLI `--maxNotEligibleRate=0`) disables the
  second one alone. The update report `_update_report.json` carries `metrics.not_eligible` and
  `thresholds.max_not_eligible_rate` (additive keys; no reader today). Spec:
  `docs/superpowers/specs/2026-10-19-not-eligible-breaker-design.md`.

  ⚠ **`updateHealthVerdict.ts` still computes `errors / processed`** for the report the BO reads.
  ```
  Si l'Edit multi-ligne est refusé ou casse les fins de ligne, passer au Step 5.

- [ ] **Step 4: Remplacer la phrase fausse (`:124`-`:127` à `3cd3b7af`, quatre lignes)**

  Edit, `old_string` (les quatre lignes consécutives, exactement) :
  ```text
  `updateHealthVerdict.ts` also emits the same `Error rate too high (` prefix as the fixed path in
  `errorRateBreaker.ts` — one occurrence in each file. That prefix is no longer a unique
  fingerprint of the corrected formula: grepping production logs for it, the exact method behind
  this lot's 69-run measurement, now silently mixes results from both formulas.
  ```
  `new_string` :
  ```text
  `updateHealthVerdict.ts` does **not** emit the `Error rate too high (` prefix: its CRITICAL message
  deliberately avoids those words (comment at `updateHealthVerdict.ts:184@3cd3b7af`, pinned by the test
  `the breaker and the health verdict do not share a message prefix`, `statNameParity.test.ts:147@3cd3b7af`).
  The prefix therefore stays a unique fingerprint of the breaker's HTTP decision — one occurrence, in
  `errorRateBreaker.ts` — and grepping production logs for it, the method behind the 69-run measurement,
  still isolates that formula. The not-eligible decision has its own prefix (`Not-eligible rate too high (`).
  ```
  Ne pas retoucher le paragraphe suivant (« Micro mode is dead code »).

- [ ] **Step 5: Contrôle d'EOL, et normalisation si l'Edit a mêlé les fins de ligne**

  `python -c "import sys; b=open(sys.argv[1],'rb').read(); print('LF', b.count(b'\n'), 'CRLF', b.count(b'\r\n'))" apps-microservices/crawler-service/CLAUDE.md`

  Attendu : deux nombres **égaux**. Sinon (fichier tout CRLF avant l'édition, donc la normalisation est sûre) : écrire par l'outil Write le script `<scratchpad>/eol_t06.py` (`b=open(sys.argv[1],'rb').read(); b=b.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'); open(sys.argv[1],'wb').write(b)`), le lancer sur le chemin de `CLAUDE.md` (`python <scratchpad>/eol_t06.py apps-microservices/crawler-service/CLAUDE.md`), puis relancer le contrôle ci-dessus.

- [ ] **Step 6: Vérifier le contenu et l'étendue du diff**

  - `grep -n -F -e "maxNotEligibleRate" -e "Not-eligible rate too high (" -e "Four thresholds" -e "does **not** emit" apps-microservices/crawler-service/CLAUDE.md` ⇒ ≥ 1 ligne par chaîne (le paragraphe en porte plusieurs).
  - `grep -c -F "also emits the same" apps-microservices/crawler-service/CLAUDE.md` ⇒ `0`.
  - `grep -c -F "the **only** live branch" apps-microservices/crawler-service/CLAUDE.md` ⇒ `0`.
  - `git diff --numstat -- apps-microservices/crawler-service/CLAUDE.md` ⇒ suppressions **exactement 6** (titre 1 + ligne `maxErrorRate` 1 + phrase fausse 4) ; ajouts = chiffre à mesurer et consigner (non dérivable d'avance). Suppressions ≠ 6 ⇒ relire `git diff -- apps-microservices/crawler-service/CLAUDE.md` avant le commit.

- [ ] **Step 7: Message de commit (bilingue), puis commit**

  Écrire par l'outil Write le fichier `<scratchpad>/msg_t06.txt` (marqueur `<scratchpad>` résolu à l'exécution en chemin absolu ENTIER ; texte sans antislash) :
  ```text
  docs(crawler): document the separate not_eligible circuit-breaker signal (A8)

  Add the maxNotEligibleRate row and a "Two numerators, one denominator"
  paragraph to the Circuit Breaker section: HTTP numerator = errors -
  not_eligible, not_eligible numerator, same denominator, both reason
  prefixes, the relaxation property, and the max_error_rate = 0 bypass that
  disables both signals. Fix the false sentence claiming that
  updateHealthVerdict.ts emits the "Error rate too high (" prefix: it does
  not (updateHealthVerdict.ts:184, statNameParity.test.ts:147).

  FR — docs(crawler) : documenter le signal not_eligible séparé du disjoncteur (A8)

  Ajoute la ligne maxNotEligibleRate et un paragraphe « Two numerators, one
  denominator » à la section Circuit Breaker : numérateur HTTP = errors -
  not_eligible, numérateur not_eligible, même dénominateur, les deux
  préfixes de raison, la propriété de relaxation et le bypass
  max_error_rate = 0 qui coupe les deux signaux. Corrige la phrase fausse
  selon laquelle updateHealthVerdict.ts émet le préfixe « Error rate too
  high (» : il ne l'émet pas (updateHealthVerdict.ts:184,
  statNameParity.test.ts:147).
  ```
  Puis, un appel par commande :
  - `git add apps-microservices/crawler-service/CLAUDE.md`
  - `git commit -F <scratchpad>/msg_t06.txt` (chemin absolu entier du fichier écrit ci-dessus)
  - `git show --stat HEAD` ⇒ exactement 1 fichier : `apps-microservices/crawler-service/CLAUDE.md`.

**Blocked by:** Task 2, Task 3, Task 4, Task 5
### Task 7: Vérification finale (sans édition, sans commit)
> NOMS NEUFS : aucun

**Goal:** Prouver, sur le HEAD de la branche du worktree, que le lot T1-T6 est complet et borné : suite TS verte avec le bon compte, build, pytest, ensemble exact des fichiers touchés, `updateHealthVerdict.ts` limité à des commentaires, et aucune branche ni commit neuf à juger avant le merge.

**Files:**
- Read: `docs/superpowers/plans/2026-10-19-not-eligible-breaker.d/00-index.md` (table File Structure) — aucun fichier édité ; aucun commit (`git status` ne doit rien gagner de cette tâche)

**Acceptance Criteria:**
- [ ] Suite TS entière : `fail 0`, `pass` = `tests`, et `tests` ≥ 653 + N, où N = nombre de `test(` ajoutés par T1-T4 (ligne de base 653 au `3cd3b7af` + tests neufs de T1-T4), N dérivé et écrit dans le rapport.
- [ ] `npm run build` rend rc 0.
- [ ] pytest de `tests/test_update_thresholds_not_eligible.py` et de `tests/test_crawler.py` : comptes `passed` non nuls, 0 `failed`.
- [ ] `git diff --stat 3cd3b7af..HEAD` liste exactement les fichiers de la table « File Structure » de l'index (plus les fichiers du plan lui-même sous `docs/superpowers/plans/`), et ni `StatsManager.ts` ni `nonHtmlPrefixWiring.test.ts`.
- [ ] `git diff 3cd3b7af..HEAD -- apps-microservices/crawler-service/crawler/src/updateHealthVerdict.ts` ne touche que des lignes de commentaire.
- [ ] Toute branche non mergée dans `features/poc`, hors `features/crawling-revert-nodejs` (jugée morte, spec §8) et la branche du worktree, est ancêtre de `features/poc` ; `git log --oneline 3cd3b7af..features/poc -- apps-microservices/crawler-service` est vide.

**Verify:** `git log --oneline 3cd3b7af..features/poc -- apps-microservices/crawler-service`

**Steps:**

Aucune édition de fichier, aucun commit, aucun `git add`. Une commande simple par appel, chemins littéraux, jamais `cd`. Chaque commande de test se lance telle qu'écrite dans la table « Commandes prescrites » de l'index (la sortie doit prouver le lieu : `crawler-engine@1.0.0 test` pour la suite TS ; chemins du worktree dans les rapports node/pytest).

- [ ] **Step 1: Lancer la suite TS entière en arrière-plan (~255 s)**

  Outil Bash avec `run_in_background: true`, la commande de l'index (usage « Suite TS entière ») :
  `npm --prefix D:/DevHellopro/Workspaces/RAG-HP-PUB/.claude/worktrees/a8-not-eligible-breaker/apps-microservices/crawler-service/crawler test`

  Ne pas attendre : enchaîner les Steps 2 à 6 pendant ce temps (aucun ne touche aux fichiers qu'elle lit). Ne pas sonder la sortie pendant l'attente ; la notification de fin arrive d'elle-même.

- [ ] **Step 2: Build TS**

  `npm --prefix D:/DevHellopro/Workspaces/RAG-HP-PUB/.claude/worktrees/a8-not-eligible-breaker/apps-microservices/crawler-service/crawler run build`

  Attendu : rc 0 imprimé (le résultat de sonde de build consigné par le contrôleur dans HANDOFF ou ledger sert de référence ; sinon écrire la sortie observée dans le rapport). rc ≠ 0 ⇒ STOP, pas de correction ici : renvoyer à T3/T4.

  La suite lit `src/**/*.test.ts` via `tsx` (`package.json:24`) et le build est `tsc` (`package.json:23`) : les deux peuvent tourner en parallèle (lecture, `grep -n -F -e "\"test\"" -e "\"build\"" apps-microservices/crawler-service/crawler/package.json` pour re-dériver). Si `tsc` écrit sous un dossier que la suite lit, relancer la suite entière après le build.

- [ ] **Step 3: Pytest — fichier neuf de T5, puis `test_crawler.py`** (une commande par appel)

  - `PYTHONPATH=apps-microservices/crawler-service python -m pytest apps-microservices/crawler-service/tests/test_update_thresholds_not_eligible.py -q -p no:cacheprovider`
  - `PYTHONPATH=apps-microservices/crawler-service python -m pytest apps-microservices/crawler-service/tests/test_crawler.py -q -p no:cacheprovider`

  Attendu : `N passed` avec N non nul, 0 `failed`, rc 0 ; `test_crawler.py` : `3 passed` (ligne de base de l'index). « no tests ran » ou fichier absent ⇒ échec (le fichier neuf doit exister : `git ls-files apps-microservices/crawler-service/tests/test_update_thresholds_not_eligible.py` non vide).

- [ ] **Step 4: Ensemble exact des fichiers touchés depuis la base**

  - `git rev-parse HEAD` puis `git rev-parse 3cd3b7af` (noter les deux SHA dans le rapport).
  - `git diff --stat 3cd3b7af..HEAD`

  Comparer à la table « File Structure » de l'index : `UpdateChecker.ts`, `UpdateChecker.deleteVerdict.test.ts`, `UpdateChecker.datasetIdentity.test.ts`, `errorsUnprocessedParity.test.ts`, `errorRateBreaker.ts`, `errorRateBreaker.test.ts`, `updateHealthVerdict.ts`, `context.ts`, `main.ts`, `routes.ts`, `functions.ts`, `app/schemas/crawler.py`, `app/router/crawler.py`, le test Python neuf, `apps-microservices/crawler-service/CLAUDE.md` — plus `statNameParity.test.ts` seulement si l'extension facultative de T4 a été faite (à écrire dans le rapport), et les fichiers du plan sous `docs/superpowers/plans/2026-10-19-not-eligible-breaker*` et de la spec sous `docs/superpowers/specs/`. Tout autre fichier = écart à nommer, STOP.

  Contrôles d'absence (deux formes) :
  - `git diff --name-only 3cd3b7af..HEAD -- apps-microservices/crawler-service/crawler/src/class/StatsManager.ts apps-microservices/crawler-service/crawler/src/nonHtmlPrefixWiring.test.ts` ⇒ sortie vide.
  - `git diff --stat 3cd3b7af..HEAD` relu à l'œil : aucune ligne `StatsManager` ni `nonHtmlPrefixWiring`.

- [ ] **Step 5: `updateHealthVerdict.ts` — commentaires seuls**

  `git diff 3cd3b7af..HEAD -- apps-microservices/crawler-service/crawler/src/updateHealthVerdict.ts`

  Chaque ligne `+` et `-` (hors en-têtes `+++`/`---`) doit, une fois les blancs de tête retirés, commencer par `//` ou `*` ou `/*`. Une ligne de code touchée ⇒ STOP (spec §4 : commentaire `:184` seul).

- [ ] **Step 6: Branches vivantes et commits neufs sur `features/poc`**

  - `git branch -a --no-merged features/poc` ⇒ liste L.
  - Pour chaque branche de L **autre que** `features/crawling-revert-nodejs` (jugée morte, spec §8, branche non mergée depuis 2026-01-29) **et** `worktree-a8-not-eligible-breaker` : `git rev-parse <branche>` puis `git merge-base --is-ancestor <tête> features/poc` (une commande par appel), rc 0 attendu. rc 1 (branche neuve non fusionnée) ⇒ STOP : la juger avant merge (`git log 3cd3b7af..<branche> --stat`).
  - `git log --oneline 3cd3b7af..features/poc -- apps-microservices/crawler-service` ⇒ **vide** attendu. Non vide ⇒ STOP : commits neufs à juger avant merge, décision pour les seuls commits neufs ; ne rien merger, rendre la liste. Le SHA de `features/poc` jugé (`git rev-parse features/poc`) s'écrit dans le rapport ; au merge, un autre SHA est non jugé.

- [ ] **Step 7: Lire le résultat de la suite TS et conclure**

  À la notification de fin du Step 1 : lire les lignes finales (`tail`, en lecture seule) de la sortie de la tâche de fond. Relever `tests`, `pass`, `fail` ; contrôler `fail 0`, `pass == tests`, et la ligne `crawler-engine@1.0.0 test` (preuve du lieu).

  Dériver N : `git diff 3cd3b7af..HEAD -- apps-microservices/crawler-service/crawler/src apps-microservices/crawler-service/tests` puis compter les `+test(` / `+    test(` ajoutés (par `git diff 3cd3b7af..HEAD -U0 -- <chemins>` filtré à l'œil ou par script Python écrit par l'outil Write) ; attendre `tests` ≥ 653 + N. Écart (suite < 653 + N) ⇒ un test ajouté n'est pas collecté : STOP, nommer le fichier.

  Rapport final : les SHA du Step 4, `tests/pass/fail`, N et 653 + N, rc du build, comptes pytest, liste des fichiers du `--stat`, verdict des Steps 5-6. Aucun commit, aucune édition : `git status --short` ne doit rien lister d'imputable à cette tâche.

**Blocked by:** Task 6
