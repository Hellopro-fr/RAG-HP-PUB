# Garde de fraîcheur sur le marqueur `.move-done` — design

**Date** : 2026-08-10
**Service** : `crawler-service` (Python, RAG-HP-PUB `features/poc`)
**Statut** : design approuvé, non implémenté
**Périmètre** : le garde seul. Pas de détecteur des crawls déjà touchés (décision utilisateur).

---

## 1. Le problème

`_move_stash_to_archive` (`app/core/crawler_manager.py:2372`) pilote le déplacement GCS
`stash/{id}.tar.gz` → `crawls/{id}.tar.gz` par échange de fichiers avec le daemon hôte : il écrit
un `.move-request`, attend un `.move-done`, puis marque le blob `archived` et efface `stashed_at`.

À `:2388` il **saute entièrement le déplacement** si un `.move-done` préexiste :

```python
if not os.path.exists(done_path):
    # écrit la requête, attend .move-done / .move-error
else:
    logger.info("Reconciling pre-existing .move-done ...")
await self._mark_as_archived(crawl_id)
```

Ce saut est **volontaire et utile** : `MOVE_TIMEOUT_SECONDS` vaut 600 s et nginx coupe `/crawler/`
à 600 s également, donc le daemon peut terminer le déplacement après le départ de l'appelant. La
tentative suivante retrouve le marqueur et réconcilie au lieu de rejouer.

**Le défaut** : le marqueur s'appelle `{id}.move-done`, sans aucune trace de la tentative qui l'a
produit. Il ne distingue pas « ma tentative, coupée à l'instant » de « une tentative d'il y a
quatre mois ». Le chemin heureux nettoie bien les trois marqueurs (`:2431-2434`), mais une
tentative interrompue avant ce nettoyage laisse un orphelin.

**Conséquence.** Un crawl re-stashé puis ré-archivé alors qu'un orphelin périmé traîne voit son
déplacement sauté : le tar reste sous `stash/` pendant que Redis dit `archived`. `/results` prend
alors sa branche archivée et va chercher dans `crawls/` — où il n'y a rien. Et la condition
« id dans l'allowlist `crawls/` » de `_repair_archived_status` échoue aussi, donc la passe de
réparation ne le rattrape pas.

**Mesuré le 2026-08-10** via `GET /admin/daemon-state` : `move_results` contient **396**
`.move-done` orphelins, du plus récent (1,8 jour) au plus vieux (27 jours). La mèche est allumée.

**Ce que ce bug n'a PAS causé.** Les 4 archives introuvables du même jour (1427, 1933, 3559, 4066)
ne viennent pas de là : ce mécanisme laisserait le tar sous `stash/`, et il n'y est pas. Voir
`project_archives_gcs_manquantes_et_move_done` — cause inconnue, investigation close, sept
mécanismes écartés.

## 2. Le mécanisme retenu

Un prédicat au niveau module dans `crawler_manager.py`, à côté de `_mtime_or_none` :

```python
def _move_done_is_fresh(done_mtime: Optional[float], stashed_at: Optional[str]) -> bool:
```

Vrai **seulement si** les deux valeurs sont présentes et que
`done_mtime > _parse_iso_naive_utc(stashed_at)` (strictement).

Pas de module pur séparé, contrairement à `archived_status_repair.py` : six lignes, **un seul
consommateur**, et la dépendance `_parse_iso_naive_utc` (`:95`) vit déjà dans ce fichier. Un module
partagé se justifiait là-bas parce que deux consommateurs devaient rester d'accord ; ici il n'y a
rien à désynchroniser. La fonction reste testable directement — `crawler_manager.py` s'importe sans
difficulté dans la suite locale.

### Pourquoi supprimer, et pas seulement « ne pas honorer »

Le marqueur est testé à **deux** endroits : le saut initial (`:2388`) et la boucle d'attente
(`:2405`). Ne pas l'honorer au premier test tout en le laissant sur le disque déplacerait le bug de
trois lignes : la boucle le verrait immédiatement et sortirait dessus.

Donc un marqueur jugé périmé est **supprimé avant le `if` existant**. Une suppression rend les deux
tests corrects, et aucun des deux n'a besoin de connaître la notion de fraîcheur — la logique
existante reste inchangée.

### Pourquoi la comparaison de dates plutôt qu'un jeton

Un jeton écrit dans la requête et renvoyé par le daemon dans le marqueur serait une identité plus
forte, immunisée à toute question d'horloge. Il exigerait de modifier `tools/download_daemon.sh`
(script **hôte**) et de **redémarrer le daemon**, les deux couches devant être déployées ensemble :
pendant la fenêtre « nouveau Python / ancien daemon », aucun marqueur ne porterait de jeton, donc
aucun ne serait honoré, et le filet anti-504 disparaîtrait. Cela demanderait un chemin de
compatibilité pour un gain invisible ici.

Un jeton dans le **nom** du marqueur (`{id}.{token}.move-done`) semble éviter de toucher au daemon,
puisqu'il dérive le nom du marqueur de celui de la requête. Mais il dérive aussi le `crawl_id` du
même nom (`download_daemon.sh:78`) et le réutilise pour construire `gs://…/$crawl_id.tar.gz` : le
jeton corromprait les chemins GCS. Écarté pour cette raison, pas par préférence.

### Pourquoi la date du fichier est digne de confiance ici

Le mtime vient du `touch` du daemon sur le répertoire de résultats, `stashed_at` de
`datetime.utcnow()` dans le conteneur. Ce répertoire est un **bind mount sur le même hôte**
(`docker-compose.yml:1361`,
`./apps-microservices/crawler-service/crawler_move_results:/app/gcs-move-results`), donc même
horloge noyau : pas de dérive à compenser. (Ne pas confondre avec le volume des archives,
`:1352` — les marqueurs de déplacement ne vivent pas là.)

Le seul cas ambigu est un stash et un archivage dans la **même seconde**, qui se lirait comme
« périmé ». On supprime alors un marqueur légitime, on re-demande, et le daemon rejoue son chemin
idempotent (`elif gcloud storage ls "$dst"`, `download_daemon.sh:86-91`) : résultat correct au prix
d'un aller-retour. **L'erreur penche du bon côté**, ce qui justifie le `>` strict plutôt qu'un `>=`
qui honorerait un marqueur de la même seconde.

## 3. Tableau de décision

| marqueur | `stashed_at` | action |
|---|---|---|
| absent | — | flux normal : requête puis attente |
| présent, mtime **>** `stashed_at` | présent | honoré — réconciliation du 504, inchangée |
| présent, mtime **≤** `stashed_at` | présent | **périmé** → suppression, log WARNING, flux normal |
| présent | absent, vide ou non parsable | **périmé** → même traitement |
| présent, mtime illisible (`OSError` autre que `FileNotFoundError`) | — | **périmé** → même traitement |
| `FileNotFoundError` au `getmtime` | — | le marqueur a disparu entre le test d'existence et le `stat` (course avec un autre réplica ou avec le daemon) → traité comme **absent**, flux normal |

La quatrième ligne porte le principe directeur : **l'absence de preuve n'est pas une preuve**. Sans
`stashed_at`, on ne peut pas établir qu'un marqueur nous appartient, donc on ne l'honore pas. C'est
la même règle que le `log_mtime is None → rejeté` de
`docs/superpowers/specs/2026-08-07-archived-status-repair-design.md`, et la même famille de bug :
*une preuve n'en est une que si elle est plus récente que ce qu'elle prétend attester.*

### Le cas « périmé mais indélébile »

Si la suppression échoue, continuer marquerait `archived` sans déplacement — exactement le bug.
On lève donc un **502** avec un code distinct et diagnosticable :

```json
{"detail": {"error_code": "STASH_MOVE_STALE_MARKER"}}
```

Un marqueur non supprimable dans le répertoire de résultats est un problème d'infrastructure, pas
une situation à contourner. `_mark_as_archived` ne doit pas être appelé sur ce chemin.

## 4. Les 396 orphelins existants : on n'y touche pas

Chacun sera supprimé comme périmé au premier archivage de son id. Ceux dont le crawl n'est jamais
ré-archivé resteront — fichiers de 0 octet, dont `GET /admin/daemon-state` rapporte déjà le compte,
donc la population reste observable.

Un nettoyage en masse serait **activement nuisible** : supprimer le marqueur d'un crawl dont
l'appelant est en train d'attendre ferait échouer son attente en 504 alors que le déplacement avait
réussi. C'est le filet anti-504 qu'on retirerait. Le garde rend ces orphelins inoffensifs ; les
balayer les rendrait dangereux.

## 5. Tests

**Le prédicat, en table** — marqueur absent ; marqueur récent ; marqueur périmé ; `stashed_at`
absent ; `stashed_at` non parsable ; **horodatages égaux → périmé** (le `>` strict).

**`_move_stash_to_archive`, quatre comportements** :

| cas | attendu |
|---|---|
| marqueur périmé | supprimé, requête écrite, attente normale |
| marqueur récent | honoré, **aucune requête écrite**, `_mark_as_archived` appelé une fois |
| `stashed_at` absent | traité comme périmé |
| périmé indélébile | 502 `STASH_MOVE_STALE_MARKER`, et **`_mark_as_archived` NON appelé** |

La dernière assertion est celle qui compte : l'appeler serait précisément le bug qu'on ferme.

**Test existant à mettre à jour** : `test_move_success_marks_archived`
(`tests/test_auto_stash_archive_move.py:45-54`) pré-crée un `70.move-done` puis appelle
`_move_stash_to_archive({"crawl_id": "70"})` **sans `stashed_at`**, et vérifie que
`_mark_as_archived` est appelé. Sous le garde, ce cas devient « périmé » — à raison. Le test doit fournir un
`stashed_at` antérieur au marqueur pour continuer d'épingler le chemin 504. En production
`archive_crawl` ne prend cette branche que si `stashed_at` est vrai (`crawler_manager.py:2451`),
donc exiger le champ ne restreint aucun appel réel.

## 6. Déploiement

Rebuild Docker de `crawler-service`. **Aucun** changement du script hôte, **aucun redémarrage de
daemon**, aucune migration, aucun changement BO.

**Pas de flag**, contrairement à la convention du dépôt pour ce qui touche l'archivage. Le garde ne
peut rendre le code que plus prudent : son seul effet possible est une requête de déplacement en
trop, jamais une de moins. Un flag signifierait « garder la possibilité d'honorer un marqueur
périmé », c'est-à-dire garder le bug disponible. Il n'y a rien à pouvoir éteindre.

## 7. Hors périmètre

**Le détecteur des crawls déjà touchés** (blob `archived`, tar resté sous `stash/`). Décision prise
de livrer le garde seul. Un tel détecteur demanderait un listing GCS, or le conteneur n'y a pas
accès : ce serait un script hôte de plus. On ne sait pas encore s'il existe des crawls dans cet
état — les 4 archives introuvables du 2026-08-10 ont été vérifiées et n'en relèvent pas.

**Le nettoyage des orphelins** — §4, délibérément écarté.

**La question ouverte des 4 archives introuvables** — autre sujet, investigation close faute de
piste, consignée dans `project_archives_gcs_manquantes_et_move_done`.
