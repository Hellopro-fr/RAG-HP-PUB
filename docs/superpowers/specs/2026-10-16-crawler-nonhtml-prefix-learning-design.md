# crawler-service — apprentissage des préfixes non-HTML (R23 (2)) — design

> 2026-10-16. Conception validée section par section par l'user.
> Base jugée : `features/poc` @ `e57409aed` — `git rev-parse features/poc` = `e57409aed…` et
> `git log e57409aed..features/poc -- apps-microservices/crawler-service` vide, mesurés le 2026-10-16 à 08:35.
> Tous les `fichier:ligne` ci-dessous ont été relus sur cette base (chemins relatifs à
> `apps-microservices/crawler-service/`, `src/` = `crawler/src/`). À une autre base, refaire la commande.
> Registre : R23 (`C:\Users\USER\.claude\projects\D--DevHellopro-Workspaces-RAG-HP-PUB\memory\ACTIONS.md`).
> Diagnostic : `project_crawler_image_url_timeout_retries.md` (même dossier).

## 1. Problème

Le crawl `3582-2480-1791970865` (marsaleix.fr) enfile des URLs image SANS extension
(`/image/_1AAAB…-equipment-equipmentPicture-apkwc`). Les filtres par extension
(`src/routes.ts:360-362`, `src/seedExtensionFilter.ts:36`) ne les voient pas. Une partie de ces URLs répond
vite en non-HTML (garde content-type), le reste expire à 90 s. Mesure du 2026-10-15 sur une fenêtre de 2 h :
1 205 reclaims sur 1 209 concernent `/image/`, 0 URL image sur 263 a réussi, et seulement 27 `Processing URL`.

Ces URLs arrivent par deux chemins. (b1) Elles sont **découvertes** : ancres lightbox des pages de liste,
`enqueueLinks` (`src/routes.ts:1114`). (b2) Elles sont **ré-amorcées** : la phase 2 de la MAJ relit toute la
`request_queue` précédente (`src/class/UrlConsolidator.ts:262-326`), puis `seedPhase2` les enfile
(`src/main.ts:1615`).

Le plafond de retry `9de07a755` (R23 (1)) réduit le coût de 6 × 90 s à 3 × 90 s par URL, sans les exclure.

## 2. Décisions prises (user, 2026-10-16 — ne pas redemander)

| # | Décision | Écarté (motif) |
|---|---|---|
| D1 | Combinaison **E + B** | A : motif propre au site. C : le HEAD peut pendre aussi, +1 requête par URL. D : l'élément d'ancre n'est visible d'aucun point de filtre (Crawlee `enqueueLinks` ne passe que des href, sélecteur `a` par défaut) ⇒ il faudrait réécrire l'extraction de liens pour ne couvrir que b1 |
| D2 | B **persisté** d'un crawl au suivant | B en mémoire seulement : les URLs qui expirent, ré-amorcées en phase 2, repaieraient 3 × 90 s avant le réapprentissage |
| D3 | Clé = **hôte + dossier parent** du chemin | 1ᵉʳ segment : trop large, il mélange des sous-dossiers sans rapport |
| D4 | Révision par **sonde** | expiration (une MAJ sur deux repaie) ; aucune (une refonte du site ne serait jamais détectée) |
| D5 | E = URLs non-HTML **isolées**, dans le **même sidecar** que B | lecture du `pdf-*` précédent : l'archive partielle n'a pas d'entrée `pdf` (`app/core/crawler_manager.py:2051-2059`), sa présence dans l'archive restaurée n'est pas établie, et le fichier compte 18 806 entrées sur marsaleix |

## 3. Composants

### 3.1 Module pur `src/nonHtmlPrefix.ts`

Patron : `src/facetCap.ts` (décisions pures, état passé en argument, sans I/O).

- `prefixKey(url): string | null` : `host + dirname(pathname)`. Requête et fragment sont ignorés. Rend `null`
  pour la racine `/`, qui n'est jamais apprise.
- État par clé : `{ nonHtml: number, sawHtml: boolean, probation?: { admitted: number, resolved: boolean } }`.
- `recordNonHtml(state, url)` : n'est appelée que pour une URL **sans** extension ignorée
  (`!hasIgnoredExtensionForSeed(url)`, même prédicat que le ré-amorçage). Elle fait `nonHtml++`. Si la clé
  n'est pas bloquée, l'URL entre dans l'ensemble `isolated`, plafonné.
- `recordHtml(state, url)` : `sawHtml = true`. La clé est libérée pour tout le crawl.
- `decide(state, url, ctx)` : rend `allow | block | probe`.
  - `allow` si la clé est `null`, si l'URL est **exemptée** (`ctx.isExempt(url)`, § 5) ou si `sawHtml` est vrai.
  - `block` si `nonHtml ≥ K` et `!sawHtml`, ou si l'URL fait partie des isolées chargées.
    > **Amendement 2026-10-16 (R23 I-2, ligne ci-dessus et D5).** Les isolées du sidecar **précédent** ne
    > sont plus bloquées d'emblée : elles entrent en probation (`isolatedProbation`), chacune sondée
    > (`probe`) jusqu'à résolution par `resolveIsolatedProbe` — non-HTML ou échec terminal ⇒ conservée
    > (`loadedIsolated`, bloquée), page HTML `ok` ⇒ libérée (`Non-HTML isolated URL released:`). Seules
    > les isolées du sidecar **courant** (relance OOM) sont chargées bloquées. Une isolée non résolue reste
    > persistée (D5 : même sidecar). Détail : `apps-microservices/crawler-service/CLAUDE.md`,
    > § Non-HTML Prefix Learning.
  - Une clé en probation suit § 3.3.
- Sidecar : `serialize(state)` et `parse(json)`. Le parse est tolérant : absent ou corrompu ⇒ état vide ;
  `version` inconnue ⇒ ignoré.
- Le mode (§ 4) est appliqué par l'appelant, pas par `decide` : en `shadow`, un `block` est journalisé
  `would block` et traité comme `allow`.

### 3.2 Câblage

L'URL apprise et testée est toujours `request.url` (l'identité de file), jamais l'URL chargée : c'est elle que
voient les trois points de blocage.

| Point | Fichier:ligne | Effet |
|---|---|---|
| Apprendre non-HTML | garde content-type `src/routes.ts:364-389` (condition `:368`, `return` `:387`) | `recordNonHtml`, puis log `Non-HTML prefix learned: <key> (n=…)` au passage du seuil |
| Apprendre HTML | `src/routes.ts:447`, juste après la politique de statut (`:398-445`) et avant `increment("processed")` `:451` | `recordHtml`. Seule une réponse HTML de classe `ok` libère la clé : une page 404 HTML sous `/image/` lève avant (`:443`) et ne libère rien |
| Bloquer à l'enfilage (b1) | `transformRequestFunction`, juste après le facet cap `src/routes.ts:1243-1247` | `return false` + `filtered_nonhtml++` |
| Bloquer en prenav (b3) | `preNavigationHooks`, juste après le facet cap `src/functions.ts:885-888` | `throw new StaleVariantSkip(…)` + `filtered_nonhtml++`. La branche existante de `failedRequestHandler` (`src/functions.ts:601-604`) compte aussi `purged_prenav` et sort avant le dataset d'erreurs et tout `checkUrl` : les deux compteurs se recouvrent sur b3, c'est voulu |
| Bloquer au ré-amorçage (b2) | `seedPhase2`, juste après `hasIgnoredExtensionForSeed` `src/main.ts:1573-1579` | skip + `filtered_nonhtml++` |
| Charger | démarrage, **après** le bloc `dropData` (`src/main.ts:588-611`) : sidecar du crawl courant (reprise après OOM) **et**, en MAJ, sidecar du crawl précédent sous `path.resolve('..', previousId)/storage/datasets/<domain>` puis `<domain sanitisé>`, même résolution que `src/functions.ts:1266-1283` | état initial ; les clés du précédent entrent en probation, celles du courant non |
| Persister | à chaque clé apprise ou confirmée, et à chaque URL isolée ajoutée | `storage/datasets/<domain>/__nonhtml_prefixes.json` |

Compteur neuf `filtered_nonhtml` : incrémenté aux trois points, relu par `readStat("filtered_nonhtml")` à côté
de `filtered_ext` (`src/main.ts:1260`) et posé dans le payload à côté de `filtered_ext` (`src/main.ts:1294`).
Le BO ne le persiste pas sans MEP (même situation que `verdict_unavailable`) : visible dans le payload et dans
le hash `stats:{id}` (`GET /admin/job/{crawl_id}`).

Une URL bloquée en b1 ou b2 n'entre plus dans la `request_queue`, donc la MAJ suivante ne la ré-amorce plus.
C'est voulu. Une URL bloquée en b3 y était déjà : elle y reste, et c'est le b2 de la MAJ suivante qui l'écarte.

### 3.3 Sonde (D4)

Une clé chargée depuis le sidecar du crawl précédent est en probation : la 1ʳᵉ URL qui se présente passe
(`probe`), les autres sont bloquées.

| Issue de la sonde | Effet dans ce crawl | Persistée ? |
|---|---|---|
| non-HTML | clé confirmée, blocage normal | oui |
| HTML | `sawHtml`, clé libérée | non, elle sort du sidecar |
| timeout ou erreur | une sonde suivante passe, jusqu'à `NONHTML_PREFIX_PROBES` (3) au total | oui, si les 3 n'ont donné aucun signal |

Frontière à accepter : après une refonte qui rend la clé HTML, les URLs ré-amorcées sous cette clé et bloquées
avant la réponse de la sonde sont perdues pour ce crawl. Elles ne reviennent que si une page les relie (b1).
Les URLs du dataset précédent ne sont jamais concernées (§ 5).

### 3.4 Sidecar `__nonhtml_prefixes.json`

```json
{ "version": 1,
  "prefixes": { "www.marsaleix.fr/image": { "nonHtml": 217, "confirmedAt": "2026-10-16T10:00:00Z" } },
  "urls": ["https://…/telechargement?id=12"] }
```

- Emplacement : `storage/datasets/<domain>/`, le dossier où `ensureUnjudgedSidecar(domain)` pose
  `__unjudged_urls.json` (`src/main.ts:619`, `src/unjudgedUrls.ts:34-35`), frère de `__collapsed_urls.json`
  (`src/functions.ts:2034`). Il voyage donc par l'entrée `IncludeInArchive.DATASET`
  (`app/core/crawler_manager.py:2052`), qui archive le dossier entier.
- Cycle de vie — le patron de `__unjudged_urls.json` se transpose, avec un écart :
  - écriture tmp + rename (`src/unjudgedUrls.ts:53-57`), jamais un `writeFileSync` nu : un SIGKILL en cours
    d'écriture laisserait un JSON illisible, que le parse tolérant lirait comme « rien appris » ;
  - le bloc `dropData` supprime le dataset principal (`src/main.ts:592`), donc le sidecar courant avec lui :
    un redémarrage propre repart vide, une relance après OOM (sans `dropData`) le retrouve ;
  - l'écart : `__unjudged_urls.json` est créé vide au démarrage parce que sa *présence* est un signal pour le
    BO (`src/main.ts:613-618`). Ici l'absence vaut état vide et personne d'autre ne lit le fichier : pas de
    création au démarrage.
- Invisible aux lecteurs du dossier dataset, tous vérifiés sur la base jugée :
  - BO `loadJsonFilesFromDirectory` saute tout nom qui commence par `_`
    (`Marketplace/BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php:5456`,
    copie locale relue le 2026-10-16 ; PROD vérifiée le même jour, taille 494 757 o = blob `1c411242`) ;
  - Python `_count_files_in_dir` (`app/core/crawler_manager.py:155`) et le listage admin
    (`app/router/admin.py:307`) ;
  - TS : `loadDatasetUrlsGenerator` (`src/functions.ts:1293`), `rehydrateDedupFromDataset`
    (`src/functions.ts:1343`), `cleanDatasetFragments` (`src/functions.ts:1940`).

## 4. Activation

`NONHTML_PREFIX_MODE` prend trois valeurs :
- `off` : défaut du build, aucun effet — ni apprentissage, ni sidecar, ni compteur ;
- `shadow` : apprend, journalise `would block`, écrit le sidecar, ne bloque rien ;
- `on` : bloque.

Une valeur inconnue retombe sur `off`.

Déploiement prévu en trois temps : build en `off`, puis la VM en `shadow` sur quelques MAJ (on y compte les
faux positifs, c'est-à-dire les clés apprises qui voient une page HTML ensuite), puis `on`.

Paramètres :

| Variable | Défaut | Rôle |
|---|---|---|
| `NONHTML_PREFIX_MIN` (K) | 5, provisoire, dérivé par rejeu (§ 6) | nombre de non-HTML avant blocage |
| `NONHTML_PREFIX_PROBES` | 3 | sondes par clé en probation |
| `NONHTML_ISOLATED_MAX` | 10 000 | plafond des URLs isolées |

⚠ Piège connu, déjà vu sur `resolveTimeoutMaxRetries("")` : une variable posée VIDE ne doit pas donner 0.
Il faut un parse explicite qui retombe sur le défaut.

## 5. Garde-fou côté BO (le consommateur le plus strict d'une absence)

Le BO désactive « URLs Milvus − URLs du dataset neuf », et seuls `__collapsed_urls.json` et
`__unjudged_urls.json` protègent de cette soustraction (`src/unjudgedUrls.ts:6-14`). Une URL image n'a jamais de
ligne dataset, donc la filtrer est neutre pour le BO. En revanche, une page produit bloquée à tort ferait
désactiver sa fiche.

**Exemption absolue** : une URL présente dans le dataset principal précédent n'est jamais bloquée, à aucun
des trois points.

Source de l'ensemble : `remainingUrls` (`src/main.ts:895`), rempli par la consolidation en MAJ
(`src/main.ts:961-963`), dont les entrées `source === 'dataset'` sont exactement le dataset précédent (clés de
`__collapsed_urls.json` comprises, `src/functions.ts:1308-1316`) — la priorité dataset > request_queue >
request_url de `UrlConsolidator` garantit qu'une URL du dataset porte `'dataset'`. On en tire un `Set<string>`
synchrone, construit avant le lancement du crawler.
- Comparaison au `/` final près, convention déjà suivie par tout l'aval (`src/class/UpdateChecker.ts:171-179`,
  et `trim($url, "/")` côté BO).
- Coût mémoire : le même ordre que `remainingUrls`, déjà tenu en mémoire en entier.
- Relance après OOM : la consolidation tourne à chaque démarrage en MAJ, sans garde de reprise
  (`src/main.ts:897-922`), donc l'ensemble est reconstruit.
- Écartés : `seenBases` (`src/main.ts:741`) ne tient que des bases normalisées et n'existe que sous
  `QM_FACET_ENABLED` (`src/main.ts:732`) ; `isInDataset` est asynchrone (inutilisable dans
  `transformRequestFunction`, synchrone) et échoue OUVERT en rendant `false` (`src/class/UpdateChecker.ts:163`),
  c'est-à-dire dans le sens qui bloquerait.

Crawl initial : pas de dataset précédent, donc pas d'exemption. Aucune fiche n'existe encore à désactiver ; le
risque restant (une page jamais créée) est borné par K et par le veto `sawHtml`.

Conséquence : `previousTotal` (`src/main.ts:981`) n'est pas affecté, puisqu'aucune URL du dataset précédent
n'est écartée.

## 6. Tests et mesure

- **Nouveau** fichier `src/nonHtmlPrefix.test.ts`. On n'étend aucun fichier existant : la suite 509/509 sert
  d'oracle publié à R23 (1). Cas couverts :
  - clé (racine, hôte + dossier, requête et fragment) ;
  - seuil K, veto `sawHtml`, exemption (au `/` final près) ;
  - automate de probation (non-HTML, HTML, timeout ×3) ;
  - plafond des isolées ;
  - parse tolérant ;
  - les trois modes, et le repli d'une valeur vide ou inconnue.
- Câblage : un test par point de blocage. Patrons : `src/seedExtensionFilter.test.ts` pour b2,
  `src/facetCap.test.ts` pour b1 et b3.
- Parité du compteur : nouveau fichier, sur le patron de `src/statNameParity.test.ts` (assertions sur le texte
  source) — l'incrément, le `readStat` et la clé de payload de `filtered_nonhtml`.
- Pin check (fait le 2026-10-16) : aucune empreinte ni golden file sur `routes.ts`, `functions.ts`, `main.ts`
  ou `admin.py`. Les seuls tests qui lisent ces sources en texte (`src/statNameParity.test.ts`,
  `src/errorsUnprocessedParity.test.ts`) cherchent des noms précis par `includes` ou regex ancrée : un ajout ne
  les touche pas. Aucun test Python ne lit le texte de `admin.py` ni ne fige `_DATASET_PREFIXES`.
- Caractérisation : en mode `off`, la suite existante reste à 509/509 **sans modification**.
- Rejeu pour dériver K : `pdf-*` et dataset principal des crawls stockés, fusionnés par `timestamp`, avec
  simulation de K = 1…10 ; on compte les faux positifs (clé apprise qui voit une page HTML ensuite).
  Prérequis : ajouter `"pdf": "pdf-"` à `_DATASET_PREFIXES` (`app/router/admin.py:225`), car l'API admin ne
  sert aujourd'hui que main, error, nfr et update. L'instrument est gratuit (données internes). À défaut,
  la mesure se fait en mode `shadow`.
- Preuve d'effet après déploiement (marsaleix, première MAJ en `on` après une MAJ en `shadow`) : 0
  `Navigation timed out` sur `/image/` une fois la clé chargée ou apprise, et `filtered_nonhtml` > 0. Cette
  sortie est impossible sans le correctif. Comparaison avec 27 `Processing URL` en 2 h (mesure du 2026-10-15).

## 7. Hors périmètre

- Persistance de `filtered_nonhtml` côté BO (whitelist `crawl_events`, colonnes `crawl_metrics`) : MEP BO
  séparée, si la phase `shadow` montre qu'elle sert.
- Exemption plus large que le dataset précédent (URLs des `request_queue` déjà réussies en HTML) : inutile tant
  que le veto `sawHtml` couvre le crawl courant.
