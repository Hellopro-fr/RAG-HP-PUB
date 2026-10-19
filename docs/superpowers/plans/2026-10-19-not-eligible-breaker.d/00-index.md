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
