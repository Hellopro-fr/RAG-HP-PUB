"""Exclusion mutuelle de NFSLock — non-regression du correctif du 01/09/2026.

Defaut corrige : ``_write_info`` creait ``info.json`` avec ``open(..., 'w')``,
donc a 0 octet PUIS ecrivait dedans. Un concurrent qui lisait ce fichier vide
prenait un ``JSONDecodeError``, et le ``except`` de ``_is_stale`` concluait
« stale » — il SUPPRIMAIT donc un verrou pris a l'instant. Deux ecrivains se
retrouvaient dans la section critique, et le premier a finir ``rmdir`` le verrou
du second, ce qui enchainait des liberations en cascade.

Effet mesure sur ``_append_manifest_logo_entry`` (read-modify-write) avant
correctif : 6,7 % d'entrees de manifest perdues a 3 ecrivains, 18,3 % a 6. Une
entree de manifest perdue, c'est une image presente sur disque et invisible du
BO — et sur ``manifest_logo.json`` ce n'est pas reparable par un rejeu de
``/logos/{domaine}/derive``, qui n'itere que sur les entrees existantes.

Ces tests echouent sur le code d'avant le correctif.
"""

import json
import os
import threading
import time

import core.nfs_lock as nfs_lock_module
from core.nfs_lock import nfs_lock


# =============================================================================
# 1. info.json n'est JAMAIS observable vide
# =============================================================================

def test_info_json_jamais_observable_vide(tmp_path):
    """Un lecteur concurrent ne doit jamais tomber sur un info.json tronque.

    C'est la cause racine : sans ecriture atomique, la fenetre entre le
    ``open('w')`` et le ``json.dump`` rend le fichier illisible.
    """
    cible = str(tmp_path / "manifest.json")
    vus_vides = []
    stop = threading.Event()

    def lecteur():
        info = os.path.join(cible + ".nfslock", "info.json")
        while not stop.is_set():
            try:
                with open(info, "r") as f:
                    contenu = f.read()
                if contenu == "":
                    vus_vides.append("vide")
                else:
                    json.loads(contenu)  # leve si tronque
            except (FileNotFoundError, NotADirectoryError):
                pass
            except json.JSONDecodeError:
                vus_vides.append("tronque")

    t = threading.Thread(target=lecteur)
    t.start()
    try:
        for _ in range(300):
            with nfs_lock(cible):
                pass
    finally:
        stop.set()
        t.join()

    assert vus_vides == [], "info.json observe vide/tronque %d fois" % len(vus_vides)


# =============================================================================
# 2. L'exclusion mutuelle tient vraiment
# =============================================================================

def test_exclusion_mutuelle_sous_concurrence(tmp_path):
    """Jamais deux porteurs simultanes dans la section critique."""
    cible = str(tmp_path / "manifest.json")
    dedans = []
    violations = []
    verrou_compteur = threading.Lock()

    def worker():
        for _ in range(25):
            with nfs_lock(cible):
                with verrou_compteur:
                    dedans.append(1)
                    if len(dedans) > 1:
                        violations.append(len(dedans))
                time.sleep(0.001)
                with verrou_compteur:
                    dedans.pop()

    ths = [threading.Thread(target=worker) for _ in range(6)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()

    assert violations == [], "exclusion violee %d fois (max %d porteurs)" % (
        len(violations), max(violations) if violations else 0)


# =============================================================================
# 3. Consequence metier : aucune entree de manifest perdue
# =============================================================================

def test_aucune_entree_de_manifest_perdue_sous_concurrence(tmp_path, monkeypatch):
    """Le read-modify-write des manifests ne doit plus perdre d'entrees.

    C'est la raison d'etre du correctif : ce test echoue (6 a 18 % de pertes)
    sur le ``_write_info`` non atomique.
    """
    import core.downloader as dl
    from conftest import _patch_package_imports

    _patch_package_imports(monkeypatch)
    monkeypatch.setattr(dl, "_STORAGE_BASE", str(tmp_path))
    domaine = "concurrent.fr"
    logo_dir = tmp_path / "images" / domaine / "logo"
    logo_dir.mkdir(parents=True)
    (logo_dir / "manifest_logo.json").write_text(
        json.dumps({"logos": [], "last_updated": None}))

    N = 6

    def ecrire(i):
        dl._append_manifest_logo_entry(domaine, {
            "key": "k%d" % i,
            "hosted_path": "logo/k%d.png" % i,
            "content_hash": "h%d" % i,
        })

    ths = [threading.Thread(target=ecrire, args=(i,)) for i in range(N)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()

    logos = json.loads((logo_dir / "manifest_logo.json").read_text())["logos"]
    presentes = {e["key"] for e in logos}
    attendues = {"k%d" % i for i in range(N)}
    assert presentes == attendues, "entrees perdues : %s" % sorted(attendues - presentes)


# =============================================================================
# 4. Le verrou ne fuit pas
# =============================================================================

def test_le_repertoire_de_verrou_est_toujours_rendu(tmp_path):
    """Un ``.tmp`` oublie ferait echouer le rmdir (ENOTEMPTY) et bloquerait
    tout le monde jusqu'au stale_timeout (60 s)."""
    cible = str(tmp_path / "manifest.json")
    for _ in range(50):
        with nfs_lock(cible):
            pass
        assert not os.path.exists(cible + ".nfslock"), "verrou non rendu"
    residus = [p for p in os.listdir(tmp_path) if p.endswith(".nfslock")
               or p.endswith(".tmp")]
    assert residus == [], "residus : %s" % residus


def test_un_verrou_reellement_perime_est_bien_repris(tmp_path):
    """Le correctif ne doit pas empecher la reprise d'un verrou abandonne."""
    cible = str(tmp_path / "manifest.json")
    verrou = nfs_lock(cible, stale_timeout=0)   # tout est perime immediatement
    verrou.acquire()
    try:
        t0 = time.time()
        with nfs_lock(cible, stale_timeout=0, max_wait=5):
            pass  # doit reprendre le verrou perime, pas attendre 5 s
        assert time.time() - t0 < 2.0
    finally:
        try:
            verrou.release()
        except Exception:
            pass


def test_stale_timeout_respecte_un_verrou_frais(tmp_path):
    """Un verrou FRAIS ne doit jamais etre vole : c'est ce vol qui cassait tout."""
    cible = str(tmp_path / "manifest.json")
    tenu = nfs_lock(cible)
    tenu.acquire()
    try:
        candidat = nfs_lock_module.NFSLock(cible)
        assert candidat._is_stale() is False, "un verrou frais est juge stale"
    finally:
        tenu.release()
