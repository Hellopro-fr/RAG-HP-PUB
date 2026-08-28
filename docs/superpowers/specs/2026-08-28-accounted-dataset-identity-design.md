# `accounted` — l'identité de file, pas la provenance

**Date** : 2026-08-28
**Service** : `apps-microservices/crawler-service` (crawler Node)
**État** : conception approuvée, plan à écrire

---

## 1. Le défaut, en une phrase

`main.ts:1606` est le seul `addRequest` du dépôt à ne pas épingler son `uniqueKey`. Crawlee
retire alors le `/` final, la copie *découverte* de la même page en garde un, et **la page
devient deux requêtes** — dont la seconde sort en `already_pushed` sans jamais créditer
`accounted`.

## 2. Comment il a été établi

Sonde du 2026-08-27, **60 runs `FINISHED`** depuis le 24/08, via
`GET /admin/sidecar/<crawl_id>?name=_update_report.json` (60/60 obtenus — les sidecars de
racine survivent au stash/archive).

| Couverture `accounted / previous_total` | runs |
|---|---|
| `accounted = 0` | 9 (15,0 %) |
| 0 < cov ≤ 0,2 | 7 |
| 0,2 < cov ≤ 0,5 | 6 |
| 0,5 < cov < 0,8 | 18 |
| cov ≥ 0,8 | 20 |

⚠⚠ **`accounted == previous_total` sur 0 run sur 60.** Le défaut est **universel**, pas
exceptionnel.

**Le cas d'école, `atox.fr` (crawl `2070-1501-1786361103`)** — 39 traitées, 20 amorcées
+ 19 découvertes, `errors = 0`, tout en HTTP 200 :

```
19 [UpdateChecker] ignored:  -> raison: already_pushed        (19/19)
20 [UpdateChecker] new_url:  -> raison: eligible_new_content   (20/20)
                                 ZÉRO confirmed, accounted = 0
```

`https://www.atox.fr/services/` figure dans **les deux listes** : la page a bien été traitée
deux fois. Et `eligible_new_content` n'apparaît **qu'une fois** dans tout `UpdateChecker.ts`
(ligne 304), dans le `else` « Non-dataset URL, 2xx » — c'est un témoin à sens unique de la
branche non-dataset.

**La cause, mesurée et non inférée** (`node -e` contre `@crawlee/core` installé localement) :

```
>> DEUX CLES | defaut=https://www.atox.fr/services  | epingle=https://www.atox.fr/services/
>> DEUX CLES | defaut=https://www.atox.fr           | epingle=https://www.atox.fr/
URLs produisant DEUX requetes : 4 / 4
```

**Expérience témoin interne au même run** : la page d'accueil, qui épingle son `uniqueKey`
(`main.ts:952`), a été traitée **une** fois ; les 19 amorces Phase 2, qui n'épinglent pas,
l'ont été **deux** fois. **19/19 contre 0/1.**

## 3. La chaîne complète

1. Phase 1 amorce l'accueil, `uniqueKey` épinglé, `userData: { source: 'seed' }`.
2. L'accueil est traité ; son `enqueueLinks` enfile les liens avec
   `userData = { source: 'discovered' }` et `request.uniqueKey = fragmentAwareUniqueKey(url)`
   = **l'URL brute** (`routes.ts:1272-1277`, venu du chantier Diez sur les fragments).
3. `[PHASE 2]` amorce ensuite les URLs du dataset **sans épingler** ⇒ clé normalisée, `/`
   final retiré ⇒ **clé différente ⇒ seconde requête**.
4. La copie découverte gagne la course — **structurellement**, Phase 2 attend que l'accueil
   soit traité pour connaître les chemins régionaux. Mesuré : `enqueueLinks` à
   `16:00:51.018`, `[PHASE 2] Finished seeding` à `16:00:51.083`, **65 ms d'écart**.
5. Elle arrive en `source: 'discovered'` ⇒ branche non-dataset ⇒ `new_url`, **et elle réclame
   l'URL dans `PushedSet`**.
6. La copie dataset arrive : `tryClaim` rend `false` ⇒ `ignored / already_pushed`, **sortie
   avant tout compteur** ⇒ `accounted` jamais incrémenté.

## 4. Ce qui change

### ① `crawler/src/main.ts:1606` — épingler l'identité de l'amorce Phase 2

```ts
await requestQueue.addRequest({
    url: seedUrl,
    uniqueKey: seedUrl,        // symétrique de :952 (Phase 1) et :1033 (amorce standard)
    userData: { source: source }
});
```

`seedUrl` et non `url` : c'est la chaîne réellement enfilée, après `stripActionAnchor` et le
re-nettoyage `processUrl` de la purge de file.

### ② `UpdateChecker` — la provenance cesse de reposer sur une course

```ts
const isFromDataset = source === 'dataset'
    || await this.consolidator.isInDatasetLoose(originalUrl);
```

et, dans `UrlConsolidator`, une lecture tolérante au `/` final :

```ts
async isInDatasetLoose(url: string): Promise<boolean> {
    if (await this.isInDataset(url)) return true;
    const alt = url.endsWith('/') ? url.slice(0, -1) : url + '/';
    return this.isInDataset(alt);
}
```

**`originalUrl` et non `loadedUrl`.** La question posée est « connaissions-nous cette URL ? »,
exactement ce que `source === 'dataset'` voulait dire. `isFromDataset` est calculé **avant** le
split en CASE 1/2/3 et gouverne les trois : le tester sur `loadedUrl` ferait entrer une
destination de redirection dans la branche dataset, ce que CASE 2 traite déjà séparément via
`destInDataset`.

⚠⚠ **Le repli vit dans la LECTURE, jamais dans le set.** `update_dataset:<crawlId>` n'est pas
qu'un test d'appartenance : il est **scanné** (`UrlConsolidator.ts:214`) pour produire la liste
d'amorçage, et il arbitre le dédoublonnage des phases 2 et 3 (`:167`, `:190`). Y stocker des
URLs sans leur `/` final ferait **amorcer des URLs modifiées**. Ne pas « simplifier » en
normalisant le set.

### Pourquoi les deux, et pas l'une ou l'autre

| | ① seule | ② seule | ① + ② |
|---|---|---|---|
| Page naviguée deux fois | ✅ | ❌ | ✅ |
| `accounted` juste | ❌ la copie découverte gagne encore la course de 65 ms | ✅ | ✅ |

① supprime le gaspillage — **49 % des navigations sur `atox.fr`** (19 requêtes sur 39).
② corrige le compteur quelle que soit l'issue de la course, **et corrige aussi la page
d'accueil**, que `main.ts:942` amorce en `source: 'seed'` et qui n'était donc jamais créditée :
`isInDatasetLoose` la reconnaît, elle fait partie des URLs du dataset précédent.

## 5. Coût et risques hérités

- **Coût** : 1 à 2 `SISMEMBER` par page, O(1) chacun, contre une médiane **mesurée** de 766 ms
  de détection par page (`k2mdistributions.fr`, `detect_ms` p50). Négligeable.
- ⚠ `isInDataset` **échoue OUVERT** (`catch → return false`, `UrlConsolidator.ts:107-109`). Un
  incident Redis sous-compterait `accounted` — **même sens qu'aujourd'hui**, donc pas de
  régression, mais le correctif en hérite et le commentaire doit le dire.
- ⚠ Aucune modification du set ⇒ l'amorçage, le dédoublonnage des phases 2/3 et le
  `destInDataset` de CASE 2 sont **inchangés**.

## 6. Tests

**Locaux** — `npm test` existe réellement ici (`node:test`). `UpdateChecker` porte déjà trois
suites au style `assert.deepEqual(stats._calls, [...])`
(`UpdateChecker.checkedSet.separation.test.ts`, `.deleteVerdict.test.ts`,
`.redirectRepeat.test.ts`). À ajouter :

- une URL du dataset arrivée avec `source: 'discovered'` ⇒ `accounted` incrémenté **exactement
  une fois** ;
- `/x` stocké, `/x/` présenté (et l'inverse) ⇒ reconnue ;
- une URL réellement inconnue ⇒ toujours `new_urls`, jamais `accounted` (la garde contre un
  correctif qui rendrait tout « dataset ») ;
- `isInDataset` en échec Redis ⇒ comportement inchangé, pas d'exception qui remonte.

**En production** — rejouer la sonde des 60 runs. Attendu : `accounted == previous_total` sur
les runs sains, contre **0 sur 60** aujourd'hui, et la distribution de couverture déplacée vers
1. L'observable métier est la file « Garde santé » du BO, qui montre run par run ce qui se
débloque, avec son Total.

## 7. Mise en service

**Nu, sans drapeau.** Le plafond de suppression de masse (`errors / previousTotal > 0,5` →
`SUSPECT`) et la garde santé du BO restent en place, inchangés, et **rien ne s'applique sans un
clic d'opérateur** dans la file.

⚠ Rendre `accounted` juste **arme** des suppressions aujourd'hui retenues : 9 runs sur 60 sont
en `PENDING_SAMPLE` à cause d'une couverture fausse. C'est l'effet recherché — ces runs sont
retenus pour une raison qui n'existe pas — mais il doit être observé, pas subi.

## 8. Hors périmètre, délibérément

- **Le verdict de santé lui-même.** `coverage` n'apparaît qu'à un seul endroit
  (`updateHealthVerdict.ts:91`), la conjonction `processed < minSample && coverage < minCoverage`,
  et **ne bloque jamais seule**. Faut-il lui redonner un pouvoir de blocage une fois vraie ?
  Cette décision se prend sur des chiffres qui n'existeront **qu'après** ce correctif.
- **Le traitement des migrations d'URL.** Sujet distinct, sorti du cas
  `k2mdistributions.fr` : les sources de redirection ne sont pas dans l'ensemble « recrawlé »
  protégé, donc elles sont orphelines par construction. Sa propre spec.
- **`__unjudged_urls.json`.** Inatteignable par HTTP (hors `_SIDECAR_WHITELIST`, mauvais
  emplacement, et le sous-arbre `storage/` est nettoyé au stash). Il n'est **plus nécessaire** :
  la cause est établie par le journal.

## 9. État du code au moment de l'écriture — mesuré le 2026-08-28

- Branche `features/poc`, arbre propre, **0 commit local non poussé**.
- L'image en production est **`2900bc29-dirty`**, construite le **2026-08-28 09:28:49 UTC**,
  démarrée 09:31:22. `2900bc29` est ancêtre de `origin/features/poc`, et **0 commit d'`origin`
  lui manque** ⇒ **ce qui tourne est la tête de la branche.**
- ⇒ Ce correctif partira **seul**, sur une base déployée : aucun passager en attente, ni le
  disjoncteur de taux d'erreurs ni le sidecar `collapsed_seen_base`, tous deux déjà en
  production.

⚠⚠ **Ces trois lignes se re-mesurent avant tout déploiement, elles ne se recopient pas.** Quatre
fois dans la session qui a produit cette spec, un état de poussée ou de déploiement lu quelques
heures plus tôt était devenu faux — dont une où l'image annoncée (`adea26ae`, build du 24/08)
avait été remplacée entre la mesure et la rédaction. L'autorité est `GET /version` croisé avec
`git rev-list --count <commit-image>..origin/features/poc`, jamais une note.
