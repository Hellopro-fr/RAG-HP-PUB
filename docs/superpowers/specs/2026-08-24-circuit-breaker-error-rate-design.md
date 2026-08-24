# Circuit breaker : le taux d'erreurs n'est pas un taux — spec

**Date** : 2026-08-24
**Service** : `apps-microservices/crawler-service`
**Fichier visé** : `crawler/src/routes.ts`, bloc « Circuit Breaker Check (Dual-Mode) »
**Voisin de** : `docs/superpowers/specs/2026-06-09-external-redirect-breaker-design.md` (l'autre disjoncteur, celui-là correct)
**Déclencheur** : 121 domaines du BO définitivement exclus de toute mise à jour, dont la cause remonte à ce bloc

---

## 1. Ce que la mesure établit

Les 69 runs de MAJ du lot du 2026-08-10 arrêtés en `circuitBreaker`, taux relevés dans leur
`crawler.log` via `GET /crawling-service/admin/logs/{crawl_id}?grep=Circuit%20breaker%20triggered`.
**69 taux lus, 0 log muet, 0 appel en erreur.** Un seul motif sur les 69 : `Error rate too high` —
les deux autres branches sont éteintes, le lanceur BO envoyant `max_redirect_rate = 0` et
`max_growth_rate = 0`, et un 0 **désactive** sa branche (`routes.ts:467-471`, gardes `> 0`).

| Taux réel | Runs | Part |
|---|---|---|
| **< 16 % — marge de moins d'un point** | **23** | **33 %** |
| 16–25 % | 17 | 25 % |
| 25–50 % | 10 | 14 % |
| 50–100 % | 7 | 10 % |
| **> 100 % — arithmétiquement impossible** | **12** | **17 %** |

⚠ **Trois runs à exactement 15,0 %** : arrêtés sur un arrondi.
⚠ Les runs les plus marginaux sont ceux qui **travaillaient le plus** : `douillet-agricole.fr` a
stocké **262** fichiers avant d'être arrêté à 15,2 %, `wallart.fr` 155 à 15,3 %, `nacelle44.com` 79
à 16,0 %. Un site qui livre 262 pages n'est pas un site en panne.

⇒ **35 des 69 (51 %)** ont été arrêtés soit sur un cheveu, soit sur un nombre invalide.

### Pourquoi c'est grave en aval, et pas seulement inélégant

Le disjoncteur ne pose pas de code de sortie fatal : le run sort en 2, que le service classe en
**succès**, et le webhook part avec `isError = "circuitBreaker"`. Côté BO, ce webhook conduit à une
ligne `update_crawling_history` en `FAILED`. Et `est_domaine_deja_en_cours()` teste
`status IN ('PENDING','RUNNING','FAILED','STOPPED')` **sans borne de date** ⇒ **une ligne FAILED
verrouille son domaine pour toujours**.

État au 2026-08-20, côté BO : **136 domaines verrouillés**, dont **121 pourtant éligibles** à la MAJ
sur 3 014 éligibles (**4,0 %**). Et **591 `PENDING` restent à drainer** : chaque arrêt marginal en
ajoute un. **Ce n'est pas un résidu, c'est un flux.**

---

## 2. Deux défauts, dont un seul est prouvé réparable

### 2.1 Le dénominateur exclut son propre numérateur — PROUVÉ

`errorRate = errors / processed` (`routes.ts:464`), mais `processed` n'est incrémenté qu'**après** la
politique de statut HTTP, laquelle `throw` avant (`routes.ts:434` puis `:444`). Une URL en erreur
HTTP compte donc au **numérateur** et **jamais** au dénominateur.

**Les 12 taux supérieurs à 100 % sont la preuve terrain** : une proportion ne peut pas dépasser 1.

⚠ **Le code compense déjà ce biais exact, trois lignes plus haut, pour le mur de proxy** — et son
commentaire l'énonce (`routes.ts:420-424`) : *« processed counts only requests that passed the status
check (blocked ones throw before increment("processed")) … so the ratio denominator is total attempts
= blocked + processed-ok »*. La correction à faire est donc **déjà écrite dans ce fichier**, pour un
autre disjoncteur, à quelques lignes de distance.

### 2.2 Le seuil de 15 % est peut-être trop serré — NON TRANCHÉ

33 % des arrêts se font à moins d'un point. Mais **ce n'est pas démontrable comme un défaut** : si
ces 15,2 % sont des erreurs réelles et matérielles, le disjoncteur fait son travail. La question ne
se tranche qu'en connaissant **de quoi `errors` est fait** sur ces runs (§4).

---

## 3. ⚠ Le correctif « plancher de matérialité » est une FAUSSE PISTE — corrigé ici

Il était tentant de transposer la conjonction de `updateHealthVerdict.ts:95`, qui exige
`errorRate > maxErrorRate` **ET** `errors >= maxAbsErrors`. **Cela ne répare rien**, et l'arithmétique
le dit :

- à `processed = 50` (la porte `minSample`), un taux de 15 % est franchi dès **8 erreurs** ;
- le `maxAbsErrors` par défaut vaut **5** ⇒ **déjà satisfait** au moment où le taux déclenche ;
- sur le run marginal à 262 fichiers, `errors` tourne autour de **40** ⇒ le plancher est hors sujet.

⇒ Le plancher de 5 ne retirerait **aucun** des 23 arrêts marginaux. Une conjonction n'aide que si son
second terme est calibré, et le calibrer demande la mesure du §4. **Cette piste est écartée, pas
différée.**

---

## 4. La mesure qui doit précéder toute décision de seuil

**De quoi `errors` est-il fait, sur les 23 runs marginaux ?** Deux écrivains vivants en mode update,
et ils désignent deux pannes différentes :

| Écrivain | Nature | Incrémente `processed` ? |
|---|---|---|
| `UpdateChecker.ts:175` | échec HTTP (`>= 400`) ou statut 0 (réseau) | **NON** — `throw` avant |
| `UpdateChecker.ts:278` | 2xx sans redirection mais jugée **non éligible** (extension, paramètre, **non-français**) | **OUI** |

**Discriminant disponible** : les fichiers JSONL `deleted` du run portent `reason: http_error_404`
contre `reason: not_eligible`. Accessibles par `GET /crawling-service/admin/dataset/{crawl_id}` et
`/admin/sidecar/{crawl_id}`.

**Ce que chaque issue implique :**
- **Majorité `http_error_*` / statut 0** ⇒ le biais du §2.1 est la cause dominante. Réparer le
  dénominateur suffit : les taux baissent mécaniquement, les 12 invalides redeviennent des
  proportions, et une partie des 23 marginaux repasse sous le seuil **sans toucher au seuil**.
- **Majorité `not_eligible`** ⇒ le dénominateur est déjà correct pour ces runs, et réparer le §2.1
  ne changera **rien** pour eux. Le sujet devient alors : **un verdict métier (non-français,
  extension) doit-il arrêter un crawl technique ?** C'est une question de conception, pas de
  calibrage.

⚠ **Sans cette mesure, on ne peut pas savoir si réparer le dénominateur résout 23 arrêts ou zéro.**

### 4.1 La mesure est BLOQUÉE PAR CONCEPTION — mesuré le 24/08

`GET /admin/dataset/{crawl_id}?kind=update` rend **404** sur ces runs :
*« Dataset not on local disk (crawl may be stashed/archived — this endpoint is deliberately
side-effect-free ; use /unstash or /results to restore cold data) »*. Vérifié y compris sur un run
terminé **deux heures plus tôt** : les datasets refroidissent vite.

⇒ Obtenir la composition de `errors` exige `/unstash` ou `/results`, qui **ont des effets de bord**
(`/results` tamponne `downloaded_at` et désarchive). **C'est une décision d'exploitation, pas une
lecture** : elle ne se prend pas au passage d'une investigation.

### 4.2 Ce qu'on peut BORNER sans restaurer quoi que ce soit

Si le dénominateur devient « toutes les tentatives », le taux corrigé d'un run vaut au mieux
`e / (processed + e)`, soit **`r / (1 + r)`** — le cas où **toutes** les erreurs contournaient
`processed`. La bascule sous 15 % se situe donc à **r = 17,65 %**.

Appliqué aux 69 taux réellement mesurés :

| Hypothèse | Runs repassant sous 15 % |
|---|---|
| **Borne haute** — toutes les erreurs contournaient `processed` | **31 sur 69 (45 %)** |
| **Borne basse** — aucune ne contournait (tout `not_eligible`) | **0** |

⚠ **Et dans TOUS les cas, quel que soit le mélange** : les **12** runs cessent d'annoncer un taux
impossible. Le maximum mesuré sur les 69 est **722 %** — il deviendrait 88 %. (Mon premier échantillon
de 5 runs donnait 228 % comme maximum : le balayage complet montre bien pire.)

⇒ **Le correctif se justifie sans attendre la mesure du §4** : 12 runs ont été arrêtés par un nombre
qui n'est pas une proportion. Ce que la mesure décide, c'est **combien** de runs marginaux il
récupère — entre 0 et 31 — pas s'il faut le faire.

---

## 5. Ce que la spec propose

**Un seul changement, celui qui est prouvé** : que `errorRate` compte au dénominateur **toutes les
tentatives**, pas seulement celles qui ont franchi le contrôle de statut.

⚠ **La symétrie avec le mur de proxy n'est PAS exacte** — la première rédaction de cette spec
l'affirmait, à tort. Les deux disjoncteurs voisins ont un numérateur **disjoint de `processed`
par construction** (`shouldTripProxyWall(blocked, blocked + processedOk, …)`,
`shouldTripExternalRedirectBreaker(external, processed, …)`). `errors` est un **mélange** :
`UpdateChecker.ts:175` (erreur HTTP) contourne `processed`, `UpdateChecker.ts:278` (2xx non
éligible) y est **déjà compté**. Écrire `processed + errors` diluerait donc le taux précisément
sur les runs dont le taux est déjà juste — cela affaiblirait une garde qui fonctionne pour en
réparer une qui est cassée. Le dénominateur est `processed + errors_unprocessed`, un **nouveau
compteur** qui n'isole que la moitié hors-livre.

⚠ **Direction du changement, énoncée franchement** : un dénominateur plus grand ⇒ des taux plus bas
⇒ **moins d'arrêts**. Ce n'est pas la direction « sûre » par défaut : des runs qui s'arrêtaient vont
désormais se terminer, et un run qui se termine applique ses actions destructives — sauf pour le
sous-ensemble que borne le §8.2, où le verdict de santé les retient quand même. Ce qui rend le
changement acceptable n'est pas sa direction mais son **fondement** : un disjoncteur qui décide sur un
nombre supérieur à 100 % ne protège rien — il tire au hasard. Les garde-fous en aval restent en place
(verdict de santé, garde de couverture, plafonds du BO, et depuis le 20/08 le filtre des orphelines
actives).

**Hors périmètre, explicitement :**
- **Le seuil de 15 %** — ne pas y toucher avant la mesure du §4.
- **Le plancher de matérialité** — écarté au §3, il ne répare rien.
- **Le mode MICRO** (`maxAbsErrors` / `maxAbsRedirects` / `maxAbsNew`) : **code mort**, `isMicroMode`
  n'est jamais mis à vrai (`main.ts:984` commenté). Ne pas le réveiller au passage — réveiller du code
  inerte change le comportement, ce n'est pas une réparation.
- **Le verrou côté BO.** Réparer le disjoncteur tarit le flux ; il ne libère **aucun** des 121
  domaines déjà verrouillés. C'est un lot BO distinct, et il ne doit pas partir avant que le flux ne
  soit tari, sinon on paie deux fois.
- **Le rejeu d'un `_callback_payload.json` périmé**, second chemin par lequel un webhook peut porter
  `circuitBreaker` sans qu'un disjoncteur ait déclenché ce run-là. Non mesuré ; discriminant :
  comparer `details_json.date_start` à la `date_start` du run.

---

## 6. Vérification

Ce service a un **vrai lanceur de tests**, contrairement au BO : `npm test`
(`node --import tsx --test src/**/*.test.ts`). C'est la première fois de la semaine qu'un correctif de
ce chantier est prouvable avant déploiement — en profiter.

- Le calcul du taux doit devenir une **fonction pure** testable, sur le modèle de
  `externalRedirectBreaker.ts` (`shouldTripExternalRedirectBreaker(external, processed, cfg)`), qui est
  déjà isolée et testée. Le disjoncteur du taux d'erreurs est aujourd'hui **en ligne** dans le
  handler : c'est pourquoi il n'a aucun test.
- Cas à épingler : un dénominateur incluant les bloqués **ne peut plus** produire un taux > 1 ;
  les 12 taux mesurés > 100 % deviennent des cas de test dérivés de la production.
- ⚠ **`npm install` échoue sur ce dépôt** (`better-sqlite3` / VS Build Tools) ⇒ `--ignore-scripts`,
  et cela mord à **chaque worktree neuf**.
- ⚠ **Relever la base de la suite avant de commencer**, et non après : un compte attendu qui n'est pas
  dérivé d'une exécution est faux.

⚠ **Le déploiement ne part pas du poste de développement** : ce service tourne sur une VM distante,
absente de la machine. Contrairement aux lots BO de cette semaine, il n'y a pas de paquet SFTP à
construire — la livraison passe par la CI/CD du dépôt.

---

## 7. Trou de documentation constaté

Le `CLAUDE.md` du service — **1013 lignes** — ne mentionne **ni** « circuit breaker », **ni**
`maxErrorRate`, **ni** `minSample` : zéro occurrence. Le mécanisme qui a arrêté 69 runs d'un lot et
verrouillé 121 domaines n'est documenté nulle part dans les instructions du service, alors que son
voisin, le disjoncteur de redirection externe, a sa spec citée dans le tableau des codes de sortie.
⇒ Le lot d'implémentation ajoute cette section, dans le même commit que le correctif.

---

## 8. Ce que ce lot ne répare pas, et qu'il faut savoir avant de le lire comme un succès

### 8.1 Le MÊME défaut vit dans le verdict de santé — hors périmètre, à dessein

`updateHealthVerdict.ts:69` calcule `errorRate: stats.processed > 0 ? stats.errors / stats.processed : 0`
— **le même dénominateur défectueux**, sur le même couple de compteurs. Ce taux part dans
`_update_report.json`, que `script_process_update_crawling.php` lit par clé, et il décide du statut
`CRITICAL` qui gouverne les plafonds de suppression du BO.

**Il n'est délibérément pas corrigé ici**, pour trois raisons :

1. Le corriger **desserrerait** la détection de `CRITICAL` — moins de verdicts critiques, donc plus
   d'actions destructives appliquées. C'est une décision produit, pas un calibrage.
2. Le lot du 2026-08-17 a rendu ce module *prouvablement non régressif* avec 16 tests, dont un
   (`updateHealthRates matches the pre-change definitions`) **épingle explicitement la formule
   actuelle**. La changer, c'est changer un contrat épinglé exprès.
3. Le disjoncteur, lui, ne décide de rien d'utile : un run arrêté sur 722 % n'est pas protégé, il
   est tiré au sort. Les deux défauts sont arithmétiquement identiques et leurs **enjeux sont
   opposés**.

### 8.2 Conséquence : ce lot tarit le VERROU, pas le blocage des suppressions

Un run marginal qui ne s'arrête plus va **se terminer**. Il n'écrit alors plus de ligne `FAILED`,
donc plus de verrou permanent via `est_domaine_deja_en_cours()` — **c'est le gain, et c'est le
préjudice rapporté**. Mais son rapport portera toujours le taux calculé à l'ancienne
(§8.1) : si ce taux dépasse 15 %, le verdict reste `CRITICAL` et le BO retient les actions
destructives. ⇒ **Le domaine cesse d'être verrouillé ; ses suppressions ne s'appliquent pas pour
autant.** Annoncer « les 23 runs marginaux sont récupérés » serait faux.

**Mesuré côté BO, avec témoin positif contre un grep menteur** : `BO/script/chatgpt/script_process_update_crawling.php:713`
retient les actions destructives par une **liste blanche**, pas par un test par verdict :

```php
if (!in_array($health_update, ["HEALTHY", "WARNING"], true)) {
    $appliquer_actions_destructives = false;
    $raison_blocage_destructif = "health={$health_update} (" . ($sante_update["message"] ?? "") . ")";
```

`CRITICAL` n'apparaît **nulle part** dans ce fichier (0 occurrence) ; témoin positif `HEALTHY` = 5,
la recherche fonctionne donc. Tout verdict hors des deux valeurs admises — `CRITICAL` compris, ainsi
qu'une clé absente ou vide — prend la branche négative : **`CRITICAL` retient les actions destructives
par la même ligne que `PENDING_SAMPLE`**.

⚠ **Ce que cette mesure ne couvre pas** : `$appliquer_reconciliation` (`:804`) n'est **pas** gouverné
par le verdict de santé — seulement par un ratio de couverture `processed / previous_total`. Cette
famille d'archivage/réconciliation est indépendante de toute cette question : §8.2 ne doit pas se
lire comme « tout est retenu ».
