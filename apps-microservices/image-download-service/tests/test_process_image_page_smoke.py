"""Smoke tests for process_image_page() — Chantier D T3.

Validates that:
1. process_image_page() returns a dict with the 4 required metadata keys
   (width, height, format, file_size) in addition to main_path/thumb_path/filename.
2. Output files are written under the pages/ sharding scheme
   (not produit-2 / produit-3).
3. The function accepts the expected (content, domain, storage_subdir, filename) signature.
4. No regression on process_image() — it must still return exactly the same keys
   it always returned (main_path, thumb_path, filename) plus the new metadata keys.
"""

import io
import os

import pytest
from PIL import Image

from core.image_processor import ImageProcessor
from core.downloader import _build_filename


# ---------------------------------------------------------------------------
# Shared image factory (tiny 10×10 images — fast, no disk I/O concerns)
# ---------------------------------------------------------------------------

def _make_jpeg_bytes(size=(10, 10), color=(200, 100, 50)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG", quality=85)
    return buf.getvalue()


def _make_png_bytes(size=(10, 10)) -> bytes:
    img = Image.new("RGBA", size, (255, 0, 0, 128))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


_REQUIRED_METADATA_KEYS = {"width", "height", "format", "file_size"}
_REQUIRED_PATH_KEYS = {"main_path", "thumb_path", "filename"}
_ALL_REQUIRED_KEYS = _REQUIRED_METADATA_KEYS | _REQUIRED_PATH_KEYS


# ---------------------------------------------------------------------------
# Tests for process_image_page()
# ---------------------------------------------------------------------------

class TestProcessImagePage:
    """Smoke tests for the new process_image_page() entry point."""

    def test_returns_all_required_keys_jpeg(self, tmp_path):
        """process_image_page() must return the 7 expected keys for a JPEG."""
        processor = ImageProcessor()
        content = _make_jpeg_bytes()
        storage_subdir = str(tmp_path / "pages_storage")
        os.makedirs(storage_subdir, exist_ok=True)

        result = processor.process_image_page(
            content=content,
            domain="example.com",
            storage_subdir=storage_subdir,
            filename="page-001.jpg",
        )

        missing = _ALL_REQUIRED_KEYS - set(result.keys())
        assert not missing, f"Clés manquantes dans le résultat de process_image_page: {missing}"

    def test_returns_all_required_keys_png(self, tmp_path):
        """process_image_page() must return all required keys for a PNG."""
        processor = ImageProcessor()
        content = _make_png_bytes()
        storage_subdir = str(tmp_path / "pages_storage")
        os.makedirs(storage_subdir, exist_ok=True)

        result = processor.process_image_page(
            content=content,
            domain="example.com",
            storage_subdir=storage_subdir,
            filename="page-001.png",
        )

        assert _ALL_REQUIRED_KEYS <= set(result.keys()), \
            f"Clés manquantes: {_ALL_REQUIRED_KEYS - set(result.keys())}"

    def test_metadata_types_and_values(self, tmp_path):
        """width/height must be positive ints; file_size must be positive int; format must be str."""
        processor = ImageProcessor()
        content = _make_jpeg_bytes(size=(30, 20))
        storage_subdir = str(tmp_path / "pages_storage")
        os.makedirs(storage_subdir, exist_ok=True)

        result = processor.process_image_page(
            content=content,
            domain="example.com",
            storage_subdir=storage_subdir,
            filename="page-abc.jpg",
        )

        assert isinstance(result["width"], int) and result["width"] > 0, \
            f"width doit être un entier positif, obtenu: {result['width']}"
        assert isinstance(result["height"], int) and result["height"] > 0, \
            f"height doit être un entier positif, obtenu: {result['height']}"
        assert isinstance(result["format"], str) and result["format"], \
            f"format doit être une chaîne non vide, obtenu: {result['format']}"
        assert isinstance(result["file_size"], int) and result["file_size"] > 0, \
            f"file_size doit être un entier positif, obtenu: {result['file_size']}"

    def test_output_under_pages_directory(self, tmp_path):
        """Fichiers de sortie doivent être sous pages/ (pas produit-2 / produit-3)."""
        processor = ImageProcessor()
        content = _make_jpeg_bytes()
        storage_subdir = str(tmp_path / "pages_storage")
        os.makedirs(storage_subdir, exist_ok=True)

        result = processor.process_image_page(
            content=content,
            domain="example.com",
            storage_subdir=storage_subdir,
            filename="page-001.jpg",
        )

        assert "pages" in result["main_path"], \
            f"main_path doit être sous pages/, obtenu: {result['main_path']}"
        assert "pages" in result["thumb_path"], \
            f"thumb_path doit être sous pages/, obtenu: {result['thumb_path']}"

        # Must NOT use the FP produit-2/produit-3 scheme
        assert "produit-2" not in result["main_path"], \
            f"main_path ne doit pas utiliser produit-2: {result['main_path']}"
        assert "produit-3" not in result["thumb_path"], \
            f"thumb_path ne doit pas utiliser produit-3: {result['thumb_path']}"

    def test_output_files_exist_on_disk(self, tmp_path):
        """Les fichiers main et thumb doivent exister sur le disque après process_image_page."""
        processor = ImageProcessor()
        content = _make_jpeg_bytes()
        storage_subdir = str(tmp_path / "pages_storage")
        os.makedirs(storage_subdir, exist_ok=True)

        result = processor.process_image_page(
            content=content,
            domain="example.com",
            storage_subdir=storage_subdir,
            filename="page-001.jpg",
        )

        assert os.path.isfile(result["main_path"]), \
            f"Le fichier main doit exister: {result['main_path']}"
        assert os.path.isfile(result["thumb_path"]), \
            f"Le fichier thumb doit exister: {result['thumb_path']}"

    def test_file_size_matches_actual_file(self, tmp_path):
        """file_size retourné doit correspondre à la taille réelle du fichier main sur disque."""
        processor = ImageProcessor()
        content = _make_jpeg_bytes()
        storage_subdir = str(tmp_path / "pages_storage")
        os.makedirs(storage_subdir, exist_ok=True)

        result = processor.process_image_page(
            content=content,
            domain="example.com",
            storage_subdir=storage_subdir,
            filename="page-001.jpg",
        )

        actual_size = os.path.getsize(result["main_path"])
        assert result["file_size"] == actual_size, \
            f"file_size={result['file_size']} ne correspond pas à la taille réelle {actual_size}"

    def test_empty_content_raises(self, tmp_path):
        """Contenu vide doit lever une exception (même comportement que process_image)."""
        processor = ImageProcessor()
        storage_subdir = str(tmp_path / "pages_storage")
        os.makedirs(storage_subdir, exist_ok=True)

        with pytest.raises(Exception):
            processor.process_image_page(
                content=b"",
                domain="example.com",
                storage_subdir=storage_subdir,
                filename="page-empty.jpg",
            )


# ---------------------------------------------------------------------------
# Non-regression: process_image() must still return the new metadata keys too
# ---------------------------------------------------------------------------

class TestProcessImageMetadataKeys:
    """Non-régression : process_image() doit aussi retourner les nouvelles clés de métadonnées."""

    def test_process_image_returns_metadata_keys(self, tmp_path):
        """process_image() doit contenir width, height, format, file_size (ajout non-breaking)."""
        processor = ImageProcessor()
        content = _make_jpeg_bytes()
        filename = _build_filename("produit-test", "42001", "https://stub.com/img.jpg", ".jpg")

        result = processor.process_image(
            content=content,
            domain="test.com",
            product_id="42001",
            product_name="produit-test",
            base_storage_dir=str(tmp_path),
            filename=filename,
        )

        missing = _ALL_REQUIRED_KEYS - set(result.keys())
        assert not missing, \
            f"process_image() ne retourne pas les clés attendues: {missing}"

    def test_process_image_still_has_fp_paths(self, tmp_path):
        """process_image() doit toujours produire des chemins dans produit-2 / produit-3."""
        processor = ImageProcessor()
        content = _make_jpeg_bytes()
        filename = _build_filename("produit-test", "42001", "https://stub.com/img.jpg", ".jpg")

        result = processor.process_image(
            content=content,
            domain="test.com",
            product_id="42001",
            product_name="produit-test",
            base_storage_dir=str(tmp_path),
            filename=filename,
        )

        assert "produit-2" in result["main_path"], \
            f"main_path doit être sous produit-2, obtenu: {result['main_path']}"
        assert "produit-3" in result["thumb_path"], \
            f"thumb_path doit être sous produit-3, obtenu: {result['thumb_path']}"
