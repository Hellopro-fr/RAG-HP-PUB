# Crawler — F2/F3/F8 : /results 400-running, hygiène blob, compteurs stash — design

**Date :** 2026-06-12
**Statut :** validé (brainstorm, approche A)
**Branche :** `features/poc`, service `apps-microservices/crawler-service`.
**Référence :** audit BO `Marketplace/docs/superpowers/audits/2026-06-10-incident-results-400-running-7-domaines-bloques.md` (§5, §9). Spec sœur BO : `Marketplace/docs/superpowers/specs/2026-06-12-bo-f1-f5-f9-f4-sync-failure-design.md`. F6/F7 en stand-by (décision 2026-06-12).

## 1. Problème

1. **F2 (cause primaire)** : le blob Redis `crawl_job:{id}` indique encore
   `status="running"` quand le BO consomme `GET /results` < 1 s après le webhook succès
   → `get_results_archive` → 400 « Cannot get results for a running crawl. » Prouvé
   live (sonde 366 ms) ; pour certains blobs le `running` persiste 1 h 30+
   (mécanisme interne exact = F6, stand-by). `cache_service.set_json` avale toutes les
   exceptions (fail-open) — une écriture perdue est silencieuse.
2. **F3** : `start_crawl` sur un crawl_id réutilisé ne purge pas l'état gen-1 du blob :
   `stashed_at` périmé → `/results` unstash un tar GCS obsolète et ÉCRASE les données
   fraîches (constaté 6430/6690, tars du 23/05) ; `*_request_id` hérités → la dédup
   PW-A côté BO absorbe les webhooks de la nouvelle génération (fenêtre 48 h) ;
   `_completion_marker.json` gen-1 sur disque → `get_job_or_recover` peut mal typer.
3. **F8** : le flux stash REMET À ZÉRO `urls_crawled`/`error_urls_crawled`/`last_activity`
   du blob → tout re-trigger BO construit depuis `/status` envoie 0 → downgrade
   `insufficientData` → DSPI=9 à tort. Prouvé 3× en prod. **Code de zérotage pas encore
   localisé** (mécanisme inféré des données).

## 2. F2 — race finalize/webhook, deux couches

### Couche A — write-then-verify dans `_monitor_process`

Après l'écriture terminale (`job_info["status"]=final_status` + `set_json`) et AVANT
la création de la task webhook :

```python
persisted = await cache_service.get_json(job_key)
if not persisted or persisted.get("status") != final_status:
    logger.error(f"Finalize write lost for '{crawl_id}' (read-back={persisted.get('status') if persisted else None}); rewriting")
    await cache_service.set_json(job_key, job_info)
    persisted2 = await cache_service.get_json(job_key)
    if not persisted2 or persisted2.get("status") != final_status:
        logger.critical(f"Finalize write STILL lost for '{crawl_id}' after rewrite — /results will 400 until reconcile heals")
```

- Couvre : écriture perdue silencieuse (set_json fail-open) et clobber concurrent
  entre l'écriture et le webhook.
- 1 read-back + au plus 1 rewrite : coût négligeable (2 ops Redis par fin de crawl).
- Ne couvre PAS un clobber postérieur au webhook → couche B.

### Couche B — tolérance dans `get_results_archive`

Au lieu du 400 inconditionnel sur `status=="running"` :

```python
if job_info.get("status") == "running":
    marker = os.path.join(job_info.get("storage_path", ""), "_completion_marker.json")
    if os.path.exists(marker):
        logger.warning(f"/results for '{crawl_id}': blob says running but completion marker exists — treating as finished (stale blob, F2)")
        job_info["status"] = "finished"   # heal en mémoire + persist
        await cache_service.set_json(f"{CRAWL_JOB_PREFIX}{crawl_id}", job_info)
    else:
        raise HTTPException(status_code=400, detail="Cannot get results for a running crawl.")
```

- Critère unique = marker (écrit par `_monitor_process` AVANT le webhook ; source
  de vérité disque). Pas de critère « finished_at posé + process mort » en plus —
  le marker suffit et reste le plus simple à raisonner ; un vrai crawl en cours n'a
  jamais de marker.
- Effet de bord assumé : heal du blob persisté (le même heal que le reconcile
  marker-check, appliqué au point de consommation).

## 3. F3 — hygiène du blob sur réutilisation de crawl_id

> **AMENDEMENT 2026-06-12 (CR-T3, vérification de scope)** : (1) le critère `dropdata is False`
> envisagé est VACUEUX — le schéma FastAPI (`schemas/crawler.py:73`) défaute `dropdata=False`
> pour tout start BO. Un premier critère `status == "stopped"` (`155edb02`) s'est révélé
> TROP ÉTROIT (revue utilisateur) : continuer un crawl `finished` est courant (limitDiez/
> limitQuestionMark/limitCrawl sortent en `finished`+isError ; traitement post-webhook cassé).
> **Règle finale (`4a805b94`) : porter `stashed_at` + exécuter le resume-on-start unstash pour
> TOUT statut gen-1, SAUF `params.dropdata` truthy (dropData=1 explicite = restart propre).**
> Sûreté : le danger tar-périmé (6430/6690) exige qu'un `stashed_at` survive NON CONSOMMÉ
> jusqu'au blob terminal gen-2 ; la reprise inconditionnelle le CONSOMME au start (unstash
> efface `stashed_at` + supprime le tar) ; en échec d'unstash, le start avorte (rollback) —
> aucun crawl ne tourne avec l'état périmé. (2) La purge du marker gen-1 existe DÉJÀ
> (`_cleanup_stale_state_for_relaunch`, appelée à chaque start ~L553) — non dupliquée, pinnée
> par test. (3) Les request_ids/compteurs gen-1 sont déjà écartés par la réécriture wholesale
> du blob au start. Update-mode (`_restore_previous_crawl`) non concerné (chemin séparé sur
> previousCrawlId). **Suivi (non bloquant)** : le rollback d'un unstash en échec SUPPRIME le
> blob (perte du pointeur stashed_at, tar orphelin → sweep) — restaurer `prior_job_info`
> serait plus sûr ; exposition élargie maintenant que finished/failed passent par l'unstash.

Site : `start_crawl`, au moment où le job_info de la nouvelle génération est construit
pour un crawl_id qui existait déjà en Redis (et/ou dont le storage existe).

Purge systématique (nouvelle génération = état neuf) :

| Clé | Raison |
|---|---|
| `stashed_at` | sinon `/results` unstash un tar GCS gen-1 et écrase les données fraîches |
| `downloaded_at` | sinon fenêtre stash 1 h héritée |
| `urls_crawled`, `error_urls_crawled`, `last_activity` | compteurs gen-1 |
| `failure_webhook_request_id`, `terminal_webhook_request_id` | sinon dédup PW-A BO absorbe les webhooks gen-2 pendant 48 h |
| `failure_cause`, `finished_at` (et tout champ terminal stampé) | cohérence d'état |
| disque : `_completion_marker.json` du storage réutilisé | sinon recovery/`/results` couche B mal typent la gen-2 |

- Implémentation : liste explicite de clés purgées (pas de « repartir d'un dict vide » —
  d'autres champs légitimes du start existant doivent survivre, ex. params).
  Le marker disque : `os.remove` best-effort (try/except log).
- NE PAS purger : `stash_lock` (verrou transverse, géré par son propre TTL).
- Tests (pytest, TDD) : start sur blob gen-1 portant chaque clé → blob gen-2 sans la clé ;
  marker supprimé ; champs params/callback préservés.

## 4. F8 — compteurs zérotés par le flux stash

**Tâche 1 — localisation (investigation, livrable = note dans le plan/commit) :**
candidats à instrumenter/lire : `stash_crawl` (réécriture du blob post-tar),
`_persist_status_snapshot`/écriture snapshot, reconstruction `get_job_or_recover`
(router : recovery sur perte de blob — re-crée sans compteurs), unstash.
Critère de fin : reproduire en test le passage compteurs non-nuls → 0.

**Tâche 2 — fix :** préserver `urls_crawled`/`error_urls_crawled`/`last_activity`
à travers stash → unstash → reconstruction. Si la reconstruction ne peut pas connaître
les vraies valeurs (blob perdu), elle ne doit PAS écrire 0 : omettre les clés
(le BO traite « clé absente » ≠ « 0 » depuis le parsing strict du récepteur).

**Test :** stash d'un job à compteurs connus → blob post-stash conserve les valeurs ;
reconstruction post-perte → clés absentes, pas 0.

## 5. Hors périmètre

- F6 (élucidation du running figé 1 h 30+ — besoin logs) : stand-by.
- F7 (persistance logs/rotation) : stand-by.
- Tout changement de contrat HTTP autre que la tolérance marker (couche B).

## 6. Risques

- **Couche B trop permissive ?** Non : marker uniquement écrit par `_monitor_process`
  à la terminaison réelle ; un crawl actif n'en a pas. Pire cas : marker gen-1 résiduel
  + blob gen-2 réellement running → faux « finished » — fermé par F3 (purge du marker
  au start). Ordre d'implémentation dans le même déploiement : F3 avec ou avant F2-B.
- **F3 et resume-on-start-unstash (design 06-04)** : le start actuel PRÉSERVE
  délibérément `stashed_at` pour la reprise d'un crawl stashé. À arbitrer au plan :
  purge inconditionnelle SAUF si le start est explicitement une reprise (param resume)
  — critère exact fixé après lecture du code start ; le danger documenté (écrasement
  gen-1) prime sur la reprise silencieuse.
- Concurrence : write-then-verify n'est pas un CAS — il réduit la fenêtre, F2-B la ferme
  au point de consommation. Suffisant sans introduire de lock Redis supplémentaire.

## 7. Vérification

- pytest TDD par tâche (conventions PW-A-CR : tests d'abord).
- Déploiement via le pipeline du service, ordre libre vs BO.
- Post-déploiement : SQL surveillance BO (audit §9) + absence de nouveaux mails
  `(HTTP 400, attempt …)`.
