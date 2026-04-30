"""Shared fixtures for image-download-service tests."""

import io
import os
import sys
import types
from pathlib import Path

import pytest
from PIL import Image


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "images"


# =============================================================================
# Helper partagé : injection des alias d'import internes
# =============================================================================

def _patch_package_imports(monkeypatch):
    """
    Injecte les modules internes sous les deux alias de chemin d'import :
      - core.* / services.*                       (pythonpath = app, convention des tests)
      - image_download_service.core.* / .services.*  (import absolu utilisé en production
                                                      par main.py, le router albums et
                                                      album_actions)

    Cela évite ModuleNotFoundError sans avoir à installer le package.
    Utilisé dans tous les fichiers de test via import depuis conftest.
    """
    import core.nfs_lock as real_nfs_lock
    import core.image_processor as real_image_processor

    if "image_download_service" not in sys.modules:
        pkg = types.ModuleType("image_download_service")
        monkeypatch.setitem(sys.modules, "image_download_service", pkg)

    if "image_download_service.core" not in sys.modules:
        core_pkg = types.ModuleType("image_download_service.core")
        monkeypatch.setitem(sys.modules, "image_download_service.core", core_pkg)

    monkeypatch.setitem(sys.modules, "image_download_service.core.nfs_lock", real_nfs_lock)
    monkeypatch.setitem(
        sys.modules, "image_download_service.core.image_processor", real_image_processor
    )

    # Aliases pour core.downloader (utilisé par le router albums via lazy import).
    # Optionnel : on tente l'import mais on tolère l'échec (downloader.py tire des
    # libs lourdes que certains tests ne veulent pas charger).
    try:
        import core.downloader as real_downloader
        monkeypatch.setitem(
            sys.modules, "image_download_service.core.downloader", real_downloader
        )
    except ImportError:
        pass

    # Aliases pour les modules services.* introduits par la feature Albums.
    # Le router et le code applicatif importent désormais via le préfixe
    # `image_download_service.services.*` (cohérent avec la prod), ces aliases
    # permettent aux tests de garder le pythonpath court (`from services.X`).
    if "image_download_service.services" not in sys.modules:
        services_pkg = types.ModuleType("image_download_service.services")
        monkeypatch.setitem(sys.modules, "image_download_service.services", services_pkg)

    for mod_name in ("album_summary", "album_products", "album_actions", "album_jobs"):
        try:
            real_mod = __import__(f"services.{mod_name}", fromlist=[mod_name])
            monkeypatch.setitem(
                sys.modules, f"image_download_service.services.{mod_name}", real_mod
            )
        except ImportError:
            # Service module absent (ex: tests anciens avant Tasks 1-4) — sans danger.
            pass


# =============================================================================
# Helpers de génération d'images in-memory
# =============================================================================

def _rgba_with_transparent_corner(size=(10, 10)):
    """Base : rouge uni avec pixel (0,0) totalement transparent."""
    img = Image.new("RGBA", size, (255, 0, 0, 255))
    img.putpixel((0, 0), (0, 0, 0, 0))
    return img


def make_transparent_png(size=(10, 10)) -> bytes:
    """PNG 10×10 rouge avec pixel (0,0) totalement transparent."""
    buf = io.BytesIO()
    _rgba_with_transparent_corner(size).save(buf, "PNG")
    return buf.getvalue()


def make_transparent_webp(size=(10, 10)) -> bytes:
    """WebP 10×10 rouge avec pixel (0,0) totalement transparent."""
    buf = io.BytesIO()
    _rgba_with_transparent_corner(size).save(buf, "WEBP")
    return buf.getvalue()


def make_transparent_gif(size=(10, 10)) -> bytes:
    """GIF 10×10 avec pixel (0,0) transparent via info['transparency']."""
    img = _rgba_with_transparent_corner(size)
    buf = io.BytesIO()
    # Pillow convertit RGBA → P automatiquement ; `transparency=0` pose
    # l'index de la couleur transparente dans la palette GIF.
    img.save(buf, "GIF", transparency=0)
    return buf.getvalue()


def make_opaque_jpeg(size=(10, 10), color=(255, 0, 0)) -> bytes:
    """JPEG 10×10 couleur unie (par défaut rouge)."""
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


# =============================================================================
# Fixtures pytest (exposées aux tests)
# =============================================================================

@pytest.fixture
def transparent_png_bytes():
    return make_transparent_png()


@pytest.fixture
def transparent_webp_bytes():
    return make_transparent_webp()


@pytest.fixture
def transparent_gif_bytes():
    return make_transparent_gif()


@pytest.fixture
def opaque_jpeg_bytes():
    return make_opaque_jpeg()


@pytest.fixture
def create_stub_files():
    """Helper pour créer des fichiers vides (stub) aux chemins main/thumb simulés."""
    def _create(main_path: str, thumb_path: str):
        os.makedirs(os.path.dirname(main_path), exist_ok=True)
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        open(main_path, "wb").close()
        open(thumb_path, "wb").close()
    return _create
