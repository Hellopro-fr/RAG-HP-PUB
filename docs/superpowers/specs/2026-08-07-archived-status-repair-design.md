# Réparation du statut des crawls archivés dont le blob ment — design

**Date** : 2026-08-07
**Service** : `crawler-service` (Python, RAG-HP-PUB `features/poc`)
**Statut** : design approuvé, **non implémenté**
**Prérequis** : le correctif SET NX de `get_job_or_recover` (commit `2a12a098`, mergé `8a5ec844`) est **poussé sur `origin/features/poc`** mais **pas déployé** — le rebuild Docker de la VM est en attente.

> Cette spec a été révisée après une relecture adversariale sur quatre axes
> (exactitude des références, solidité du prédicat, cohérence interne, sûreté du
> déploiement). Sept trouvailles bloquantes ont été vérifiées ligne à ligne et
> intégrées. Les §4, §5, §6 et §9 diffèrent substantiellement de la première
> rédaction ; §10 conserve la trace de ce qui a été écarté et pourquoi.

---

## 1. Le problème

Un crawl dont les données ont été archivées dans GCS porte `status='archived'` dans
Redis. C'est ce statut, et lui seul, qui fait prendre à `get_results_archive` sa
branche de récupération GCS (`crawler_manager.py:1638`). Quand le blob dit
`'finished'` alors que le tar est en GCS et que les données locales sont parties,
`GET /results/{id}` répond **404** — « the crawl data may have been cleaned up after
archiving to GCS » — et continuera de le faire indéfiniment.

Deux causes produisent cet état, distinctes mais indiscernables à l'arrivée :

**La régression `get_job_or_recover`.** `cache_service.get_json` avale les erreurs
Redis et rend `None`, indiscernable de « clé absente ». La récupération disque
reconstruisait alors un stub de 8 champs et l'écrasait sur le blob vivant. Le statut
du stub est recopié du marqueur de complétion, qui ne porte que
`finished`/`failed`/`stopped` : **le marqueur d'un crawl archivé dit encore
`finished`**, puisque `_mark_as_archived` (`:2652`) n'écrit que dans Redis et ne
touche jamais le disque. Un crawl archivé revient donc en `'finished'`. (Un crawl
arrêté reviendrait en `'stopped'` — mais `archive_crawl` exige `finished`
(`:2452`), donc un crawl arrêté n'est jamais archivé et sort du périmètre de lui-même.)
Corrigé pour l'avenir par `2a12a098` (écriture en SET NX) ; le stock accumulé reste.

**Les « legacy stuck at finished ».** Le commentaire de `crawler_manager.py:2503-2505`
les décrit : des crawls dont le tar est monté en GCS mais dont `_mark_as_archived`
n'a jamais été appelé, par un bug antérieur. Même symptôme, même preuve disponible,
même remède.

Ce design traite les deux, parce que le prédicat qui identifie l'un identifie l'autre
sans une ligne de plus.

## 2. Ce qui a été mesuré

Production, 2026-08-07, via la gateway, en lecture seule. Toutes les extrapolations
utilisent le facteur 6756 / 1800 = 3,753.

**Méthode d'échantillonnage.** `GET /admin/storage-dirs?sizes=false` pagine sur un
tri **lexicographique** des noms de répertoires (`admin.py:509`). Six pages de 300
prises aux offsets **0, 1200, 2400, 3600, 4800, 6000**, soit 1800 répertoires sur
6756 (27 %). Rejouable tel quel.

| statut Redis | échantillon | extrapolé |
|---|---|---|
| `archived` | 1241 | ~4657 |
| `finished` | 517 | ~1940 |
| `failed` | 42 | ~158 |
| absent de Redis | 0 | 0 |

Décomposition des 517 `finished` :

| sous-population | échantillon | extrapolé | lecture |
|---|---|---|---|
| `stashed_at` non nul | 282 | ~1058 | légitime — `/results` déstashe en ligne |
| non stashé, sous-arbre `storage/` présent | 196 | ~736 | **suspects** |
| non stashé, sans sous-arbre | 39 | ~146 | **cassés** |

312 répertoires de l'échantillon portent `stashed_at` tous statuts confondus ; 282
sont `finished`, les 30 restants relèvent des statuts `archived`/`failed` et sortent
du périmètre par la condition 1.

**Population que le reclean supprimerait.** 639 crawls `archived` de l'échantillon
ont encore leur sous-arbre `storage/`, soit **~2398 extrapolés**. C'est le volume que
la génération de l'allowlist met en file de suppression (§6).

**Nature des 196 suspects.** Six sondés via `GET /admin/job` : **6 sur 6 sont des
stubs** (ni `params` ni `id` dans le blob). Leur sous-arbre survit pour **deux raisons
cumulées, dont une suffirait** : le stub a effacé le `status='archived'` qu'exige la
collecte du reclean (`:3666`), *et* l'allowlist est absente en production, ce qui
désactive le sweep pour tout le monde (`:3988-3990`).

**Volume de la régression** (`GET /admin/recent-logs`, fenêtre 2026-08-04 14:01 →
2026-08-07 08:40, soit ~3 jours depuis le dernier redémarrage) : **345 récupérations
sur 266 crawl_ids distincts**, reconstruites en `'finished'` dans 345 cas sur 345.
60 blobs sur 60 échantillonnés parmi ces ids portent aujourd'hui la forme stub.
242 de ces 266 ids figurent aussi dans le jeu des erreurs de lecture Redis
(551 lignes / 311 ids — plancher, le tampon de log est par réplica).

**Majorant des candidats** : ~736 + ~146 ≈ **882**. C'est un **majorant avant les
conditions 3 à 6** : `/admin/storage-dirs` ne renvoie ni la présence d'un snapshot,
ni les mtime, ni l'appartenance à l'allowlist (`admin.py:520-546`). Le compte réel
viendra du dry-run, et lui seul.

**La population est un flux, pas un stock.** Les stubs sont écrits avec un TTL de
7 jours (`app/router/crawler.py`, `set_json_nx(..., ttl=604800)`). Un stub non réparé
expire, la clé disparaît, et le crawl devient invisible du prédicat — sans être
réparé pour autant. Le dry-run doit donc être **rejoué juste avant le flip** et les
deux comptes comparés : une baisse signifie une population perdue de vue, pas résolue.

**Cas témoin vérifié de bout en bout** : le crawl 6712. Blob = stub
(`domain: "unknown"`, `status: finished`), `/results` a répondu 404 le 2026-08-06 à
09:06:32, et le crawl 6713 lu 22 secondes plus tôt, blob intact, a servi son archive
GCS normalement.

## 3. L'invariant

> Un crawl dont un tar de taille plausible est présent sous
> `gs://{bucket}/crawls/{id}.tar.gz` (≥ 1024 octets, hors `.tmp.tar.gz`), qui n'est
> pas stashé, sur lequel aucun run ne s'est terminé depuis son archivage, et qui
> n'est pas en cours d'archivage, doit porter `status='archived'` dans Redis.

« Présent avec une taille plausible », et non « prouvé » : `verify_archives_in_gcs.sh`
n'émet que des **ids** (`:54-60`), sans date ni génération. Le fichier atteste qu'un
tar existe sous cet id — pas qu'il corresponde aux données actuelles du crawl. Cette
limite est exactement ce que les conditions 5 et 6 compensent.

Le container n'a aucun accès GCS : ce fichier est la seule évidence recevable. C'est
déjà le motif retenu par `_reclean_archived_leftovers` (`:3959-3990`) pour une action
plus dangereuse encore — supprimer des données. Fichier absent ou vide ⇒ aucune action.

## 4. Le prédicat

Nouveau module **pur**, `apps-microservices/crawler-service/app/core/archived_status_repair.py`
— aucune dépendance, aucune I/O, uniquement des primitives en entrée, donc exécutable
et testable en local sans Docker.

```python
def is_status_repair_candidate(
    crawl_id: str,
    status: str | None,
    stashed_at: str | None,
    verified_ids: set[str],
    snapshot_mtime: float | None,
    log_mtime: float | None,
    archive_lock_held: bool,
) -> bool:
```

Six conditions conjointes, **évaluées dans cet ordre** — la première en échec donne
le motif de rejet exposé par le dry-run :

| # | condition | ce qu'elle écarte |
|---|---|---|
| 1 | `status == 'finished'` | les `archived` déjà corrects, les `failed`, les `stopped`, les `running` |
| 2 | `not stashed_at` | les ~1058 `finished` stashés, dont le tar est sous `stash/` et non `crawls/` |
| 3 | `crawl_id in verified_ids` | tout ce dont le tar n'est pas listé dans `crawls/` |
| 4 | `snapshot_mtime is not None` | les crawls sans instantané — ni archivés, ni migrés |
| 5 | `log_mtime is not None and log_mtime < snapshot_mtime` | le cas re-crawl |
| 6 | `not archive_lock_held` | un archivage en cours |

### Condition 5 : pourquoi `crawler.log` et pas le marqueur de complétion

La première rédaction ancrait cette condition sur `_completion_marker.json`, avec une
disjonction `marker_mtime is None or marker_mtime < snapshot_mtime`. **C'était
fail-open sur le cas même qu'elle prétendait fermer**, et la relecture adversariale
l'a démontré à la ligne :

- `_cleanup_stale_state_for_relaunch` (`:3494-3500`) **supprime** le marqueur au
  démarrage de chaque relance (`start_crawl:615`), en laissant le snapshot ;
- `_monitor_process` écrit `status='finished'` dans Redis à `:1284`, puis
  `_verify_terminal_status_persisted` (`:1285`, plusieurs allers-retours Redis), puis
  `_publish_update` (`:1288`), et n'écrit le marqueur qu'à `:1298` — dont l'échec est
  **avalé** à `:1301-1302`, rendant l'état permanent.

Entre ces deux points, un crawl relancé sous le même `crawl_id` est `finished` sans
marqueur, avec le snapshot de la génération précédente. Les cinq conditions
d'origine étaient réunies. La bascule en `archived` aurait alors : fait servir par
`/results` le **tar de la génération précédente** (`:1638-1647`) — que le BO ingère
en croyant lire le nouveau crawl, sans une seule erreur ; fait servir par `/status`
les compteurs de l'ancien run ; autorisé le reclean à supprimer les données fraîches ;
et rendu `POST /archive` définitivement 409 (`:2446-2450`), donc le tar de la nouvelle
génération n'aurait jamais existé.

`crawler.log` n'a aucun de ces défauts. Il vit à la racine du répertoire de crawl, il
est écrit en append pendant toute la durée du run, et `_cleanup_local_data` le
**conserve** délibérément — son docstring le dit : « Everything else in the crawl dir
(crawler.log, logs/, *.json sidecars) is small and kept for investigation »
(`:2637-2640`). Rien ne le supprime.

- Crawl normalement archivé : dernière ligne écrite à la fin du run, snapshot posé
  plus tard par `archive_crawl` ⇒ `log_mtime < snapshot_mtime` ⇒ candidat. Les 196
  suspects sont conservés.
- Crawl relancé : le log de la nouvelle génération est postérieur au snapshot de
  l'ancienne ⇒ écarté, que le marqueur existe ou non.

Aucune disjonction : `log_mtime is None` ⇒ **écarté**.

### Condition 4 : ce que le snapshot prouve, et ce qu'il ne prouve pas

`_status_snapshot.json` est écrit par `archive_crawl` (`:2550`) **et** par les deux
chemins de `migration.py` (`:403-435`, `:607-634`), qui l'écrivent pour des crawls
jamais archivés. Sa présence signifie donc « un archivage **ou** une migration a
écrit un instantané » — ce n'est pas une preuve d'archivage, contrairement à ce que
la première rédaction affirmait. La condition 4 ne sert qu'à garantir que
`snapshot_mtime` existe pour la comparaison de la condition 5 ; la preuve
d'archivage, c'est la condition 3, et la fraîcheur, c'est la 5. Un crawl migré non
archivé est écarté par la 3.

Vérification empirique cohérente : le crawl 3423 est un stub, avec ses données
locales et **sans** snapshot — un crawl jamais archivé, correctement écarté.

### Condition 6 : la course avec un archivage en cours

`archive_crawl` écrit le snapshot à `:2550`, crée le tar à `:2601` — `make_archive`
sur l'arbre complet, plusieurs minutes sur un crawl multi-Go — et n'appelle
`_mark_as_archived` qu'à `:2605`. Pendant toute la durée du tar, le blob vaut encore
`finished` et le snapshot vient d'être réécrit, donc il est le fichier le plus
récent : `log_mtime < snapshot_mtime` est vrai **par construction**. Sur un
ré-archivage d'un id déjà présent dans l'allowlist, les conditions 1 à 5 sont réunies
de façon déterministe pendant plusieurs minutes.

Sur le chemin nominal la bascule serait inoffensive (`:2605` referait la même chose).
Le dégât est sur l'échec : si `_create_archive` lève (`:2622` → HTTP 500 — volume
d'archives plein, tar corrompu, rename raté), `archive_crawl` n'a jamais marqué le
crawl, mais la passe de réparation, elle, l'a fait. Le crawl reste `archived` avec ses
données fraîches sur disque et l'ancien tar en GCS ; `/results` sert l'ancien ;
`/archive` répond 409 ; le reclean supprime les données fraîches.

`archive_lock:{crawl_id}` est posé à `:2466` et libéré à `:2633` : il couvre
exactement la fenêtre. Un `EXISTS` par candidat ayant passé les conditions 1 à 5,
donc au plus `MAX_PER_TICK` par tick.

### Ce que le prédicat n'utilise délibérément pas

**L'absence de données locales.** Le réflexe naturel, et il écarterait ~736 des ~882
candidats — les suspects dont le sous-arbre survit précisément parce que le reclean
attend le statut qu'on veut réparer.

**La forme du blob** (`params`/`id` absents). Le périmètre retenu est « tout blob dont
le statut ment alors qu'un tar existe », ce qui couvre les legacy de §1 sans code
supplémentaire, et résiste aux stubs partiellement mutés (un `downloaded_at`
estampillé par `_record_downloaded_at`, par exemple).

## 5. Les deux portes

Une seule règle, deux points d'entrée sur le même module.

### Passe de réconciliation

Trois modifications à `_reconcile_locked`, que la première rédaction avait
incorrectement présentées comme inutiles :

1. **Accumuler les candidats.** La boucle de scan ne collecte aujourd'hui que
   `archived_candidates` (`status == 'archived'`, `:3666-3667`) et, si
   `AUTO_STASH_ENABLED`, `auto_stash_pool` (`:3669-3671`). Ajouter au même endroit un
   accumulateur `finished_candidates` (`status == 'finished'`).
2. **Hisser le chargement de l'allowlist.** `_load_reclean_allowlist()` est aujourd'hui
   appelé **dans** `_reclean_archived_leftovers` (`:3988`), donc après le point
   d'insertion. Le hisser dans `_reconcile_locked` avant `:3899` et le passer en
   paramètre aux deux passes : une seule lecture de fichier pour les deux.
3. **Chaîner vers le reclean.** `archived_candidates` est figée avant `:3899` : un
   crawl réparé n'y est pas. La passe doit y **ajouter** chaque job réparé pour qu'il
   soit nettoyé au même tick.

Coût réel, à écrire noir sur blanc : la passe n'ajoute **aucun SCAN Redis ni aucune
relecture de blob** pour la sélection — elle réutilise ceux de la boucle. Elle ajoute
**2 `os.stat` par blob ayant passé les conditions 1 à 3**, **1 `EXISTS` Redis par
candidat atteignant la condition 6**, et **1 `get_json` + 1 `set_json` + 1 `publish`
par réparation** (via `_mark_as_archived`, `:2656-2663`), soit jusqu'à 150 allers-retours
Redis par tick au plafond de 50.

Nouveaux réglages, alignés sur les `ARCHIVED_RECLEAN_*` (`app/core/config.py:110-120`) :

| réglage | défaut | rôle |
|---|---|---|
| `ARCHIVED_STATUS_REPAIR_ENABLED` | `False` | interrupteur ; à `False`, comportement inchangé |
| `ARCHIVED_STATUS_REPAIR_MAX_PER_TICK` | `10` | plafonne les écritures Redis par tick |

Le plafond démarre à **10**, et non 50 : le `reconcile_leader_lock` a un TTL de 600 s
(`:3350`) et **aucun heartbeat**, contrairement aux verrous d'archive et de stash qui
ont `_LockHeartbeat` (`:2478`). Le service tourne à 7 réplicas. Allonger le tick
au-delà du TTL ferait élire un second leader pendant que le premier travaille. La
durée du tick est déjà journalisée (« Reconciliation complete », `:3917`) : on
l'observe, puis on relève le plafond si la marge le permet. À 10 par tick de 300 s,
~880 candidats se résorbent en une douzaine d'heures — acceptable pour une campagne
qu'on veut surveiller.

### `GET /admin/archived-status-repair`

En **lecture seule** — c'est le seul endpoint de ce design, et il n'appelle pas
`get_job_or_recover`. Paramètres `limit` (défaut 500, borné) et un budget de temps,
sur le modèle de `/admin/storage-dirs` (`admin.py:485-486`) : un parcours non borné de
6756 blobs avec deux `os.stat` chacun n'a pas sa place dans une requête HTTP.

Forme de la réponse — **valeurs illustratives, non additives** :

```json
{
  "verified_list_present": true,
  "verified_ids_count": "<n>",
  "scanned": "<n>",
  "truncated": false,
  "candidates": ["6712", "..."],
  "candidates_count": "<n>",
  "rejected": {
    "not_finished": "<n>", "stashed": "<n>", "not_in_gcs_list": "<n>",
    "no_snapshot": "<n>", "run_after_archive": "<n>", "archive_in_progress": "<n>"
  },
  "stash_only_hint": "<n>"
}
```

Les buckets de `rejected` suivent l'ordre d'évaluation du §4 : un blob échouant
plusieurs conditions est compté dans **la première** qui échoue. `not_finished`
compte les blobs écartés par la condition 1 — ce ne sont pas des « `finished` non
retenus », ils ne sont simplement pas concernés. Les candidats sont rendus par
`crawl_id` seul : servir le `domain` supposerait de lire chaque `_status_snapshot.json`,
et le blob stub ne le porte pas (il vaut `"unknown"` dès que `--domain=` n'est pas
retrouvé dans les 300 premières lignes du log). Un `GET /status/{id}` donne le domaine
au cas par cas.

`stash_only_hint` compte les blobs qui échouent **uniquement** à la condition 3 :
`finished`, non stashés, avec snapshot, log antérieur au snapshot, archivage non en
cours — mais absents de la liste `crawls/`. C'est la population résiduelle de §7,
majorée : elle contient aussi des crawls dont le tar n'existe nulle part.

Une précision qui s'impose vu l'incident traité ici : dire que « `/admin/*` est en
lecture seule » serait faux. Quatre routes admin (`:115`, `:153`, `:246`, `:352`)
dépendent de `get_job_or_recover` et écrivent donc par son chemin de récupération —
depuis `2a12a098`, seulement quand la clé est réellement absente. Au total **12
endpoints** en dépendent (8 dans `crawler.py`, 4 dans `admin.py`), dont **8 en GET**.
Le nouvel endpoint, lui, n'en dépend pas.

## 6. Sûreté, échecs, annulation

**L'écriture réutilise `_mark_as_archived` (`:2652`) sans la modifier.** Elle relit le
blob à frais — donc n'écrase pas une écriture concurrente sur d'autres champs — pose
`status` et `archived_at`, écrit via `set_json` **sans TTL**, puis publie l'événement.
L'absence de TTL efface l'expiration à 7 jours posée par le stub : sans cela on
réparerait un blob qui disparaît une semaine plus tard.

Deux réserves à consigner :

`archived_at` portera **l'heure de la réparation**, pas la date réelle d'archivage.
Vérifié : `grep -rn archived_at` sur `.py`/`.ts`/`.go`/`.sh` de `apps-microservices/`,
`libs/` et `tools/` au 2026-08-07 → un seul écrivain (`crawler_manager.py:2661`),
aucun lecteur (le `last_archived_at` de `dlq-manager-service` est un homonyme sans
rapport). Inoffensif, mais à ne pas prendre plus tard pour une date d'archivage.

`set_json` **avale ses exceptions** (`cache_service.py`) : une réparation peut échouer
en silence et `_mark_as_archived` rendra la main sans erreur. La passe doit donc
compter les réparations **effectivement observées** — relire le statut au tick suivant
plutôt que faire confiance au compteur d'appels — et le dry-run rejoué après la
campagne est la vraie mesure de complétion.

**Chaîne fail-closed.** Allowlist absente ou vide → `_load_reclean_allowlist()` rend
`None` → zéro réparation. Pour les `os.stat` : seul un `FileNotFoundError` produit un
`None` interprétable ; **toute autre `OSError` rend le candidat non éligible**, sans
exception. C'est un point où la première rédaction se contredisait — elle annonçait
« candidat écarté » alors que la disjonction `is None` le retenait. La passe ne lève
jamais, par protection de la boucle de réconciliation.

**Idempotence.** Après réparation le statut vaut `archived`, la condition 1 échoue.

**Concurrence.** Leader-only, sous le `reconcile_leader_lock`, avec la réserve de TTL
sans heartbeat décrite au §5 qui justifie le plafond bas.

### Les suppressions de données, et comment les arrêter

**Générer l'allowlist arme le reclean pour les ~2398 crawls `archived` qui ont encore
un sous-arbre `storage/`** (§2), indépendamment de ce design.
`ARCHIVED_RECLEAN_ENABLED` vaut `True` par défaut (`config.py:110`) et n'est même pas
dans le bloc `environment:` du compose — il n'atteint le conteneur que par
`env_file: .env`. La seule chose qui retient le sweep aujourd'hui est le fichier
manquant, comme le dit le log de production : *« verification list
'/app/archives/verified_in_gcs.list' missing/empty — sweep disabled (fail-closed) »*.
À 3 par tick de 300 s, soit 864 par jour, les ~2398 partent en moins de trois jours.

Un crawl réparé s'ajoute à cette file au même tick (§5).

**Trois niveaux de réversibilité, à ne pas confondre :**

| niveau | réversible ? | geste |
|---|---|---|
| armement du sweep | oui, en ≤ 300 s | `rm /app/archives/verified_in_gcs.list` — le fichier est relu à chaque tick, aucun redémarrage nécessaire |
| bascule du blob | **non** | `_mark_as_archived` est le seul écrivain ; il n'existe pas de `_mark_as_finished` |
| `shutil.rmtree` du sous-arbre | **non** | récupérable seulement en re-téléchargeant le tar — c'est-à-dire l'hypothèse même qu'on teste |

**Le coupe-circuit d'urgence n'est pas `ARCHIVED_STATUS_REPAIR_ENABLED`.** Éteindre le
flag de réparation n'arrête pas le sweep : ce sont deux réglages disjoints. Le geste
correct est de supprimer l'allowlist ; `ARCHIVED_RECLEAN_ENABLED=false` + redémarrage
est le secondaire.

## 7. Hors périmètre

**Les stubs de crawls stashés.** Leur tar est sous `stash/`, absent de l'allowlist
`crawls/` : la condition 3 les écarte par construction. Ils restent cassés, et le
dry-run les majore (`stash_only_hint`). Les réparer supposerait de reposer un
`stashed_at` dont la valeur est perdue, donc fabriquée — or `/results` sur un crawl
stashé déclenche un unstash qui **supprime** la copie GCS. C'est la raison pour
laquelle `_reclean_archived_leftovers` exclut déjà délibérément les leftovers stashés
(`:3979-3982`).

**Les crawls dont le stub a expiré.** Le TTL de 7 jours les fait disparaître de Redis
avant qu'on les voie (§2). Ils sont hors d'atteinte de ce design ; seule une
énumération partant du **disque** plutôt que de Redis les retrouverait.

**Les blobs `failed` et `stopped`.** Un crawl échoué ou arrêté n'est jamais archivé
(`:2452`). Une correspondance dans l'allowlist signalerait une anomalie à comprendre,
pas à réparer automatiquement.

**Les champs perdus autres que `status`** (`params`, `callback_url`,
`previous_crawl_id`). Ils ne servent plus à un crawl terminal. `domain`, `start_url`
et les compteurs ne sont **pas** perdus pour les consommateurs : `get_status` les sert
depuis `_status_snapshot.json` (`:1490-1517`) en réécrivant depuis Redis `status`
(`:1500`), `is_error` (`:1503`) et les champs d'auto-stash (`:1506-1509`). Vérifié en
production sur 6712, dont `/status` renvoie `smblyon.com` / 23 URLs.

**`POST /reindex-storage`.** Il reproduit la même classe de bug, en pire :
`scan_keys_by_prefix` avale l'exception Redis et rend `[]` (`cache_service.py`), donc
un hoquet fait passer tous les crawls pour orphelins et les ré-indexe en stubs
(`crawler_manager.py:2083-2092`). **Ne pas l'appeler pendant la campagne.** Un
correctif du même type que `2a12a098` lui est dû, dans un autre lot.

**P-1 et les dérives de compteur.** Documentés dans
`docs/superpowers/audits/2026-04-19-crawler-service-redis-resilience-audit.md` ;
91 occurrences de « Running jobs counter drifted » relevées sur la même fenêtre de log
que §2. Autre défaut, autre design.

## 8. Tests

| cible | contenu |
|---|---|
| `tests/test_archived_status_repair.py` | le prédicat en table : une entrée par condition ; les deux ordres de mtime ; `log_mtime is None` → écarté (le cas qui était fail-open) ; `archive_lock_held` → écarté |
| `tests/test_reconcile_status_repair.py` | flag off → zéro écriture ; allowlist absente → zéro écriture ; plafond respecté ; `finished_candidates` alimenté par la boucle ; **un job réparé est visible du reclean dans le même tick** ; `_mark_as_archived` appelé, aucun blob construit |
| `tests/test_admin_status_repair_endpoint.py` | buckets de rejet conformes à l'ordre d'évaluation ; `limit`/`truncated` respectés ; **assertion explicite qu'aucune écriture n'a lieu** |
| erreurs de `stat` | un cas par branche : `FileNotFoundError` vs autre `OSError`, sur le snapshot et sur le log |
| verrou de régression | sur la source de la passe (`inspect.getsource`, idiome du dépôt) : `_mark_as_archived` présent, `set_json` direct absent |

Tout tourne en local avec les motifs de mock existants. Référence actuelle de la
suite `crawler-service` : 360/361, l'unique échec (`test_archive_mock_e2e`, script
bash) étant préexistant et lié à Windows.

## 9. Séquence de déploiement

L'ordre a été revu : la première rédaction armait la suppression de masse (ancienne
étape 3) **avant** le seul dry-run (ancienne étape 4), et ne nommait aucun
coupe-circuit.

1. **Implémenter, tester, merger** dans `features/poc`. La spec décrit du code qui
   n'existe pas encore ; les étapes suivantes en dépendent.
2. **Mesurer d'abord ce qui sera supprimé.** Compter `archived` **et**
   `has_storage_subtree` sur un échantillon `/admin/storage-dirs` — read-only, même
   méthode qu'en §2 — et convertir en Go. Décider en connaissance de cause.
3. **Vérifier l'environnement** via `GET /admin/config` : `AUTO_STASH_ENABLED` (son
   pool est `status in (finished, failed, stopped) and not stashed_at`, `:3670` —
   c'est exactement la population de réparation, et il tourne dans le même tick),
   ainsi que `ARCHIVED_RECLEAN_*`.
4. **Poser `ARCHIVED_RECLEAN_ENABLED=false`** dans le `.env` de la VM et redémarrer.
   Le sweep doit être désarmé **avant** que l'allowlist n'existe.
5. **Générer l'allowlist vers un chemin non monté** :
   `verify_archives_in_gcs.sh <bucket> /tmp/verified.list` — le script prend `OUT_FILE`
   en second argument positionnel (`:38`), aucune modification de code. L'inspecter,
   recouper quelques ids à la main. ⚠️ Le script n'a pas de `set -euo pipefail` : si
   `mv` échoue (EACCES — `upload_daemon.sh:36` fait un `chown -R` sur ce répertoire),
   il imprime quand même son résumé « Listed / Kept / Output » et sort en 0. Vérifier
   le fichier, pas le message.
6. **Pousser et rebuilder** le Docker de `crawler-service`, flag
   `ARCHIVED_STATUS_REPAIR_ENABLED` à **off**. Le prérequis SET NX (`2a12a098`) est
   déjà sur `origin/features/poc` et prend effet à ce rebuild.
7. **Déposer l'allowlist** sur le volume `/app/archives`. Le sweep reste désarmé par
   l'étape 4.
8. **Dry-run** : `GET /admin/archived-status-repair`. Vérifier `verified_list_present`
   et `verified_ids_count` avant de lire quoi que ce soit d'autre. Contrôler que 6712
   figure dans les candidats, en sonder quelques-uns à la main.
9. **Flipper `ARCHIVED_STATUS_REPAIR_ENABLED=true`.** Suivre les logs. Coupe-circuit :
   `rm /app/archives/verified_in_gcs.list` (§6), **pas** le flag qu'on vient d'allumer.
10. **Rejouer le dry-run** et comparer : `candidates_count` doit décroître vers 0. Une
    baisse plus rapide que le nombre de réparations journalisées signale des stubs
    expirés par TTL, pas résolus (§2).
11. `GET /results/6712` → 200 par récupération GCS.
12. **Rallumer le reclean délibérément**, comme une décision séparée :
    `ARCHIVED_RECLEAN_ENABLED=true`, en démarrant à `ARCHIVED_RECLEAN_MAX_PER_TICK=1`
    le temps de mesurer le coût réel d'un `rmtree`, puis remonter.

**Resserrage optionnel.** `verify_archives_in_gcs.sh` accepte `INTERSECT_FILE` :
n'émettre que les ids présents à la fois dans le listing GCS et dans la liste
`est_archiver=1` du BO. Attention, `comm -12` (`:70`) est sensible au tri **et aux
fins de ligne** : un export BO en CRLF donne une intersection vide, et le script sort
alors en 1 sur « verified id set is empty » — fail-safe mais opaque. Normaliser en LF.

**Régime permanent de l'allowlist.** Un fichier généré une fois vieillit : les crawls
archivés après la génération n'y sont pas, donc ni réparés ni recleanés. Soit un cron
hôte le régénère périodiquement, soit on assume qu'il ne couvre que le stock à sa date
— à écrire dans le runbook, pas à laisser implicite.

Aucune migration, aucun changement BO.

## 10. Écarté, et pourquoi

**`POST /archive/{id}` en masse.** Le remède qui vient d'abord, et il est dangereux.
Si le repli GCS (`:2506`) échoue de façon transitoire — daemon occupé, timeout — le
code enchaîne sur `:2520` « Proceeding with fresh archiving » et tar un répertoire
réduit à son marqueur et son log. Seule une archive de **0 octet** est rejetée
(`:2580`) : le moignon passe, et le daemon le téléverse **par-dessus l'archive
réelle**.

**Script hôte one-shot dans `tools/`** (à la racine du dépôt, pas sous
`crawler-service/`). Il tournerait sans rebuild. Mais il duplique le prédicat et le
chargement de l'allowlist hors du service, doit voir `/app/storage` depuis l'hôte, et
ne couvre pas le flux résiduel.

**S'en remettre au repli GCS existant.** Il ne se déclenche que quand le BO appelle
`/archive` pour un domaine éligible ; les crawls cassés n'y sont plus.

**Un critère « absence de données locales ».** Écarterait ~736 des ~882 candidats (§4).

**Un critère de forme du blob.** Laisserait les legacy de §1 cassés, sans rien gagner
en sûreté.

**L'ancrage de la condition 5 sur `_completion_marker.json`.** Fail-open sur le cas
re-crawl, détaillé au §4 — la raison d'être de la révision de cette spec.
