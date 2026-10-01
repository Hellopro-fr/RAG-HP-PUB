# Correctif `accounted` — l'identité de file, pas la provenance — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faire qu'une URL du dataset précédent produise **une** requête et **un** crédit `accounted`, au lieu de deux requêtes dont la seconde est rejetée sans compter.

**Architecture:** Deux modifications indépendantes et complémentaires. ① `main.ts` épingle le `uniqueKey` de l'amorce Phase 2, ce qui fusionne la copie découverte et la copie dataset en une seule requête. ② `UpdateChecker` cesse de croire `userData.source` — qu'une course de 65 ms lui fait perdre — et interroge le consolidateur, avec un repli sur le `/` final. ① supprime le gaspillage de crawl, ② corrige le compteur quelle que soit l'issue de la course.

**Tech Stack:** TypeScript, Node.js, Crawlee (`@crawlee/core`), Redis, `node:test` via `tsx`.

**User decisions (already made):**
- « Les deux : compteur juste ET crawl non dupliqué » — traiter la cause, pas les deux symptômes séparément.
- « Épingler Phase 2 sur l'URL brute, comme les trois autres amorces » — et **non** normaliser partout.
- « `UpdateChecker` cesse de croire `source` et interroge le consolidateur » — plutôt que filtrer à l'enfilage ou ré-étiqueter après coup.
- « Livrer nu, et observer la file Garde santé » — **pas** de drapeau d'environnement.
- Spec approuvée : `docs/superpowers/specs/2026-08-28-accounted-dataset-identity-design.md` (commits `74624471`, `80adcfff`).

**Hors périmètre, décidé :** le verdict de santé lui-même (`updateHealthVerdict.ts`), le traitement des migrations d'URL, et `__unjudged_urls.json`.

⚠ **Les outils de tâches natifs sont indisponibles dans cette session.** Le fichier `.tasks.json` co-localisé est le seul suivi.

---

## Structure des fichiers

| Fichier | Responsabilité | Action |
|---|---|---|
| `apps-microservices/crawler-service/crawler/src/main.ts` | amorçage des files, Phase 1 / Phase 2 | modifier (1 ligne, `:1606-1609`) |
| `apps-microservices/crawler-service/crawler/src/class/UpdateChecker.ts` | moteur de décision par page en mode update | modifier (`:166` + 1 helper privé) |
| `apps-microservices/crawler-service/crawler/src/tests/uniqueKeyPinning.test.ts` | épingle la prémisse du correctif ① | **créer** |
| `apps-microservices/crawler-service/crawler/src/tests/UpdateChecker.datasetIdentity.test.ts` | les quatre cas du correctif ② | **créer** |

⚠ **Aucun fichier de test existant n'est modifié.** C'est la raison pour laquelle le repli vit dans un helper privé à `UpdateChecker` et non sur `UrlConsolidator` : cinq suites simulent le consolidateur par un objet littéral ne portant que `isInDataset`, et élargir son API les casserait toutes en `not a function`.

---

### Task 0 : Épingler l'identité de l'amorce Phase 2

**Goal :** Une URL du dataset et sa copie découverte partagent désormais le même `uniqueKey`, donc une seule requête Crawlee.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts:1606-1609`
- Create: `apps-microservices/crawler-service/crawler/src/tests/uniqueKeyPinning.test.ts`

**Acceptance Criteria:**
- [ ] `main.ts` passe `uniqueKey: seedUrl` à l'`addRequest` de Phase 2.
- [ ] La valeur épinglée est `seedUrl` (après `stripActionAnchor` et `processUrl`), **jamais** `url`.
- [ ] Un test échoue si Crawlee cesse de normaliser le `/` final — c'est-à-dire si la prémisse du correctif disparaît.
- [ ] Les 43 suites existantes restent vertes.

**Verify:** `cd apps-microservices/crawler-service/crawler && npm test` → toutes les suites passent, dont `uniqueKeyPinning.test.ts`.

**Steps:**

- [ ] **Step 1 : Écrire le test qui épingle la prémisse**

Créer `src/tests/uniqueKeyPinning.test.ts` :

```ts
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Request } from '@crawlee/core';

// POURQUOI ce test existe : le correctif de main.ts:1606 repose entièrement sur le fait
// que le uniqueKey PAR DÉFAUT de Crawlee diffère de l'URL brute (il retire le / final),
// alors que routes.ts:1277 épingle les liens découverts sur l'URL brute. Si une montée de
// version de Crawlee changeait cette normalisation, la prémisse tomberait — et ce test le
// dirait, au lieu de laisser le correctif devenir un no-op silencieux.
test('Crawlee default uniqueKey drops the trailing slash — the premise of the Phase-2 pin', () => {
    const url = 'https://www.example.fr/services/';
    assert.notEqual(
        new Request({ url }).uniqueKey,
        url,
        'si cette assertion casse, Crawlee ne normalise plus : relire main.ts:1606',
    );
    assert.equal(new Request({ url }).uniqueKey, 'https://www.example.fr/services');
});

test('pinning uniqueKey reproduces the raw URL, matching routes.ts:1277', () => {
    const url = 'https://www.example.fr/services/';
    assert.equal(new Request({ url, uniqueKey: url }).uniqueKey, url);
});

test('a URL with no trailing slash is unaffected either way', () => {
    const url = 'https://www.example.fr/services';
    assert.equal(new Request({ url }).uniqueKey, url);
    assert.equal(new Request({ url, uniqueKey: url }).uniqueKey, url);
});
```

- [ ] **Step 2 : Lancer le test, constater qu'il PASSE déjà**

```bash
cd apps-microservices/crawler-service/crawler
npx tsx --test src/tests/uniqueKeyPinning.test.ts
```

Attendu : **3 pass, 0 fail**. ⚠ Ce test ne peut pas échouer avant le correctif — il décrit le comportement de Crawlee, pas le nôtre. C'est un **témoin de prémisse**, pas un test TDD. Il est écrit d'abord pour que la raison du correctif soit lisible dans la suite, et pour qu'une montée de version qui l'invalide se signale.

- [ ] **Step 3 : Appliquer le correctif**

Dans `main.ts`, remplacer exactement :

```ts
                await requestQueue.addRequest({
                    url: seedUrl,
                    userData: { source: source }
                });
```

par :

```ts
                // Épinglage de l'identité de file, comme Phase 1 (:952) et l'amorce standard
                // (:1033). Sans lui, Crawlee calcule un uniqueKey NORMALISÉ (il retire le /
                // final) alors que routes.ts:1277 épingle les liens découverts sur l'URL BRUTE :
                // la même page devient alors deux requêtes, et la copie dataset — celle qui
                // porte source='dataset' — arrive seconde et sort en already_pushed sans
                // créditer 'accounted'. Mesuré le 2026-08-27 sur atox.fr : 19 amorces sur 19
                // dupliquées, contre 0 sur 1 pour la page d'accueil, qui épingle déjà.
                // seedUrl et non url : c'est la chaîne réellement enfilée, après
                // stripActionAnchor et le re-nettoyage processUrl de la purge de file.
                await requestQueue.addRequest({
                    url: seedUrl,
                    uniqueKey: seedUrl,
                    userData: { source: source }
                });
```

- [ ] **Step 4 : Vérifier la non-régression**

```bash
cd apps-microservices/crawler-service/crawler
npm test
```

Attendu : toutes les suites passent. Noter le compte de tests avant/après — il doit augmenter de 3 exactement.

- [ ] **Step 5 : Commiter**

```bash
git add apps-microservices/crawler-service/crawler/src/main.ts \
        apps-microservices/crawler-service/crawler/src/tests/uniqueKeyPinning.test.ts
git commit -F - <<'EOF'
fix(crawler): the Phase-2 dataset seed names its own queue identity

It was the only addRequest in the repo letting Crawlee compute the uniqueKey, and
Crawlee drops the trailing slash. Discovered links are pinned to the raw URL at
routes.ts:1277, so the same page became two requests — the dataset copy arriving
second and exiting on already_pushed without crediting accounted.

Measured on atox.fr: 19 of 19 unpinned seeds duplicated, against 0 of 1 for the
homepage, which already pins. The new test pins the premise rather than our code:
it fails if a Crawlee upgrade stops normalising, which would silently turn this
fix into a no-op.

FR — fix(crawler) : l'amorce dataset de Phase 2 nomme sa propre identité de file

C'était le seul addRequest du dépôt à laisser Crawlee calculer le uniqueKey, et
Crawlee retire le / final. Les liens découverts sont épinglés sur l'URL brute à
routes.ts:1277, donc la même page devenait deux requêtes — la copie dataset
arrivant seconde et sortant en already_pushed sans créditer accounted.

Mesuré sur atox.fr : 19 amorces non épinglées sur 19 dupliquées, contre 0 sur 1
pour la page d'accueil, qui épingle déjà. Le nouveau test épingle la prémisse
plutôt que notre code : il casse si une montée de Crawlee cesse de normaliser, ce
qui rendrait ce correctif silencieusement inerte.
EOF
```

---

### Task 1 : La provenance dataset cesse de dépendre d'une course

**Goal :** `UpdateChecker` reconnaît une URL du dataset précédent même quand la requête survivante porte `source: 'discovered'`, et crédite `accounted` une fois exactement.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/class/UpdateChecker.ts:166`
- Create: `apps-microservices/crawler-service/crawler/src/tests/UpdateChecker.datasetIdentity.test.ts`

**Acceptance Criteria:**
- [ ] Une URL connue du dataset arrivant en `source: 'discovered'` rend `action: 'confirmed'` et incrémente `accounted` **exactement une fois**.
- [ ] Le repli sur le `/` final fonctionne **dans les deux sens** : `/x` stocké / `/x/` présenté, et l'inverse.
- [ ] Une URL réellement inconnue rend toujours `action: 'new_url'` et n'incrémente **jamais** `accounted`.
- [ ] Quand `source === 'dataset'`, le consolidateur n'est **pas** interrogé — court-circuit, zéro appel Redis ajouté sur le chemin qui sait déjà.
- [ ] Les cinq suites `UpdateChecker.*` existantes restent vertes **sans être modifiées**.

**Verify:** `cd apps-microservices/crawler-service/crawler && npm test` → toutes vertes, dont les 5 suites `UpdateChecker.*` intactes.

**Steps:**

- [ ] **Step 1 : Écrire les tests qui échouent**

Créer `src/tests/UpdateChecker.datasetIdentity.test.ts` :

```ts
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { UpdateChecker } from '../class/UpdateChecker.js';

// Consolidateur simulé : le dataset est un Set explicite, et chaque appel est compté.
// Le compteur sert la 4e assertion — prouver que source='dataset' court-circuite.
function makeConsolidator(urls: string[]) {
    const set = new Set(urls);
    const calls: string[] = [];
    return {
        _calls: calls,
        async isInDataset(url: string) { calls.push(url); return set.has(url); },
        async cleanup() {},
    };
}
function makeStats() {
    const calls: string[] = [];
    return { async increment(c: string) { calls.push(c); }, _calls: calls };
}
function makeWriter() {
    const calls: Array<[string, unknown]> = [];
    return { async writeLine(f: string, d: unknown) { calls.push([f, d]); }, _calls: calls };
}
// PushedSet absent : checkUrl ne réclame rien, on isole la seule décision de provenance.
function makeChecker(consolidator: unknown, stats: unknown, writer: unknown) {
    return new UpdateChecker(consolidator as any, stats as any, writer as any, undefined as any);
}

// TEST 1 — le cœur du correctif. La copie DÉCOUVERTE gagne la course de 65 ms
// (enqueueLinks à 16:00:51.018 contre [PHASE 2] à 16:00:51.083, mesuré sur atox.fr),
// donc la requête survivante porte source='discovered'. Elle doit malgré tout compter.
test('a dataset URL arriving as discovered still credits accounted exactly once', async () => {
    const url = 'https://www.example.fr/services/';
    const consolidator = makeConsolidator([url]);
    const stats = makeStats();
    const checker = makeChecker(consolidator, stats, makeWriter());

    const r = await checker.checkUrl(url, url, 'discovered', 200, true);

    assert.equal(r.action, 'confirmed');
    assert.deepEqual(stats._calls, ['accounted']);
});

// TEST 2 — repli sur le / final, DANS LES DEUX SENS. L'URL stockée vient du dataset
// précédent, l'URL présentée vient du lien tel qu'écrit dans la page : rien ne garantit
// la même orthographe.
test('the trailing-slash fold works both ways', async () => {
    const stored = 'https://www.example.fr/produits';
    const c1 = makeConsolidator([stored]);
    const s1 = makeStats();
    const r1 = await makeChecker(c1, s1, makeWriter())
        .checkUrl(stored + '/', stored + '/', 'discovered', 200, true);
    assert.equal(r1.action, 'confirmed', 'stocké sans /, présenté avec /');
    assert.deepEqual(s1._calls, ['accounted']);

    const c2 = makeConsolidator([stored + '/']);
    const s2 = makeStats();
    const r2 = await makeChecker(c2, s2, makeWriter())
        .checkUrl(stored, stored, 'discovered', 200, true);
    assert.equal(r2.action, 'confirmed', 'stocké avec /, présenté sans /');
    assert.deepEqual(s2._calls, ['accounted']);
});

// TEST 3 — la garde contre un correctif trop gourmand. Une URL réellement neuve doit
// rester neuve : si celle-ci passait 'confirmed', le correctif aurait supprimé la
// détection des nouvelles pages au lieu de réparer un compteur.
test('a genuinely unknown URL stays new and never credits accounted', async () => {
    const consolidator = makeConsolidator(['https://www.example.fr/connue/']);
    const stats = makeStats();
    const writer = makeWriter();
    const r = await makeChecker(consolidator, stats, writer)
        .checkUrl('https://www.example.fr/toute-neuve/', 'https://www.example.fr/toute-neuve/',
                  'discovered', 200, true);

    assert.equal(r.action, 'new_url');
    assert.deepEqual(stats._calls, ['new_urls']);
    assert.ok(!stats._calls.includes('accounted'));
});

// TEST 4 — court-circuit. Quand la provenance est déjà connue, on n'ajoute aucun
// aller-retour Redis : le || de JavaScript n'évalue pas sa droite si la gauche est vraie,
// et ce test empêche qu'un refactor le perde.
test('source=dataset short-circuits: the consolidator is never consulted', async () => {
    const url = 'https://www.example.fr/services/';
    const consolidator = makeConsolidator([url]);
    const stats = makeStats();
    const r = await makeChecker(consolidator, stats, makeWriter())
        .checkUrl(url, url, 'dataset', 200, true);

    assert.equal(r.action, 'confirmed');
    assert.deepEqual(stats._calls, ['accounted']);
    assert.deepEqual(consolidator._calls, [], 'aucun appel Redis ajouté sur ce chemin');
});
```

- [ ] **Step 2 : Lancer les tests, constater l'échec**

```bash
cd apps-microservices/crawler-service/crawler
npx tsx --test src/tests/UpdateChecker.datasetIdentity.test.ts
```

Attendu : **TEST 1, 2 et 4 échouent**, TEST 3 passe. TEST 1 et 2 échouent parce que `isFromDataset` vaut `false` et que la branche non-dataset rend `new_url` au lieu de `confirmed`. TEST 4 échoue sur `consolidator._calls` — non pas parce que le court-circuit manque, mais parce que `checkUrl` n'appelle pas encore le consolidateur du tout ; il passera pour la bonne raison après le correctif.

- [ ] **Step 3 : Appliquer le correctif**

Dans `UpdateChecker.ts`, remplacer exactement la ligne 166 :

```ts
        const isFromDataset = source === 'dataset';
```

par :

```ts
        // La provenance ne peut PAS reposer sur userData.source : la copie DÉCOUVERTE d'une
        // URL du dataset est enfilée ~65 ms avant l'amorce Phase 2 (mesuré sur atox.fr :
        // enqueueLinks à 16:00:51.018, [PHASE 2] à 16:00:51.083), et c'est structurel — Phase 2
        // attend que la page d'accueil soit traitée pour connaître les chemins régionaux. La
        // requête survivante porte donc source='discovered'. On demande au consolidateur, qui
        // sait. Le || court-circuite : aucun aller-retour Redis ajouté quand source suffit.
        const isFromDataset = source === 'dataset' || await this.estConnueDuDataset(originalUrl);
```

Puis ajouter le helper **privé**, juste avant `checkUrl` :

```ts
    /**
     * Cette URL fait-elle partie du dataset précédent, au / final près ?
     *
     * Le repli est nécessaire parce que l'URL stockée vient du dataset précédent tandis que
     * l'URL présentée vient du lien tel qu'écrit dans la page : rien ne garantit la même
     * orthographe. C'est déjà la convention de tout l'aval — `isRedirect` compare en
     * `rightTrimSlash` quelques lignes plus bas, et la soustraction d'orphelins du BO fait
     * `trim($url, "/")` sur ses deux côtés.
     *
     * ⚠ Le repli vit ICI, en lecture, et JAMAIS dans le set `update_dataset:<crawlId>` : ce set
     * est aussi SCANNÉ (UrlConsolidator.ts:214) pour produire la liste d'amorçage, et il arbitre
     * le dédoublonnage des phases 2 et 3. Y stocker des URLs sans leur / final ferait amorcer
     * des URLs modifiées.
     *
     * ⚠ Le helper est privé plutôt qu'une méthode du consolidateur parce que cinq suites de
     * test simulent celui-ci par un objet littéral ne portant que `isInDataset` : élargir son
     * API les casserait toutes en « not a function », pour un seul appelant.
     *
     * ⚠ `isInDataset` échoue OUVERT (catch → false, UrlConsolidator.ts:107-109). Un incident
     * Redis fait donc sous-compter `accounted` — même sens qu'avant ce correctif, aucune
     * régression, mais ce n'est pas une garantie.
     */
    private async estConnueDuDataset(url: string): Promise<boolean> {
        if (await this.consolidator.isInDataset(url)) {
            return true;
        }
        const alt = url.endsWith('/') ? url.slice(0, -1) : url + '/';
        return this.consolidator.isInDataset(alt);
    }
```

- [ ] **Step 4 : Vérifier que les quatre tests passent**

```bash
cd apps-microservices/crawler-service/crawler
npx tsx --test src/tests/UpdateChecker.datasetIdentity.test.ts
```

Attendu : **4 pass, 0 fail**.

- [ ] **Step 5 : Vérifier que les cinq suites existantes sont intactes**

```bash
cd apps-microservices/crawler-service/crawler
npx tsx --test src/tests/UpdateChecker.checkedSet.separation.test.ts \
                src/tests/UpdateChecker.deleteVerdict.test.ts \
                src/tests/UpdateChecker.forbiddenParams.test.ts \
                src/tests/UpdateChecker.pushedSet.test.ts \
                src/tests/UpdateChecker.redirectRepeat.test.ts
git diff --name-only -- src/tests/
```

Attendu : toutes vertes, et `git diff --name-only` ne montre **que** le fichier créé — **aucune** des cinq suites modifiée. Si l'une a dû l'être, le helper n'est pas au bon endroit : relire la spec §4.

- [ ] **Step 6 : Suite complète**

```bash
cd apps-microservices/crawler-service/crawler
npm test
```

Attendu : toutes les suites passent, le compte augmente de 4 exactement par rapport à la fin de la Task 0.

- [ ] **Step 7 : Commiter**

```bash
git add apps-microservices/crawler-service/crawler/src/class/UpdateChecker.ts \
        apps-microservices/crawler-service/crawler/src/tests/UpdateChecker.datasetIdentity.test.ts
git commit -F - <<'EOF'
fix(crawler): dataset membership is asked, not inferred from a race it loses

userData.source cannot carry the provenance: the discovered copy of a dataset URL
is enqueued ~65 ms before the Phase-2 seed, and that ordering is structural since
Phase 2 waits for the homepage to reveal the regional paths. The surviving request
therefore says 'discovered', and accounted was never credited — 0 runs out of 60
counted their previous dataset in full.

UpdateChecker now asks the consolidator, with a trailing-slash fold that matches
what the rest of the pipeline already does. The fold lives in the read, never in
the set, which is also scanned to build the seed list. The helper is private to its
one caller so the five existing UpdateChecker suites stay untouched.

FR — fix(crawler) : l'appartenance au dataset se demande, elle ne se déduit pas d'une course perdue

userData.source ne peut pas porter la provenance : la copie découverte d'une URL du
dataset est enfilée ~65 ms avant l'amorce Phase 2, et cet ordre est structurel
puisque Phase 2 attend que la page d'accueil révèle les chemins régionaux. La
requête survivante dit donc « discovered », et accounted n'était jamais crédité —
0 run sur 60 comptait son dataset précédent en entier.

UpdateChecker interroge désormais le consolidateur, avec un repli sur le / final
conforme à ce que fait déjà tout l'aval. Le repli vit dans la lecture, jamais dans
le set, qui sert aussi à construire la liste d'amorçage. Le helper est privé à son
unique appelant, de sorte que les cinq suites UpdateChecker existantes restent
intactes.
EOF
```

---

## Vérification en production, après déploiement

Ce n'est pas une tâche du plan — rien ici ne se déploie depuis ce dépôt par MEP — mais la procédure doit exister avant le déploiement, sinon elle ne sera pas faite.

**Ligne de base, déjà mesurée le 2026-08-27** : sur 60 runs `FINISHED` depuis le 24/08,
`accounted == previous_total` sur **0**, et 9 runs à `accounted = 0`.

**Après déploiement**, rejouer la même sonde sur des runs **postérieurs** au build :

1. Base BO : `SELECT id_history, TO_BASE64(storage_folder_name) FROM update_crawling_history WHERE status='FINISHED' AND date_start >= '<horodatage du build>'`. ⚠ `TO_BASE64` est indispensable — le masquage PII du MCP corrompt `storage_folder_name` et rend le `crawl_id` inadressable.
2. Pour chaque : `GET /admin/sidecar/<crawl_id>?name=_update_report.json`, en-tête `X-API-Key`.
3. Attendu : `accounted == previous_total` sur les runs sans erreur, et la distribution de couverture déplacée vers 1.

⚠ **Le déployé se lit par `GET /version`, jamais depuis une note.** Croiser avec `git rev-list --count <commit-image>..origin/features/poc`. Quatre fois durant la conception, un état lu quelques heures plus tôt était devenu faux.

**L'observable métier** est la file « Garde santé » du BO : elle montre run par run ce qui se débloque, avec son Total, et rien ne s'applique sans un clic. ⚠ Filtrer sur `blocage_par_plafond = 0` — la file collecte aussi les blocages par plafond, sans rapport avec la couverture.
