# Garde de fraîcheur sur le balayage destructeur `_reclean_archived_leftovers` — design

**Date** : 2026-08-10
**Service** : `crawler-service` (Python, RAG-HP-PUB `features/poc`)
**Statut** : design approuvé, non implémenté
**Périmètre** : le défaut de perte de données seul. Deux autres défauts mesurés le même jour sont
explicitement hors périmètre — §8.

---

## 1. Le problème

`_reclean_archived_leftovers` (`app/core/crawler_manager.py:4179`) supprime le sous-arbre Crawlee
d'un crawl archivé — `datasets/`, `request_queues/`, `key_value_stores/` sous
`{storage_path}/storage` — par `shutil.rmtree` via `_cleanup_local_data` (`:2713`). **Aucun retour
arrière.** Le reste du dossier de crawl (`crawler.log`, sidecars) est conservé.

Son prédicat, sept conditions (`:4208-4245`) : flag activé ∧ allowlist non-`None` ∧ statut du blob
`archived` ∧ le sous-arbre existe ∧ `str(crawl_id)` dans l'allowlist ∧ `crawl_id` hors
`active_prev_ids` ∧ âge du mtime du sous-arbre ≥ `ARCHIVED_RECLEAN_MIN_AGE_SECONDS`.

**Ce qu'il ne compare jamais : la fraîcheur du tar attesté face à celle de l'arbre qu'il efface.**
Son jumeau non destructeur la compare, lui (`archived_status_repair.py:82-85`).

### La chaîne qui perd des données

`archive_crawl` marque `archived` **sans re-tarrer** dans deux branches :

- **réutilisation idempotente d'un tar local** (`:2570-2578`) — un tar existe déjà sur place, on
  marque et on rend la main ;
- **fallback GCS** (`:2583-2594`) — `_retrieve_from_gcs_daemon` télécharge le tar, on lit sa
  taille, `cleanup_temp_download` **supprime le téléchargement**, on marque `archived`. La branche
  est documentée comme un rattrapage de crawls « legacy stuck at finished ».

Or une relance réutilise le **même crawl id**, et la clé GCS `crawls/{crawl_id}.tar.gz` est
exactement ce que l'allowlist énumère. D'où :

> domaine archivé → relancé sous le même id → nouveau dataset sur le disque → `/archive` → une des
> deux branches trouve l'**ancien** tar → `archived` → le sweep supprime le **nouveau** dataset,
> qui n'existe nulle part ailleurs.

L'allowlist ne protège pas de ça : elle atteste correctement qu'un tar existe — l'ancien. **Elle
autorise la suppression.**

C'est la classe du garde `.move-done` (spec du même jour) : *une preuve n'en est une que si elle
est plus récente que ce qu'elle prétend attester.*

### Pourquoi les deux branches produisent précisément la population que le sweep balaie

Les deux `return` avant le nettoyage local du chemin normal (`:2688`). Le sous-arbre survit donc à
l'archivage, et le blob dit `archived` : c'est la définition du candidat. Mesuré le 2026-08-10 :
**2495** dossiers `status=archived` portant encore un sous-arbre, sur 6769 (14/14 pages lues).

## 2. Ce qui rend le correctif simple

`_status_snapshot.json` **est déjà l'ancre « quand un tar a-t-il réellement été produit »**.

Il est écrit sur le vrai chemin d'archivage (`crawler_manager.py:2627`), que les deux branches
raccourci contournent par un `return` avant d'y arriver. `_mark_as_archived` n'y touche pas
(`:2729-2741` écrit `status`, `archived_at`, republie — pas de sidecar). L'autre occurrence à
`:1535` est une **lecture** (`get_status` préfère le snapshot au recalcul, utile justement quand
les datasets ont été supprimés). Restent deux écrivains de backfill dans `app/router/migration.py`
(`:412`, `:613`), qui créent le snapshot pour des crawls migrés — donc cohérents avec la
sémantique « un archivage a eu lieu ».

C'est exactement pour cette raison que la garde du jumeau fonctionne, et c'est l'ancre qui manque
au sweep. **Aucune écriture nouvelle, aucun champ nouveau** : les 2495 arbres existants sont
protégés dès le déploiement.

### `archived_at` est disqualifié

`_mark_as_archived` le réécrit dans **les deux** branches raccourci. Il dit donc « à l'instant »
précisément dans le cas dangereux, où le tar est vieux. Un garde fondé sur lui serait trompé par
construction.

### Enregistrer l'horodatage du tar : inutile

Envisagé puis écarté. Il faudrait écrire un champ à l'archivage, ce qui ne protégerait que les
archivages **futurs** et laisserait les 2495 existants dehors. Le snapshot rend ce champ superflu.

## 3. Le mécanisme

Une fonction pure partagée dans `app/core/archived_status_repair.py` — pas un contrôle recopié dans
le sweep.

**La raison n'est pas l'esthétique DRY : la cause du défaut est que les deux passes portaient des
gardes divergentes.** Un prédicat partagé rend la divergence structurellement impossible. Le module
est déjà pur, documenté et testé.

Le jumeau distingue deux motifs de rejet que son dry-run compte séparément. Le partagé rend donc un
**verdict**, pas un booléen :

```python
def archive_freshness_verdict(log_mtime: Optional[float],
                              snapshot_mtime: Optional[float]) -> Optional[str]:
    """NO_SNAPSHOT / RUN_AFTER_ARCHIVE, ou None quand le tar est postérieur à l'arbre."""
```

- `snapshot_mtime is None` → `NO_SNAPSHOT`
- `log_mtime is None` → `RUN_AFTER_ARCHIVE`
- `log_mtime >= snapshot_mtime` → `RUN_AFTER_ARCHIVE`
- sinon → `None`

Ce sont les **constantes existantes** du module (`archived_status_repair.py:19-20`), pas de nouvelles
chaînes : le dry-run du repair compte déjà ces deux motifs par ces noms, et le sweep doit les
nommer pareil pour que les deux passes se lisent ensemble.

`classify` retourne ce verdict tel quel à la place de ses conditions 4 et 5 actuelles (`:82-85`).
**Zéro changement de comportement pour le repair** — c'est le critère d'acceptation du refactor, et
il se vérifie par le fait que sa suite existante passe inchangée.

Le sweep appelle la même fonction : verdict non-`None` ⇒ ne pas supprimer, et compter.

## 4. Table de décision

| `snapshot_mtime` | `log_mtime` | verdict | le sweep |
|---|---|---|---|
| absent | — | `no_snapshot` | ne supprime pas |
| présent | absent | `run_after_archive` | ne supprime pas |
| présent | **>** snapshot | `run_after_archive` | ne supprime pas |
| présent | **=** snapshot | `run_after_archive` | ne supprime pas |
| présent | **<** snapshot | `None` | supprime, si les autres conditions passent |
| illisible (`OSError` ≠ `FileNotFoundError`) | — | — | ne supprime pas (§6) |

Le `>=` est strict par choix, comme le garde `.move-done` : l'égalité est inatteignable en pratique
à la résolution du float, et l'erreur penche du côté sûr.

Les trois cas de refus portent le même principe : **l'absence de preuve n'est pas une preuve.**

## 5. Où le garde s'insère

Après `active_prev_ids`, **avant** le contrôle d'âge existant.

L'ordre est un choix d'observabilité, pas de performance. Les deux conditions doivent passer, donc
l'ordre ne change pas le résultat — mais si l'âge rejetait d'abord, les cas dangereux rejetés par
l'âge ne seraient jamais comptés comme dangereux. **On veut que la synthèse compte tout cas où O1
aurait frappé**, y compris ceux qu'une autre condition aurait de toute façon sauvés.

Le coût est deux `os.stat` par candidat, après les conditions gratuites. C'est le même arbitrage que
le repair documente explicitement (`:4113-4119`) : les contrôles libres et l'appartenance à
l'allowlist d'abord, l'I/O ensuite.

Lecture des deux mtimes : `_mtime_or_none` sur `{storage_path}/_status_snapshot.json` et
`{storage_path}/crawler.log`, comme le repair (`:4125-4127`).

## 6. Les `None` et les erreurs

`_mtime_or_none` (`:83-92`) rend `None` sur `FileNotFoundError` et **laisse remonter tout autre
`OSError`** — « unreadable » n'est pas « absent ».

Le sweep reprend le traitement explicite du repair (`:4128-4132`) : `except OSError` → log
d'avertissement → `continue`. Formulation du repair, « skipping, not rejecting », qui pour le sweep
veut dire « on ne supprime pas ».

Un `try/except Exception` par item existe déjà autour du corps du sweep (`:4216`, `:4242-4244`) et
ferait déjà `continue`, donc le fail-closed est acquis même sans ce bloc. **On l'écrit quand même
explicitement** : un fail-closed accidentel que personne ne sait accidentel se casse au premier
refactor qui déplace le `try`.

## 7. Observabilité

Pas de log par item : la population candidate se compte en milliers, et le sweep saute déjà
`not in verified` en silence pour cette raison (`:4224`).

Une **ligne de synthèse par tick**, à côté du `return recleaned` :

```
ARCHIVED_LEFTOVER_RECLEAN_SUMMARY actioned=N skipped_tree_newer=X skipped_no_snapshot=Y
```

Chaque `skipped_tree_newer` est un cas où la chaîne du §1 aurait frappé. C'est ce qui rend le garde
vérifiable au lieu de simplement présent.

**Limite assumée** : le court-circuit flag-off (`:4208-4209`) rend `0` avant tout calcul, donc
cette synthèse ne dit rien **avant** l'armement. Le sweep n'a pas de dry-run, contrairement au
repair (`GET /admin/archived-status-repair`). Concrètement, le premier armement s'observe à
`ARCHIVED_RECLEAN_MAX_PER_TICK` = 3 suppressions par tick (~550 s mesuré, soit ~471/jour), en lisant
la synthèse entre deux ticks. Un dry-run rendrait l'armement calme au lieu de surveillé — §8.

## 8. Hors périmètre

**Le défaut de navigabilité de l'arbre restauré.** `tar.extractall` restitue les mtimes de
l'archive, donc un arbre extrait il y a dix secondes depuis un tar de trente jours se déclare vieux
de trente jours et la grâce de 24 h ne le protège pas — alors que la docstring du sweep
(`:4196-4198`) dit exactement le contraire de son intention. **Ce n'est pas une perte de données** :
ce qui disparaît est une copie, le tar l'a toujours, on re-restaure. Le correctif demande
d'horodater l'extraction elle-même, donc de toucher un autre chemin. Autre spec, autre gravité.

**Le trou du garde `active_prev_ids`.** Il n'admet que les blobs Redis `starting` / `running` /
`restarting_oom` / `stopping` (`:3730`, `:3740-3742`). Une MAJ `PENDING` côté BO n'a pas encore de
blob, donc n'y entre jamais — mesuré le 2026-08-10 : 1134 `PENDING` contre 9 `RUNNING`. Mais la mise
en file MAJ pose `est_archiver = 0` (`fonctions_maj_crawling.php:295-306`), donc **une allowlist
régénérée après coup exclut déjà ces domaines**. Le trou est masqué par la fraîcheur de la liste,
pas fermé : il ne se rouvre que si un domaine est `est_archiver = 1` à la génération **et** devient
le précédent d'une MAJ dans la même fenêtre. Consigné comme risque résiduel borné plutôt que traité
par un mécanisme spéculatif.

**Un dry-run pour le sweep.** Un endpoint de plus, sans rapport avec le garde. Recommandé comme
suivi : c'est ce qui manque pour que l'armement soit une décision et non une surveillance.

**Retourner le défaut de code `ARCHIVED_RECLEAN_ENABLED = True`** (`config.py:110`). Les deux portes
sont désormais épinglées à `false` dans un `environment:` versionné (`73b08cb7`), ce qui couvre le
chemin de déploiement réel. Retourner le défaut reste recommandé pour les exécutions qui ne passent
pas par ce compose — autre changement, autre décision.

## 9. Tests

**Le prédicat en table** : snapshot absent · `crawler.log` absent · log postérieur · **log égal**
(la strictesse) · log antérieur.

**La neutralité du refactor** : la suite existante de `archived_status_repair` passe **sans
modification**. Si un seul de ses tests bouge, le comportement du repair a changé, ce qui n'est pas
le sujet.

**La chaîne du §1, de bout en bout** : blob `archived`, snapshot vieux, `crawler.log` récent →
`_cleanup_local_data` **n'est pas appelé**. C'est le test qui aurait attrapé le défaut, et le seul
dont l'échec signifie « le bug est revenu ».

**Le complément qui empêche un garde trop zélé** : log antérieur au snapshot → `_cleanup_local_data`
appelé une fois. Sans lui, un garde qui refuse tout passerait pour correct.

Style : `tmp_path` et `settings` monkeypatché, comme `tests/test_auto_stash_archive_move.py`.

## 10. Déploiement

Rebuild Docker de `crawler-service`. **Aucun flag** : le garde ne peut rendre le sweep que plus
prudent, son seul effet possible est une suppression en moins. Aucun changement de script hôte,
aucun redémarrage de daemon, aucune migration, aucun BO.

Le garde est **inerte au déploiement** : `ARCHIVED_RECLEAN_ENABLED` vaut `false` et l'allowlist est
absente du volume, donc le sweep ne tourne pas. Il n'a d'effet qu'au moment où l'armement sera
décidé — ce qu'il rend précisément moins dangereux.

## 11. Écarté pendant l'analyse, et pourquoi

**Une incohérence de type apparente entre `str(crawl_id) not in verified` (`:4223`) et
`crawl_id in active_prev_ids` (`:4225`).** Vérifié : `start_crawl` annote `crawl_id: str` et
`previous_crawl_id` passe par `os.path.join`, donc les deux sont des chaînes et le `str()` est
défensif. **Ce n'est pas un défaut** — à ne pas re-signaler.

**`archived_at` comme ancre de fraîcheur** — §2, trompé par construction dans le cas dangereux.

**Enregistrer l'horodatage du tar à l'archivage** — §2, rendu superflu par le snapshot et sans effet
sur les 2495 existants.
