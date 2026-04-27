"""Tests garde-fou sur ImageProcessor — couvrent les régressions R1, R2, R3
du fix de parité avec le PHP creer_image() (commit 582fdc6c).
"""

from PIL import Image

from core.image_processor import ImageProcessor
from core.downloader import _build_filename


# Slug et product_id communs à tous les tests
_SLUG = "produit-test"
_PID = "1"
_STUB_URL = "https://stub.com/fake.jpg"


def test_png_transparent_flattened_on_white(transparent_png_bytes, tmp_path):
    """R1 — Un PNG avec pixel transparent doit ressortir opaque sur fond blanc.

    Garde-fou sur : app/core/image_processor.py:99-104
        if output_format == 'PNG':
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            canvas = Image.new('RGB', image.size, (255, 255, 255))
            canvas.paste(image, mask=image.split()[-1])
            image = canvas

    Parité PHP : case 3 de creer_image() (imagecreatetruecolor + imagefill(blanc)).
    """
    processor = ImageProcessor()
    filename = _build_filename(_SLUG, _PID, _STUB_URL, ".png")

    result = processor.process_image(
        content=transparent_png_bytes,
        domain="test.com",
        product_id=_PID,
        product_name=_SLUG,
        base_storage_dir=str(tmp_path),
        filename=filename,
    )

    assert result["main_path"].endswith(".png"), \
        f"extension attendue .png, obtenu : {result['main_path']}"

    with Image.open(result["main_path"]) as out:
        out.load()
        assert out.mode == "RGB", \
            f"attendu mode RGB (flatten fait), obtenu : {out.mode}"
        assert out.getpixel((0, 0)) == (255, 255, 255), \
            f"pixel transparent doit devenir blanc, obtenu : {out.getpixel((0, 0))}"


def test_pyvips_path_png_also_flattens(transparent_png_bytes, tmp_path, monkeypatch):
    """R1 via branche pyvips — le flatten sur blanc doit aussi fonctionner
    en shrink-on-load.

    Garde-fou sur : app/core/image_processor.py:187-189
        if output_format_suffix == '.png' and main_vips.hasalpha():
            main_vips = main_vips.flatten(background=[255, 255, 255])

    On force la branche pyvips en réduisant LARGE_IMAGE_THRESHOLD à 10 :
    une image 10×10 (100 pixels) déclenche alors le chemin pyvips.
    """
    from core import image_processor

    monkeypatch.setattr(image_processor, "LARGE_IMAGE_THRESHOLD", 10)

    processor = image_processor.ImageProcessor()
    filename = _build_filename(_SLUG, _PID, _STUB_URL, ".png")

    result = processor.process_image(
        content=transparent_png_bytes,
        domain="test.com",
        product_id=_PID,
        product_name=_SLUG,
        base_storage_dir=str(tmp_path),
        filename=filename,
    )

    assert result["main_path"].endswith(".png"), \
        f"extension attendue .png, obtenu : {result['main_path']}"

    with Image.open(result["main_path"]) as out:
        out.load()
        assert out.mode == "RGB", \
            f"pyvips flatten attendu (mode RGB), obtenu : {out.mode}"
        assert out.getpixel((0, 0)) == (255, 255, 255), (
            f"pixel transparent doit devenir blanc (branche pyvips), "
            f"obtenu : {out.getpixel((0, 0))}"
        )


def test_webp_transparent_converted_to_png_on_white(transparent_webp_bytes, tmp_path):
    """R2 — Un WebP avec alpha doit ressortir en PNG opaque sur fond blanc.

    Garde-fou sur : app/core/image_processor.py:86-93 (conversion WEBP→PNG)
                  + app/core/image_processor.py:99-104 (flatten blanc)

    Parité PHP : case 18 de creer_image() (WebP → PNG avec imagefill blanc).

    Note : le filename est pré-construit avec .png car WebP est converti en PNG par
    le processeur ; l'appelant (download_and_process) détecte .webp dans l'URL et
    construit le filename avec .webp, mais ici on teste l'ImageProcessor directement
    avec le bon format de sortie pour valider l'assertion d'extension.
    """
    processor = ImageProcessor()
    # WebP → converti en PNG par process_image, donc on pré-build avec .png
    filename = _build_filename(_SLUG, _PID, _STUB_URL, ".png")

    result = processor.process_image(
        content=transparent_webp_bytes,
        domain="test.com",
        product_id=_PID,
        product_name=_SLUG,
        base_storage_dir=str(tmp_path),
        filename=filename,
    )

    assert result["main_path"].endswith(".png"), \
        f"WebP doit être converti en PNG, obtenu : {result['main_path']}"

    with Image.open(result["main_path"]) as out:
        out.load()
        assert out.mode == "RGB", \
            f"attendu mode RGB (flatten fait), obtenu : {out.mode}"
        assert out.getpixel((0, 0)) == (255, 255, 255), \
            f"WebP transparent doit être composé sur fond blanc, obtenu : {out.getpixel((0, 0))}"


def test_gif_transparency_preserved(transparent_gif_bytes, tmp_path):
    """R3 — Un GIF avec transparence de palette doit la conserver après process.

    Garde-fou sur : app/core/image_processor.py:125-127
        save_kwargs["save_all"] = True
        if gif_transparency is not None:
            save_kwargs["transparency"] = gif_transparency

    Parité PHP : case 1 de creer_image() (imagecolortransparent + imagepalettecopy).

    Note : si cette assertion échoue malgré un code source correct (piège Pillow
    version-dépendant), le plan B est d'asserter `out.mode == "P"` et que
    `out.getpixel((0,0))` vaut l'index transparent du GIF.
    """
    processor = ImageProcessor()
    filename = _build_filename(_SLUG, _PID, _STUB_URL, ".gif")

    result = processor.process_image(
        content=transparent_gif_bytes,
        domain="test.com",
        product_id=_PID,
        product_name=_SLUG,
        base_storage_dir=str(tmp_path),
        filename=filename,
    )

    assert result["main_path"].endswith(".gif"), \
        f"extension attendue .gif, obtenu : {result['main_path']}"

    with Image.open(result["main_path"]) as out:
        out.load()
        assert "transparency" in out.info, \
            "la transparence GIF doit être préservée au save (info['transparency'])"


def test_webp_url_filename_extension_corrected_to_png(transparent_webp_bytes, tmp_path):
    """Bug R2b — URL WebP produit un filename .webp, mais le contenu est PNG.

    Scénario réel : download_and_process() détecte '.webp' dans l'URL et passe
    filename='produit-test-1-<hash>.webp' à process_image().
    Après conversion WEBP→PNG, _build_paths doit corriger l'extension en .png
    pour que le fichier sur disque porte l'extension cohérente avec son contenu.

    Garde-fou sur : app/core/image_processor.py – _build_paths()
        if filename:
            base, _ = os.path.splitext(filename)
            filename = base + extension   # enforce actual output extension
    """
    processor = ImageProcessor()
    # Simule le filename URL-dérivé avec extension .webp (le bug réel)
    filename_with_wrong_ext = _build_filename(_SLUG, _PID, _STUB_URL, ".webp")

    result = processor.process_image(
        content=transparent_webp_bytes,
        domain="test.com",
        product_id=_PID,
        product_name=_SLUG,
        base_storage_dir=str(tmp_path),
        filename=filename_with_wrong_ext,
    )

    assert result["main_path"].endswith(".png"), (
        f"WebP converti en PNG : le fichier doit porter l'extension .png, "
        f"obtenu : {result['main_path']}"
    )
    assert result["filename"].endswith(".png"), (
        f"filename retourné doit finir en .png (pas .webp), "
        f"obtenu : {result['filename']}"
    )

    # Vérifie que le fichier est bien lisible en tant que PNG
    with Image.open(result["main_path"]) as out:
        out.load()
        assert out.format == "PNG", f"contenu attendu PNG, détecté : {out.format}"


def test_jpeg_stays_rgb_no_regression(opaque_jpeg_bytes, tmp_path):
    """Non-régression JPEG — ne doit PAS être aplati sur blanc par erreur.

    Le code de flatten (ligne 99 de image_processor.py) est protégé par
    `if output_format == 'PNG':`. Ce test vérifie que cette condition
    filtre bien les JPEG (sinon un JPEG rouge sortirait blanc).
    """
    processor = ImageProcessor()
    filename = _build_filename(_SLUG, _PID, _STUB_URL, ".jpg")

    result = processor.process_image(
        content=opaque_jpeg_bytes,
        domain="test.com",
        product_id=_PID,
        product_name=_SLUG,
        base_storage_dir=str(tmp_path),
        filename=filename,
    )

    assert result["main_path"].endswith(".jpg"), \
        f"extension attendue .jpg, obtenu : {result['main_path']}"

    with Image.open(result["main_path"]) as out:
        out.load()
        assert out.mode == "RGB", \
            f"JPEG attendu en RGB, obtenu : {out.mode}"

        # Vérifie que le pixel reste rouge (pas blanc suite à un flatten erroné).
        # JPEG est lossy — on tolère ±55 sur chaque canal.
        r, g, b = out.getpixel((0, 0))
        assert r >= 200 and g <= 55 and b <= 55, (
            f"JPEG rouge attendu, obtenu ({r},{g},{b}) — "
            f"le code aurait-il flatten le JPEG sur fond blanc par erreur ?"
        )
