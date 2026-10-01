# Garde de fraîcheur sur le marqueur `.move-done` — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** N'honorer un `.move-done` préexistant que s'il est prouvablement plus récent que le `stashed_at` courant ; sinon le supprimer et rejouer le déplacement `stash/` → `crawls/`.

**Architecture:** Un prédicat pur au niveau module (`_move_done_is_fresh`) posé à côté de `_mtime_or_none` dans `crawler_manager.py`, plus un garde de quelques lignes en tête de `_move_stash_to_archive` qui **supprime** le marqueur jugé périmé avant le `if` existant. La logique de réconciliation du 504 (`:2388`) et la boucle d'attente (`:2405`) restent inchangées : elles n'ont pas à connaître la notion de fraîcheur, puisque le disque ne porte plus que des marqueurs légitimes quand elles s'exécutent. Un marqueur périmé indélébile lève un 502 `STASH_MOVE_STALE_MARKER` sans appeler `_mark_as_archived`.

**Tech Stack:** Python 3.12, FastAPI, pytest + pytest-asyncio. Aucun nouveau module, aucune dépendance ajoutée.

**Spec:** `docs/superpowers/specs/2026-08-10-move-done-freshness-guard-design.md` (commit `f7ddac46`).

**User decisions (already made):**
- « Garde seul » — pas de détecteur des crawls déjà touchés par le bug (hors périmètre, spec §7).
- Les 396 orphelins existants ne sont pas nettoyés en masse : ils se consomment d'eux-mêmes (spec §4).
- Langue des messages de commit : **both (EN + FR)** pour ce dépôt.
- L'utilisateur contrôle push et déploiement : **ne jamais pousser**. Merge local no-ff dans `features/poc` au maximum.

---

## File Structure

| Fichier | Responsabilité | Action |
|---|---|---|
| `app/core/crawler_manager.py` | le prédicat `_move_done_is_fresh` (niveau module, à côté de `_mtime_or_none:83`) et le garde en tête de `_move_stash_to_archive:2372` | Modifier |
| `tests/test_auto_stash_archive_move.py` | la table du prédicat, les quatre comportements du garde, et la mise à jour du test existant `test_move_success_marks_archived:45-54` | Modifier |

**Pas de module pur séparé**, contrairement à `app/core/archived_status_repair.py`. Six lignes, **un seul consommateur**, et la dépendance `_parse_iso_naive_utc` (`crawler_manager.py:95`) vit déjà dans ce fichier. Un module partagé se justifiait là-bas parce que deux consommateurs devaient rester d'accord ; ici il n'y a rien à désynchroniser, et `crawler_manager.py` s'importe sans difficulté dans la suite locale (`tests/test_auto_stash_archive_move.py` le fait déjà, 6/6 vérifiés le 2026-08-10).

**Une seule tâche.** Le prédicat sans son appelant serait du code mort — un commit qui ne change aucun comportement — et le garde sans le prédicat ne compile pas. Les deux plus la mise à jour du test existant forment un unique concern (« ne pas honorer un marqueur qu'on ne peut pas prouver nôtre ») et un unique commit.

---

### Task 1: Garde de fraîcheur `.move-done`

**Goal:** `_move_stash_to_archive` ne saute le déplacement GCS que sur un `.move-done` plus récent que le `stashed_at` courant ; tout autre marqueur est supprimé et le déplacement est redemandé.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (ajout du prédicat après `_mtime_or_none` à `:83-92` ; garde inséré après `error_path = ...` à `:2383`, avant le commentaire de réconciliation à `:2385`)
- Test: `apps-microservices/crawler-service/tests/test_auto_stash_archive_move.py`

**Acceptance Criteria:**
- [ ] `_move_done_is_fresh(done_mtime, stashed_at)` existe au niveau module et rend `True` **seulement si** les deux valeurs sont présentes, `stashed_at` est parsable, et `done_mtime` est **strictement** supérieur à l'epoch de `stashed_at`.
- [ ] Horodatages égaux → `False` (le `>` strict, pas `>=`).
- [ ] `stashed_at` absent, vide ou non parsable → `False`.
- [ ] Un `.move-done` périmé est **supprimé du disque**, puis le flux normal écrit un `.move-request` et attend (donc un 504 en test, avec `MOVE_TIMEOUT_SECONDS=1`).
- [ ] Un `.move-done` frais est honoré : **aucun** `.move-request` écrit, `_mark_as_archived` appelé une fois.
- [ ] Un `FileNotFoundError` au `getmtime` (marqueur disparu entre le test d'existence et le `stat`) est traité comme **absent**, pas comme périmé.
- [ ] Tout autre `OSError` au `getmtime` (marqueur illisible) est traité comme **périmé** : illisible n'est pas absent.
- [ ] Un marqueur périmé indélébile lève un 502 `{"error_code": "STASH_MOVE_STALE_MARKER"}` et **`_mark_as_archived` n'est PAS appelé**.
- [ ] `test_move_success_marks_archived` fournit désormais un `stashed_at` antérieur au marqueur et continue d'épingler le chemin de réconciliation du 504.
- [ ] Les 5 autres tests préexistants du fichier passent inchangés.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_archive_move.py -v` → tous passent (6 préexistants + les nouveaux). Puis la suite complète : `python -m pytest tests/ -q` → aucune régression par rapport à la référence prise à l'étape 1.

**Steps:**

- [ ] **Step 1: Prendre la référence de la suite AVANT toute modification**

Un contrôle qui ne compare pas à une référence ne distingue pas l'introduit du préexistant. La suite porte un échec préexistant connu (`tests/test_check_urls.py`, `pymilvus` absent localement).

```bash
cd apps-microservices/crawler-service
python -m pytest tests/ -q 2>&1 | tail -5
```

Noter les compteurs (`N passed, M failed`). Ce sont eux qu'il faudra retrouver à la fin, aux nouveaux tests près.

- [ ] **Step 2: Écrire les tests du prédicat (rouge)**

Dans `tests/test_auto_stash_archive_move.py`, étendre les imports en tête de fichier :

```python
"""archive_crawl stashed-branch move (auto-stash P3, Task 12)."""
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import HTTPException

from app.core import crawler_manager as cm_module
from app.core.crawler_manager import CrawlerManager
```

Puis ajouter, juste après la fixture `mgr` (donc après la ligne 19), le helper et la table du prédicat :

```python
def _iso_offset_from(path: str, seconds: float) -> str:
    """Naive-UTC ISO string `seconds` away from the mtime of `path`.

    Exact inverse of the conversion _move_done_is_fresh performs, so a test can
    place stashed_at on either side of a real file's mtime without guessing the
    clock.
    """
    ts = os.path.getmtime(path) + seconds
    return datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None).isoformat()


def _epoch_of(iso: str) -> float:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp()


STASH_ISO = "2026-01-01T00:00:00"


def test_predicate_absent_marker_is_not_fresh():
    """No marker means nothing to honour."""
    assert cm_module._move_done_is_fresh(None, STASH_ISO) is False


def test_predicate_marker_newer_than_stash_is_fresh():
    assert cm_module._move_done_is_fresh(_epoch_of(STASH_ISO) + 1, STASH_ISO) is True


def test_predicate_marker_older_than_stash_is_stale():
    assert cm_module._move_done_is_fresh(_epoch_of(STASH_ISO) - 1, STASH_ISO) is False


def test_predicate_equal_timestamps_are_stale():
    """Strictly newer: a stash and an archive inside the same second read as stale.
    We then delete, re-request, and the daemon replays its idempotent already-moved
    branch -- one extra round trip, correct outcome. The error leans the safe way."""
    assert cm_module._move_done_is_fresh(_epoch_of(STASH_ISO), STASH_ISO) is False


@pytest.mark.parametrize("stashed_at", [None, "", "t", "not-a-date"])
def test_predicate_without_usable_stashed_at_is_stale(stashed_at):
    """Absence of proof is not proof: without a parsable stashed_at we cannot
    establish that a marker is ours, so we do not honour it."""
    assert cm_module._move_done_is_fresh(_epoch_of(STASH_ISO) + 1, stashed_at) is False
```

- [ ] **Step 3: Lancer les tests du prédicat pour vérifier qu'ils échouent**

Run: `python -m pytest tests/test_auto_stash_archive_move.py -k predicate -v`
Expected: FAIL — `AttributeError: module 'app.core.crawler_manager' has no attribute '_move_done_is_fresh'`

- [ ] **Step 4: Écrire le prédicat**

Dans `app/core/crawler_manager.py`, insérer **après** `_mtime_or_none` (qui se termine ligne 92) et **avant** `_parse_iso_naive_utc` (ligne 95) :

```python
def _move_done_is_fresh(done_mtime: Optional[float], stashed_at: Optional[str]) -> bool:
    """True only when a .move-done marker provably belongs to the CURRENT stash.

    The marker is named `{crawl_id}.move-done` and carries no trace of the attempt
    that produced it, so on its own it cannot tell "my attempt, cut a moment ago"
    from "an attempt four months ago". A marker written AFTER the current stash
    began is necessarily this stash's; one written before belongs to an earlier one.

    Both clocks are the same kernel's: the mtime comes from the host daemon's touch
    on a bind-mounted results dir (docker-compose.yml:1361), stashed_at from
    datetime.utcnow() in the container. No drift to compensate.

    Strictly newer, on purpose: a stash and an archive inside the same second read
    as stale, so we delete and re-request, and the daemon replays its idempotent
    already-moved branch (tools/download_daemon.sh:86-91) -- one extra round trip,
    correct outcome. The error leans the safe way.

    Missing or unparseable evidence returns False: absence of proof is not proof.
    """
    if done_mtime is None or not stashed_at:
        return False
    try:
        stashed_epoch = _parse_iso_naive_utc(stashed_at).replace(
            tzinfo=timezone.utc).timestamp()
    except (ValueError, TypeError):
        return False
    return done_mtime > stashed_epoch
```

`Optional` et `timezone` sont déjà importés dans ce fichier (`_mtime_or_none:83` utilise le premier, `_parse_iso_naive_utc:113` le second) — ne rien ajouter aux imports.

- [ ] **Step 5: Lancer les tests du prédicat pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_auto_stash_archive_move.py -k predicate -v`
Expected: PASS (8 tests : 4 cas nominaux + 4 paramétrages de `stashed_at` inutilisable)

- [ ] **Step 6: Écrire les tests du garde (rouge)**

Toujours dans `tests/test_auto_stash_archive_move.py`, **remplacer** `test_move_success_marks_archived` (lignes 45-54) par sa version fournissant un `stashed_at` antérieur au marqueur. En production `archive_crawl` ne prend cette branche que si `stashed_at` est vrai (`crawler_manager.py:2451`), donc exiger le champ ne restreint aucun appel réel :

```python
@pytest.mark.asyncio
async def test_move_success_marks_archived(mgr):
    m, cache, tmp = mgr
    with patch("app.core.crawler_manager.settings") as s:
        s.MOVE_REQUESTS_PATH = str(tmp / "req"); s.MOVE_RESULTS_PATH = str(tmp / "res")
        s.MOVE_TIMEOUT_SECONDS = 5
        os.makedirs(s.MOVE_REQUESTS_PATH); os.makedirs(s.MOVE_RESULTS_PATH)
        done = os.path.join(s.MOVE_RESULTS_PATH, "70.move-done")
        open(done, "w").close()
        # The stash began BEFORE the marker was written -> the marker is this
        # stash's, so the freshness guard honours it (504-reconciliation path).
        await m._move_stash_to_archive(
            {"crawl_id": "70", "stashed_at": _iso_offset_from(done, -10)})
    m._mark_as_archived.assert_awaited_once_with("70")
```

Faire la même mise à jour sur `test_move_reconciles_preexisting_done_without_new_request` (lignes 57-70), qui pré-crée aussi un marqueur et repose sur la même branche :

```python
@pytest.mark.asyncio
async def test_move_reconciles_preexisting_done_without_new_request(mgr):
    """Prior-504 limbo recovery: a FRESH pre-existing .move-done is reconciled
    (mark archived) WITHOUT writing a fresh .move-request."""
    m, cache, tmp = mgr
    with patch("app.core.crawler_manager.settings") as s:
        s.MOVE_REQUESTS_PATH = str(tmp / "req"); s.MOVE_RESULTS_PATH = str(tmp / "res")
        s.MOVE_TIMEOUT_SECONDS = 5
        os.makedirs(s.MOVE_REQUESTS_PATH); os.makedirs(s.MOVE_RESULTS_PATH)
        done = os.path.join(s.MOVE_RESULTS_PATH, "70.move-done")
        open(done, "w").close()
        await m._move_stash_to_archive(
            {"crawl_id": "70", "stashed_at": _iso_offset_from(done, -10)})
        # No fresh request written — it reconciled the existing done marker.
        assert not os.path.exists(os.path.join(s.MOVE_REQUESTS_PATH, "70.move-request"))
    m._mark_as_archived.assert_awaited_once_with("70")
```

Puis **ajouter** les quatre comportements du garde à la fin du fichier :

```python
@pytest.mark.asyncio
async def test_move_stale_marker_is_deleted_and_move_replayed(mgr):
    """The bug this closes: an orphan .move-done from an earlier attempt made a
    later stash->crawls move be skipped, leaving the tar under stash/ while Redis
    said archived. The stale marker must be deleted and the move re-requested."""
    m, cache, tmp = mgr
    with patch("app.core.crawler_manager.settings") as s:
        s.MOVE_REQUESTS_PATH = str(tmp / "req"); s.MOVE_RESULTS_PATH = str(tmp / "res")
        s.MOVE_TIMEOUT_SECONDS = 1  # one poll tick then timeout
        os.makedirs(s.MOVE_REQUESTS_PATH); os.makedirs(s.MOVE_RESULTS_PATH)
        done = os.path.join(s.MOVE_RESULTS_PATH, "70.move-done")
        open(done, "w").close()
        # The stash began AFTER the marker -> the marker is an older attempt's.
        with pytest.raises(HTTPException) as exc:
            await m._move_stash_to_archive(
                {"crawl_id": "70", "stashed_at": _iso_offset_from(done, +10)})
        # 504 proves the normal request+poll branch ran instead of reconciling.
        assert exc.value.status_code == 504
        assert not os.path.exists(done)
    m._mark_as_archived.assert_not_called()


@pytest.mark.asyncio
async def test_move_marker_without_stashed_at_is_treated_as_stale(mgr):
    """No stashed_at means no way to prove the marker is ours -> do not honour it."""
    m, cache, tmp = mgr
    with patch("app.core.crawler_manager.settings") as s:
        s.MOVE_REQUESTS_PATH = str(tmp / "req"); s.MOVE_RESULTS_PATH = str(tmp / "res")
        s.MOVE_TIMEOUT_SECONDS = 1
        os.makedirs(s.MOVE_REQUESTS_PATH); os.makedirs(s.MOVE_RESULTS_PATH)
        done = os.path.join(s.MOVE_RESULTS_PATH, "70.move-done")
        open(done, "w").close()
        with pytest.raises(HTTPException) as exc:
            await m._move_stash_to_archive({"crawl_id": "70"})
        assert exc.value.status_code == 504
        assert not os.path.exists(done)
    m._mark_as_archived.assert_not_called()


@pytest.mark.asyncio
async def test_move_marker_vanishing_at_stat_is_treated_as_absent(mgr):
    """FileNotFoundError at getmtime = the marker disappeared between the exists
    check and the stat (race with the daemon or another replica). That is 'absent',
    not 'stale': the normal flow is already the right answer, and no 502 is due.
    The side effect really removes the file, so the exists() test three lines down
    sees what it would see in the real race."""
    m, cache, tmp = mgr
    with patch("app.core.crawler_manager.settings") as s:
        s.MOVE_REQUESTS_PATH = str(tmp / "req"); s.MOVE_RESULTS_PATH = str(tmp / "res")
        s.MOVE_TIMEOUT_SECONDS = 1
        os.makedirs(s.MOVE_REQUESTS_PATH); os.makedirs(s.MOVE_RESULTS_PATH)
        done = os.path.join(s.MOVE_RESULTS_PATH, "70.move-done")
        open(done, "w").close()

        def _vanish(path):
            os.remove(path)  # the daemon (or another replica) got there first
            raise FileNotFoundError(path)

        with patch("app.core.crawler_manager.os.path.getmtime", side_effect=_vanish):
            with pytest.raises(HTTPException) as exc:
                await m._move_stash_to_archive(
                    {"crawl_id": "70", "stashed_at": "2026-01-01T00:00:00"})
        assert exc.value.status_code == 504  # timeout, not STASH_MOVE_STALE_MARKER
    m._mark_as_archived.assert_not_called()


@pytest.mark.asyncio
async def test_move_unreadable_marker_is_treated_as_stale(mgr):
    """Unreadable is not absent: a marker we cannot stat cannot be proven ours, so
    it must not be honoured. _mtime_or_none deliberately lets any OSError other
    than FileNotFoundError propagate (crawler_manager.py:86-88) — this pins the
    guard's handling of it."""
    m, cache, tmp = mgr
    with patch("app.core.crawler_manager.settings") as s:
        s.MOVE_REQUESTS_PATH = str(tmp / "req"); s.MOVE_RESULTS_PATH = str(tmp / "res")
        s.MOVE_TIMEOUT_SECONDS = 1
        os.makedirs(s.MOVE_REQUESTS_PATH); os.makedirs(s.MOVE_RESULTS_PATH)
        done = os.path.join(s.MOVE_RESULTS_PATH, "70.move-done")
        open(done, "w").close()
        with patch("app.core.crawler_manager.os.path.getmtime",
                   side_effect=PermissionError("EACCES")):
            with pytest.raises(HTTPException) as exc:
                await m._move_stash_to_archive(
                    {"crawl_id": "70", "stashed_at": "2026-01-01T00:00:00"})
        assert exc.value.status_code == 504  # deleted, then normal flow timed out
        assert not os.path.exists(done)
    m._mark_as_archived.assert_not_called()


@pytest.mark.asyncio
async def test_move_undeletable_stale_marker_raises_502_without_archiving(mgr):
    """The assertion that matters: marking archived here would BE the bug, since
    the tar would still sit under stash/. An undeletable marker in the results dir
    is an infrastructure problem, not a situation to work around."""
    m, cache, tmp = mgr
    with patch("app.core.crawler_manager.settings") as s:
        s.MOVE_REQUESTS_PATH = str(tmp / "req"); s.MOVE_RESULTS_PATH = str(tmp / "res")
        s.MOVE_TIMEOUT_SECONDS = 1
        os.makedirs(s.MOVE_REQUESTS_PATH); os.makedirs(s.MOVE_RESULTS_PATH)
        done = os.path.join(s.MOVE_RESULTS_PATH, "70.move-done")
        open(done, "w").close()
        stashed_at = _iso_offset_from(done, +10)
        with patch("app.core.crawler_manager.os.remove",
                   side_effect=OSError("EPERM")):
            with pytest.raises(HTTPException) as exc:
                await m._move_stash_to_archive(
                    {"crawl_id": "70", "stashed_at": stashed_at})
        assert exc.value.status_code == 502
        assert exc.value.detail == {"error_code": "STASH_MOVE_STALE_MARKER"}
    m._mark_as_archived.assert_not_called()
```

- [ ] **Step 7: Lancer les tests du garde pour vérifier qu'ils échouent**

Run: `python -m pytest tests/test_auto_stash_archive_move.py -v`
Expected: FAIL sur les **cinq** nouveaux tests du garde, tous en `Failed: DID NOT RAISE`. Sans le garde, `_move_stash_to_archive` n'appelle jamais `getmtime` : un marqueur préexistant est honoré quelle qu'en soit la date, donc les cinq scénarios prennent la branche de réconciliation et sortent sans exception. Dans le cas indélébile, le `os.remove` patché échoue bien, mais le nettoyage final `:2431-2434` avale l'`OSError` — d'où l'absence de 502 elle aussi.

Les deux tests préexistants mis à jour à l'étape 6 (`test_move_success_marks_archived`, `test_move_reconciles_preexisting_done_without_new_request`) doivent passer **avant comme après** : le `stashed_at` ajouté est ignoré par le code actuel et honoré par le garde. S'ils échouent ici, l'erreur est dans le test, pas dans le code.

- [ ] **Step 8: Écrire le garde**

Dans `app/core/crawler_manager.py`, insérer **après** `error_path = os.path.join(res_dir, f"{crawl_id}.move-error")` (ligne 2383) et **avant** le commentaire `# Reconcile a prior 504 limbo:` (ligne 2385) :

```python
        # A pre-existing .move-done is honoured only if it provably belongs to THIS
        # stash (see _move_done_is_fresh). A stale one is DELETED rather than merely
        # ignored: the marker is tested twice -- the skip below and the poll loop --
        # so leaving it on disk would move the bug three lines down instead of
        # closing it. Deleting makes both tests correct without either needing to
        # know about freshness.
        stale_marker = False
        try:
            done_mtime = _mtime_or_none(done_path)
        except OSError as e:
            # Unreadable is not absent: we cannot prove the marker is ours.
            logger.warning(f"STASH_MOVE_STALE_MARKER crawl_id={crawl_id} "
                           f"reason=marker_unreadable detail={e}")
            stale_marker = True
        else:
            if done_mtime is not None and not _move_done_is_fresh(
                    done_mtime, job_info.get("stashed_at")):
                logger.warning(
                    f"STASH_MOVE_STALE_MARKER crawl_id={crawl_id} "
                    f"reason=marker_older_than_stash done_mtime={done_mtime} "
                    f"stashed_at={job_info.get('stashed_at')}")
                stale_marker = True
        if stale_marker:
            try:
                os.remove(done_path)
                logger.info(f"Deleted stale .move-done for '{crawl_id}'; "
                            f"the stash->archive move will be requested again.")
            except FileNotFoundError:
                pass  # gone already (daemon or another replica): normal flow is right
            except OSError as e:
                # Proceeding would mark archived without a move -- the very bug.
                logger.error(f"Cannot delete stale .move-done for '{crawl_id}': {e}")
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                                    detail={"error_code": "STASH_MOVE_STALE_MARKER"})
```

Rien d'autre ne change : le `if not os.path.exists(done_path):` de `:2388`, la boucle d'attente, le nettoyage final `:2431-2434` et la branche `archive_crawl` `:2451` restent tels quels.

Pourquoi `try/except/else` plutôt qu'une simple affectation : `_mtime_or_none` laisse volontairement remonter tout `OSError` autre que `FileNotFoundError` (`:86-88`), et ce garde a besoin des deux issues distinctement — disparu (flux normal) contre illisible (périmé).

- [ ] **Step 9: Lancer le fichier de test complet pour vérifier qu'il passe**

Run: `python -m pytest tests/test_auto_stash_archive_move.py -v`
Expected: PASS sur les 19 tests (6 préexistants dont 2 mis à jour + 8 du prédicat + 5 du garde).

- [ ] **Step 10: Contrôler l'absence de régression sur toute la suite**

```bash
python -m pytest tests/ -q 2>&1 | tail -5
```

Comparer aux compteurs de l'étape 1 : le nombre de `passed` doit avoir augmenté d'exactement le nombre de tests ajoutés, et le nombre de `failed` doit être **inchangé** (l'échec préexistant de `tests/test_check_urls.py` reste, `pymilvus` étant absent localement). Tout écart autre que celui-là est une régression à traiter avant de committer.

- [ ] **Step 11: Committer**

Message bilingue EN + FR, convention du dépôt RAG-HP-PUB.

```bash
git add app/core/crawler_manager.py tests/test_auto_stash_archive_move.py
git commit -F- <<'MSG'
fix(archivage): n'honorer un .move-done que s'il est plus recent que le stash / honour a .move-done only when it is newer than the stash

Le marqueur s'appelle {crawl_id}.move-done et ne porte aucune trace de la
tentative qui l'a produit, donc _move_stash_to_archive ne distinguait pas
« ma tentative, coupee a l'instant » de « une tentative d'il y a quatre
mois ». Un orphelin perime faisait sauter entierement le deplacement
stash/ -> crawls/ : le tar restait sous stash/ pendant que Redis disait
archived, et /results allait chercher dans crawls/. Mesure du 2026-08-10 :
396 orphelins en production, jusqu'a 27 jours d'age.

Nouveau predicat _move_done_is_fresh : un marqueur n'est honore que si son
mtime est strictement posterieur au stashed_at courant. Le marqueur juge
perime est SUPPRIME avant le if existant, parce qu'il est teste deux fois
(le saut et la boucle d'attente) et que ne pas l'honorer sans l'effacer
deplacerait le bug de trois lignes. Un marqueur perime indelebile leve un
502 STASH_MOVE_STALE_MARKER sans appeler _mark_as_archived : marquer
archived sans deplacement serait exactement le bug qu'on ferme.

Le filet anti-504 est preserve : un marqueur legitime (ecrit apres le
debut du stash courant) est toujours reconcilie sans nouvelle requete.
Aucun flag, aucun changement du script hote, aucun redemarrage de daemon,
aucune migration.

--

The marker is named {crawl_id}.move-done and carries no trace of the
attempt that produced it, so _move_stash_to_archive could not tell "my
attempt, cut a moment ago" from "an attempt four months ago". A stale
orphan made it skip the stash/ -> crawls/ move entirely: the tar stayed
under stash/ while Redis said archived, and /results looked in crawls/.
Measured 2026-08-10: 396 orphans in production, up to 27 days old.

New _move_done_is_fresh predicate: a marker is honoured only when its
mtime is strictly newer than the current stashed_at. A marker judged
stale is DELETED before the existing if, because it is tested twice (the
skip and the poll loop) and merely not honouring it would move the bug
three lines down. An undeletable stale marker raises 502
STASH_MOVE_STALE_MARKER without calling _mark_as_archived: marking
archived with no move is the very bug being closed.

The anti-504 net is preserved: a legitimate marker (written after the
current stash began) is still reconciled without a fresh request. No
flag, no host-script change, no daemon restart, no migration.
MSG
```

---

## Déploiement

Rebuild Docker de `crawler-service`. **Aucun** changement du script hôte `tools/download_daemon.sh`, **aucun redémarrage de daemon**, aucune migration, aucun changement BO, aucun flag.

**Pas de flag**, contrairement à la convention du dépôt pour ce qui touche l'archivage. Le garde ne peut rendre le code que plus prudent : son seul effet possible est une requête de déplacement en trop, jamais une de moins. Un flag signifierait « garder la possibilité d'honorer un marqueur périmé », c'est-à-dire garder le bug disponible.

**Smoke après rebuild** — `GET /admin/daemon-state` donne le compte de `.move-done` dans `move_results` (396 le 2026-08-10). Il doit décroître au fil des archivages, chaque orphelin étant supprimé au premier archivage de son id. Chercher `STASH_MOVE_STALE_MARKER` dans les logs : chaque occurrence est un cas où le bug aurait frappé.

Les 396 orphelins existants ne sont **pas** nettoyés : un balayage en masse supprimerait le marqueur d'un crawl dont l'appelant attend encore, le faisant échouer en 504 alors que le déplacement avait réussi. Le garde les rend inoffensifs ; les balayer les rendrait dangereux.
