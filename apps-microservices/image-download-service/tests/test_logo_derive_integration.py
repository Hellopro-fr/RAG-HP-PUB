"""Tests de la GREFFE du derive d'affichage dans image-download-service.

``tests/test_logo_derive.py`` couvre la RECETTE (``app/core/logo_derive.py``, pur,
sans disque). Ce fichier-ci couvre son BRANCHEMENT : fusion du manifest, ecriture
des variantes, flux de telechargement, endpoint a la demande.

Ce qui est verifie ici, et pourquoi :
  - la FUSION ne touche ni les autres cles de l'entree ni les autres entrees, et
    RELEVE au lieu d'avaler (``_append_manifest_logo_entry`` avale : un
    enrichissement muet produirait un 200 sans ecriture) ;
  - l'ecriture des variantes est atomique ET lisible par le CDN (nginx tourne ses
    workers sous l'utilisateur ``nginx``, ``mkstemp`` cree en 0600) ;
  - l'idempotence tient sur les DEUX conditions (bloc manifest ET fichiers) :
    un manifest non enrichi ne doit pas devenir un trou permanent ;
  - le flag est OFF par defaut et un echec de derivation ne casse jamais le
    telechargement du master (c'est lui qui porte le ``content_hash`` du cycle 4b) ;
  - la course « telechargement APRES backfill » : ``_append_manifest_logo_entry``
    remplace l'entree entiere, il ne doit pas effacer les cles du derive.

Conventions du depot : ``asyncio.run`` (pas de pytest-asyncio), monkeypatch de
``core.downloader._STORAGE_BASE`` pour l'isolement FS, mock aiohttp par
``unittest.mock``, ``TestClient(main.app)`` sans lifespan.
"""

import asyncio
import hashlib
import io
import json
import os
import stat
import sys
import threading
import time

import pytest
from PIL import Image, ImageDraw
from unittest.mock import AsyncMock, MagicMock, patch

from conftest import _patch_package_imports


# =============================================================================
# Fixtures d'octets — caracterisees par une mesure reelle de derive_logo
# =============================================================================

def png_logo_sombre() -> bytes:
    """Encre sombre sur transparent : 1 variante (sq200a), aucun flag."""
    img = Image.new("RGBA", (240, 120), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([20, 10, 120, 110], outline=(30, 30, 30, 255), width=14)
    draw.rectangle([140, 30, 219, 89], fill=(30, 30, 30, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def png_logo_blanc() -> bytes:
    """Encre BLANCHE sur transparent : surface dark_required -> sq200a + sq200d."""
    img = Image.new("RGBA", (240, 120), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([20, 10, 120, 110], outline=(255, 255, 255, 255), width=14)
    draw.rectangle([140, 30, 219, 89], fill=(255, 255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def png_logo_autre() -> bytes:
    """Autres octets, meme nature : sert aux MAJ (content_hash different)."""
    img = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle([20, 20, 179, 79], fill=(10, 40, 90, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


SVG_AVEC_TEXTE = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60">'
    b'<text x="5" y="40">ACME</text></svg>'
)


# =============================================================================
# Helpers — flux direct
# =============================================================================

def _setup_storage(monkeypatch, tmp_path):
    import core.downloader as dl
    monkeypatch.setattr(dl, "_STORAGE_BASE", str(tmp_path))
    return dl


def _make_downloader():
    """Downloader sans __init__ (pas d'ImageProcessor reel), avec le vrai process_logo."""
    import core.downloader as dl
    from core.image_processor import process_logo

    d = dl.Downloader.__new__(dl.Downloader)
    d.image_processor = MagicMock()
    d.process_logo = process_logo
    d.proxy_password = None
    d.proxy_url = None
    return d


def _mock_session_ok(content_bytes: bytes):
    response = MagicMock()
    response.status = 200
    response.read = AsyncMock(return_value=content_bytes)
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.get = MagicMock(return_value=response)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _download(downloader, domain="acme.fr", key="logo-principal",
              content=None, url="https://acme.fr/logo.png"):
    payload = {"domaine": domain, "url_logo": url, "key": key}
    with patch("aiohttp.ClientSession", return_value=_mock_session_ok(content)):
        return asyncio.run(downloader.process_logo_download(payload))


def _manifest(tmp_path, domain="acme.fr") -> dict:
    path = tmp_path / "images" / domain / "logo" / "manifest_logo.json"
    if not path.exists():
        return {"logos": [], "last_updated": None}
    return json.loads(path.read_text())


def _entry(tmp_path, domain="acme.fr", key="logo-principal"):
    for candidate in _manifest(tmp_path, domain).get("logos", []):
        if candidate.get("key") == key:
            return candidate
    return None


def _derive_dir(tmp_path, domain="acme.fr"):
    return tmp_path / "images" / domain / "logo" / "d"


# =============================================================================
# Fixture TestClient — miroir test_logos_endpoint.py::_alias_main_dependencies
# =============================================================================

def _alias_main_dependencies(monkeypatch):
    _patch_package_imports(monkeypatch)

    import core.archiver as real_archiver
    _orig_archiver_init = real_archiver.Archiver.__init__

    def _archiver_init_envaware(self, storage_base: str = None):
        if storage_base is None:
            storage_base = os.environ.get("STORAGE_BASE", "/app/storage")
        return _orig_archiver_init(self, storage_base)

    monkeypatch.setattr(real_archiver.Archiver, "__init__", _archiver_init_envaware)
    monkeypatch.setitem(sys.modules, "image_download_service.core.archiver", real_archiver)

    import core.downloader as real_downloader
    monkeypatch.setitem(sys.modules, "image_download_service.core.downloader", real_downloader)

    import messaging as real_messaging
    monkeypatch.setitem(sys.modules, "image_download_service.messaging", real_messaging)
    import messaging.consumer as real_consumer
    monkeypatch.setitem(sys.modules, "image_download_service.messaging.consumer", real_consumer)
    import messaging.page_image_consumer as real_page_image_consumer
    monkeypatch.setitem(
        sys.modules, "image_download_service.messaging.page_image_consumer", real_page_image_consumer
    )
    import messaging.logo_consumer as real_logo_consumer
    monkeypatch.setitem(sys.modules, "image_download_service.messaging.logo_consumer", real_logo_consumer)

    import routers as real_routers
    monkeypatch.setitem(sys.modules, "image_download_service.routers", real_routers)
    import routers.albums as real_routers_albums
    monkeypatch.setitem(sys.modules, "image_download_service.routers.albums", real_routers_albums)
    import routers.pages as real_routers_pages
    monkeypatch.setitem(sys.modules, "image_download_service.routers.pages", real_routers_pages)
    import routers.logos as real_routers_logos
    monkeypatch.setitem(sys.modules, "image_download_service.routers.logos", real_routers_logos)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient + storage isole (env STORAGE_BASE pour le routeur,
    _STORAGE_BASE pour core.downloader)."""
    _alias_main_dependencies(monkeypatch)
    monkeypatch.setenv("STORAGE_BASE", str(tmp_path))
    (tmp_path / "images").mkdir(exist_ok=True)
    _setup_storage(monkeypatch, tmp_path)

    for mod_key in ("main", "image_download_service.main"):
        if mod_key in sys.modules:
            del sys.modules[mod_key]

    import main as main_module
    monkeypatch.setitem(sys.modules, "image_download_service.main", main_module)

    from fastapi.testclient import TestClient
    return TestClient(main_module.app), tmp_path


# =============================================================================
# 1. FUSION DU MANIFEST
# =============================================================================

def test_fusion_preserve_les_autres_cles_et_les_autres_entrees(tmp_path, monkeypatch):
    _patch_package_imports(monkeypatch)
    dl = _setup_storage(monkeypatch, tmp_path)

    dl._append_manifest_logo_entry("acme.fr", {
        "key": "logo-principal", "hosted_path": "logo/a.png", "content_hash": "a" * 64,
        "format": "png", "width": 240, "height": 120,
    })
    dl._append_manifest_logo_entry("acme.fr", {
        "key": "logo-secondaire", "hosted_path": "logo/b.png", "content_hash": "b" * 64,
    })

    merged = dl._merge_manifest_logo_entry(
        "acme.fr", "logo-principal", {"derive": {"recipe": "r1m0", "variants": []}}
    )

    assert merged["derive"]["recipe"] == "r1m0"
    # Les cles du master de l'entree visee survivent...
    assert merged["content_hash"] == "a" * 64
    assert merged["width"] == 240 and merged["format"] == "png"

    logos = _manifest(tmp_path)["logos"]
    assert len(logos) == 2, "la fusion ne doit pas dupliquer ni supprimer d'entree"
    # ... et l'autre entree n'est pas touchee du tout.
    autre = [e for e in logos if e["key"] == "logo-secondaire"][0]
    assert autre == {"key": "logo-secondaire", "hosted_path": "logo/b.png",
                     "content_hash": "b" * 64}
    assert "derive" not in autre

    # L'ordre des entrees est preserve (le manifest est une liste ordonnee).
    assert [e["key"] for e in logos] == ["logo-principal", "logo-secondaire"]


def test_fusion_leve_si_la_cle_est_absente(tmp_path, monkeypatch):
    _patch_package_imports(monkeypatch)
    dl = _setup_storage(monkeypatch, tmp_path)
    dl._append_manifest_logo_entry("acme.fr", {"key": "logo-principal"})

    with pytest.raises(KeyError):
        dl._merge_manifest_logo_entry("acme.fr", "cle-inexistante", {"derive": {}})


def test_fusion_releve_la_ou_append_avale(tmp_path, monkeypatch):
    """Le contraste EST la raison d'etre de la fonction de fusion."""
    _patch_package_imports(monkeypatch)
    dl = _setup_storage(monkeypatch, tmp_path)
    dl._append_manifest_logo_entry("acme.fr", {"key": "logo-principal", "content_hash": "a" * 64})

    def _boom(domain, manifest):
        raise OSError("disque plein")

    monkeypatch.setattr(dl, "_save_manifest_logo_file", _boom)

    # _append_manifest_logo_entry avale (comportement historique, inchange)
    dl._append_manifest_logo_entry("acme.fr", {"key": "autre"})

    # la fusion, elle, releve : sinon l'endpoint repondrait 200 sans rien ecrire
    with pytest.raises(OSError):
        dl._merge_manifest_logo_entry("acme.fr", "logo-principal", {"derive": {}})


def test_fusion_ne_laisse_pas_le_verrou_nfs_derriere_elle(tmp_path, monkeypatch):
    """Un verrou orphelin bloquerait 30 s tous les ecrivains suivants."""
    _patch_package_imports(monkeypatch)
    dl = _setup_storage(monkeypatch, tmp_path)
    dl._append_manifest_logo_entry("acme.fr", {"key": "logo-principal"})

    dl._merge_manifest_logo_entry("acme.fr", "logo-principal", {"derive": {}})
    lock_dir = tmp_path / "images" / "acme.fr" / "logo" / "manifest_logo.json.nfslock"
    assert not lock_dir.exists()

    with pytest.raises(KeyError):
        dl._merge_manifest_logo_entry("acme.fr", "absente", {"derive": {}})
    assert not lock_dir.exists(), "verrou non relache sur le chemin d'exception"


def test_fusion_detecte_un_ecrasement_concurrent_et_reprend(tmp_path, monkeypatch):
    """NFSLock n'est pas exclusif (mesure : 6 threads x 30 prises -> exclusion
    violee 8 fois, cf. _MANIFEST_MERGE_ATTEMPTS). La fusion doit donc relire son
    ecriture et reprendre, au lieu d'annoncer un succes qu'elle n'a pas obtenu."""
    _patch_package_imports(monkeypatch)
    dl = _setup_storage(monkeypatch, tmp_path)
    dl._append_manifest_logo_entry("acme.fr", {"key": "logo-principal",
                                               "content_hash": "a" * 64})

    vrai_save = dl._save_manifest_logo_file
    ecrasements = []

    def _save_puis_ecrasement_concurrent(domain, manifest):
        vrai_save(domain, manifest)
        if not ecrasements:
            # Un concurrent qui avait lu AVANT nous reecrit le fichier depuis son
            # propre instantane : notre patch disparait.
            ecrasements.append(True)
            vrai_save(domain, {"logos": [{"key": "logo-principal",
                                          "content_hash": "a" * 64}]})

    monkeypatch.setattr(dl, "_save_manifest_logo_file", _save_puis_ecrasement_concurrent)

    merged = dl._merge_manifest_logo_entry(
        "acme.fr", "logo-principal", {"derive": {"recipe": "r1m0"}}
    )

    assert ecrasements == [True], "l'ecrasement simule n'a pas eu lieu"
    assert merged["derive"]["recipe"] == "r1m0"
    entree = _entry(tmp_path)
    assert entree["derive"] == {"recipe": "r1m0"}, "la reprise n'a pas repose le patch"
    assert entree["content_hash"] == "a" * 64


def test_fusion_leve_si_le_patch_ne_survit_jamais(tmp_path, monkeypatch):
    """Perte non reparable : il faut LEVER. Le rapport de l'endpoint la nommera
    (manifest_non_fusionne) et le rejeu reparera grace aux deux conditions."""
    _patch_package_imports(monkeypatch)
    dl = _setup_storage(monkeypatch, tmp_path)
    dl._append_manifest_logo_entry("acme.fr", {"key": "logo-principal"})

    passes = []
    monkeypatch.setattr(dl, "_logo_patch_survived",
                        lambda domain, key, expected: passes.append(1) or False)

    with pytest.raises(RuntimeError, match="perdue"):
        dl._merge_manifest_logo_entry("acme.fr", "logo-principal", {"derive": {}}, attempts=3)

    assert len(passes) == 3, "chaque passe doit verifier son ecriture"


# =============================================================================
# 2. ECRITURE DES VARIANTES
# =============================================================================

def _variants_fixture():
    return [
        {"variant": "sq200a", "filename": "logo-x--abc-r1m0-sq200a.png",
         "bytes": b"\x89PNG-a", "width": 200, "height": 200, "format": "png"},
        {"variant": "sq200d", "filename": "logo-x--abc-r1m0-sq200d.png",
         "bytes": b"\x89PNG-d", "width": 200, "height": 200, "format": "png"},
    ]


def test_ecriture_variantes_dans_le_sous_repertoire_dedie(tmp_path, monkeypatch):
    _patch_package_imports(monkeypatch)
    dl = _setup_storage(monkeypatch, tmp_path)

    written = dl._write_logo_derive_variants("acme.fr", _variants_fixture())

    assert [w["variant"] for w in written] == ["sq200a", "sq200d"]
    assert written[0]["path"] == "logo/d/logo-x--abc-r1m0-sq200a.png"
    assert written[0]["file_size"] == len(b"\x89PNG-a")
    assert "bytes" not in written[0], "les octets ne doivent pas partir dans le manifest"

    d = _derive_dir(tmp_path)
    assert (d / "logo-x--abc-r1m0-sq200a.png").read_bytes() == b"\x89PNG-a"
    assert (d / "logo-x--abc-r1m0-sq200d.png").read_bytes() == b"\x89PNG-d"
    assert not list(d.glob("*.tmp")), "aucun tempfile ne doit subsister"


def test_variantes_lisibles_par_le_conteneur_cdn(tmp_path, monkeypatch):
    """mkstemp cree en 0600 ; nginx tourne ses workers sous l'utilisateur nginx."""
    _patch_package_imports(monkeypatch)
    dl = _setup_storage(monkeypatch, tmp_path)

    dl._write_logo_derive_variants("acme.fr", _variants_fixture()[:1])

    mode = stat.S_IMODE(os.stat(_derive_dir(tmp_path) / "logo-x--abc-r1m0-sq200a.png").st_mode)
    assert mode & stat.S_IROTH, "un derive en 0600 serait servi en 403 par le CDN"
    assert mode == 0o644


def test_ecriture_variantes_echec_ne_corrompt_pas_la_cible(tmp_path, monkeypatch):
    """nginx a un open_file_cache de 30 s : un PNG tronque serait memorise."""
    _patch_package_imports(monkeypatch)
    dl = _setup_storage(monkeypatch, tmp_path)

    cible = _derive_dir(tmp_path) / "logo-x--abc-r1m0-sq200a.png"
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(b"ANCIENNE-VERSION-INTACTE")

    def _boom(src, dst):
        raise OSError("replace refuse")

    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(OSError):
        dl._write_logo_derive_variants("acme.fr", _variants_fixture()[:1])
    monkeypatch.undo()

    assert cible.read_bytes() == b"ANCIENNE-VERSION-INTACTE"
    assert not list(_derive_dir(tmp_path).glob("*.tmp")), "tempfile non nettoye"


@pytest.mark.parametrize("nom", [
    "../evade.png", "sous/repertoire.png", "..", ".", "", "a\\b.png",
])
def test_nom_de_variante_traversant_refuse(tmp_path, monkeypatch, nom):
    _patch_package_imports(monkeypatch)
    dl = _setup_storage(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        dl._logo_derive_variant_path("acme.fr", nom)


@pytest.mark.parametrize("hosted", [
    "../../etc/passwd", "logo/sous/x.png", "/etc/passwd", "", None,
])
def test_hosted_path_hors_du_repertoire_logo_refuse(tmp_path, monkeypatch, hosted):
    """hosted_path est relu du manifest et sert a OUVRIR un fichier."""
    _patch_package_imports(monkeypatch)
    dl = _setup_storage(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        dl._logo_master_path("acme.fr", hosted)


def test_hosted_path_legitime_accepte(tmp_path, monkeypatch):
    _patch_package_imports(monkeypatch)
    dl = _setup_storage(monkeypatch, tmp_path)
    resolu = dl._logo_master_path("acme.fr", "logo/logo-acme_fr.png")
    assert resolu == str(tmp_path / "images" / "acme.fr" / "logo" / "logo-acme_fr.png")


# =============================================================================
# 3. GREFFE DANS LE FLUX
# =============================================================================

def test_flag_off_aucun_derive(tmp_path, monkeypatch):
    _patch_package_imports(monkeypatch)
    _setup_storage(monkeypatch, tmp_path)
    monkeypatch.delenv("ENABLE_LOGO_DERIVE", raising=False)

    result = _download(_make_downloader(), content=png_logo_sombre())

    assert result is not None
    assert "derive" not in result, "OFF par defaut : aucune cle derive"
    assert "derive" not in _entry(tmp_path)
    assert not _derive_dir(tmp_path).exists(), "aucun fichier, aucun repertoire"


def test_flag_on_produit_les_variantes_et_enrichit_le_manifest(tmp_path, monkeypatch):
    _patch_package_imports(monkeypatch)
    _setup_storage(monkeypatch, tmp_path)
    monkeypatch.setenv("ENABLE_LOGO_DERIVE", "true")

    content = png_logo_sombre()
    result = _download(_make_downloader(), content=content)

    # Le master n'a pas bouge : ni ses octets, ni son hash.
    master = tmp_path / "images" / "acme.fr" / result["hosted_path"]
    assert master.read_bytes() == content
    assert result["content_hash"] == hashlib.sha256(content).hexdigest()

    bloc = result["derive"]
    assert bloc["recipe"] == "r1m0"
    assert bloc["source_hash"] == result["content_hash"]
    assert bloc["dir"] == "logo/d"
    assert bloc["publishable"] is True
    assert bloc["blocking_flags"] == []
    assert bloc["error"] is None
    assert [v["variant"] for v in bloc["variants"]] == ["sq200a"]

    # Les metriques sont completes : le BO doit pouvoir remplir ses colonnes.
    for cle in ("recipe", "libvips_version", "source_hash", "surface", "flags",
                "fill_pct", "ratio_x100", "master_width", "master_height",
                "ink_bbox", "alpha_ratio", "ink_on_white", "ink_on_black", "is_light"):
        assert cle in bloc["metrics"], cle

    # Le fichier existe, il est nomme par le contenu, et c'est un PNG 200x200.
    variante = bloc["variants"][0]
    h12 = hashlib.sha256(("%s|r1m0" % result["content_hash"]).encode()).hexdigest()[:12]
    assert variante["filename"] == "logo-logo-principal--%s-r1m0-sq200a.png" % h12
    chemin = tmp_path / "images" / "acme.fr" / variante["path"]
    assert chemin.is_file()
    with Image.open(chemin) as im:
        assert im.size == (200, 200)
        assert im.format == "PNG"

    # Et le manifest sur disque porte le meme bloc (fusion, pas seulement retour).
    assert _entry(tmp_path)["derive"] == bloc


def test_flag_on_dark_required_ecrit_les_deux_variantes(tmp_path, monkeypatch):
    _patch_package_imports(monkeypatch)
    _setup_storage(monkeypatch, tmp_path)
    monkeypatch.setenv("ENABLE_LOGO_DERIVE", "true")

    result = _download(_make_downloader(), content=png_logo_blanc())
    bloc = result["derive"]

    assert bloc["metrics"]["surface"] == "dark_required"
    assert sorted(v["variant"] for v in bloc["variants"]) == ["sq200a", "sq200d"]
    for variante in bloc["variants"]:
        assert (tmp_path / "images" / "acme.fr" / variante["path"]).is_file()
    assert bloc["publishable"] is True


def test_echec_derivation_ne_casse_pas_le_telechargement(tmp_path, monkeypatch):
    _patch_package_imports(monkeypatch)
    _setup_storage(monkeypatch, tmp_path)
    monkeypatch.setenv("ENABLE_LOGO_DERIVE", "true")

    import core.logo_derive as ld

    def _boom(*args, **kwargs):
        raise RuntimeError("libvips indisponible")

    monkeypatch.setattr(ld, "derive_logo", _boom)

    content = png_logo_sombre()
    result = _download(_make_downloader(), content=content)

    assert result is not None, "le telechargement du master doit reussir"
    assert result["content_hash"] == hashlib.sha256(content).hexdigest()
    assert (tmp_path / "images" / "acme.fr" / result["hosted_path"]).read_bytes() == content
    assert "derive" not in result and "derive" not in _entry(tmp_path)
    # Pas d'errors_logo.json : la derivation n'est pas une erreur de telechargement.
    assert not (tmp_path / "images" / "acme.fr" / "logo" / "errors_logo.json").exists()


def test_flux_ne_re_derive_pas_les_memes_octets(tmp_path, monkeypatch):
    """Deux ingestions des memes octets : 145 ms de pyvips ne doivent etre payes qu'une fois."""
    _patch_package_imports(monkeypatch)
    _setup_storage(monkeypatch, tmp_path)
    monkeypatch.setenv("ENABLE_LOGO_DERIVE", "true")

    import core.logo_derive as ld
    appels = []
    vrai_derive = ld.derive_logo

    def _compte(content, key, content_hash, **kwargs):
        appels.append(content_hash)
        return vrai_derive(content, key, content_hash, **kwargs)

    monkeypatch.setattr(ld, "derive_logo", _compte)

    content = png_logo_sombre()
    d = _make_downloader()
    premier = _download(d, content=content)
    second = _download(d, content=content)

    assert len(appels) == 1, "la 2e ingestion doit reprendre le bloc existant"
    assert second["derive"] == premier["derive"]
    assert len(_manifest(tmp_path)["logos"]) == 1


# =============================================================================
# 4. LA COURSE « TELECHARGEMENT APRES BACKFILL »
# =============================================================================

def test_download_apres_backfill_ne_supprime_pas_le_derive(tmp_path, monkeypatch):
    """_append_manifest_logo_entry REMPLACE l'entree entiere : sans reprise du
    bloc, un re-telechargement flag ETEINT effacerait le travail du backfill."""
    _patch_package_imports(monkeypatch)
    dl = _setup_storage(monkeypatch, tmp_path)
    monkeypatch.delenv("ENABLE_LOGO_DERIVE", raising=False)

    content = png_logo_sombre()
    d = _make_downloader()

    # 1. flux flag OFF -> entree master seule
    _download(d, content=content)
    assert "derive" not in _entry(tmp_path)

    # 2. backfill a la demande (l'endpoint fonctionne flag eteint)
    rapport = asyncio.run(dl.derive_logos_for_domain("acme.fr"))
    assert rapport["counts"]["created"] == 1
    bloc = _entry(tmp_path)["derive"]
    assert bloc["publishable"] is True

    # 3. re-telechargement des MEMES octets, toujours flag OFF
    result = _download(d, content=content)

    assert _entry(tmp_path)["derive"] == bloc, "le bloc derive a ete efface"
    assert result["derive"] == bloc, "l'entree retournee doit porter le bloc repris"
    assert len(_manifest(tmp_path)["logos"]) == 1


def test_download_de_nouveaux_octets_retire_le_derive_perime(tmp_path, monkeypatch):
    """Master change -> le derive decrit d'autres octets : il doit disparaitre,
    sinon le BO afficherait une vignette qui n'est plus celle du logo."""
    _patch_package_imports(monkeypatch)
    dl = _setup_storage(monkeypatch, tmp_path)
    monkeypatch.delenv("ENABLE_LOGO_DERIVE", raising=False)

    d = _make_downloader()
    _download(d, content=png_logo_sombre())
    asyncio.run(dl.derive_logos_for_domain("acme.fr"))
    ancien = _entry(tmp_path)["derive"]

    result = _download(d, content=png_logo_autre())

    assert result["content_hash"] != ancien["source_hash"]
    assert "derive" not in _entry(tmp_path), "bloc perime conserve"
    # Le PNG de l'ancien hash reste sur disque (nomme par contenu, donc jamais
    # reutilise pour d'autres octets) : c'est du residu, pas une corruption.
    assert (tmp_path / "images" / "acme.fr" / ancien["variants"][0]["path"]).exists()


def test_download_ne_reprend_pas_un_bloc_dont_les_fichiers_ont_disparu(tmp_path, monkeypatch):
    _patch_package_imports(monkeypatch)
    dl = _setup_storage(monkeypatch, tmp_path)
    monkeypatch.delenv("ENABLE_LOGO_DERIVE", raising=False)

    content = png_logo_sombre()
    d = _make_downloader()
    _download(d, content=content)
    asyncio.run(dl.derive_logos_for_domain("acme.fr"))

    variante = _entry(tmp_path)["derive"]["variants"][0]
    (tmp_path / "images" / "acme.fr" / variante["path"]).unlink()

    result = _download(d, content=content)
    assert "derive" not in result, "annoncer une URL CDN absente serait un 404 cote BO"
    assert "derive" not in _entry(tmp_path)


# =============================================================================
# 5. DERIVE A LA DEMANDE — cœur du backfill des 3762
# =============================================================================

def _prepare_domaine(tmp_path, monkeypatch, content=None, key="logo-principal",
                     domain="acme.fr"):
    """Un domaine avec son master heberge et son entree manifest, sans derive."""
    monkeypatch.delenv("ENABLE_LOGO_DERIVE", raising=False)
    return _download(_make_downloader(), domain=domain, key=key,
                     content=content if content is not None else png_logo_sombre())


def test_endpoint_derive_cree_puis_confirme(client, monkeypatch):
    c, tmp_path = client
    telecharge = _prepare_domaine(tmp_path, monkeypatch)
    master = tmp_path / "images" / "acme.fr" / telecharge["hosted_path"]
    octets_master = master.read_bytes()

    r1 = c.post("/logos/acme.fr/derive")
    assert r1.status_code == 200
    corps = r1.json()
    assert corps["domaine"] == "acme.fr"
    assert corps["recipe"] == "r1m0"
    assert corps["manifest_entries"] == 1
    assert corps["counts"] == {"total": 1, "created": 1, "skipped": 0, "failed": 0}

    cree = corps["created"][0]
    assert cree["key"] == "logo-principal"
    assert cree["status"] == "created"
    assert cree["publishable"] is True
    assert cree["flags"] == []
    assert cree["metrics"]["surface"] == "any"
    assert cree["metrics"]["master_width"] == 240
    assert cree["variants"][0]["path"].startswith("logo/d/")
    assert (tmp_path / "images" / "acme.fr" / cree["variants"][0]["path"]).is_file()

    # 2e appel : idempotent, et il REDONNE les metriques (le BO ne relit pas le manifest)
    r2 = c.post("/logos/acme.fr/derive")
    assert r2.status_code == 200
    corps2 = r2.json()
    assert corps2["counts"] == {"total": 1, "created": 0, "skipped": 1, "failed": 0}
    saute = corps2["skipped"][0]
    assert saute["reason"] == "complet"
    assert saute["variants"] == cree["variants"]
    assert saute["metrics"] == cree["metrics"]
    assert saute["publishable"] is True

    # Le derive est ADDITIF : le master et son content_hash n'ont pas bouge.
    assert master.read_bytes() == octets_master
    assert _entry(tmp_path)["content_hash"] == telecharge["content_hash"]
    assert _entry(tmp_path)["hosted_path"] == telecharge["hosted_path"]


def test_endpoint_regenere_si_le_fichier_manque(client, monkeypatch):
    """Condition 2 de l'idempotence : le fichier."""
    c, tmp_path = client
    _prepare_domaine(tmp_path, monkeypatch)
    c.post("/logos/acme.fr/derive")

    variante = _entry(tmp_path)["derive"]["variants"][0]
    chemin = tmp_path / "images" / "acme.fr" / variante["path"]
    chemin.unlink()

    corps = c.post("/logos/acme.fr/derive").json()
    assert corps["counts"]["created"] == 1
    assert corps["created"][0]["reason"] == "derive"
    assert chemin.is_file(), "le fichier doit avoir ete recree"


def test_endpoint_regenere_si_le_bloc_manifest_manque(client, monkeypatch):
    """Condition 1 : un manifest non enrichi ne doit pas devenir un trou permanent."""
    c, tmp_path = client
    _prepare_domaine(tmp_path, monkeypatch)
    c.post("/logos/acme.fr/derive")

    manifest_path = tmp_path / "images" / "acme.fr" / "logo" / "manifest_logo.json"
    data = json.loads(manifest_path.read_text())
    del data["logos"][0]["derive"]          # fichiers presents, bloc absent
    manifest_path.write_text(json.dumps(data))

    corps = c.post("/logos/acme.fr/derive").json()
    assert corps["counts"]["created"] == 1
    assert "derive" in _entry(tmp_path)


def test_endpoint_force_regenere_un_derive_complet(client, monkeypatch):
    c, tmp_path = client
    _prepare_domaine(tmp_path, monkeypatch)
    c.post("/logos/acme.fr/derive")

    corps = c.post("/logos/acme.fr/derive", json={"force": True}).json()
    assert corps["counts"] == {"total": 1, "created": 1, "skipped": 0, "failed": 0}


def test_endpoint_cible_une_cle_et_signale_les_inconnues(client, monkeypatch):
    c, tmp_path = client
    _prepare_domaine(tmp_path, monkeypatch, key="logo-principal")
    _prepare_domaine(tmp_path, monkeypatch, key="logo-alternatif", content=png_logo_autre())

    corps = c.post("/logos/acme.fr/derive",
                   json={"keys": ["logo-alternatif", "cle-fantome"]}).json()

    assert corps["manifest_entries"] == 2
    assert [i["key"] for i in corps["created"]] == ["logo-alternatif"]
    assert [(i["key"], i["reason"]) for i in corps["failed"]] == [("cle-fantome", "cle_inconnue")]
    assert corps["counts"] == {"total": 2, "created": 1, "skipped": 0, "failed": 1}

    # L'entree NON ciblee n'a pas ete derivee.
    assert "derive" not in _entry(tmp_path, key="logo-principal")


def test_endpoint_refus_de_recette_est_un_etat_complet_non_publiable(client, monkeypatch):
    """svg_text : aucune variante, mais l'etat est stable — pas de re-derivation
    en boucle sur 3762 domaines, et le BO sait qu'il ne doit rien publier."""
    c, tmp_path = client
    _prepare_domaine(tmp_path, monkeypatch, content=SVG_AVEC_TEXTE)

    corps = c.post("/logos/acme.fr/derive").json()
    cree = corps["created"][0]
    assert cree["variants"] == []
    assert cree["flags"] == ["svg_text"]
    assert cree["blocking_flags"] == ["svg_text"]
    assert cree["publishable"] is False
    assert cree["error"] is None, "un refus n'est pas une defaillance"

    corps2 = c.post("/logos/acme.fr/derive").json()
    assert corps2["counts"]["skipped"] == 1
    assert corps2["skipped"][0]["reason"] == "refus_sans_variante"


def test_endpoint_refuse_un_master_dont_les_octets_ont_change(client, monkeypatch):
    """Le nommage est adresse par contenu et le CDN est immutable 30 jours sans purge."""
    c, tmp_path = client
    result = _prepare_domaine(tmp_path, monkeypatch)

    master = tmp_path / "images" / "acme.fr" / result["hosted_path"]
    master.write_bytes(png_logo_autre())      # octets != content_hash du manifest

    corps = c.post("/logos/acme.fr/derive").json()
    assert corps["counts"] == {"total": 1, "created": 0, "skipped": 0, "failed": 1}
    echec = corps["failed"][0]
    assert echec["reason"] == "master_hash_different"
    assert result["content_hash"] in echec["error"]
    assert not _derive_dir(tmp_path).exists()


def test_endpoint_signale_un_master_absent(client, monkeypatch):
    c, tmp_path = client
    result = _prepare_domaine(tmp_path, monkeypatch)
    (tmp_path / "images" / "acme.fr" / result["hosted_path"]).unlink()

    corps = c.post("/logos/acme.fr/derive").json()
    assert corps["counts"]["failed"] == 1
    assert corps["failed"][0]["reason"] == "master_illisible"


def test_endpoint_domaine_inconnu_repond_200_vide(client):
    c, _tmp = client
    r = c.post("/logos/jamais-vu.fr/derive")
    assert r.status_code == 200
    corps = r.json()
    assert corps["manifest_entries"] == 0
    assert corps["counts"] == {"total": 0, "created": 0, "skipped": 0, "failed": 0}


@pytest.mark.parametrize("domaine, attendu", [
    ("bad domain", 400),        # atteint la route -> garde _validate_domain
    ("acme.fr%00.png", 400),    # octet nul -> garde
    ("..%2F..%2Fetc", 404),     # normalise par le client/routeur avant la route
    ("..", 404),
    ("acme.fr/x", 404),         # segment surnumeraire -> aucune route
])
def test_endpoint_garde_de_domaine(client, domaine, attendu):
    """Le parametre construit un chemin d'ECRITURE : la garde est obligatoire.

    Les cas 404 documentent que la normalisation d'URL retire d'elle-meme les
    ``..`` AVANT le routage — c'est un filet, pas la garde : la garde est
    verifiee sans client HTTP par le test suivant.
    """
    c, tmp_path = client
    r = c.post("/logos/%s/derive" % domaine)
    assert r.status_code == attendu, r.text
    if attendu == 400:
        assert r.json()["detail"] == "domaine invalide"
    assert not (tmp_path / "images").joinpath("logo").exists()


def test_garde_de_domaine_bloque_avant_toute_ecriture(client, monkeypatch):
    """Appel DIRECT de la vue : un proxy qui transmet le chemin brut ne doit pas
    faire ecrire hors du domaine. Le cœur ne doit meme pas etre appele."""
    from fastapi import HTTPException
    import core.downloader as dl
    import routers.logos as routeur

    appels = []

    async def _ne_doit_pas_etre_appele(domain, keys=None, force=False):
        appels.append(domain)
        return {}

    monkeypatch.setattr(dl, "derive_logos_for_domain", _ne_doit_pas_etre_appele)

    for domaine in ("../../etc", "acme.fr/../../etc", "/etc/passwd"):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(routeur.derive_domain_logos(domaine, None))
        assert exc.value.status_code == 400

    assert appels == [], "la garde doit preceder tout acces disque"


def test_endpoint_erreur_de_fusion_est_rapportee_en_echec(client, monkeypatch):
    """Variantes ecrites mais manifest non fusionne : ne PAS annoncer un succes."""
    c, tmp_path = client
    _prepare_domaine(tmp_path, monkeypatch)

    import core.downloader as dl

    def _boom(domain, key, patch):
        raise OSError("verrou indisponible")

    monkeypatch.setattr(dl, "_merge_manifest_logo_entry", _boom)

    corps = c.post("/logos/acme.fr/derive").json()
    assert corps["counts"]["failed"] == 1
    echec = corps["failed"][0]
    assert echec["reason"] == "manifest_non_fusionne"
    # Les metriques sont quand meme rendues (le travail pyvips a eu lieu)...
    assert echec["metrics"]["surface"] == "any"
    # ... et le rejeu reparera, parce que le bloc manque au manifest.
    assert "derive" not in _entry(tmp_path)


# =============================================================================
# 6. NON-REGRESSION DU CONTRAT DE LECTURE
# =============================================================================

def test_get_logos_expose_le_bloc_derive_verbatim(client, monkeypatch):
    c, tmp_path = client
    _prepare_domaine(tmp_path, monkeypatch)
    cree = c.post("/logos/acme.fr/derive").json()["created"][0]

    corps = c.get("/logos/acme.fr").json()
    entree = corps["logos"][0]

    # Les cles historiques du manifest sont intactes...
    for cle in ("key", "hosted_path", "format", "width", "height",
                "content_hash", "downloaded_at"):
        assert cle in entree, cle
    # ... et le derive est ajoute a cote, sous une cle dediee.
    assert entree["derive"]["variants"] == cree["variants"]
    assert entree["derive"]["metrics"] == cree["metrics"]


# =============================================================================
# 7. ENTREES LEGACY (sans content_hash) — CONVERGENCE DU BACKFILL
# =============================================================================
# ``content_hash`` a ete introduit AVEC ce chantier : les logos heberges avant
# lui n'en ont pas. C'est precisement la population visee par le rattrapage.
# ``_logo_derive_state`` ne peut rien conclure sans hash de reference, donc
# ``_derive_logo_entry`` doit re-evaluer l'idempotence avec le hash du master
# REELLEMENT lu — sinon ces entrees repondent eternellement ``created`` et un
# pilote de backfill qui boucle « jusqu'a ce que tout soit skipped » ne s'arrete
# jamais (mesure avant correctif : 5 appels, 5 fois ``created``).

def _rendre_legacy(tmp_path, domain="acme.fr", key="logo-principal"):
    """Retire ``content_hash`` de l'entree, comme une entree d'avant le chantier."""
    chemin = tmp_path / "images" / domain / "logo" / "manifest_logo.json"
    manifest = json.loads(chemin.read_text())
    for entree in manifest["logos"]:
        if entree.get("key") == key:
            entree.pop("content_hash", None)
    chemin.write_text(json.dumps(manifest, indent=2))
    return manifest


def test_entree_legacy_converge_vers_skipped(client, monkeypatch):
    """2e appel = skipped, et non un ``created`` perpetuel."""
    c, tmp_path = client
    _prepare_domaine(tmp_path, monkeypatch)
    _rendre_legacy(tmp_path)
    assert "content_hash" not in _entry(tmp_path)

    premier = c.post("/logos/acme.fr/derive").json()
    assert premier["counts"]["created"] == 1, premier

    for tour in range(3):
        suivant = c.post("/logos/acme.fr/derive").json()
        assert suivant["counts"]["skipped"] == 1, "tour %d : %s" % (tour, suivant)
        assert suivant["skipped"][0]["reason"] == "complet"
        assert suivant["counts"]["created"] == 0


def test_entree_legacy_ne_reecrit_pas_les_fichiers_au_2e_appel(client, monkeypatch):
    """La convergence doit etre reelle : aucun inode touche au rejeu."""
    c, tmp_path = client
    _prepare_domaine(tmp_path, monkeypatch)
    _rendre_legacy(tmp_path)
    c.post("/logos/acme.fr/derive")

    dossier = _derive_dir(tmp_path)
    avant = {f.name: (f.stat().st_ino, f.stat().st_mtime_ns)
             for f in dossier.iterdir()}
    assert avant, "aucune variante produite"

    c.post("/logos/acme.fr/derive")
    apres = {f.name: (f.stat().st_ino, f.stat().st_mtime_ns)
             for f in dossier.iterdir()}
    assert avant == apres, "fichiers reecrits alors que le derive etait complet"


def test_entree_legacy_force_regenere_quand_meme(client, monkeypatch):
    """``force`` doit continuer a outrepasser l'idempotence, hash absent inclus."""
    c, tmp_path = client
    _prepare_domaine(tmp_path, monkeypatch)
    _rendre_legacy(tmp_path)
    c.post("/logos/acme.fr/derive")

    forcee = c.post("/logos/acme.fr/derive", json={"force": True}).json()
    assert forcee["counts"]["created"] == 1, forcee


def test_entree_legacy_derive_sur_les_octets_du_disque(client, monkeypatch):
    """Sans hash annonce, le refus dur ne s'applique pas : on derive ce qu'on lit,
    et le bloc porte le hash de ces octets-la."""
    c, tmp_path = client
    telecharge = _prepare_domaine(tmp_path, monkeypatch)
    _rendre_legacy(tmp_path)
    master = tmp_path / "images" / "acme.fr" / telecharge["hosted_path"]
    attendu = hashlib.sha256(master.read_bytes()).hexdigest()

    cree = c.post("/logos/acme.fr/derive").json()["created"][0]
    assert cree["source_hash"] == attendu
    assert _entry(tmp_path)["derive"]["source_hash"] == attendu
    # le master n'a pas ete touche
    assert hashlib.sha256(master.read_bytes()).hexdigest() == attendu


# =============================================================================
# 7. NON-REGRESSION G1 — refus LEGITIME contre DEFAILLANCE
# =============================================================================
# Les deux produisent la MEME forme dans le manifest (``variants == []`` +
# ``metrics`` porteur de ``flags``). Le discriminant est ``error`` :
#   - refus  -> error is None -> etat COMPLET et terminal -> reste ``skipped`` ;
#   - panne  -> error renseignee -> JAMAIS complet -> le rejeu la reprend.
# Sans ce discriminant, une panne pyvips transitoire devenait un trou PERMANENT
# (mesure : passe 1 en panne -> created ; passe 2 panne DISPARUE -> skipped ;
# passe 3 -> skipped ; 0 variante sur disque, et seul ``force=true`` reparait).

def _derive_en_panne(monkeypatch):
    """Fait echouer pyvips DANS la recette : ``derive_logo`` rend derivation_failed
    (avec ``error``), il ne leve pas — c'est son contrat."""
    from core import logo_derive
    monkeypatch.setattr(
        logo_derive, "_load_raster",
        lambda content: (_ for _ in ()).throw(RuntimeError("panne pyvips transitoire")),
    )


def test_defaillance_de_derivation_est_rapportee_en_echec(client, monkeypatch):
    """Une panne ne doit pas etre annoncee ``created`` : un pilote qui boucle
    « jusqu'a ce que tout soit skipped » lirait un trou comme un succes."""
    c, tmp_path = client
    _prepare_domaine(tmp_path, monkeypatch)
    _derive_en_panne(monkeypatch)

    corps = c.post("/logos/acme.fr/derive").json()
    assert corps["counts"] == {"total": 1, "created": 0, "skipped": 0, "failed": 1}, corps
    echec = corps["failed"][0]
    assert echec["reason"] == "derivation_defaillante"
    assert echec["flags"] == ["derivation_failed"]
    assert echec["publishable"] is False
    assert echec["error"]


def test_defaillance_transitoire_est_reparee_par_le_rejeu(client, monkeypatch):
    """Le cœur de G1 : la panne disparait, la passe suivante doit REPARER."""
    c, tmp_path = client
    _prepare_domaine(tmp_path, monkeypatch)

    with monkeypatch.context() as panne:
        _derive_en_panne(panne)
        assert c.post("/logos/acme.fr/derive").json()["counts"]["failed"] == 1

    # panne retiree, meme master, meme content_hash
    passe2 = c.post("/logos/acme.fr/derive").json()
    assert passe2["counts"]["created"] == 1, passe2
    assert passe2["created"][0]["publishable"] is True
    assert _entry(tmp_path)["derive"]["variants"], "aucune variante apres reparation"

    passe3 = c.post("/logos/acme.fr/derive").json()
    assert passe3["counts"]["skipped"] == 1
    assert passe3["skipped"][0]["reason"] == "complet"


def test_refus_de_recette_reste_terminal(client, monkeypatch):
    """Sens inverse : un refus legitime (error is None) ne doit PAS etre rejoue."""
    c, tmp_path = client
    _prepare_domaine(tmp_path, monkeypatch, content=SVG_AVEC_TEXTE)

    p1 = c.post("/logos/acme.fr/derive").json()
    assert p1["created"][0]["flags"] == ["svg_text"]
    assert p1["created"][0]["error"] is None

    p2 = c.post("/logos/acme.fr/derive").json()
    assert p2["counts"]["skipped"] == 1
    assert p2["skipped"][0]["reason"] == "refus_sans_variante"


def test_telechargement_ne_reprend_pas_un_bloc_en_echec(tmp_path, monkeypatch):
    """``_carry_over_logo_derive_block`` reprenait le bloc en ECHEC : flag ON, un
    re-telechargement identique ne re-derivait donc pas non plus."""
    _patch_package_imports(monkeypatch)
    dl = _setup_storage(monkeypatch, tmp_path)
    monkeypatch.delenv("ENABLE_LOGO_DERIVE", raising=False)

    content = png_logo_sombre()
    _download(_make_downloader(), content=content)
    with monkeypatch.context() as panne:
        _derive_en_panne(panne)
        asyncio.run(dl.derive_logos_for_domain("acme.fr"))
    assert _entry(tmp_path)["derive"]["error"]

    repris = dl._carry_over_logo_derive_block(
        "acme.fr", "logo-principal", hashlib.sha256(content).hexdigest()
    )
    assert repris is None, "un bloc en echec ne doit pas etre repris"


# =============================================================================
# 8. NON-REGRESSION G2 — bornes de ressources (memoire et concurrence)
# =============================================================================
# MESURE du 01/09/2026 sur ce poste (VmHWM, pire format = GIF, que libvips ne
# peut pas lire en flux) : un master de 64 Mpx pese 131 Ko et coute 383 Mo ; a
# 8 derivations simultanees, 2460 Mo — au-dela des 2 Go de la replica. Un
# OOM-kill ne leve aucune exception Python : le message RabbitMQ n'est jamais
# acquitte, requeue sans x-death, n'atteint jamais MAX_RETRIES, ne part jamais en
# DLQ, et tue la replica suivante. APRES : 65 Mo (refus) et 2 simultanees max.

def test_master_trop_grand_est_refuse_sans_etre_derive(client, monkeypatch):
    """Le plafond se lit sur les dimensions DEJA connues : aucune trame decodee."""
    c, tmp_path = client
    _prepare_domaine(tmp_path, monkeypatch)
    monkeypatch.setenv("LOGO_DERIVE_MAX_MASTER_PIXELS", "1000")

    from core import logo_derive
    monkeypatch.setattr(
        logo_derive, "derive_logo",
        lambda *a, **k: pytest.fail("derive_logo appele malgre le plafond"),
    )

    corps = c.post("/logos/acme.fr/derive").json()
    cree = corps["created"][0]
    assert cree["flags"] == ["master_too_large"]
    assert cree["error"] is None, "un refus n'est pas une defaillance"
    assert cree["variants"] == []
    assert cree["publishable"] is False
    # « la publication se decide sur BLOCKING_FLAGS SEUL » : le motif doit y etre.
    assert cree["blocking_flags"] == ["master_too_large"]

    bloc = _entry(tmp_path)["derive"]
    assert bloc["metrics"]["master_width"] == 240
    assert "1000" in bloc["metrics"]["refus_politique"]


def test_refus_de_taille_est_terminal_mais_rejouable_par_force(client, monkeypatch):
    """Terminal (sinon chaque passe de backfill relit le master pour rien), et
    rejouable des que le porteur releve le plafond."""
    c, tmp_path = client
    _prepare_domaine(tmp_path, monkeypatch)

    with monkeypatch.context() as petit:
        petit.setenv("LOGO_DERIVE_MAX_MASTER_PIXELS", "1000")
        c.post("/logos/acme.fr/derive")
        p2 = c.post("/logos/acme.fr/derive").json()
        assert p2["counts"]["skipped"] == 1
        assert p2["skipped"][0]["reason"] == "refus_sans_variante"

    # plafond releve -> force regenere
    forcee = c.post("/logos/acme.fr/derive", json={"force": True}).json()
    assert forcee["counts"]["created"] == 1
    assert forcee["created"][0]["publishable"] is True


def test_un_svg_echappe_au_plafond_de_surface(client, monkeypatch):
    """Un SVG n'a pas de surface : ses dimensions declarees peuvent etre enormes
    alors que le rendu est borne a MAX_WORK_EDGE par la recette."""
    c, tmp_path = client
    svg = (b'<svg xmlns="http://www.w3.org/2000/svg" width="20000" height="20000" '
           b'viewBox="0 0 20000 20000"><rect x="2000" y="2000" width="16000" '
           b'height="16000" fill="#1e1e1e"/></svg>')
    _prepare_domaine(tmp_path, monkeypatch, content=svg)
    monkeypatch.setenv("LOGO_DERIVE_MAX_MASTER_PIXELS", "1000000")

    corps = c.post("/logos/acme.fr/derive").json()
    cree = corps["created"][0]
    assert "master_too_large" not in cree["flags"], cree
    assert cree["variants"], cree


def test_semaphore_borne_les_derivations_pyvips_simultanees(tmp_path, monkeypatch):
    """Le seul plafond etait le ThreadPoolExecutor par defaut de to_thread, soit
    min(32, os.cpu_count() + 4) — et dans un conteneur a QUOTA CPU cet appel rend
    les CPU de l'HOTE."""
    _patch_package_imports(monkeypatch)
    dl = _setup_storage(monkeypatch, tmp_path)
    monkeypatch.setenv("LOGO_DERIVE_MAX_PARALLEL", "2")
    monkeypatch.setenv("LOGO_DERIVE_MAX_QUEUE", "8")

    from core import logo_derive
    content = png_logo_sombre()
    empreinte = hashlib.sha256(content).hexdigest()

    verrou = threading.Lock()
    etat = {"courant": 0, "max": 0}
    vrai_derive = logo_derive.derive_logo

    def instrumente(*args, **kwargs):
        with verrou:
            etat["courant"] += 1
            etat["max"] = max(etat["max"], etat["courant"])
        try:
            time.sleep(0.05)  # fenetre de chevauchement
            return vrai_derive(*args, **kwargs)
        finally:
            with verrou:
                etat["courant"] -= 1

    monkeypatch.setattr(logo_derive, "derive_logo", instrumente)

    async def principal():
        return await asyncio.gather(*[
            dl._derive_and_write_logo("acme.fr", "logo-%d" % i, content, empreinte)
            for i in range(8)
        ])

    blocs = asyncio.run(principal())
    assert len(blocs) == 8
    assert all(b["variants"] for b in blocs), "les 8 doivent aboutir, pas etre refusees"
    assert etat["max"] <= 2, "derivations simultanees : %d" % etat["max"]


def test_admission_refuse_au_dela_de_la_file(tmp_path, monkeypatch):
    """Mieux vaut un 429 honnete qu'une file d'attente invisible qui expire chez
    l'appelant pendant que le serveur continue d'ecrire."""
    _patch_package_imports(monkeypatch)
    dl = _setup_storage(monkeypatch, tmp_path)
    monkeypatch.delenv("ENABLE_LOGO_DERIVE", raising=False)
    monkeypatch.setenv("LOGO_DERIVE_MAX_PARALLEL", "1")
    monkeypatch.setenv("LOGO_DERIVE_MAX_QUEUE", "1")

    _download(_make_downloader(), content=png_logo_sombre())

    async def principal():
        return await asyncio.gather(
            *[dl.derive_logos_for_domain("acme.fr", force=True) for _ in range(4)],
            return_exceptions=True,
        )

    resultats = asyncio.run(principal())
    satures = [r for r in resultats if isinstance(r, dl.LogoDeriveOverloaded)]
    servis = [r for r in resultats if isinstance(r, dict)]
    autres = [r for r in resultats
              if not isinstance(r, (dict, dl.LogoDeriveOverloaded))]
    assert autres == []
    assert len(servis) == 2, "max_parallel + max_queue = 2 places"
    assert len(satures) == 2


def test_endpoint_repond_429_quand_les_derivations_sont_saturees(client, monkeypatch):
    c, _tmp = client
    import core.downloader as dl

    async def sature(*args, **kwargs):
        raise dl.LogoDeriveOverloaded("derivations saturees")

    monkeypatch.setattr(dl, "derive_logos_for_domain", sature)

    r = c.post("/logos/acme.fr/derive")
    assert r.status_code == 429
    assert r.headers.get("Retry-After") == "5"


# =============================================================================
# 9. NON-REGRESSION G3 — l'ecriture MASTER ne detruit plus le bloc derive
# =============================================================================
# MESURE sous concurrence reelle (threads + barriere, 20 rondes) : bloc derive
# absent a l'arrivee 8 fois sur 20 (40 %) avec le REPLACE, 0 fois sur 20 avec la
# FUSION. Et en interleaving deterministe (report-over lu AVANT la fusion, puis
# _append), la perte etait systematique.

def test_ecriture_master_preserve_un_bloc_derive_pose_entre_temps(tmp_path, monkeypatch):
    """Interleaving deterministe du rapport de revue : le telechargement a lu son
    report-over (rien), le backfill fusionne, puis le telechargement ecrit."""
    _patch_package_imports(monkeypatch)
    dl = _setup_storage(monkeypatch, tmp_path)
    monkeypatch.delenv("ENABLE_LOGO_DERIVE", raising=False)

    telecharge = _download(_make_downloader(), content=png_logo_sombre())
    asyncio.run(dl.derive_logos_for_domain("acme.fr"))
    bloc = _entry(tmp_path)["derive"]

    # L'entree master seule, telle que _append la recevrait.
    dl._append_manifest_logo_entry("acme.fr", dict(telecharge))

    assert _entry(tmp_path).get("derive") == bloc, "bloc derive efface par le master"


def test_ecriture_master_et_fusion_derive_en_concurrence(tmp_path, monkeypatch):
    """Course libre : 8 rondes, depart simultane sur barriere."""
    _patch_package_imports(monkeypatch)
    dl = _setup_storage(monkeypatch, tmp_path)
    monkeypatch.delenv("ENABLE_LOGO_DERIVE", raising=False)

    telecharge = _download(_make_downloader(), content=png_logo_sombre())
    asyncio.run(dl.derive_logos_for_domain("acme.fr"))
    bloc = _entry(tmp_path)["derive"]

    perdus = 0
    for _ronde in range(8):
        manifest = dl._load_manifest_logo_file("acme.fr")
        for e in manifest["logos"]:
            e.pop("derive", None)
        dl._save_manifest_logo_file("acme.fr", manifest)

        barriere = threading.Barrier(2)
        soucis = []

        def maitre():
            barriere.wait()
            dl._append_manifest_logo_entry("acme.fr", dict(telecharge))

        def derive():
            barriere.wait()
            try:
                dl._merge_manifest_logo_entry(
                    "acme.fr", "logo-principal", {"derive": bloc}
                )
            except Exception as exc:  # remonte, il ne doit pas y en avoir
                soucis.append(exc)

        fils = [threading.Thread(target=maitre), threading.Thread(target=derive)]
        for f in fils:
            f.start()
        for f in fils:
            f.join()

        assert soucis == [], soucis
        if not (_entry(tmp_path) or {}).get("derive"):
            perdus += 1

    assert perdus == 0, "bloc derive perdu %d fois sur 8" % perdus


def test_ecriture_master_preserve_une_cle_inconnue(tmp_path, monkeypatch):
    """La fusion est generique : elle ne detruit AUCUNE cle qu'elle ne possede pas
    (les cles du master, elles, gagnent toujours)."""
    _patch_package_imports(monkeypatch)
    dl = _setup_storage(monkeypatch, tmp_path)

    dl._append_manifest_logo_entry("acme.fr", {
        "key": "logo-principal", "content_hash": "a" * 64, "width": 10,
        "annotation_bo": {"valide_par": "moi"},
    })
    dl._append_manifest_logo_entry("acme.fr", {
        "key": "logo-principal", "content_hash": "b" * 64, "width": 20,
    })

    entree = _entry(tmp_path)
    assert entree["annotation_bo"] == {"valide_par": "moi"}
    assert entree["content_hash"] == "b" * 64
    assert entree["width"] == 20


# =============================================================================
# 10. NON-REGRESSION G5 — les stat() d'idempotence ne bloquent plus la boucle
# =============================================================================
# MESURE : 60 entrees deja derivees, stat NFS simule a 10 ms, 2e passage qui ne
# fait RIEN -> 612 ms de blocage CONTINU de la boucle (1 seul tick de chien de
# garde). C'est la meme boucle qui porte les heartbeats aio_pika du LogoConsumer
# et /health. APRES : 1 ms, 120 ticks.

def test_l_idempotence_ne_bloque_pas_la_boucle(tmp_path, monkeypatch):
    _patch_package_imports(monkeypatch)
    dl = _setup_storage(monkeypatch, tmp_path)
    monkeypatch.delenv("ENABLE_LOGO_DERIVE", raising=False)
    monkeypatch.setenv("LOGO_DERIVE_MAX_ENTRIES", "1000")
    monkeypatch.setenv("LOGO_DERIVE_TIME_BUDGET_S", "600")

    contenu = png_logo_sombre()
    d = _make_downloader()
    for i in range(12):
        _download(d, key="logo-%02d" % i, content=contenu)
    assert asyncio.run(dl.derive_logos_for_domain("acme.fr"))["counts"]["created"] == 12

    vrai_isfile = os.path.isfile

    def isfile_nfs(chemin):
        if "/logo/d/" in str(chemin) or "\\logo\\d\\" in str(chemin):
            time.sleep(0.010)
        return vrai_isfile(chemin)

    monkeypatch.setattr(os.path, "isfile", isfile_nfs)

    async def principal():
        intervalles = []
        arret = asyncio.Event()

        async def chien():
            precedent = time.perf_counter()
            while not arret.is_set():
                await asyncio.sleep(0.005)
                maintenant = time.perf_counter()
                intervalles.append(maintenant - precedent)
                precedent = maintenant

        tache = asyncio.create_task(chien())
        debut = time.perf_counter()
        rapport = await dl.derive_logos_for_domain("acme.fr")
        mur = time.perf_counter() - debut
        arret.set()
        await tache
        return rapport, mur, intervalles

    rapport, mur, intervalles = asyncio.run(principal())

    assert rapport["counts"]["skipped"] == 12, rapport["counts"]
    assert mur > 0.10, "le banc doit vraiment couter du stat (%.3f s)" % mur
    blocage = max(intervalles) - 0.005
    assert blocage < 0.050, "boucle bloquee %.0f ms d'affilee" % (blocage * 1000)


# =============================================================================
# 11. NON-REGRESSION G6 — le travail est borne par requete
# =============================================================================
# AVANT : sans ``keys``, TOUTES les entrees etaient traitees (40 entrees en
# 3,4 s, ~13 s pour 200 cles), sans aucun plafond ni timeout serveur, et une
# prise de verrou pouvait couter 29,3 s.

def _domaine_a_n_entrees(monkeypatch, tmp_path, n):
    dl = _setup_storage(monkeypatch, tmp_path)
    monkeypatch.delenv("ENABLE_LOGO_DERIVE", raising=False)
    contenu = png_logo_sombre()
    d = _make_downloader()
    for i in range(n):
        _download(d, key="logo-%02d" % i, content=contenu)
    return dl


def test_plafond_d_entrees_par_requete_et_reste_visible(tmp_path, monkeypatch):
    _patch_package_imports(monkeypatch)
    dl = _domaine_a_n_entrees(monkeypatch, tmp_path, 12)
    monkeypatch.setenv("LOGO_DERIVE_MAX_ENTRIES", "5")
    monkeypatch.setenv("LOGO_DERIVE_TIME_BUDGET_S", "600")

    rapport = asyncio.run(dl.derive_logos_for_domain("acme.fr"))
    assert rapport["counts"]["created"] == 5
    assert rapport["truncated"] is True
    assert rapport["stop_reason"] == "max_entries"
    assert len(rapport["remaining"]) == 7
    assert rapport["remaining"][0] == "logo-05"
    # ``counts`` garde sa forme historique : c'est un contrat pour le pilote.
    assert set(rapport["counts"]) == {"total", "created", "skipped", "failed"}


def test_les_skipped_ne_consomment_pas_le_plafond(tmp_path, monkeypatch):
    """Sinon un domaine ayant plus d'entrees que le plafond ne progresserait
    JAMAIS : chaque appel reconsommerait sa borne sur les entrees deja faites."""
    _patch_package_imports(monkeypatch)
    dl = _domaine_a_n_entrees(monkeypatch, tmp_path, 12)
    monkeypatch.setenv("LOGO_DERIVE_MAX_ENTRIES", "5")
    monkeypatch.setenv("LOGO_DERIVE_TIME_BUDGET_S", "600")

    faits = 0
    for appel in range(5):
        rapport = asyncio.run(dl.derive_logos_for_domain("acme.fr"))
        faits += rapport["counts"]["created"]
        if not rapport["truncated"]:
            break
    assert faits == 12, "%d derivees en %d appels" % (faits, appel + 1)
    assert rapport["truncated"] is False
    # Le dernier appel a EXAMINE les 12 entrees : la borne n'a pas ete consommee
    # par les 10 deja completes.
    assert rapport["counts"]["total"] == 12, rapport["counts"]
    assert rapport["counts"]["skipped"] == 10

    # Et un appel de plus ne fait plus rien du tout : le pilote peut s'arreter.
    dernier = asyncio.run(dl.derive_logos_for_domain("acme.fr"))
    assert dernier["counts"] == {"total": 12, "created": 0, "skipped": 12, "failed": 0}
    assert dernier["truncated"] is False


def test_budget_de_temps_arrete_la_requete(tmp_path, monkeypatch):
    _patch_package_imports(monkeypatch)
    dl = _domaine_a_n_entrees(monkeypatch, tmp_path, 12)
    monkeypatch.setenv("LOGO_DERIVE_MAX_ENTRIES", "1000")
    monkeypatch.setenv("LOGO_DERIVE_TIME_BUDGET_S", "0.15")

    debut = time.perf_counter()
    rapport = asyncio.run(dl.derive_logos_for_domain("acme.fr"))
    mur = time.perf_counter() - debut

    assert rapport["truncated"] is True
    assert rapport["stop_reason"] == "time_budget"
    assert rapport["remaining"], rapport
    assert rapport["counts"]["total"] < 12
    assert mur < 5.0, "budget non respecte (%.2f s)" % mur


def test_attente_de_verrou_bornee_sur_le_chemin_http(tmp_path, monkeypatch):
    """``nfs_lock`` fige son max_wait a 30 s : plus long que le timeout de la
    plupart des appelants, qui abandonnent pendant que le serveur ecrit encore."""
    _patch_package_imports(monkeypatch)
    dl = _domaine_a_n_entrees(monkeypatch, tmp_path, 1)
    monkeypatch.setenv("LOGO_DERIVE_LOCK_TIMEOUT_S", "1")

    from core.nfs_lock import NFSLockError, nfs_lock
    chemin = os.path.join(str(tmp_path), "images", "acme.fr", "logo",
                          "manifest_logo.json")
    tenu = threading.Event()
    relache = threading.Event()

    def squatteur():
        with nfs_lock(chemin, max_wait=30):
            tenu.set()
            relache.wait(30)

    fil = threading.Thread(target=squatteur, daemon=True)
    fil.start()
    assert tenu.wait(10)

    debut = time.perf_counter()
    with pytest.raises(NFSLockError):
        dl._merge_manifest_logo_entry("acme.fr", "logo-00", {"sonde": 1})
    attente = time.perf_counter() - debut

    relache.set()
    fil.join(timeout=10)
    assert attente < 3.0, "attente de verrou %.1f s" % attente
