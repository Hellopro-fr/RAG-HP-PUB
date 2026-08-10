# Garde de fraîcheur sur le balayage destructeur — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `_reclean_archived_leftovers` ne supprime plus le sous-arbre d'un crawl dont l'arbre local est plus récent que le tar attesté.

**Architecture:** La comparaison de fraîcheur que le jumeau non destructeur porte déjà (`archived_status_repair.classify`, conditions 4-5) devient une fonction pure partagée `archive_freshness_verdict` du même module. `classify` la réutilise **sans changer de comportement**, et le sweep l'appelle après `active_prev_ids` et avant son contrôle d'âge, en comptant ses refus dans une ligne de synthèse par tick. Aucune écriture nouvelle, aucun champ nouveau : l'ancre `_status_snapshot.json` existe déjà sur le disque pour les 2495 arbres concernés.

**Tech Stack:** Python 3.12, pytest + pytest-asyncio. Aucune dépendance ajoutée, aucun import nouveau (`archived_status_repair` est déjà importé dans `crawler_manager.py`, cf. son appel à `classify` à `:4136`).

**Spec:** `docs/superpowers/specs/2026-08-10-reclean-freshness-guard-design.md` (commit `a611c42f`).

**User decisions (already made):**
- Périmètre = le défaut de **perte de données seul**. La navigabilité de l'arbre restauré, le trou `active_prev_ids` sur les MAJ `PENDING`, un dry-run pour le sweep et le retournement du défaut de code `True` sont hors périmètre (spec §8).
- Le prédicat vit en **fonction pure partagée**, pas recopié dans le sweep — « la cause du défaut est que les deux passes portaient des gardes divergentes ».
- Le prédicat rend un **verdict** et non un booléen, pour que le repair garde ses deux motifs de rejet distincts.
- **Aucun flag** : le garde ne peut rendre le sweep que plus prudent.
- L'utilisateur contrôle push et déploiement : **ne jamais pousser**. Merge local no-ff dans `features/poc` au maximum.
- Langue des messages de commit pour ce dépôt : **both (EN + FR)**.

---

## File Structure

| Fichier | Responsabilité | Action |
|---|---|---|
| `app/core/archived_status_repair.py` | le prédicat pur partagé `archive_freshness_verdict`, et `classify` qui le réutilise à la place de ses conditions 4-5 (`:82-85`) | Modifier |
| `tests/test_archived_status_repair.py` | la table du prédicat ; les 15 tests existants doivent passer **inchangés** | Modifier |
| `app/core/crawler_manager.py` | l'appel du garde dans `_reclean_archived_leftovers` (`:4179`) et la ligne de synthèse par tick | Modifier |
| `tests/test_crawler_manager_reclean.py` | le helper `_make_archived_dir` rendu déterministe face au garde, plus les quatre tests de comportement | Modifier |

Le module reste **pur par construction** — c'est ce que sa docstring promet (« no I/O, no framework imports, every input a primitive gathered by the caller ») et ce qui le rend testable sans Docker ni Redis. La lecture des mtimes reste chez l'appelant.

**Deux tâches, dans cet ordre.** La tâche 1 est un refactor à neutralité prouvée : son commit a du sens seul, et le prédicat n'est pas du code mort puisque `classify` l'appelle immédiatement. La tâche 2 est le changement de comportement. Les fusionner mêlerait « extraire sans rien changer » et « changer quelque chose » dans un même diff, ce qui rend la neutralité invérifiable.

---

### Task 1: Prédicat partagé `archive_freshness_verdict`

**Goal:** Extraire la comparaison de fraîcheur des conditions 4-5 de `classify` en fonction pure réutilisable, sans changer le comportement du repair.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/archived_status_repair.py` (nouvelle fonction avant `classify:33` ; conditions 4-5 remplacées à `:82-85`)
- Test: `apps-microservices/crawler-service/tests/test_archived_status_repair.py`

**Acceptance Criteria:**
- [ ] `archive_freshness_verdict(log_mtime, snapshot_mtime)` existe au niveau module et rend les **constantes existantes** `NO_SNAPSHOT` / `RUN_AFTER_ARCHIVE` (`:22-23`), jamais de chaîne nouvelle.
- [ ] `snapshot_mtime is None` → `NO_SNAPSHOT`, et ce cas **précède** le test sur `log_mtime` (l'ordre est le contrat du dry-run : un blob est compté dans son PREMIER motif d'échec).
- [ ] `log_mtime is None` → `RUN_AFTER_ARCHIVE`.
- [ ] `log_mtime >= snapshot_mtime` → `RUN_AFTER_ARCHIVE` (`>=`, pas `>`).
- [ ] `log_mtime < snapshot_mtime` → `None`.
- [ ] `classify` retourne ce verdict tel quel à la place de ses conditions 4 et 5, et l'ordre global des sept motifs est inchangé.
- [ ] **Les 15 tests existants de `tests/test_archived_status_repair.py` passent sans qu'une seule ligne soit modifiée.** C'est le critère de neutralité.
- [ ] Le module reste sans I/O et sans import de framework.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_archived_status_repair.py -v` → 15 existants + 6 nouveaux passent, et `git diff` ne montre aucune modification des 15 existants.

**Steps:**

- [ ] **Step 1: Prendre la référence AVANT toute modification**

Un test vert qui ne couvre pas la surface modifiée ne prouve rien, et un contrôle sans référence ne distingue pas l'introduit du préexistant.

```bash
cd apps-microservices/crawler-service
python -m pytest tests/test_archived_status_repair.py -q 2>&1 | tail -3
python -m pytest tests/ -q 2>&1 | tail -3
```

Noter les deux compteurs. La suite complète porte **un échec préexistant connu** :
`tests/test_archive_mock_e2e.py::TestArchiveMockE2E::test_daemon_logic` (script bash sous Windows,
vérifié identique sur la base — ne pas le chasser).

- [ ] **Step 2: Écrire les tests du prédicat (rouge)**

Dans `tests/test_archived_status_repair.py`, ajouter **à la fin du fichier**. Le module est déjà importé en tête sous l'alias `asr` (`from app.core import archived_status_repair as asr`) — ne rien ajouter aux imports.

```python
def test_freshness_no_snapshot():
    """No snapshot means no local proof that a tar was ever produced."""
    assert asr.archive_freshness_verdict(1000.0, None) == asr.NO_SNAPSHOT


def test_freshness_no_log():
    """No crawler.log means no proof the crawl's activity predates the archive."""
    assert asr.archive_freshness_verdict(None, 1000.0) == asr.RUN_AFTER_ARCHIVE


def test_freshness_log_after_snapshot():
    assert asr.archive_freshness_verdict(1001.0, 1000.0) == asr.RUN_AFTER_ARCHIVE


def test_freshness_equal_timestamps_reject():
    """>= and not >: an archive and a crawl landing in the same clock tick must
    not authorise a deletion. Equality is unreachable in practice at float
    resolution, so the strictness costs nothing and the error leans safe."""
    assert asr.archive_freshness_verdict(1000.0, 1000.0) == asr.RUN_AFTER_ARCHIVE


def test_freshness_log_before_snapshot_is_clear():
    assert asr.archive_freshness_verdict(999.0, 1000.0) is None


def test_freshness_both_absent_reports_snapshot_first():
    """Order is the dry-run contract: a blob is counted in its FIRST failing
    bucket, so no-snapshot must win over no-log."""
    assert asr.archive_freshness_verdict(None, None) == asr.NO_SNAPSHOT
```

- [ ] **Step 3: Lancer pour vérifier que ça échoue**

Run: `python -m pytest tests/test_archived_status_repair.py -k freshness -v`
Expected: FAIL — `AttributeError: module 'app.core.archived_status_repair' has no attribute 'archive_freshness_verdict'`

- [ ] **Step 4: Écrire le prédicat**

Dans `app/core/archived_status_repair.py`, insérer **après le bloc de constantes** (qui se termine par `ARCHIVE_IN_PROGRESS = "archive_in_progress"` à `:32`) et **avant** `def classify(` (`:33`) :

```python
def archive_freshness_verdict(log_mtime: Optional[float],
                              snapshot_mtime: Optional[float]) -> Optional[str]:
    """NO_SNAPSHOT / RUN_AFTER_ARCHIVE, or None when the archive postdates the tree.

    `_status_snapshot.json` is written only on the real archiving path
    (crawler_manager.py:2627). archive_crawl's two shortcut branches — local-tar
    reuse (:2570-2578) and the GCS fallback (:2583-2594) — return before reaching
    it, and _mark_as_archived (:2729-2741) never touches it. Its mtime therefore
    answers "when was a tar actually produced", which is the only local evidence
    of the attested tar's age. `archived_at` cannot serve: _mark_as_archived
    rewrites it in BOTH shortcut branches, so it reads "just now" precisely when
    the tar is old.

    Both passes need this comparison and used to disagree about it: the repair
    rejected on it, the destructive sweep never checked at all. Sharing one
    predicate makes that divergence impossible to reintroduce — which is the
    actual cause of the data-loss defect, not a DRY preference.

    Returns the module's existing bucket constants rather than new strings: the
    repair's dry-run already counts these two by name, and the sweep's per-tick
    summary must agree with it.

    Missing evidence rejects — absence of proof is not proof. Equal timestamps
    reject too, for the same reason the .move-done guard uses a strict
    comparison: the error leans the safe way.
    """
    if snapshot_mtime is None:
        return NO_SNAPSHOT
    if log_mtime is None or log_mtime >= snapshot_mtime:
        return RUN_AFTER_ARCHIVE
    return None
```

`Optional` est déjà importé (`:10`). Ne rien ajouter aux imports.

- [ ] **Step 5: Lancer pour vérifier que ça passe**

Run: `python -m pytest tests/test_archived_status_repair.py -k freshness -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Faire réutiliser le prédicat par `classify`**

Dans `classify`, remplacer les conditions 4 et 5 (`:82-85`) :

```python
    if snapshot_mtime is None:
        return NO_SNAPSHOT
    if log_mtime is None or log_mtime >= snapshot_mtime:
        return RUN_AFTER_ARCHIVE
```

par :

```python
    freshness = archive_freshness_verdict(log_mtime, snapshot_mtime)
    if freshness is not None:
        return freshness
```

Rien d'autre ne change : ni les conditions 1-3 au-dessus, ni la condition 6 en dessous, ni la
docstring de `classify`, ni l'ordre d'évaluation. Le verdict rendu est identique pour toute entrée.

- [ ] **Step 7: Prouver la neutralité**

```bash
python -m pytest tests/test_archived_status_repair.py -q 2>&1 | tail -3
git diff --stat tests/test_archived_status_repair.py
```

Expected: 21 passés (15 existants + 6 nouveaux) et `git diff --stat` ne montre que des **insertions**
sur le fichier de test. Si une ligne existante apparaît en suppression, le comportement du repair a
changé — revenir au Step 6 au lieu d'ajuster le test.

- [ ] **Step 8: Committer**

Écrire le message dans un fichier **relatif** puis l'utiliser avec `-F`. Deux pièges de cette machine : `git commit -F- <<'EOF'` échoue (`error: could not read file '-'`), et un chemin POSIX absolu comme `/tmp/…` n'est pas compris par le git de Windows. Le fichier temporaire n'est jamais mis en index puisque le `git add` nomme explicitement ses fichiers, et il est supprimé juste après.

```bash
cd apps-microservices/crawler-service
cat > commit_msg.txt <<'MSG'
refactor(archivage): extraire la comparaison de fraicheur en predicat partage / extract the freshness comparison into a shared predicate

Les conditions 4-5 de classify deviennent archive_freshness_verdict, fonction
pure du meme module rendant les constantes existantes NO_SNAPSHOT /
RUN_AFTER_ARCHIVE. classify la reutilise : verdict identique pour toute entree,
ordre d'evaluation inchange, et les 15 tests existants passent sans qu'une
ligne soit modifiee -- c'est le critere de neutralite de ce commit.

Motif : le balayage destructeur _reclean_archived_leftovers ne porte AUCUNE
comparaison de fraicheur alors que son jumeau non destructeur en porte une. La
cause du defaut est cette divergence, pas une duplication a factoriser. Un
predicat partage la rend structurellement impossible a reintroduire. Le
branchement du sweep vient dans le commit suivant.

Le module reste pur : aucune I/O, aucun import de framework, la lecture des
mtimes reste chez l'appelant.

--

classify's conditions 4-5 become archive_freshness_verdict, a pure function in
the same module returning the existing NO_SNAPSHOT / RUN_AFTER_ARCHIVE
constants. classify reuses it: identical verdict for every input, evaluation
order unchanged, and the 15 existing tests pass without a single line edited --
that is this commit's neutrality criterion.

Why: the destructive sweep _reclean_archived_leftovers carries NO freshness
comparison while its non-destructive twin does. The defect's cause is that
divergence, not duplication waiting to be factored out. One shared predicate
makes it structurally impossible to reintroduce. Wiring the sweep comes in the
next commit.

The module stays pure: no I/O, no framework imports, mtime reads remain the
caller's job.
MSG
git add app/core/archived_status_repair.py tests/test_archived_status_repair.py
git commit -F commit_msg.txt
rm commit_msg.txt
```

---

### Task 2: Brancher le garde dans le sweep et compter ses refus

**Goal:** `_reclean_archived_leftovers` appelle le prédicat après `active_prev_ids` et avant son contrôle d'âge, ne supprime rien sur un verdict non-`None`, et émet une synthèse par tick.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (garde inséré après `:4229` et avant le bloc d'âge `:4230-4235` ; compteurs initialisés près de `recleaned = 0` à `:4212` ; synthèse avant `return recleaned` à `:4245`)
- Test: `apps-microservices/crawler-service/tests/test_crawler_manager_reclean.py`

**Acceptance Criteria:**
- [ ] Le garde s'exécute **après** le test `active_prev_ids` et **avant** le test d'âge — l'ordre est un choix d'observabilité : si l'âge rejetait d'abord, les cas dangereux qu'il sauve ne seraient jamais comptés comme dangereux.
- [ ] Verdict non-`None` ⇒ `_cleanup_local_data` **n'est pas appelé** pour ce crawl, et le compteur correspondant est incrémenté.
- [ ] Un `OSError` autre que `FileNotFoundError` au `stat` d'un sidecar ⇒ avertissement puis `continue`, sans suppression — même traitement explicite que le repair (`:4128-4132`, « skipping, not rejecting »).
- [ ] Une ligne `ARCHIVED_LEFTOVER_RECLEAN_SUMMARY actioned=N skipped_tree_newer=X skipped_no_snapshot=Y` est émise quand au moins un crawl a été traité ou refusé.
- [ ] `_make_archived_dir` donne à `crawler.log` un mtime **strictement antérieur** à celui de `_status_snapshot.json`, de façon déterministe.
- [ ] Les tests reclean préexistants passent, y compris ceux qui attendent une suppression.
- [ ] Suite complète : `failed` inchangé par rapport à la référence du Step 1 de la tâche 1.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager_reclean.py -v` → tous passent. Puis `python -m pytest tests/ -q` → `failed` identique à la référence (1, `test_daemon_logic`).

**Steps:**

- [ ] **Step 1: Rendre le helper déterministe face au garde**

C'est un prérequis, pas un ajustement de confort. Dans `tests/test_crawler_manager_reclean.py`, `_make_archived_dir` (`:56-67`) écrit `crawler.log` puis `_status_snapshot.json` **coup sur coup** : sur un système de fichiers à résolution de mtime grossière, les deux valeurs sont égales, et le garde rejette l'égalité. Tous les tests attendant une suppression échoueraient — pour une raison qui n'a rien à voir avec le comportement testé.

Remplacer `_make_archived_dir` par :

```python
def _make_archived_dir(base, crawl_id: str, age_seconds: int = MIN_AGE * 2):
    """Build a realistic archived crawl dir: heavy storage/ tree + small
    sidecars at the root (which the reclean must NOT touch).

    crawler.log is deliberately stamped OLDER than _status_snapshot.json: a real
    archived crawl logged while it ran and was snapshotted at archive time, so
    the log precedes the snapshot. The freshness guard compares exactly those two
    mtimes, and writing them back-to-back would leave them equal on a
    coarse-resolution filesystem — which the guard rejects, by design.
    """
    root = base / crawl_id
    datasets = root / "storage" / "datasets"
    datasets.mkdir(parents=True)
    (datasets / "000000001.json").write_text(json.dumps({"url": "https://x.test"}))
    (root / "crawler.log").write_text("log line\n")
    (root / "_status_snapshot.json").write_text("{}")
    backdate = time.time() - age_seconds
    os.utime(root / "storage", (backdate, backdate))
    snapshot_at = time.time()
    os.utime(root / "_status_snapshot.json", (snapshot_at, snapshot_at))
    os.utime(root / "crawler.log", (snapshot_at - 60, snapshot_at - 60))
    return root
```

- [ ] **Step 2: Écrire les tests du garde (rouge)**

Ajouter **à la fin** de `tests/test_crawler_manager_reclean.py`. Les ids employés (`crawl-c`, `crawl-d`, `crawl-e`, `crawl-0`, `crawl-1`, `crawl-2`) sont déjà dans `ALL_TEST_IDS` (`:40-42`), donc l'allowlist de la fixture les couvre ; `tmp_path` étant propre à chaque test, la réutilisation d'un id par un autre test ne collisionne pas.

```python
@pytest.mark.asyncio
async def test_tree_newer_than_archive_is_not_deleted(manager, tmp_path):
    """THE regression. Archived blob + old snapshot + fresh crawler.log means the
    crawl ran after its last real archiving, so the tar in GCS is OLDER than this
    tree. archive_crawl's two shortcut branches produce exactly this state, and
    the allowlist attests that old tar — it authorises the deletion. Deleting
    here destroys a dataset that exists nowhere else."""
    root = _make_archived_dir(tmp_path, "crawl-c")
    snapshot_at = os.stat(root / "_status_snapshot.json").st_mtime
    os.utime(root / "crawler.log", (snapshot_at + 60, snapshot_at + 60))

    verified = manager._load_reclean_allowlist()
    actioned = await manager._reclean_archived_leftovers(
        [_job("crawl-c", root)], set(), verified)

    assert actioned == 0
    assert (root / "storage").is_dir()


@pytest.mark.asyncio
async def test_missing_snapshot_is_not_deleted(manager, tmp_path):
    """No snapshot: nothing locally proves a tar was ever produced."""
    root = _make_archived_dir(tmp_path, "crawl-d")
    (root / "_status_snapshot.json").unlink()

    verified = manager._load_reclean_allowlist()
    actioned = await manager._reclean_archived_leftovers(
        [_job("crawl-d", root)], set(), verified)

    assert actioned == 0
    assert (root / "storage").is_dir()


@pytest.mark.asyncio
async def test_missing_log_is_not_deleted(manager, tmp_path):
    """No crawler.log: nothing proves the crawl's activity predates the archive."""
    root = _make_archived_dir(tmp_path, "crawl-e")
    (root / "crawler.log").unlink()

    verified = manager._load_reclean_allowlist()
    actioned = await manager._reclean_archived_leftovers(
        [_job("crawl-e", root)], set(), verified)

    assert actioned == 0
    assert (root / "storage").is_dir()


@pytest.mark.asyncio
async def test_summary_counts_each_refusal(manager, tmp_path, caplog):
    """The summary is what makes the guard verifiable while arming: every
    skipped_tree_newer is a case where the data-loss chain would have fired."""
    ok = _make_archived_dir(tmp_path, "crawl-0")
    newer = _make_archived_dir(tmp_path, "crawl-1")
    snapshot_at = os.stat(newer / "_status_snapshot.json").st_mtime
    os.utime(newer / "crawler.log", (snapshot_at + 60, snapshot_at + 60))
    nosnap = _make_archived_dir(tmp_path, "crawl-2")
    (nosnap / "_status_snapshot.json").unlink()

    verified = manager._load_reclean_allowlist()
    with caplog.at_level("INFO"):
        actioned = await manager._reclean_archived_leftovers(
            [_job("crawl-0", ok), _job("crawl-1", newer), _job("crawl-2", nosnap)],
            set(), verified)

    assert actioned == 1
    assert not (ok / "storage").exists()
    assert (newer / "storage").is_dir()
    assert (nosnap / "storage").is_dir()
    assert ("ARCHIVED_LEFTOVER_RECLEAN_SUMMARY actioned=1 "
            "skipped_tree_newer=1 skipped_no_snapshot=1") in caplog.text
```

- [ ] **Step 3: Lancer pour vérifier que ça échoue**

Run: `python -m pytest tests/test_crawler_manager_reclean.py -v`
Expected: les quatre nouveaux échouent. Sans garde, les trois premiers suppriment quand même
(`actioned == 1` au lieu de `0`, et `(root / "storage")` a disparu), et le quatrième échoue sur
l'absence de la ligne de synthèse dans `caplog.text`. Les tests préexistants doivent déjà passer
avec le helper du Step 1 — s'ils échouent ici, l'erreur est dans le Step 1.

- [ ] **Step 4: Écrire le garde**

Dans `app/core/crawler_manager.py`, dans `_reclean_archived_leftovers` :

**4a.** À côté de `recleaned = 0` (`:4212`), ajouter les deux compteurs :

```python
        recleaned = 0
        skipped_tree_newer = 0
        skipped_no_snapshot = 0
```

**4b.** Après le bloc `active_prev_ids` (qui se termine par son `continue` à `:4229`) et **avant**
le bloc d'âge (`:4230`), insérer :

```python
                # Freshness: the allowlist attests that a tar EXISTS in GCS, not
                # that it is newer than this tree. archive_crawl marks 'archived'
                # without re-tarring in two branches (local-tar reuse :2570-2578,
                # GCS fallback :2583-2594), and a relaunch reuses the same crawl
                # id — so an OLD tar can authorise deleting a NEW dataset that
                # exists nowhere else. _status_snapshot.json is written only on the
                # real archiving path (:2627), which both branches return before
                # reaching, so its mtime is the age of the attested tar. Checked
                # BEFORE the age gate on purpose: we want the summary to count
                # every dangerous case, including those the age gate would save.
                try:
                    snapshot_mtime = _mtime_or_none(
                        os.path.join(storage_path, '_status_snapshot.json'))
                    log_mtime = _mtime_or_none(os.path.join(storage_path, 'crawler.log'))
                except OSError as e:
                    logger.warning(
                        f"reclean: cannot stat sidecars of '{crawl_id}' ({e}) "
                        f"— skipping, not deleting.")
                    continue
                verdict = archived_status_repair.archive_freshness_verdict(
                    log_mtime, snapshot_mtime)
                if verdict == archived_status_repair.RUN_AFTER_ARCHIVE:
                    skipped_tree_newer += 1
                    continue
                if verdict == archived_status_repair.NO_SNAPSHOT:
                    skipped_no_snapshot += 1
                    continue
```

**4c.** Avant `return recleaned` (`:4245`), ajouter la synthèse :

```python
        if recleaned or skipped_tree_newer or skipped_no_snapshot:
            logger.info(
                f"ARCHIVED_LEFTOVER_RECLEAN_SUMMARY actioned={recleaned} "
                f"skipped_tree_newer={skipped_tree_newer} "
                f"skipped_no_snapshot={skipped_no_snapshot}")
        return recleaned
```

`archived_status_repair` et `_mtime_or_none` sont déjà disponibles dans ce fichier (`classify` est
appelé à `:4136`, `_mtime_or_none` défini à `:83`). Ne rien ajouter aux imports. Le reste de la
fonction — les six conditions préexistantes, le cap par tick, l'appel à `_cleanup_local_data`, le
`try/except Exception` par item — reste inchangé.

- [ ] **Step 5: Lancer le fichier de test complet**

Run: `python -m pytest tests/test_crawler_manager_reclean.py -v`
Expected: PASS, préexistants comme nouveaux.

- [ ] **Step 6: Contrôler l'absence de régression sur toute la suite**

```bash
python -m pytest tests/ -q 2>&1 | tail -3
```

Comparer à la référence du Step 1 de la tâche 1 : `passed` augmenté du nombre de tests ajoutés,
`failed` **inchangé** (1, `test_daemon_logic`). Tout autre écart est une régression à traiter avant
de committer.

- [ ] **Step 7: Committer**

Même précaution qu'à la tâche 1 : fichier relatif, `-F`, jamais `-F-`.

```bash
cd apps-microservices/crawler-service
cat > commit_msg.txt <<'MSG'
fix(archivage): ne plus supprimer un arbre plus recent que le tar atteste / stop deleting a tree newer than the attested tar

_reclean_archived_leftovers appelle desormais archive_freshness_verdict, apres
le garde active_prev_ids et AVANT son controle d'age, et ne supprime rien sur un
verdict non-None.

Le defaut ferme : l'allowlist atteste qu'un tar EXISTE en GCS, pas qu'il soit
plus recent que l'arbre. archive_crawl marque 'archived' sans re-tarrer dans
deux branches (reutilisation d'un tar local :2570-2578, fallback GCS
:2583-2594) et une relance reutilise le MEME crawl id, donc un ancien tar
autorisait la suppression d'un dataset neuf qui n'existe nulle part ailleurs.
_status_snapshot.json n'etant ecrit que sur le vrai chemin d'archivage (:2627),
que ces deux branches contournent, son mtime donne l'age du tar atteste.

L'ordre est un choix d'observabilite : si le controle d'age rejetait d'abord,
les cas dangereux qu'il sauve ne seraient jamais comptes comme dangereux. D'ou
la ligne de synthese par tick ARCHIVED_LEFTOVER_RECLEAN_SUMMARY, ou chaque
skipped_tree_newer est un cas ou la chaine aurait frappe.

Un OSError autre que FileNotFoundError au stat d'un sidecar saute le candidat
sans supprimer, explicitement, comme le fait le repair -- le try/except par item
suffirait deja, mais un fail-closed accidentel que personne ne sait accidentel
se casse au premier refactor.

_make_archived_dir horodate desormais crawler.log strictement avant
_status_snapshot.json : les ecrire coup sur coup les laissait egaux sur un
systeme de fichiers a resolution grossiere, et le garde rejette l'egalite. Un
vrai crawl archive a de toute facon logge avant d'etre snapshotte.

Aucun flag, aucune migration, aucun BO, rebuild Docker seul. Le garde est inerte
au deploiement (flag off, allowlist absente) et ne compte qu'au moment de
l'armement, ce qu'il rend moins dangereux.

--

_reclean_archived_leftovers now calls archive_freshness_verdict, after the
active_prev_ids guard and BEFORE its age gate, and deletes nothing on a non-None
verdict.

The defect closed: the allowlist attests that a tar EXISTS in GCS, not that it
is newer than the tree. archive_crawl marks 'archived' without re-tarring in two
branches (local-tar reuse :2570-2578, GCS fallback :2583-2594) and a relaunch
reuses the SAME crawl id, so an old tar authorised deleting a new dataset that
exists nowhere else. Since _status_snapshot.json is written only on the real
archiving path (:2627), which both branches bypass, its mtime gives the attested
tar's age.

The ordering is an observability choice: if the age gate rejected first, the
dangerous cases it happens to save would never be counted as dangerous. Hence
the per-tick ARCHIVED_LEFTOVER_RECLEAN_SUMMARY line, where every
skipped_tree_newer is a case where the chain would have fired.

An OSError other than FileNotFoundError while stat-ing a sidecar skips the
candidate without deleting, explicitly, as the repair does -- the per-item
try/except would already suffice, but an accidental fail-closed nobody knows is
accidental breaks at the first refactor.

_make_archived_dir now stamps crawler.log strictly before
_status_snapshot.json: writing them back-to-back left them equal on a
coarse-resolution filesystem, and the guard rejects equality. A real archived
crawl logged before it was snapshotted anyway.

No flag, no migration, no BO, Docker rebuild only. The guard is inert on
deployment (flag off, allowlist absent) and only matters when arming is decided,
which is exactly what it makes less dangerous.
MSG
git add app/core/crawler_manager.py tests/test_crawler_manager_reclean.py
git commit -F commit_msg.txt
rm commit_msg.txt
```

---

## Déploiement

Rebuild Docker de `crawler-service`. **Aucun flag**, aucun changement de script hôte, aucun
redémarrage de daemon, aucune migration, aucun BO.

Le garde est **inerte au déploiement** : `ARCHIVED_RECLEAN_ENABLED` vaut `false` (désormais épinglé
dans un `environment:` versionné, `73b08cb7`) et l'allowlist est absente du volume, donc le sweep ne
tourne pas. Il ne prend effet qu'au moment où l'armement sera décidé.

**Ce rebuild peut porter, dans la même interruption**, les deux autres changements locaux non
déployés : `ead9ff50` (garde `.move-done`) et `9d00da77` (namespacing du pool Redis, dont
`CRAWLER_REDIS_MAX_CONNECTIONS=40` à poser dans le `.env`).

⚠ **Avant tout recreate** : `docker-compose.yml` déclare `deploy.replicas: 1` alors que **7**
identités de répliques répondent en production (mesuré le 2026-08-10). Vérifier comment les 7 ont
été obtenues et si un `docker compose up -d crawler-service` les préserve — sinon la flotte tombe à
1 pendant que la file MAJ se déverse.

**Smoke après armement** (pas après ce déploiement, puisque le garde est inerte) : lire
`ARCHIVED_LEFTOVER_RECLEAN_SUMMARY` entre deux ticks (~550 s) et vérifier que `skipped_tree_newer`
n'est pas nul sur un parc où l'on sait que des domaines ont été relancés. Chaque unité comptée est
une suppression que l'ancien code aurait faite.
