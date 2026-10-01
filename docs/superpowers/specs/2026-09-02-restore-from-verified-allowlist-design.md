# Restaurer un crawl de référence quand son blob Redis a disparu mais que son archive est vérifiée dans GCS

**Date** : 2026-09-02
**Service** : `crawler-service`
**Statut** : spécifié, non implémenté

## Le défaut

Une MAJ en mode update exige que les données du crawl de référence soient sur disque. Quand elles
n'y sont pas, deux mécanismes existent pour les ramener — et **tous deux dépendent d'un état en
mémoire, aucun ne regarde GCS ni le disque en dernier recours** :

| Mécanisme | Condition d'entrée | Devient aveugle si |
|---|---|---|
| `_repair_archived_status` (bascule `finished` → `archived`) | le blob porte `status == "finished"` (`crawler_manager.py:3775`) | le blob est **absent**, ou n'a **pas** de champ `status` |
| `_restore_previous_crawl` (téléchargement GCS) | `prev_status == "archived"` **ou** `stashed_at` | `prev_status` vaut `None` |

⇒ **Blob Redis perdu ⇒ ni bascule ni restauration ⇒ impasse définitive**, alors que l'archive est
intacte dans GCS et listée dans l'allowlist vérifiée.

La MAJ rejoue alors un 400 à chaque tentative, indéfiniment, et rien dans le système ne peut la
sortir de là — seule une extraction manuelle du tar y parvient.

## La mesure qui motive le lot

Le 2026-09-02, sur les 14 crawls de référence des MAJ relancées :

| blob | `status` | datasets | Domaines | Verdict |
|---|---|---|---|---|
| oui | `archived` | présents | 4 | ✅ le 400 est inatteignable |
| oui | `archived` | absents | 8 | ✅ se restaure seul (chemin GCS ouvert) |
| **absent** | — | **présents** | 1 (`3171`) | ✅ passe : `has_local_data` vrai, et le répertoire existant fait sauter la branche « ni blob ni répertoire » |
| **absent** | — | **absents** | 1 (`4688`) | ⛔ **impasse** |

**2 sur 14 avaient perdu leur blob** ; l'un s'en sortait grâce à ses datasets survivants, l'autre non.
L'allowlist GCS listait **les 14** — elle prouvait que le tar existait, et cela ne servait à rien.

`4688` a été débloqué à la main, par la même procédure que `7046` le 2026-09-01 : extraire
`<id>.tar.gz` dans `/app/storage/<id>/`. **Deux interventions manuelles en deux jours** pour un
état que le code peut reconnaître seul.

## Le comportement visé

Une troisième voie, entre la restauration existante et le rejet : **quand les données manquent et
que l'identifiant du crawl de référence figure dans l'allowlist GCS vérifiée, tenter la
restauration** au lieu de rejeter.

### Frontière — le seul cas qui change

| Scénario | Aujourd'hui | Après |
|---|---|---|
| `archived` ou stashé, pas de données | restauration GCS | **inchangé** |
| `prev_status == "failed"` | 400 | **inchangé** — ne jamais ressusciter un crawl en échec |
| Données présentes | la MAJ part | **inchangé** |
| Pas de données, **id dans l'allowlist** | ⛔ 400, impasse | ✅ **restauration tentée** |
| Pas de données, **id absent de l'allowlist** | 400 | **inchangé** — l'archive n'existe pas, le rejet est juste |
| Pas de données, **allowlist absente du disque** | 400 | **inchangé** — fail-closed |

Le cas mesuré qui reste légitimement rejeté est `3559` (`gilles-morel.com`) : son tar **n'est pas**
dans GCS, ses données sont perdues, et le 400 est la bonne réponse.

## Point d'accroche

`crawler_manager.py`, dans `start_crawl`, la branche de rejet actuelle :

```python
stashed = bool(prev_job_info.get("stashed_at")) if prev_job_info else False
if (prev_status == "archived" or stashed) and not has_local_data:
    ... _restore_previous_crawl(...)
elif not has_local_data:
    ... raise HTTPException(400, ...)      # <-- la nouvelle voie s'insère AVANT ce rejet
```

La condition ajoutée s'évalue **uniquement** sur le chemin `not has_local_data`, donc elle
n'introduit aucun coût sur le chemin nominal.

## Décisions de conception

**① Appeler `_restore_archived_crawl(previous_crawl_id)`, pas `_restore_previous_crawl(prev_job_info, …)`.**
La seconde dispatche sur les champs du blob (`stashed_at`, `status`) — or ici le blob est **absent**.
La première ne prend que l'identifiant, et c'est exactement ce dont on dispose. Elle porte déjà son
verrou Redis (`restore_lock:<id>`) et son attente d'une restauration concurrente : rien à ajouter
pour la concurrence.

**② Fail-closed sur l'allowlist.** `_load_reclean_allowlist()` rend `None` quand le fichier est
absent. Dans ce cas, **ne rien tenter** et retomber sur le 400 existant. Le comportement actuel est
ainsi préservé à l'octet sur toute installation sans allowlist.
⚠ Un ensemble **vide** n'est pas `None` : « l'allowlist existe et ne contient rien » est un état
valide qui doit rejeter, pas planter.

**③ Ne pas toucher au rejet `prev_status == "failed"`**, qui est évalué plus haut et reste
prioritaire. Un crawl explicitement en échec ne doit pas être ressuscité par cette voie.

**④ L'échec de restauration reste un 503, pas un 400.** `_restore_archived_crawl` lève sur
téléchargement impossible ; la branche existante mappe cela en 503 avec rollback de la réservation.
La nouvelle voie réutilise ce traitement.
⚠ **Changement de code observable** : un crawl aujourd'hui rejeté en **400** pourra désormais
échouer en **503** si son tar a été supprimé de GCS après la génération de l'allowlist. C'est une
information plus juste (« je devais pouvoir, je n'ai pas pu ») mais elle change ce que lit
l'opérateur. À mentionner dans la procédure de MEP.

**⑤ Journaliser la voie empruntée.** Le message doit dire que la restauration part **sur la foi de
l'allowlist** et non d'un statut, sinon un lecteur du log croira que le blob existait :
```
Update crawl '<id>' : previous crawl '<prev>' has no blob and no local data, but its archive is
verified in GCS (allowlist) — attempting restore.
```

## Ce que le lot ne fait PAS

⛔ **Il ne recrée pas le blob Redis manquant.** Après restauration, `has_local_data` devient vrai et
la MAJ part ; le blob reste absent. Conséquence assumée : un nettoyage ultérieur peut re-supprimer
ces données, et le cas se reproduira — au prix d'une restauration automatique, plus d'une
intervention manuelle. Recréer le blob serait un lot distinct, avec sa propre question (quel
`status` écrire, et qui en devient responsable).

⛔ **Il ne traite pas la cause de la perte du blob.** Pourquoi `crawl_job:4688` et `crawl_job:3171`
ont disparu n'est pas établi — éviction Redis, nettoyage, ou autre. Ce lot rend la perte
**récupérable**, il ne l'empêche pas.

⛔ **Il ne rend pas l'allowlist auto-générée.** Elle reste produite par
`tools/verify_archives_in_gcs.sh`, à la main. Une allowlist périmée fait simplement retomber sur le
comportement actuel pour les archives récentes.

## Vérification

Suite `pytest` du service (base actuelle : **440 passés**, plus l'échec préexistant et lié à la
plateforme `test_archive_mock_e2e::TestArchiveMockE2E::test_daemon_logic`).

Cas à couvrir, tous sur le chemin `not has_local_data` :

| Cas | Attendu |
|---|---|
| allowlist **absente** (`None`) | 400 inchangé, aucune tentative de restauration |
| allowlist **vide** | 400 inchangé |
| id **hors** allowlist | 400 inchangé |
| id **dans** l'allowlist, blob absent | `_restore_archived_crawl` appelé une fois avec le bon identifiant |
| restauration qui lève | 503, et la réservation est rollbackée |
| `prev_status == "failed"`, id dans l'allowlist | **400**, la nouvelle voie ne s'applique pas |
| données présentes | aucun appel à l'allowlist ni à la restauration |

⚠ **Le test qui compte est le premier** : il épingle une **absence** (aucune tentative sans
allowlist). Un test qui ne vérifierait que le cas heureux passerait tout aussi bien avec une
condition fail-**open**, qui est précisément le défaut à ne pas introduire.

## Déploiement

Reconstruction d'image obligatoire — `crawler-service` n'a aucun bind-mount de source
(`docker-compose.yml:1404-1405` monte le volume nommé `crawler_data`, jamais la source). `./tools/build_crawler.sh --up 7`.
Aucune migration, aucun drapeau nouveau : la voie est gouvernée par la seule présence de
l'allowlist, déjà en place.
