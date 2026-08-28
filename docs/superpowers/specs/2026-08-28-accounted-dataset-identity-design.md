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
const match = source === 'dataset' ? 'exact' : await this.datasetMatch(originalUrl);
const isFromDataset = match !== 'none';
```

avec, **privé à `UpdateChecker`**, un repli tolérant au `/` final :

```ts
private async datasetMatch(url: string): Promise<'exact' | 'folded' | 'none'> {
    if (await this.consolidator.isInDataset(url)) return 'exact';
    const alt = url.endsWith('/') ? url.slice(0, -1) : url + '/';
    if (await this.consolidator.isInDataset(alt)) return 'folded';
    return 'none';
}
```

⚠ **Le helper est privé à `UpdateChecker`, pas une nouvelle méthode publique du
consolidateur** — révision du 2026-08-28, à la planification. **Cinq suites de test** simulent
le consolidateur par un objet littéral ne portant que `isInDataset`
(`UpdateChecker.{checkedSet.separation, deleteVerdict, forbiddenParams, pushedSet,
redirectRepeat}.test.ts`) : élargir l'API du consolidateur les casserait toutes les cinq en
`not a function`, pour un seul appelant. Et CASE 2 n'a pas besoin du repli — `isRedirect`
compare déjà en `rightTrimSlash`, donc `/x` → `/x/` n'atteint jamais cette branche.

**`originalUrl` et non `loadedUrl`.** La question posée est « connaissions-nous cette URL ? »,
exactement ce que `source === 'dataset'` voulait dire. `isFromDataset` est calculé **avant** le
split en CASE 1/2/3 et gouverne CASE 2 et CASE 3 — CASE 1, depuis le correctif de la vague
précédente (§③ ci-dessous), est gouverné par `match === 'exact'`, pas par `isFromDataset` : le
tester sur `loadedUrl` ferait entrer une destination de redirection dans la branche dataset, ce
que CASE 2 traite déjà séparément via `destInDataset`.

⚠⚠ **Le repli vit dans la LECTURE, jamais dans le set.** `update_dataset:<crawlId>` n'est pas
qu'un test d'appartenance : il est **scanné** (`UrlConsolidator.ts:214`) pour produire la liste
d'amorçage, et il arbitre le dédoublonnage des phases 2 et 3 (`:167`, `:190`). Y stocker des
URLs sans leur `/` final ferait **amorcer des URLs modifiées**. Ne pas « simplifier » en
normalisant le set.

### ③ CASE 1 — la garde d'exactitude (revue finale de branche)

⚠⚠ **CASE 1 ne peut pas se contenter d'`isFromDataset`.** Un appariement REPLIÉ ne prouve rien
sur le statut HTTP de l'AUTRE orthographe : le dataset contient `/a` ; une page lie `/a/`, qui
n'a **jamais** été au dataset ; un serveur à routage strict rend 404 sur `/a/` alors que `/a`
est vivant. Le booléen d'origine aurait laissé passer un `deleted` pour `/a/` **et** un
`confirmed` pour `/a` dans le même run — deux instructions contradictoires pour la même page
envoyées au BO, qui replie lui aussi le `/`.

Le helper devient donc `datasetMatch(): 'exact' | 'folded' | 'none'`, et CASE 1 (le bloc
404/410 **et** le comptage `errors` / `errors_unprocessed` qui le précède) ne s'engage que sur
`'exact'` : un appariement `'folded'` retombe entièrement sur la branche non-dataset (`ignored /
non_dataset_error`), à l'identique du comportement d'avant ce lot. Gater seulement le bloc
404/410 en laissant `errors` / `errors_unprocessed` s'appliquer à une variante repliée a été
écarté : cette population alimenterait le numérateur d'`errorRate`, exactement ce que §7 met en
garde de ne pas aggraver. CASE 2 et CASE 3 gardent le repli intégral — un 200 ou une redirection
sur la variante repliée enseigne bien quelque chose sur la page, à la différence d'une erreur.

Cette asymétrie prolonge un principe déjà en place, pas une nouvelle prudence : CASE 1 avait été
délibérément réduit à 404/410 après l'incident **1320-402** (63 blocages anti-bot 403 devenus 59
fausses suppressions de fiches BO-side). Ce correctif applique le même principe à l'identité de
l'URL plutôt qu'au statut HTTP.

### ④ CASE 2/3 — le crédit `accounted` se réserve à l'exact (2e moitié du correctif)

⚠⚠ **Miroir exact du défaut fermé en ③.** `PushedSet.tryClaim` est un `sAdd` de chaîne brute
(`PushedSet.ts:58-62`, aucun repli), donc une orthographe exacte et sa variante repliée
réclament chacune leur propre entrée et atteignent toutes les deux CASE 2 ou CASE 3 — chacune
incrémentait `accounted`, doublant le crédit d'une seule entrée du dataset précédent et pouvant
porter `coverage` au-dessus de 1.

`accounted` compte des **entrées du dataset précédent re-observées**. Seule l'orthographe
**exacte** en est une ; la repliée n'en est pas une, et l'exacte est de toute façon seedée et
observée pour son propre compte (①). Les quatre incréments restants — les deux de CASE 2
(`redirect_to_existing` et la redirection hors dataset) et les deux de CASE 3 (`confirmed` et
`deleted` sur `not_eligible`) — sont donc gatés sur `match === 'exact'`, à l'identique du
gate posé en ③ pour CASE 1.

Ce que le gate NE change PAS — les branches, seulement le crédit :
- CASE 2 écrit toujours son événement `REDIRECTED` (mapping ancien→nouveau nécessaire au BO,
  indépendant du comptage) et incrémente toujours `redirects` sur la redirection hors dataset ;
- CASE 3 éligible reste `confirmed` sur une variante repliée — sans JSONL et désormais sans
  crédit, c'est un no-op, ce qui est le comportement recherché ;
- CASE 3 non éligible écrit toujours son événement `deleted` : l'inéligibilité juge le
  **contenu**, valable pour les deux orthographes d'une même page — contrairement au statut
  HTTP de CASE 1, qui ne l'est pas.

### Pourquoi les deux, et pas l'une ou l'autre

| | ① seule | ② seule | ① + ② |
|---|---|---|---|
| Page naviguée deux fois | ✅ | ❌ | ✅ |
| `accounted` juste | ❌ la copie découverte gagne encore la course de 65 ms | ✅ | ✅ |

① supprime le gaspillage — **49 % des navigations sur `atox.fr`** (19 requêtes sur 39).
② corrige le compteur quelle que soit l'issue de la course, **et corrige aussi la page
d'accueil**, que `main.ts:942` amorce en `source: 'seed'` et qui n'était donc jamais créditée :
`datasetMatch` la reconnaît, elle fait partie des URLs du dataset précédent.

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
- `source === 'dataset'` ⇒ le consolidateur n'est **pas** interrogé, prouvant qu'aucun
  aller-retour Redis n'est ajouté sur le chemin qui connaît déjà la provenance.

⚠ **Un cinquième cas a été écarté à la planification : « `isInDataset` en échec Redis ».** Il
n'est pas testable honnêtement — `isInDataset` **attrape en interne** (`catch → return false`,
`UrlConsolidator.ts:107-109`), donc l'exception qu'il décrirait ne peut être produite qu'en
simulant un comportement que la vraie classe n'a pas. Le risque réel est ailleurs et reste
documenté en §5 : la dégradation est **silencieuse**, pas bruyante.

**En production** — rejouer la sonde des 60 runs. Attendu : `accounted == previous_total` sur
les runs sains, contre **0 sur 60** aujourd'hui, et la distribution de couverture déplacée vers
1. L'observable métier est la file « Garde santé » du BO, qui montre run par run ce qui se
débloque, avec son Total.

⚠⚠ **La sonde post-déploiement doit aussi compter les verdicts `CRITICAL` et `SUSPECT`**, pas
seulement la distribution de couverture — voir §7 : `errorRate` peut basculer défavorablement
sur des runs jusqu'ici `HEALTHY`. Décision du partenaire humain : livraison **nue, sans
drapeau** ; c'est donc cette sonde, et elle seule, qui doit voir la bascule si elle se produit.

## 7. Mise en service

**Nu, sans drapeau.** Le plafond de suppression de masse (`errors / previousTotal > 0,5` →
`SUSPECT`) et la garde santé du BO restent en place, inchangés, et **rien ne s'applique sans un
clic d'opérateur** dans la file.

⚠ Rendre `accounted` juste **arme** des suppressions aujourd'hui retenues : 9 runs sur 60 sont
en `PENDING_SAMPLE` à cause d'une couverture fausse. C'est l'effet recherché — ces runs sont
retenus pour une raison qui n'existe pas — mais il doit être observé, pas subi.

⚠⚠ **Le risque n'est pas à sens unique — la revue finale de branche l'a trouvé.** Ce lot bouge
les entrées du verdict de santé DÉFAVORABLEMENT des deux côtés à la fois :

- ② monte le **numérateur** d'`errorRate = errors / processed` : les erreurs d'une URL dataset
  arrivée en `discovered` étaient AVALÉES avant ce lot (branche non-dataset de CASE 1, aucun
  `errors` incrémenté) ; elles comptent désormais ;
- ① baisse le **dénominateur** : `processed` passe de 39 à ~20 sur `atox.fr` (les requêtes
  dupliquées disparaissent) ;
- ⇒ `errorRate = errors / processed` peut **environ doubler par arithmétique seule**, et
  `HEALTHY → CRITICAL` devient possible sur un domaine qui n'a fait que quelques 404 ordinaires.
  Les seuils `maxErrorRate` / `maxAbsErrors` ont été calibrés contre un nombre faux **des deux
  côtés** — pas seulement optimiste comme le paragraphe précédent le donne à penser.
  `SUSPECT` (`errors / previousTotal > 0,5`) n'est concerné que par la moitié de cet effet : son
  dénominateur `previousTotal` est la taille du dataset précédent, que ce lot ne touche pas —
  seule la hausse du numérateur `errors` peut l'y faire basculer, sans le doublement
  arithmétique du ratio lui-même.

Ce n'est **pas un bug** : les nouveaux chiffres sont les bons, `processed` et `errors` mesurent
enfin ce qu'ils prétendent mesurer. C'est un risque de **mise en service** — un domaine jusqu'ici
`HEALTHY` peut basculer le jour du déploiement sans qu'aucune régression n'ait eu lieu. Voir §6
« En production » pour la sonde qui doit l'observer.

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
