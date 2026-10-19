# Disjoncteur `not_eligible` séparé du disjoncteur HTTP — spec

**Date** : 2026-10-19
**Service** : `apps-microservices/crawler-service`
**Base jugée (base gate)** : `features/poc@3cd3b7afb649a5f0bc4a696ba28ade17d1ee8ca7` — `git log 3cd3b7af..features/poc -- apps-microservices/crawler-service/crawler/src` vide à l'arrivée (2026-10-19 14:05) et re-joué avant rédaction (2026-10-19 14:13, `features/poc` = `3cd3b7af`, 0 commit). Toutes les ancres `fichier:ligne` ci-dessous sont lues à ce SHA.
**Action** : A8 (c) du registre Marketplace — `C:/Users/USER/.claude/projects/D--DevHellopro-Marketplace/memory/ACTIONS.md`
**Design approuvé** : 2026-10-19 par l'user, seuil 0,5 — `D:/DevHellopro/Marketplace/.claude/a8/design_c_approuve_2026-10-19.md`
**Voisin de** : `docs/superpowers/specs/2026-08-24-circuit-breaker-error-rate-design.md` (dénominateur `processed + errors_unprocessed`, inchangé ici)

---

## 1. Le problème, en une phrase

Le disjoncteur de MAJ coupe un run quand `errors / (processed + errors_unprocessed) > maxErrorRate` (0,15). Or `errors` additionne deux natures : les erreurs HTTP sur une URL du dataset (CASE 1) et les URLs du dataset qui répondent 2xx mais ne sont plus éligibles (CASE 3 — extension, paramètre interdit, contenu non-FR). Un site dont 16 % des pages sont devenues non-FR est coupé comme un site en panne.

**Ce que la séparation ne fait PAS** : aucun seuil de taux ne sépare les non-FR justes des faux (6 runs mesurés : 15,4 J · 15,9 J · 16,7 F · 22 J · ≈48 J · 62 F — ligne « Brainstorm (c) » de l'entrée A8). Le seuil `not_eligible` borne donc le **coût** d'un run, pas sa justesse ; la sûreté des suppressions reste au verdict de santé et aux plafonds BO (§5).

## 2. Comptage

### 2.1 Nouveau compteur `not_eligible`

`checkUrl()` — `class/UpdateChecker.ts:363@3cd3b7af` (CASE 3, branche « No longer eligible ») : ajouter `await this.statsManager.increment("not_eligible");` **immédiatement après** `increment("errors")`, avant l'écriture du JSONL `deleted`.

- Couvre les trois inéligibilités, puisque `isEligible()` les juge toutes ici. Écrit pour les deux orthographes (`exact` et `folded`), comme `errors` à la même ligne — le crédit `accounted` reste réservé à `exact`, inchangé.
- `errors` inchangé : même nombre d'écrivains, mêmes sites.
- `StatsManager` n'est pas modifié : `increment(metric)` est générique (`class/StatsManager.ts:67`), et `saveStateToDisk()`/`loadStateFromDisk()` persistent tout le hash (`hGetAll`, `:107`) — le compteur traverse un redémarrage OOM sans code neuf.
- **Ordre `errors` puis `not_eligible`, imposé** : les deux `hIncrBy` ne sont pas atomiques. Entre les deux, un lecteur concurrent voit `errors` déjà incrémenté et `not_eligible` pas encore, donc compte l'URL comme HTTP — sens prudent (plus d'arrêts, jamais moins). L'ordre inverse produirait un numérateur HTTP transitoirement sous-évalué.

### 2.2 Numérateur HTTP = `errors − not_eligible`

Et non `errors_unprocessed`. Aujourd'hui les deux sont égaux, parce que les deux autres écrivains de `errors` — `routes.ts:416` et `functions.ts:650` — sont gatés par `request.userData.is_existing`, que `main.ts:1063` ne pose qu'à `false`. Mais un futur écrivain de `errors` serait compté comme HTTP par la soustraction (sens prudent), et comme rien par `errors_unprocessed` (sens laxiste).

Plancher à 0 dans la fonction pure : `Math.max(0, errors − notEligible)`. `StatsManager.increment()` avale ses erreurs Redis et rend 0 (`:73-76`) ; un `errors` perdu suivi d'un `not_eligible` réussi rendrait la différence négative.

**Run repris à cheval sur le déploiement** : un `update_stats.json` écrit avant le déploiement n'a pas de clé `not_eligible` ⇒ `getValue` rend 0 ⇒ numérateur HTTP = `errors`, c'est-à-dire exactement l'ancien disjoncteur. Sens prudent.

## 3. Disjoncteur — `errorRateBreaker.ts`

La fonction pure `shouldTripErrorRateBreaker()` (`errorRateBreaker.ts:49`) prend deux décisions sur le même dénominateur `attempts = processed + errorsUnprocessed` et derrière la même porte d'échantillon `processed >= minSample` :

| Ordre | Décision | Taux | Seuil | Raison émise si déclenché |
|---|---|---|---|---|
| 1 | porte d'échantillon | — | `processed < minSample` ⇒ pas d'arrêt | inchangée |
| 2 | signal coupé | — | `!(maxErrorRate > 0)` ⇒ pas d'arrêt, **les deux décisions** | inchangée |
| 3 | HTTP | `httpErrors / attempts` | `> maxErrorRate` (0,15, inchangé) | `Error rate too high (` … — préfixe conservé |
| 4 | not_eligible | `notEligible / attempts` | `> maxNotEligibleRate` (nouveau, défaut **0,5**), seulement si `maxNotEligibleRate > 0` | `Not-eligible rate too high (` … — préfixe neuf, distinct |

Interfaces :

```ts
export interface ErrorRateBreakerStats {
    errors: number;
    processed: number;
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
```

Retour : `{ trip, rate, attempts, reason }` conservé ; `rate` devient le taux **HTTP** ; ajout de `notEligibleRate`. `notEligible` absent vaut 0, donc tout appel qui ne le passe pas rend **exactement** l'ancien résultat : les 9 tests existants de `errorRateBreaker.test.ts` restent verts sans modification — c'est le contrôle de non-régression.

**Propriété de relaxation stricte.** `httpRate + notEligibleRate = ancien rate`. Donc, pour `maxNotEligibleRate = 0` ou `maxNotEligibleRate >= maxErrorRate` : `trip_nouveau ⇒ trip_ancien`. Avec un seuil `not_eligible` strictement entre 0 et `maxErrorRate`, la propriété tombe (un run à 10 % non-FR serait coupé alors qu'il ne l'était pas). Le défaut 0,5 la respecte ; la valeur future du référentiel BO devra la respecter aussi — écrit dans le commentaire d'en-tête du module.

**Échappatoire opérateur** : `?bypasscberrors=1` (`shell.php`) envoie `max_error_rate = 0` ⇒ décision 2 ⇒ les deux signaux coupés, sans paquet BO.

**Raison HTTP** : préfixe `Error rate too high (` conservé octet pour octet (logs de prod greppés dessus, test `the reason keeps the grepped prefix on trip`, `statNameParity.test.ts:151-154`). Le suffixe compte désormais `${httpErrors} HTTP errors / ${attempts} attempts` au lieu de `${errors} errors / …` : une ligne de log postérieure au déploiement se distingue ainsi de l'ancienne formule sans changer le préfixe greppé. Aucun lecteur du suffixe : 0 occurrence de `Error rate too high` sous `Marketplace/BO` (pin check, §8). *Précision de rédaction, hors design.*

### 3.1 Appel — `routes.ts`, bloc « Circuit Breaker Check (Dual-Mode) »

- Lire `const notEligible = await context.statsManager.getValue("not_eligible");` à côté de `errorsUnprocessed` (`routes.ts:465`).
- Le passer : `shouldTripErrorRateBreaker({ errors, processed, errorsUnprocessed, notEligible }, cb)` (`routes.ts:485-488`). `cb` porte déjà `maxNotEligibleRate` (§3.2).
- Rien d'autre : `stopReason = "circuitBreaker"`, `dropped_cb`, `stopCrawler` inchangés (`:504-511`). Mode micro et branche legacy `maxErrors` inchangés.

### 3.2 Paramètre `maxNotEligibleRate`

Sur le modèle de `maxErrorRate`, à chaque étage :

| Étage | Fichier | Ajout |
|---|---|---|
| Défaut du contexte | `context.ts:65` | `maxNotEligibleRate: 0.50,` |
| CLI Node | `main.ts:132` | `const maxNotEligibleRate = parseNumericArg('maxNotEligibleRate', 'npm_config_maxnoteligiblerate', 0.50);` + champ dans `circuitBreaker` (`main.ts:168`) |
| Log de démarrage | `main.ts:1022` | `NotEligibleRate=…%` dans la ligne `Limits:` |
| Schéma Python | `app/schemas/crawler.py:51` | `max_not_eligible_rate: Optional[float] = None` dans `UpdateThresholds` |
| Mappage Python | `app/router/crawler.py:292` | `params["maxNotEligibleRate"] = …` si non `None` |

⚠ **Précision ajoutée à la rédaction, hors design approuvé** : le design dit « paramètre CLI sur le modèle de `maxErrorRate` » ; or `maxErrorRate` n'atteint Node que par le schéma et le mappage Python (`crawler.py:292-293`, `crawler_manager.py:778-780`). Sans ces deux lignes, le paramètre n'est réglable par aucun appelant, et le BO qui l'enverrait un jour serait ignoré en silence (Pydantic ignore les champs inconnus). Le défaut reste 0,5 tant que personne ne l'envoie. À retirer à la revue si l'user préfère un lot Python séparé.

## 4. Lecteurs de `errors` — inchangés, à dessein

`errors` reste le compteur combiné pour :

- mode micro `routes.ts:471` (code mort, `isMicroMode` jamais posé) ;
- legacy `maxErrors` `routes.ts:517` ;
- garde de masse `SUSPECT` `updateHealthVerdict.ts:217` (`errors / previousTotal > 0.5`) ;
- verdict `CRITICAL` `updateHealthVerdict.ts:177` (`errorRate > maxErrorRate && errors >= maxAbsErrors`). Le séparer était l'option (b), écartée.

Conséquence voulue : un run que le disjoncteur laisse aller au bout avec 16 % de non-FR sort `CRITICAL` au verdict final si son taux combiné reste > 15 % ⇒ le BO retient suppressions et redirections (`script_process_update_crawling.php:894`), applique le reste, autorisation opérateur possible (`:945`).

`updateHealthVerdict.ts` n'est modifié que dans un commentaire : `:184` cite `errorRateBreaker.ts:73` par numéro de ligne, que ce lot déplace — le re-pointer sur le symbole (`shouldTripErrorRateBreaker()` dans `errorRateBreaker.ts`). Aucune ligne de code.

## 5. BO — aucun paquet

- `stopReason` reste `circuitBreaker` ⇒ `script_process_update_crawling.php:594` (`FAILED`, rien appliqué), mail, `crawl_metrics` inchangés.
- `_update_report.json` (`generateUpdateReport()` — `functions.ts:1429`) : deux clés additives, `metrics.not_eligible` et `thresholds.max_not_eligible_rate`. Le rapport n'est pas lu par nom de fichier côté BO : Python en recopie les champs `mode, health, metrics, rates, thresholds, jsonl_files` dans le webhook de succès (`crawler_manager.py:1104-1117`, webhook GET aux paramètres aplatis en crochets), et le BO relit aussi le fichier sur disque (`script_process_update_crawling.php:839-841`). Lecteurs relevés : `script_process_update_crawling.php:867-898,1082-1083` et `fonctions_garde_sante_bilan_pure.php:253-284` — tous par clé nommée avec `??` ou par `foreach` sur une **liste fixe** de noms ; aucun contrôle de schéma, aucun comptage de clés, aucun rendu de toutes les clés. Deux clés de plus sont ignorées. Seul effet : la query string du webhook s'allonge d'environ 60 octets (limite de ligne de requête Apache/FPM et d'argv non mesurées — l'ordre de grandeur, ~60 octets contre des milliers, ne justifie pas la mesure).
- Placement dans `functions.ts` : `const notEligible = await context.statsManager.getValue("not_eligible");` à côté de `errorsUnprocessed` (`:1441`) ; `not_eligible: notEligible,` dans `metrics` **après** `errors_unprocessed` et **avant** `previous_total`, sans aucun `}` intérieur (pin `statNameParity.test.ts:81-135`, §8) ; `max_not_eligible_rate: cb.maxNotEligibleRate,` dans `thresholds` après `max_error_rate`.
- Seuil dans `referentiel_seuils_cb` / `shell.php` : plus tard, optionnel ; défaut crawler d'ici là.

## 6. Effet attendu

Frontière : un run change de sort ssi, après `minSample`, **taux combiné > 15 %** ET **HTTP ≤ 15 %** ET **not_eligible ≤ 50 %**. Sur les 7 runs de la vague 2 (47) :

| Run | Avant | Après |
|---|---|---|
| vall.fr (62 % non-FR) | coupé | coupé (not_eligible) |
| formatoverde, aria, ogimat, macdon | coupés | vont au bout ; verdict sur run complet |
| groupetanguy (16,7 %, non-FR faux) | coupé | au bout ; 14 faux retenus si taux final > 15 % (`CRITICAL`), appliqués sinon — risque résiduel, plafonds BO 50 % restent |
| 1780 | coupé | probablement au bout |

## 7. Tests

`npm test` = `node --import tsx --test src/**/*.test.ts` (`crawler/package.json`).

| Fichier | Cas |
|---|---|
| `errorRateBreaker.test.ts` (étendu, 9 cas existants intacts) | HTTP seul déclenche ; not_eligible seul déclenche sous préfixe `Not-eligible rate too high (` ; combiné > 15 % mais chacun sous son seuil ⇒ pas d'arrêt ; `maxNotEligibleRate = 0` désactive la décision 4 ; `maxErrorRate = 0` désactive les deux ; égalité stricte au seuil 0,5 ⇒ pas d'arrêt ; plancher `errors − notEligible >= 0` ; **grille** : pour tout `processed, eOff, eOn, ne <= eOn` et `maxNotEligibleRate ∈ {0, 0.15, 0.5, 1}`, `trip_nouveau ⇒ trip_ancien` |
| `errorsUnprocessedParity.test.ts` (étendu) | `UpdateChecker.ts` contient exactement 1 `increment("not_eligible")`, situé après le marqueur `CASE 3: Success` ; `routes.ts` lie `const notEligible = await … getValue("not_eligible")` et le passe dans l'appel `shouldTripErrorRateBreaker({…notEligible…})` ; le test `errors keeps exactly its two live writers` reste à 2 |
| `tests/UpdateChecker.deleteVerdict.test.ts` | ⚠ **seul attendu existant modifié** : `:116` `['errors', 'accounted']` → `['errors', 'not_eligible', 'accounted']` (le `deepEqual` épingle la séquence d'appels de CASE 3 — impossible d'ajouter un compteur sans le toucher). CASE 1 (`:71`, `:87`) inchangés : la preuve que HTTP n'incrémente pas `not_eligible` |
| `tests/UpdateChecker.datasetIdentity.test.ts` ou fichier neuf | CASE 3 orthographe `folded`, 200 non éligible : `['errors', 'not_eligible']`, pas d'`accounted` |
| Python `tests/` | `max_not_eligible_rate` présent ⇒ `params["maxNotEligibleRate"]` ; absent ⇒ clé absente |

Vérification de build : `npm run build` (tsc) — `context.config.circuitBreaker` est typé par inférence depuis `context.ts`, donc le champ doit y exister avant que `main.ts` l'affecte.

## 8. Pin check

Énumération par nom de fichier (chemin et basename) sur tout le dépôt, faite le 2026-10-19 à `3cd3b7af` ; rapport : `C:/Users/USER/AppData/Local/Temp/claude/D--DevHellopro-Marketplace/983af791-0c73-4072-a9de-1d8143219d21/scratchpad/a8_pincheck.md` (temporaire). Aucun hash, golden ni snapshot sur `crawler/src` ; aucun test Python ne lit ces fichiers. Trois tests exécutés lisent le TEXTE source (`git grep import.meta.dirname` = exactement ces trois) :

| Consommateur | Ce qu'il épingle | Points d'édition de ce lot | Verdict |
|---|---|---|---|
| `errorsUnprocessedParity.test.ts` | `routes.ts` : appel `shouldTripErrorRateBreaker({…errorsUnprocessed…})` (regex `[^}]*`) et liaison `const errorsUnprocessed = await …getValue("errors_unprocessed")` ; `UpdateChecker.ts` : 1 seul `increment("errors_unprocessed")` avant `CASE 3: Success`, exactement 2 `increment("errors")` | ajout de `notEligible` dans le même objet littéral ; ajout d'un `increment("not_eligible")` | tient : `[^}]*` traverse une propriété de plus ; le compte de `errors` reste 2 |
| `statNameParity.test.ts` | `functions.ts` : tranche `const report = {` → premier `};`, tranche `metrics: {` → premier `}` ; `errorRateBreaker.ts` contient `Error rate too high (` ; `updateHealthVerdict.ts` n'a aucun `statusMessage` qui le contienne | clés `metrics.not_eligible`, `thresholds.max_not_eligible_rate` ; raison HTTP | tient si aucune `}` n'entre dans `metrics` avant `previous_total` (§5) ; préfixe conservé |
| `nonHtmlPrefixWiring.test.ts` | `routes.ts`, `functions.ts`, `main.ts` : câblage R23 | aucun point dans les régions R23 | hors des régions |
| `tests/UpdateChecker.deleteVerdict.test.ts:116` | séquence d'appels de CASE 3 | ajout de `not_eligible` | **attendu mis à jour**, §7 |
| `updateHealthVerdict.ts:184` (commentaire) | `errorRateBreaker.ts:73` par numéro de ligne | la ligne bouge | re-pointé sur le symbole, §4 |
| `crawler-service/CLAUDE.md` § Circuit Breaker (`:94-127`) | doc des seuils | nouveau signal | **mis à jour dans le lot** : ligne `maxNotEligibleRate` dans la table, paragraphe sur les deux numérateurs. Au passage, `:124` affirme que `updateHealthVerdict.ts` émet le même préfixe — contredit par `updateHealthVerdict.ts:184` et `statNameParity.test.ts:160-169` : corriger cette phrase, c'est le même paragraphe |

**Comptes PASS publiés** : aucun pour ces fichiers de test dans `RAG-HP-PUB/docs/superpowers` ni `Marketplace/docs/superpowers`. ⚠ Le grep de `D:/DevHellopro/banc_selecteurs_data` a **expiré** (60 s) : absence non établie. Le plan le rejoue en tête, borné (`--include='*.md'`, en arrière-plan) — ce répertoire porte les bancs PHP du BO, une épingle de tests TS du crawler y serait inattendue.

**Branches vivantes** : 4 branches, 1 worktree. Seule `features/crawling-revert-nodejs` (dernier commit 2026-01-29) n'est pas ancêtre de `features/poc` et touche `StatsManager.ts`, `context.ts`, `functions.ts`, `main.ts`, `routes.ts` — branche morte depuis 9 mois, non bloquante. Condition à re-dériver avant le merge : `git merge-base --is-ancestor <tête de branche> features/poc` pour toute branche neuve.

## 9. Hors périmètre

- Option (b) : séparer le verdict de santé — écartée.
- Seuil dans `referentiel_seuils_cb` et `shell.php` — plus tard.
- Classer les non-FR justes et faux — aucun seuil de taux ne le fait (§1) ; c'est le chantier de la détection de langue, pas du disjoncteur.
